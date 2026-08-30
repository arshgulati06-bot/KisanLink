"""
A tiny declarative request-validation layer.

Schemas are plain dicts of ``field name -> Field(...)``. ``validate`` returns a
cleaned dictionary with values already coerced to the right Python type, or
raises :class:`ValidationError` listing every problem at once so the caller can
fix the whole form in one round trip.

    LOGIN_SCHEMA = {
        "phone": Field(str, required=True, pattern=PHONE_PATTERN),
        "password": Field(str, required=True, min_len=6),
    }
    data = validate(request.get_json(), LOGIN_SCHEMA)
"""
import datetime as dt
import re

from app.utils.responses import ValidationError

PHONE_PATTERN = r"^[6-9]\d{9}$"
EMAIL_PATTERN = r"^[^@\s]+@[^@\s]+\.[a-zA-Z]{2,}$"
PINCODE_PATTERN = r"^\d{6}$"
GST_PATTERN = r"^\d{2}[A-Z]{5}\d{4}[A-Z]{1}[A-Z\d]{1}[Z]{1}[A-Z\d]{1}$"

_UNSET = object()


class Field:
    """One expected key in a request body or query string."""

    def __init__(
        self,
        type_=str,
        required=False,
        default=_UNSET,
        choices=None,
        min_value=None,
        max_value=None,
        min_len=None,
        max_len=None,
        pattern=None,
        nullable=False,
        item_type=None,
    ):
        self.type_ = type_
        self.required = required
        self.default = default
        self.choices = list(choices) if choices else None
        self.min_value = min_value
        self.max_value = max_value
        self.min_len = min_len
        self.max_len = max_len
        self.pattern = pattern
        self.nullable = nullable
        self.item_type = item_type

    # -- coercion -----------------------------------------------------------
    def coerce(self, name, value):
        if self.type_ is bool:
            return self._to_bool(name, value)
        if self.type_ is int:
            return self._to_int(name, value)
        if self.type_ is float:
            return self._to_float(name, value)
        if self.type_ is dt.date:
            return self._to_date(name, value)
        if self.type_ is dt.datetime:
            return self._to_datetime(name, value)
        if self.type_ is list:
            return self._to_list(name, value)
        if self.type_ is dict:
            if not isinstance(value, dict):
                raise ValidationError(f"'{name}' must be an object.")
            return value
        return str(value).strip()

    @staticmethod
    def _to_bool(name, value):
        if isinstance(value, bool):
            return value
        text = str(value).strip().lower()
        if text in ("1", "true", "yes", "y", "on"):
            return True
        if text in ("0", "false", "no", "n", "off"):
            return False
        raise ValidationError(f"'{name}' must be true or false.")

    @staticmethod
    def _to_int(name, value):
        try:
            if isinstance(value, str):
                value = value.strip()
            return int(value)
        except (TypeError, ValueError):
            raise ValidationError(f"'{name}' must be a whole number.") from None

    @staticmethod
    def _to_float(name, value):
        try:
            if isinstance(value, str):
                value = value.strip()
            return float(value)
        except (TypeError, ValueError):
            raise ValidationError(f"'{name}' must be a number.") from None

    @staticmethod
    def _to_date(name, value):
        if isinstance(value, dt.datetime):
            return value.date()
        if isinstance(value, dt.date):
            return value
        text = str(value).strip()
        for fmt in ("%Y-%m-%d", "%d-%m-%Y", "%d/%m/%Y"):
            try:
                return dt.datetime.strptime(text, fmt).date()
            except ValueError:
                continue
        raise ValidationError(f"'{name}' must be a date in YYYY-MM-DD format.")

    @staticmethod
    def _to_datetime(name, value):
        if isinstance(value, dt.datetime):
            return value
        text = str(value).strip().replace("Z", "+00:00")
        try:
            return dt.datetime.fromisoformat(text)
        except ValueError:
            pass
        try:
            return dt.datetime.combine(Field._to_date(name, text), dt.time.min)
        except ValidationError:
            raise ValidationError(
                f"'{name}' must be a timestamp in ISO 8601 format."
            ) from None

    def _to_list(self, name, value):
        if isinstance(value, str):
            value = [part for part in (p.strip() for p in value.split(",")) if part]
        if not isinstance(value, (list, tuple)):
            raise ValidationError(f"'{name}' must be a list.")
        items = list(value)
        if self.item_type is int:
            return [Field._to_int(name, item) for item in items]
        if self.item_type is float:
            return [Field._to_float(name, item) for item in items]
        return items

    # -- constraints --------------------------------------------------------
    def check(self, name, value):
        if self.choices is not None:
            comparable = value.upper() if isinstance(value, str) else value
            allowed = [c.upper() if isinstance(c, str) else c for c in self.choices]
            if comparable not in allowed:
                raise ValidationError(
                    f"'{name}' must be one of: {', '.join(str(c) for c in self.choices)}."
                )
            if isinstance(value, str):
                value = self.choices[allowed.index(comparable)]
        if self.min_value is not None and isinstance(value, (int, float)) and value < self.min_value:
            raise ValidationError(f"'{name}' must be at least {self.min_value}.")
        if self.max_value is not None and isinstance(value, (int, float)) and value > self.max_value:
            raise ValidationError(f"'{name}' must not be greater than {self.max_value}.")
        unit = "items" if isinstance(value, (list, tuple)) else "characters"
        if self.min_len is not None and hasattr(value, "__len__") and len(value) < self.min_len:
            raise ValidationError(f"'{name}' must contain at least {self.min_len} {unit}.")
        if self.max_len is not None and hasattr(value, "__len__") and len(value) > self.max_len:
            raise ValidationError(f"'{name}' must not exceed {self.max_len} {unit}.")
        if self.pattern and isinstance(value, str) and not re.match(self.pattern, value):
            raise ValidationError(f"'{name}' is not in the expected format.")
        return value


def validate(payload, schema, partial=False):
    """
    Validate ``payload`` against ``schema``.

    Args:
        payload: the raw dict from the request (``None`` is treated as ``{}``).
        schema: mapping of field name to :class:`Field`.
        partial: when True, ``required`` is ignored — used by PATCH/PUT so a
            caller can send only the keys they want to change.

    Returns:
        dict: cleaned data containing only keys the caller actually supplied
        (plus any defaults declared on the schema).
    """
    if payload is None:
        payload = {}
    if not isinstance(payload, dict):
        raise ValidationError("Request body must be a JSON object.")

    cleaned = {}
    errors = {}

    for name, field in schema.items():
        supplied = name in payload and payload[name] is not None and payload[name] != ""
        if not supplied:
            if field.required and not partial:
                errors[name] = f"'{name}' is required."
            elif name in payload and payload[name] is None and field.nullable:
                cleaned[name] = None
            elif field.default is not _UNSET and not partial:
                cleaned[name] = field.default
            continue
        try:
            value = field.coerce(name, payload[name])
            cleaned[name] = field.check(name, value)
        except ValidationError as exc:
            errors[name] = exc.message

    if errors:
        raise ValidationError(
            "Some fields are invalid. Please correct them and try again.", details=errors
        )
    return cleaned


def require(cleaned, *names):
    """Assert that keys survived a partial validation (used by PUT handlers)."""
    missing = [n for n in names if n not in cleaned]
    if missing:
        raise ValidationError(
            "Missing required fields.", details={n: f"'{n}' is required." for n in missing}
        )
    return cleaned


def pagination_args(args, default_size=20, max_size=100):
    """Read ``page``/``page_size`` from a query string, clamped to sane values."""
    try:
        page = max(1, int(args.get("page", 1)))
    except (TypeError, ValueError):
        page = 1
    try:
        page_size = int(args.get("page_size", default_size))
    except (TypeError, ValueError):
        page_size = default_size
    page_size = max(1, min(page_size, max_size))
    return page, page_size
