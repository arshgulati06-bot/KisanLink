"""Service and database health check."""
from flask import Blueprint, jsonify

from app.config.db import active_backend, check_db_connection, table_exists

health_bp = Blueprint("health", __name__)

#: Tables the API cannot work without. Their absence means the schema was
#: never loaded, which is a different problem from the database being down.
CORE_TABLES = ("users", "crops", "markets", "lots", "buyer_requirements", "offers", "transactions")


@health_bp.route("/api/health", methods=["GET"])
def health_check():
    """Report whether the service is up and the database is usable."""
    db_connected, db_message = check_db_connection()

    schema_ready, missing = False, []
    if db_connected:
        missing = [table for table in CORE_TABLES if not table_exists(table)]
        schema_ready = not missing

    if db_connected and schema_ready:
        status, message = "healthy", "KisanLink Flask backend is up and the schema is loaded."
    elif db_connected:
        status = "degraded"
        message = (
            "Database is reachable but the schema is incomplete. "
            "Run: python -m scripts.init_db"
        )
    else:
        status, message = "degraded", "KisanLink Flask backend is up but the database is not."

    return jsonify(
        {
            "status": status,
            "message": message,
            "database": {
                "connected": db_connected,
                "backend": active_backend() if db_connected else None,
                "schema_ready": schema_ready,
                "missing_tables": missing,
                "details": db_message,
            },
        }
    ), 200
