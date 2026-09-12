"""
KisanLink — SQLite persistence layer.
======================================
Thin wrapper around stdlib sqlite3.  All SQL lives in repositories and schema.sql.

Usage::

    from app.db import execute, query_one, query_all, init_schema

The connection is per-thread (via :mod:`threading.local`), so it is safe to call
these helpers from Flask request handlers without locking.
"""
import os
import re
import sqlite3
import threading

_local = threading.local()

# ------------------------------------------------------------------
# Location of the SQLite file and schema.
# ------------------------------------------------------------------
_HERE = os.path.dirname(os.path.abspath(__file__))   # backend/
_PROJECT_ROOT = os.path.dirname(_HERE)                 # KisanLink/

# Database lives alongside backend/kl_db.py
SQLITE_PATH = os.environ.get(
    "KISANLINK_SQLITE_PATH",
    os.path.join(_HERE, "kisanlink.sqlite3"),
)
SCHEMA_PATH = os.path.join(_PROJECT_ROOT, "database", "schema.sql")


# ------------------------------------------------------------------
# Connection management
# ------------------------------------------------------------------

def _get_connection():
    """Return the per-thread SQLite connection, opening it if necessary."""
    conn = getattr(_local, "conn", None)
    if conn is None:
        conn = sqlite3.connect(SQLITE_PATH, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        # Enable FK enforcement — SQLite does not do this by default.
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute("PRAGMA journal_mode = WAL")  # better concurrent reads
        _local.conn = conn
    return conn


def _rows_to_dicts(rows):
    """Convert sqlite3.Row results to plain dicts."""
    return [dict(row) for row in (rows or [])]


# ------------------------------------------------------------------
# Public helpers — the only SQL interface used by repositories
# ------------------------------------------------------------------

def execute(sql, params=()):
    """Run an INSERT / UPDATE / DELETE.  Returns lastrowid or rowcount."""
    conn = _get_connection()
    cur = conn.cursor()
    try:
        cur.execute(sql, tuple(params))
        conn.commit()
        return cur.lastrowid if cur.lastrowid else cur.rowcount
    except Exception:
        conn.rollback()
        raise
    finally:
        cur.close()


def query_one(sql, params=()):
    """Return the first row as a dict, or None."""
    conn = _get_connection()
    cur = conn.cursor()
    try:
        cur.execute(sql, tuple(params))
        row = cur.fetchone()
        return dict(row) if row else None
    finally:
        cur.close()


def query_all(sql, params=()):
    """Return all rows as a list of dicts."""
    conn = _get_connection()
    cur = conn.cursor()
    try:
        cur.execute(sql, tuple(params))
        return _rows_to_dicts(cur.fetchall())
    finally:
        cur.close()


def query_scalar(sql, params=(), default=None):
    """Return the first column of the first row, or *default*."""
    row = query_one(sql, params)
    if row is None:
        return default
    return next(iter(row.values()), default)


# ------------------------------------------------------------------
# Schema initialisation
# ------------------------------------------------------------------

_MYSQL_TO_SQLITE = [
    # INT AUTO_INCREMENT PRIMARY KEY → INTEGER PRIMARY KEY AUTOINCREMENT
    (r"\bINT\s+AUTO_INCREMENT\s+PRIMARY\s+KEY\b", "INTEGER PRIMARY KEY AUTOINCREMENT"),
    (r"\bAUTO_INCREMENT\b", "AUTOINCREMENT"),
    # Type translations
    (r"\bDATETIME\b", "TIMESTAMP"),
    (r"\bTINYINT\(1\)", "INTEGER"),
    (r"\bDOUBLE\b", "REAL"),
    # MySQL-only clauses to strip
    (r"\s+ENGINE\s*=\s*\w+", ""),
    (r"\s+DEFAULT\s+CHARSET\s*=\s*\w+", ""),
    (r"\s+COLLATE\s*=\s*\w+", ""),
    (r"\s+ON\s+UPDATE\s+CURRENT_TIMESTAMP\b", ""),
    # FULLTEXT INDEX — SQLite does not support, drop the column-list entry
    (r",\s*FULLTEXT[^,)]*", ""),
]


def _translate_ddl(statement):
    """Best-effort MySQL DDL → SQLite translation."""
    sql = statement
    for pattern, replacement in _MYSQL_TO_SQLITE:
        sql = re.sub(pattern, replacement, sql, flags=re.IGNORECASE)
    return sql


def _split_statements(script):
    """Split a SQL script into individual statements (handles quoted strings)."""
    statements = []
    current = []
    in_string = False
    i, n = 0, len(script)
    while i < n:
        ch = script[i]
        if in_string:
            current.append(ch)
            if ch == "'":
                if i + 1 < n and script[i + 1] == "'":
                    current.append(script[i + 1])
                    i += 2
                    continue
                in_string = False
            i += 1
            continue
        if ch == "'":
            in_string = True
            current.append(ch)
            i += 1
            continue
        if ch == "-" and script.startswith("--", i):
            newline = script.find("\n", i)
            i = n if newline == -1 else newline + 1
            current.append("\n")
            continue
        if ch == "/" and script.startswith("/*", i):
            end = script.find("*/", i + 2)
            i = n if end == -1 else end + 2
            continue
        if ch == ";":
            stmt = "".join(current).strip()
            if stmt:
                statements.append(stmt)
            current = []
            i += 1
            continue
        current.append(ch)
        i += 1
    trailing = "".join(current).strip()
    if trailing:
        statements.append(trailing)
    return statements


def init_schema():
    """
    Create all tables from ``database/schema.sql`` if they don't already exist.

    Called once at application startup.  Safe to call repeatedly (uses
    ``CREATE TABLE IF NOT EXISTS``).
    """
    if not os.path.exists(SCHEMA_PATH):
        print(f"[DB] WARNING: schema file not found at {SCHEMA_PATH}")
        return False
    with open(SCHEMA_PATH, encoding="utf-8") as fh:
        script = fh.read()

    conn = _get_connection()
    cur = conn.cursor()
    try:
        for stmt in _split_statements(script):
            # Skip MySQL-specific statements that have no SQLite equivalent.
            if re.match(r"^\s*(CREATE\s+DATABASE|USE\s|SET\s)", stmt, re.IGNORECASE):
                continue
            prepared = _translate_ddl(stmt)
            if not prepared.strip():
                continue
            try:
                cur.execute(prepared)
            except sqlite3.OperationalError as exc:
                # "already exists" is safe — we used IF NOT EXISTS everywhere.
                if "already exists" not in str(exc).lower():
                    print(f"[DB] Schema warning on: {prepared[:80]!r} → {exc}")
        conn.commit()
        _apply_additive_migrations(conn, cur)
        print(f"[DB] Schema initialised. Database: {SQLITE_PATH}")
        return True
    except Exception as exc:
        conn.rollback()
        print(f"[DB] Schema init error: {exc}")
        return False
    finally:
        cur.close()


def _apply_additive_migrations(conn, cur):
    """
    Add columns introduced after a database was first created.

    CREATE TABLE IF NOT EXISTS will not alter an existing table, so a database
    made before a column existed would otherwise never gain it. Only additive,
    nullable columns belong here — nothing is dropped or rewritten.
    """
    wanted = [
        ("lots", "image_file", "VARCHAR(120)"),
    ]
    for table, column, coltype in wanted:
        try:
            cur.execute(f"PRAGMA table_info({table})")
            existing = {row[1] for row in cur.fetchall()}
            if not existing or column in existing:
                continue
            cur.execute(f"ALTER TABLE {table} ADD COLUMN {column} {coltype}")
            conn.commit()
            print(f"[DB] Added column {table}.{column}")
        except Exception as exc:
            print(f"[DB] Migration warning for {table}.{column}: {exc}")


def table_exists(table_name):
    """Return True if the table is present in the SQLite database."""
    row = query_one(
        "SELECT name FROM sqlite_master WHERE type='table' AND name = ?",
        (table_name,),
    )
    return row is not None
