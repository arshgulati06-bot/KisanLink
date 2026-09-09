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
                          # (increased from 60 — combined dataset now provides 200-300+
                          #  observations for well-covered markets; 150 is conservative
                          #  and safe for Chronos-T5-Tiny on CPU)
MIN_RECORDS        = 14   # minimum records needed for forecasting
MIN_EVAL_RECORDS   = 21   # minimum records needed for evaluation (train + test)
EVAL_TEST_SIZE     = 7    # holdout size for backtesting

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
