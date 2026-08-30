"""
Data access.

Repositories are the only place in the application that writes SQL. Services
call repositories; controllers call services. Keeping that rule means a schema
change never leaks past this package.
"""
import datetime as dt

from app.config import db


def utcnow():
    """A timestamp both MySQL and SQLite accept in a parameter slot."""
    return dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")


class Filter:
    """A reusable WHERE-clause builder."""

    def __init__(self):
        self.clauses = []
        self.params = []

    def add(self, sql_fragment, *params):
        """Add a raw fragment, e.g. ``add("status = ?", "OPEN")``."""
        self.clauses.append(sql_fragment)
        self.params.extend(params)
        return self

    def eq(self, column, value):
        """Add ``column = value`` only when a value was actually supplied."""
        if value is not None and value != "":
            self.add(f"{column} = ?", value)
        return self

    def like(self, column, value):
        if value:
            self.add(f"{column} LIKE ?", f"%{value}%")
        return self

    def in_(self, column, values):
        values = [v for v in (values or []) if v is not None]
        if values:
            placeholders = ", ".join("?" for _ in values)
            self.add(f"{column} IN ({placeholders})", *values)
        return self

    def gte(self, column, value):
        if value is not None and value != "":
            self.add(f"{column} >= ?", value)
        return self

    def lte(self, column, value):
        if value is not None and value != "":
            self.add(f"{column} <= ?", value)
        return self

    def where_sql(self):
        if not self.clauses:
            return "", []
        return " WHERE " + " AND ".join(self.clauses), list(self.params)


class BaseRepository:
    """
    Generic CRUD against one table.

    Subclasses set ``table`` and ``model`` and then add only the queries that
    are actually specific to their domain.
    """

    table = None
    model = None
    #: Columns a caller is allowed to sort by, guarding against SQL injection
    #: through an ``order_by`` query parameter.
    sortable_columns = ("id", "created_at", "updated_at")
    default_order = "id DESC"

    # -- reads --------------------------------------------------------------
    def find_by_id(self, record_id):
        row = db.query_one(f"SELECT * FROM {self.table} WHERE id = ?", (record_id,))
        return self.model.from_row(row) if row else None

    def find_one_by(self, column, value):
        row = db.query_one(f"SELECT * FROM {self.table} WHERE {column} = ?", (value,))
        return self.model.from_row(row) if row else None

    def find_where(self, filters, order_by=None, limit=None, offset=None):
        where_sql, params = filters.where_sql()
        sql = f"SELECT * FROM {self.table}{where_sql} ORDER BY {self.safe_order(order_by)}"
        if limit is not None:
            sql += " LIMIT ? OFFSET ?"
            params = params + [int(limit), int(offset or 0)]
        return self.model.from_rows(db.query_all(sql, params))

    def count_where(self, filters):
        where_sql, params = filters.where_sql()
        return int(
            db.query_scalar(f"SELECT COUNT(*) AS c FROM {self.table}{where_sql}", params, 0) or 0
        )

    def exists(self, column, value, exclude_id=None):
        sql = f"SELECT id FROM {self.table} WHERE {column} = ?"
        params = [value]
        if exclude_id is not None:
            sql += " AND id <> ?"
            params.append(exclude_id)
        return db.query_one(sql, params) is not None

    def safe_order(self, order_by):
        """Only allow sorting by whitelisted columns."""
        if not order_by:
            return self.default_order
        parts = str(order_by).strip().split()
        column = parts[0]
        direction = parts[1].upper() if len(parts) > 1 else "ASC"
        if column not in self.sortable_columns or direction not in ("ASC", "DESC"):
            return self.default_order
        return f"{column} {direction}"

    # -- writes -------------------------------------------------------------
    def insert(self, data):
        """Insert a row from a dict and return the new id."""
        payload = {k: v for k, v in data.items() if v is not None or k in getattr(self, "nullable_on_insert", ())}
        columns = ", ".join(payload.keys())
        placeholders = ", ".join("?" for _ in payload)
        sql = f"INSERT INTO {self.table} ({columns}) VALUES ({placeholders})"
        return db.execute(sql, list(payload.values()))

    def update(self, record_id, data):
        """Update the supplied columns only. Returns the number of rows changed."""
        payload = {k: v for k, v in data.items() if k != "id"}
        if not payload:
            return 0
        if "updated_at" not in payload and self.has_updated_at:
            payload["updated_at"] = utcnow()
        assignments = ", ".join(f"{key} = ?" for key in payload)
        sql = f"UPDATE {self.table} SET {assignments} WHERE id = ?"
        return db.execute(sql, list(payload.values()) + [record_id])

    def delete(self, record_id):
        return db.execute(f"DELETE FROM {self.table} WHERE id = ?", (record_id,))

    has_updated_at = True
