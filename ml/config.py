"""
KisanLink ML Pipeline — Configuration
=======================================
All configurable constants for the mandi price forecasting pipeline.
"""

import os

# ---------------------
# Paths
# ---------------------

# Default CSV path — relative to this file's directory
_ML_DIR = os.path.dirname(os.path.abspath(__file__))
DEFAULT_CSV_PATH = os.path.join(_ML_DIR, "data", "Agriculture_price_dataset.csv")

# Output directory for plots
OUTPUTS_DIR = os.path.join(_ML_DIR, "outputs")

# ---------------------
# Chronos Model
# ---------------------

MODEL_NAME = "amazon/chronos-t5-tiny"
MODEL_DEVICE = "cpu"
MODEL_DTYPE = "float32"  # used as torch.float32

# ---------------------
# Forecasting
# ---------------------

FORECAST_HORIZON = 7          # days to forecast
MAX_CONTEXT_LENGTH = 60       # max historical records to feed as context
MIN_RECORDS = 14              # minimum records needed for forecasting
MIN_EVAL_RECORDS = 21         # minimum records needed for evaluation (train + test)
EVAL_TEST_SIZE = 7            # holdout size for backtesting

# ---------------------
# CSV Column Names
# ---------------------

COL_STATE = "STATE"
COL_DISTRICT = "District Name"
COL_MARKET = "Market Name"
COL_COMMODITY = "Commodity"
COL_VARIETY = "Variety"
COL_GRADE = "Grade"
COL_MIN_PRICE = "Min_Price"
COL_MAX_PRICE = "Max_Price"
COL_MODAL_PRICE = "Modal_Price"
COL_DATE = "Price Date"
