"""Request shapes for registration, login and account management."""
from app.schemas import EMAIL_PATTERN, PHONE_PATTERN, PINCODE_PATTERN, Field
from app.models.buyer_profile import BUYER_TYPES
from app.models.user import ROLES

REGISTER_SCHEMA = {
    "name": Field(str, required=True, min_len=2, max_len=120),
    "phone": Field(str, required=True, pattern=PHONE_PATTERN),
    "email": Field(str, pattern=EMAIL_PATTERN, max_len=150),
    "password": Field(str, required=True, min_len=6, max_len=128),
    "role": Field(str, required=True, choices=ROLES),
    "language": Field(str, default="en", max_len=10),
    # Optional profile fields, applied to whichever profile the role creates.
    "village": Field(str, max_len=120),
    "district": Field(str, max_len=120),
    "state": Field(str, default="Maharashtra", max_len=120),
    "pincode": Field(str, pattern=PINCODE_PATTERN),
    "latitude": Field(float, min_value=-90, max_value=90),
    "longitude": Field(float, min_value=-180, max_value=180),
    "land_size_acres": Field(float, min_value=0),
    "business_name": Field(str, max_len=180),
    "buyer_type": Field(str, choices=BUYER_TYPES),
    "gst_number": Field(str, max_len=20),
    "fpo_name": Field(str, max_len=180),
    "registration_number": Field(str, max_len=80),
}

LOGIN_SCHEMA = {
    "phone": Field(str, required=True, pattern=PHONE_PATTERN),
    "password": Field(str, required=True, min_len=1),
}

UPDATE_ACCOUNT_SCHEMA = {
    "name": Field(str, min_len=2, max_len=120),
    "phone": Field(str, pattern=PHONE_PATTERN),
    "email": Field(str, pattern=EMAIL_PATTERN, max_len=150, nullable=True),
    "language": Field(str, max_len=10),
}

CHANGE_PASSWORD_SCHEMA = {
    "current_password": Field(str, required=True),
    "new_password": Field(str, required=True, min_len=6, max_len=128),
}

FARMER_PROFILE_SCHEMA = {
    "village": Field(str, max_len=120),
    "district": Field(str, max_len=120),
    "state": Field(str, max_len=120),
    "pincode": Field(str, pattern=PINCODE_PATTERN),
    "latitude": Field(float, min_value=-90, max_value=90),
    "longitude": Field(float, min_value=-180, max_value=180),
    "land_size_acres": Field(float, min_value=0),
    "primary_crops": Field(str, max_len=255),
}
