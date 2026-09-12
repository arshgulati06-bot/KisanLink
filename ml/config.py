"""
KisanLink ML Pipeline — Configuration
=======================================
All configurable constants for the mandi price forecasting pipeline.
"""

import os

# ---------------------
# Paths
# ---------------------

# Directory containing this file
_ML_DIR = os.path.dirname(os.path.abspath(__file__))

# Data directory
DATA_DIR = os.path.join(_ML_DIR, "data")

# Individual CSV paths
CSV_AGRICULTURE = os.path.join(DATA_DIR, "Agriculture_price_dataset.csv")
CSV_2022        = os.path.join(DATA_DIR, "2022.csv")
CSV_2026        = os.path.join(DATA_DIR, "2026.csv")

# Default CSV path — kept for backward compatibility with --csv CLI flag
DEFAULT_CSV_PATH = CSV_AGRICULTURE

# Output directory for plots
OUTPUTS_DIR = os.path.join(_ML_DIR, "outputs")

# Combined-frame cache (avoids re-reading ~5.8M CSV rows every process start)
CACHE_DIR = os.path.join(DATA_DIR, "_cache")
COMBINED_CACHE_PATH = os.path.join(CACHE_DIR, "combined.pkl")
COMBINED_CACHE_SIG = os.path.join(CACHE_DIR, "combined.sig")

# Incrementally ingested records (persisted; merged into the combined frame)
INGEST_DIR = os.path.join(DATA_DIR, "ingested")
INGESTED_RECORDS_PATH = os.path.join(INGEST_DIR, "records.csv")
INGEST_LOG_PATH = os.path.join(INGEST_DIR, "ingest.log")

# Platform seed buyer requirements (not a live procurement API)
BUYER_DEMANDS_PATH = os.path.join(DATA_DIR, "buyers", "demands.json")

# Ingestion / official source (credentials MUST come from the environment)
INGEST_MAX_RECORDS = int(os.environ.get("KISANLINK_INGEST_MAX_RECORDS", "2000"))
INGEST_MAX_BYTES = int(os.environ.get("KISANLINK_INGEST_MAX_BYTES", str(2 * 1024 * 1024)))
INGEST_TOKEN = os.environ.get("KISANLINK_INGEST_TOKEN", "").strip()
MIN_MODAL_PRICE = 0.01
MAX_MODAL_PRICE = 10_000_000.0  # reject impossible data-entry errors
DATA_GOV_API_KEY = os.environ.get("DATA_GOV_API_KEY", "").strip()
DATA_GOV_RESOURCE_ID = os.environ.get("DATA_GOV_RESOURCE_ID", "").strip()
DATA_GOV_BASE_URL = os.environ.get(
    "DATA_GOV_BASE_URL", "https://api.data.gov.in/resource"
).rstrip("/")
ROUTING_API_KEY = os.environ.get("ROUTING_API_KEY", "").strip() or os.environ.get("ORS_API_KEY", "").strip()
OSRM_BASE_URL = os.environ.get("OSRM_BASE_URL", "https://router.project-osrm.org").rstrip("/")

# ---------------------
# Chronos Model
# ---------------------

MODEL_NAME   = "amazon/chronos-t5-tiny"
MODEL_DEVICE = "cpu"
MODEL_DTYPE  = "float32"  # used as torch.float32

# ---------------------
# Forecasting
# ---------------------

FORECAST_HORIZON   = 7    # days to forecast
MAX_CONTEXT_LENGTH = 150  # max historical daily records fed as context to Chronos
MAX_GAP_DAYS       = 365  # if a time gap > this many days exists in the daily series,
                          #   only the most recent continuous segment is used for context
                          #   and evaluation.  This prevents cross-regime contamination
                          #   when different source datasets cover different price eras
                          #   (e.g. 2022.csv flower prices vs 2026.csv flower prices).
OUTLIER_IQR_K      = 5.0  # multiplier for the IQR-based winsorization fence applied
                          #   to context prices before building the Chronos tensor:
                          #   fence = (Q1 - k*IQR, Q3 + k*IQR).
                          #   k=5.0 is very conservative — only genuine data-entry
                          #   errors (e.g. Rs.191 million rows) are capped.
MIN_RECORDS        = 14   # minimum records needed for forecasting
MIN_EVAL_RECORDS   = 21   # minimum records needed for evaluation (train + test)
EVAL_TEST_SIZE     = 7    # holdout size for backtesting
FORECAST_SAMPLES   = 20   # number of Monte-Carlo samples for uncertainty quantiles (q10/q90)

# ---------------------
# Normalized Column Names
# (all datasets are normalized to this common schema by load_combined_data)
# ---------------------

COL_STATE        = "State"
COL_DISTRICT     = "District"
COL_MARKET       = "Market"
COL_COMMODITY    = "Commodity"
COL_VARIETY      = "Variety"
COL_GRADE        = "Grade"
COL_MIN_PRICE    = "Min_Price"
COL_MAX_PRICE    = "Max_Price"
COL_MODAL_PRICE  = "Modal_Price"
COL_DATE         = "Date"
