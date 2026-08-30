"""
Central application configuration.

Every tunable number used by the intelligence layer (matching weights, cost
assumptions, forecast thresholds) lives here so it can be reviewed and tuned
in one place instead of being buried inside business logic.
"""
import os


def _env_float(key, default):
    try:
        return float(os.getenv(key, default))
    except (TypeError, ValueError):
        return float(default)


def _env_int(key, default):
    try:
        return int(os.getenv(key, default))
    except (TypeError, ValueError):
        return int(default)


def _env_bool(key, default=False):
    raw = os.getenv(key)
    if raw is None:
        return default
    return raw.strip().lower() in ("1", "true", "yes", "on")


class Settings:
    """Runtime settings resolved from environment variables."""

    # ----- Flask -----
    # Development fallback only. Set a real 32+ character SECRET_KEY in .env
    # before deploying anywhere other people can reach.
    SECRET_KEY = os.getenv(
        "SECRET_KEY", "kisanlink-development-secret-key-change-me-in-dot-env"
    )
    ENV = os.getenv("FLASK_ENV", "development")
    JSON_SORT_KEYS = False

    # ----- Database -----
    # "mysql" is the production target. "sqlite" lets the API and the test
    # suite run on a machine without a MySQL server.
    DB_BACKEND = os.getenv("DB_BACKEND", "mysql").strip().lower()
    DB_HOST = os.getenv("DB_HOST", "localhost")
    DB_PORT = _env_int("DB_PORT", 3306)
    DB_USER = os.getenv("DB_USER", "root")
    DB_PASSWORD = os.getenv("DB_PASSWORD", "root")
    DB_NAME = os.getenv("DB_NAME", "kisanlink_db")
    SQLITE_PATH = os.getenv("SQLITE_PATH", os.path.join(os.getcwd(), "kisanlink.sqlite3"))
    # Fall back to SQLite automatically when MySQL is unreachable at startup.
    DB_ALLOW_SQLITE_FALLBACK = _env_bool("DB_ALLOW_SQLITE_FALLBACK", True)

    # ----- Auth -----
    JWT_ALGORITHM = "HS256"
    JWT_EXPIRY_HOURS = _env_int("JWT_EXPIRY_HOURS", 24)

    # ----- Matching engine weights (must sum to 1.0) -----
    # Starting values taken from the project documentation. They are
    # deliberately explicit and tunable; they are NOT learned from data.
    WEIGHT_PRICE = _env_float("WEIGHT_PRICE", 0.35)
    WEIGHT_QUANTITY = _env_float("WEIGHT_QUANTITY", 0.20)
    WEIGHT_QUALITY = _env_float("WEIGHT_QUALITY", 0.20)
    WEIGHT_DISTANCE = _env_float("WEIGHT_DISTANCE", 0.15)
    WEIGHT_TRUST = _env_float("WEIGHT_TRUST", 0.10)

    # Distance beyond which a buyer scores 0 on the distance component.
    MAX_MATCH_DISTANCE_KM = _env_float("MAX_MATCH_DISTANCE_KM", 300.0)
    # Straight-line distance is multiplied by this to approximate road distance.
    ROAD_DISTANCE_FACTOR = _env_float("ROAD_DISTANCE_FACTOR", 1.3)

    # ----- Logistics cost model (ESTIMATES, not quoted tariffs) -----
    TRANSPORT_BASE_FARE = _env_float("TRANSPORT_BASE_FARE", 300.0)
    TRANSPORT_RATE_PER_KM_PER_TONNE = _env_float("TRANSPORT_RATE_PER_KM_PER_TONNE", 6.0)
    TRANSPORT_MIN_CHARGE = _env_float("TRANSPORT_MIN_CHARGE", 500.0)
    LOADING_COST_PER_TONNE = _env_float("LOADING_COST_PER_TONNE", 150.0)

    # ----- Mandi channel deductions (typical APMC-style charges) -----
    MANDI_COMMISSION_PERCENT = _env_float("MANDI_COMMISSION_PERCENT", 2.0)
    MANDI_MARKET_FEE_PERCENT = _env_float("MANDI_MARKET_FEE_PERCENT", 1.0)

    # ----- Storage cost model -----
    DEFAULT_STORAGE_COST_PER_TONNE_PER_DAY = _env_float(
        "DEFAULT_STORAGE_COST_PER_TONNE_PER_DAY", 12.0
    )
    # Assumed physical loss while stored, per day, as a fraction of quantity.
    STORAGE_LOSS_PERCENT_PER_DAY = _env_float("STORAGE_LOSS_PERCENT_PER_DAY", 0.3)

    # ----- Forecasting thresholds -----
    # Below this many historical observations we refuse to forecast.
    MIN_FORECAST_HISTORY_POINTS = _env_int("MIN_FORECAST_HISTORY_POINTS", 10)
    FORECAST_DEFAULT_HORIZON_DAYS = _env_int("FORECAST_DEFAULT_HORIZON_DAYS", 7)
    FORECAST_MAX_HORIZON_DAYS = _env_int("FORECAST_MAX_HORIZON_DAYS", 30)
    # A predicted gain must beat holding cost by this margin to advise waiting.
    SALE_WINDOW_GAIN_MARGIN_PERCENT = _env_float("SALE_WINDOW_GAIN_MARGIN_PERCENT", 2.0)

    # ----- Pagination -----
    DEFAULT_PAGE_SIZE = _env_int("DEFAULT_PAGE_SIZE", 20)
    MAX_PAGE_SIZE = _env_int("MAX_PAGE_SIZE", 100)

    @classmethod
    def matching_weights(cls):
        return {
            "price": cls.WEIGHT_PRICE,
            "quantity": cls.WEIGHT_QUANTITY,
            "quality": cls.WEIGHT_QUALITY,
            "distance": cls.WEIGHT_DISTANCE,
            "trust": cls.WEIGHT_TRUST,
        }

    @classmethod
    def as_flask_config(cls):
        return {
            "SECRET_KEY": cls.SECRET_KEY,
            "JSON_SORT_KEYS": cls.JSON_SORT_KEYS,
            "ENV": cls.ENV,
        }


settings = Settings()
