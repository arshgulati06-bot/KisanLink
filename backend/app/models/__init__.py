"""
Domain models.

These are plain dataclasses, not an ORM. A repository runs the SQL and hands
the row to ``Model.from_row``; the controller calls ``model.to_dict()`` to get
JSON-safe output. Keeping the mapping this thin means the SQL in
``database/schema.sql`` stays the single source of truth for the data model.
"""
import dataclasses
import datetime as dt
from decimal import Decimal


def to_jsonable(value):
    """Convert a value coming out of MySQL or SQLite into something JSON can hold."""
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, (dt.datetime, dt.date)):
        return value.isoformat()
    if isinstance(value, dt.timedelta):
        return value.total_seconds()
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return value


@dataclasses.dataclass
class BaseModel:
    """Shared row-mapping behaviour for every model in this package."""

    #: Columns stored as 0/1 that should surface as real booleans.
    BOOL_FIELDS = ()
    #: Columns stored as DECIMAL that should surface as floats.
    FLOAT_FIELDS = ()

    @classmethod
    def field_names(cls):
        return [f.name for f in dataclasses.fields(cls)]

    @classmethod
    def from_row(cls, row):
        """Build a model from a DB row, ignoring columns the model doesn't declare."""
        if row is None:
            return None
        data = dict(row)
        known = set(cls.field_names())
        return cls(**{key: value for key, value in data.items() if key in known})

    @classmethod
    def from_rows(cls, rows):
        return [cls.from_row(row) for row in (rows or [])]

    def to_dict(self, extra=None):
        out = {}
        for field in dataclasses.fields(self):
            value = getattr(self, field.name)
            if field.name in self.BOOL_FIELDS and value is not None:
                out[field.name] = bool(value)
            elif field.name in self.FLOAT_FIELDS and value is not None:
                out[field.name] = float(value)
            else:
                out[field.name] = to_jsonable(value)
        if extra:
            out.update(extra)
        return out


def rows_to_dicts(rows):
    """JSON-safe conversion for ad-hoc joined rows that have no model class."""
    return [{key: to_jsonable(value) for key, value in dict(row).items()} for row in (rows or [])]


def row_to_dict(row):
    if row is None:
        return None
    return {key: to_jsonable(value) for key, value in dict(row).items()}


from app.models.user import User  # noqa: E402
from app.models.farmer_profile import FarmerProfile  # noqa: E402
from app.models.buyer_profile import BuyerProfile  # noqa: E402
from app.models.fpo_profile import FpoProfile  # noqa: E402
from app.models.fpo_member import FpoMember  # noqa: E402
from app.models.crop import Crop  # noqa: E402
from app.models.lot import Lot  # noqa: E402
from app.models.lot_contribution import LotContribution  # noqa: E402
from app.models.market import Market  # noqa: E402
from app.models.market_data import MarketData  # noqa: E402
from app.models.price_forecast import PriceForecast  # noqa: E402
from app.models.buyer_requirement import BuyerRequirement  # noqa: E402
from app.models.offer import Offer  # noqa: E402
from app.models.storage_facility import StorageFacility  # noqa: E402
from app.models.logistics_request import LogisticsRequest  # noqa: E402
from app.models.transaction import Transaction, TransactionStatusHistory  # noqa: E402
from app.models.payment import Payment  # noqa: E402
from app.models.rating import Rating  # noqa: E402
from app.models.grievance import Grievance  # noqa: E402
from app.models.recommendation import Recommendation  # noqa: E402

__all__ = [
    "BaseModel",
    "BuyerProfile",
    "BuyerRequirement",
    "Crop",
    "FarmerProfile",
    "FpoMember",
    "FpoProfile",
    "Grievance",
    "LogisticsRequest",
    "Lot",
    "LotContribution",
    "Market",
    "MarketData",
    "Offer",
    "Payment",
    "PriceForecast",
    "Rating",
    "Recommendation",
    "StorageFacility",
    "Transaction",
    "TransactionStatusHistory",
    "User",
    "row_to_dict",
    "rows_to_dicts",
    "to_jsonable",
]
