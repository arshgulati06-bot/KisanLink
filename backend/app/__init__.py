"""
Flask application factory.

Wires up configuration, CORS, the error handlers that keep every response in
one envelope, the per-request database teardown, and all API blueprints.
"""
import os

from dotenv import load_dotenv
from flask import Flask, jsonify
from flask_cors import CORS

# Load .env before anything reads settings.
load_dotenv()

from app.config import db  # noqa: E402
from app.config.settings import settings  # noqa: E402
from app.routes import ALL_BLUEPRINTS, register_routes  # noqa: E402
from app.utils.responses import register_error_handlers  # noqa: E402

API_VERSION = "1.0.0"


def create_app(config_overrides=None):
    """
    Build the application.

    Args:
        config_overrides: dict merged into ``app.config`` after defaults.
            Tests use it to switch on TESTING.
    """
    app = Flask(__name__)
    app.config.update(settings.as_flask_config())
    app.config["JSON_SORT_KEYS"] = False
    if config_overrides:
        app.config.update(config_overrides)

    CORS(app, resources={r"/api/*": {"origins": os.getenv("CORS_ORIGINS", "*")}})

    register_error_handlers(app)
    register_routes(app)

    # One database connection per thread, closed when the request ends.
    app.teardown_appcontext(db.close_connection)

    @app.route("/")
    def index():
        return jsonify(
            {
                "success": True,
                "data": {
                    "name": "KisanLink API",
                    "version": API_VERSION,
                    "description": (
                        "Market intelligence and transaction enablement for farmers, "
                        "FPOs and verified buyers."
                    ),
                    "health": "/api/health",
                    "endpoints": "/api",
                },
            }
        )

    @app.route("/api")
    def api_index():
        """A machine-readable list of every route, useful during integration."""
        routes = []
        for rule in sorted(app.url_map.iter_rules(), key=lambda r: str(r)):
            if not str(rule).startswith("/api"):
                continue
            methods = sorted(rule.methods - {"HEAD", "OPTIONS"})
            routes.append({"path": str(rule), "methods": methods, "endpoint": rule.endpoint})
        return jsonify(
            {
                "success": True,
                "data": {
                    "version": API_VERSION,
                    "blueprints": [bp.name for bp in ALL_BLUEPRINTS],
                    "route_count": len(routes),
                    "routes": routes,
                },
            }
        )

    return app
