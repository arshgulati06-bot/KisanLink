"""
Database access layer.

The project targets MySQL. To keep the API and the test-suite runnable on a
machine that has no MySQL server, the same layer can also drive SQLite. All
application SQL is written once, using ``?`` placeholders, and translated to
``%s`` when the MySQL driver is in use.

Nothing above this module needs to know which backend is active.
"""
import os
import re
import sqlite3
import threading
from contextlib import contextmanager

from app.config.settings import settings

try:  # MySQL is optional at import time so SQLite-only runs still work.
    import mysql.connector
    from mysql.connector import Error as MySQLError

    MYSQL_AVAILABLE = True
except ImportError:  # pragma: no cover - depends on install
    mysql = None
    MySQLError = Exception
    MYSQL_AVAILABLE = False


_state = threading.local()
# Resolved once at first use: which backend actually answered.
_active_backend = {"name": None}


class DatabaseError(RuntimeError):
    """Raised when the database cannot serve a request."""


# --------------------------------------------------------------------------
# Backend resolution
# --------------------------------------------------------------------------
def _mysql_config():
    return {
        "host": settings.DB_HOST,
        "port": settings.DB_PORT,
        "user": settings.DB_USER,
        "password": settings.DB_PASSWORD,
        "database": settings.DB_NAME,
    }


def _open_mysql():
    if not MYSQL_AVAILABLE:
        raise DatabaseError("mysql-connector-python is not installed.")
    return mysql.connector.connect(**_mysql_config())


def _open_sqlite():
    path = settings.SQLITE_PATH
    if path != ":memory:":
        directory = os.path.dirname(os.path.abspath(path))
        if directory:
            os.makedirs(directory, exist_ok=True)
    conn = sqlite3.connect(path, detect_types=0)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def active_backend():
    """Return the backend actually in use: ``"mysql"`` or ``"sqlite"``."""
    if _active_backend["name"] is None:
        configured = (settings.DB_BACKEND or "mysql").lower()
        if configured == "sqlite":
            _active_backend["name"] = "sqlite"
        else:
            try:
                conn = _open_mysql()
                conn.close()
                _active_backend["name"] = "mysql"
            except Exception as exc:  # noqa: BLE001 - any driver failure
                if not settings.DB_ALLOW_SQLITE_FALLBACK:
                    raise DatabaseError(f"MySQL connection failed: {exc}") from exc
                print(
                    f"[DB Warning] MySQL unavailable ({exc}). "
                    f"Falling back to SQLite at {settings.SQLITE_PATH}."
                )
                _active_backend["name"] = "sqlite"
    return _active_backend["name"]


def reset_backend():
    """Forget the resolved backend. Used by tests when settings change."""
    _active_backend["name"] = None
    close_connection()


# --------------------------------------------------------------------------
# Connections
# --------------------------------------------------------------------------
def get_db_connection():
    """
    Return a live DB-API connection, creating one for this thread if needed.

    Kept as a module-level function (rather than a class) because that is how
    the rest of the project — and the original health check — consumes it.
    """
    conn = getattr(_state, "conn", None)
    if conn is not None:
        try:
            if active_backend() == "mysql":
                conn.ping(reconnect=True, attempts=2, delay=1)
            else:
                conn.execute("SELECT 1")
            return conn
        except Exception:  # noqa: BLE001 - stale connection, reopen below
            try:
                conn.close()
            except Exception:  # noqa: BLE001
                pass
            _state.conn = None

    backend = active_backend()
    try:
        conn = _open_mysql() if backend == "mysql" else _open_sqlite()
    except Exception as exc:  # noqa: BLE001
        raise DatabaseError(f"Could not open a {backend} connection: {exc}") from exc

    _state.conn = conn
    return conn


def close_connection(exception=None):  # noqa: ARG001 - Flask teardown signature
    """Close this thread's connection. Registered as a Flask teardown hook."""
    conn = getattr(_state, "conn", None)
    if conn is not None:
        try:
            conn.close()
        except Exception:  # noqa: BLE001
            pass
        _state.conn = None


def check_db_connection():
    """
    Report connectivity without raising.

    Returns:
        tuple[bool, str]: (is_connected, human readable detail)
    """
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT 1")
        cursor.fetchall()
        cursor.close()
        backend = active_backend()
        target = (
            f"{settings.DB_USER}@{settings.DB_HOST}:{settings.DB_PORT}/{settings.DB_NAME}"
            if backend == "mysql"
            else settings.SQLITE_PATH
        )
        return True, f"Connected to {backend} ({target})."
    except Exception as exc:  # noqa: BLE001
        return False, (
            f"Could not connect to the database: {exc}. "
            "Check that the server is running and the credentials in .env are correct."
        )


# --------------------------------------------------------------------------
# Query helpers
# --------------------------------------------------------------------------
def _translate(sql):
    """Convert the project's ``?`` placeholders to the driver's dialect."""
    if active_backend() == "mysql":
        return sql.replace("?", "%s")
    return sql


def _cursor(conn):
    if active_backend() == "mysql":
        return conn.cursor(dictionary=True)
    return conn.cursor()


def _rows_to_dicts(rows):
    out = []
    for row in rows or []:
        out.append(dict(row) if not isinstance(row, dict) else row)
    return out


def query_all(sql, params=()):
    """Run a SELECT and return every row as a list of dicts."""
    conn = get_db_connection()
    cursor = _cursor(conn)
    try:
        cursor.execute(_translate(sql), tuple(params))
        return _rows_to_dicts(cursor.fetchall())
    finally:
        cursor.close()


def query_one(sql, params=()):
    """Run a SELECT and return the first row as a dict, or ``None``."""
    rows = query_all(sql, params)
    return rows[0] if rows else None


def query_scalar(sql, params=(), default=None):
    """Run a SELECT and return the first column of the first row."""
    row = query_one(sql, params)
    if not row:
        return default
    return next(iter(row.values()), default)


def execute(sql, params=()):
    """
    Run an INSERT/UPDATE/DELETE and commit.

    Returns:
        int: ``lastrowid`` for inserts, otherwise the affected row count.
    """
    conn = get_db_connection()
    cursor = _cursor(conn)
    try:
        cursor.execute(_translate(sql), tuple(params))
        conn.commit()
        if cursor.lastrowid:
            return cursor.lastrowid
        return cursor.rowcount
    except Exception as exc:  # noqa: BLE001
        conn.rollback()
        raise DatabaseError(str(exc)) from exc
    finally:
        cursor.close()


def execute_many(sql, seq_of_params):
    """Run the same statement for many parameter tuples in one commit."""
    rows = [tuple(p) for p in seq_of_params]
    if not rows:
        return 0
    conn = get_db_connection()
    cursor = _cursor(conn)
    try:
        cursor.executemany(_translate(sql), rows)
        conn.commit()
        return cursor.rowcount
    except Exception as exc:  # noqa: BLE001
        conn.rollback()
        raise DatabaseError(str(exc)) from exc
    finally:
        cursor.close()


@contextmanager
def transaction():
    """
    Group several writes so they either all land or none do.

    Statements inside the block must use :func:`tx_execute` on the yielded
    cursor so they share one connection and one commit.
    """
    conn = get_db_connection()
    cursor = _cursor(conn)
    wrapper = _TransactionCursor(cursor)
    try:
        yield wrapper
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        cursor.close()


class _TransactionCursor:
    """Thin wrapper giving a transaction the same helper API as the module."""

    def __init__(self, cursor):
        self._cursor = cursor

    def execute(self, sql, params=()):
        self._cursor.execute(_translate(sql), tuple(params))
        return self._cursor.lastrowid or self._cursor.rowcount

    def query_all(self, sql, params=()):
        self._cursor.execute(_translate(sql), tuple(params))
        return _rows_to_dicts(self._cursor.fetchall())

    def query_one(self, sql, params=()):
        rows = self.query_all(sql, params)
        return rows[0] if rows else None


# --------------------------------------------------------------------------
# Schema management
# --------------------------------------------------------------------------
def _split_statements(script):
    """
    Split a .sql file into individual statements.

    Scans character by character rather than splitting on ";" so that a
    semicolon or a "--" sequence inside a quoted string - which the seed files
    do contain, in notes and descriptions - is treated as text, not as a
    statement boundary or a comment.
    """
    statements = []
    current = []
    in_string = False
    index, length = 0, len(script)

    while index < length:
        char = script[index]

        if in_string:
            current.append(char)
            if char == "'":
                # A doubled quote is an escaped quote, not the end of the string.
                if index + 1 < length and script[index + 1] == "'":
                    current.append(script[index + 1])
                    index += 2
                    continue
                in_string = False
            index += 1
            continue

        if char == "'":
            in_string = True
            current.append(char)
            index += 1
            continue

        if char == "-" and script.startswith("--", index):
            newline = script.find("\n", index)
            index = length if newline == -1 else newline + 1
            current.append("\n")
            continue

        if char == "/" and script.startswith("/*", index):
            end = script.find("*/", index + 2)
            index = length if end == -1 else end + 2
            current.append(" ")
            continue

        if char == ";":
            statement = "".join(current).strip()
            if statement:
                statements.append(statement)
            current = []
            index += 1
            continue

        current.append(char)
        index += 1

    trailing = "".join(current).strip()
    if trailing:
        statements.append(trailing)
    return statements


def _mysql_ddl_to_sqlite(statement):
    """
    Translate the MySQL DDL subset used by ``database/schema.sql`` to SQLite.

    The schema is deliberately written in a narrow, portable subset so this
    translation stays small and predictable.
    """
    sql = statement
    sql = re.sub(r"\s+ENGINE\s*=\s*\w+", "", sql, flags=re.IGNORECASE)
    sql = re.sub(r"\s+DEFAULT\s+CHARSET\s*=\s*\w+", "", sql, flags=re.IGNORECASE)
    sql = re.sub(r"\s+COLLATE\s*=\s*\w+", "", sql, flags=re.IGNORECASE)
    sql = re.sub(
        r"\bINT\s+AUTO_INCREMENT\s+PRIMARY\s+KEY\b",
        "INTEGER PRIMARY KEY AUTOINCREMENT",
        sql,
        flags=re.IGNORECASE,
    )
    sql = re.sub(r"\bAUTO_INCREMENT\b", "AUTOINCREMENT", sql, flags=re.IGNORECASE)
    sql = re.sub(r"\bDATETIME\b", "TIMESTAMP", sql, flags=re.IGNORECASE)
    sql = re.sub(r"\bTINYINT\(1\)", "INTEGER", sql, flags=re.IGNORECASE)
    sql = re.sub(r"\bDOUBLE\b", "REAL", sql, flags=re.IGNORECASE)
    sql = re.sub(r"\bON\s+UPDATE\s+CURRENT_TIMESTAMP\b", "", sql, flags=re.IGNORECASE)
    # SQLite has no FULLTEXT and no per-column index declarations inside CREATE.
    sql = re.sub(r",\s*FULLTEXT[^,)]*", "", sql, flags=re.IGNORECASE)
    return _translate_date_functions(sql)


def _translate_date_functions(sql):
    """
    Translate the few MySQL date helpers the seed scripts use.

    The demo data is written with dates relative to today - DATE_SUB(CURDATE(),
    INTERVAL 5 DAY) - so a demo loaded months from now still looks current
    instead of showing stale prices.
    """
    sql = re.sub(
        r"DATE_SUB\s*\(\s*CURDATE\s*\(\s*\)\s*,\s*INTERVAL\s+(\d+)\s+DAY\s*\)",
        lambda m: f"date('now','-{m.group(1)} day')",
        sql,
        flags=re.IGNORECASE,
    )
    sql = re.sub(
        r"DATE_ADD\s*\(\s*CURDATE\s*\(\s*\)\s*,\s*INTERVAL\s+(\d+)\s+DAY\s*\)",
        lambda m: f"date('now','+{m.group(1)} day')",
        sql,
        flags=re.IGNORECASE,
    )
    sql = re.sub(r"\bCURDATE\s*\(\s*\)", "date('now')", sql, flags=re.IGNORECASE)
    sql = re.sub(r"\bNOW\s*\(\s*\)", "datetime('now')", sql, flags=re.IGNORECASE)
    return sql


def _is_already_exists(statement, exc):
    """True when a DDL statement failed only because the object is already there."""
    if not re.match(r"^\s*CREATE\s+(UNIQUE\s+)?INDEX", statement, flags=re.IGNORECASE):
        return False
    message = str(exc).lower()
    return "exist" in message or "duplicate key name" in message


def run_sql_script(script):
    """Execute a multi-statement SQL script against the active backend."""
    conn = get_db_connection()
    cursor = _cursor(conn)
    sqlite_mode = active_backend() == "sqlite"
    try:
        for statement in _split_statements(script):
            prepared = _mysql_ddl_to_sqlite(statement) if sqlite_mode else statement
            if not prepared.strip():
                continue
            if sqlite_mode and re.match(
                r"^\s*(CREATE\s+DATABASE|USE|SET\s)", prepared, flags=re.IGNORECASE
            ):
                continue
            try:
                cursor.execute(prepared)
            except Exception as exc:  # noqa: BLE001
                # MySQL has no "CREATE INDEX IF NOT EXISTS", so re-running the
                # schema on an initialised database is treated as a no-op.
                if _is_already_exists(prepared, exc):
                    continue
                raise
        conn.commit()
    except Exception as exc:  # noqa: BLE001
        conn.rollback()
        raise DatabaseError(f"Failed running SQL script: {exc}") from exc
    finally:
        cursor.close()


def _sql_file(name):
    root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    return os.path.join(root, "database", name)


def init_schema():
    """Create every table from ``database/schema.sql`` if it is missing."""
    with open(_sql_file("schema.sql"), "r", encoding="utf-8") as handle:
        run_sql_script(handle.read())


def load_seed_data(filename="seed.sql"):
    """Load reference/demo rows from a script in ``database/``."""
    with open(_sql_file(filename), "r", encoding="utf-8") as handle:
        run_sql_script(handle.read())


def table_exists(table_name):
    backend = active_backend()
    if backend == "sqlite":
        row = query_one(
            "SELECT name FROM sqlite_master WHERE type='table' AND name = ?",
            (table_name,),
        )
    else:
        row = query_one(
            "SELECT table_name FROM information_schema.tables "
            "WHERE table_schema = ? AND table_name = ?",
            (settings.DB_NAME, table_name),
        )
    return row is not None
