"""Request shapes for the crop master."""
from app.models.crop import CATEGORIES, UNITS
from app.schemas import Field

CREATE_CROP_SCHEMA = {
    "name": Field(str, required=True, min_len=2, max_len=120),
    "local_name": Field(str, max_len=120),
    "category": Field(str, choices=CATEGORIES, default="OTHER"),
    "default_unit": Field(str, choices=UNITS, default="QUINTAL"),
    "shelf_life_days": Field(int, min_value=0, max_value=3650),
    "is_perishable": Field(bool, default=False),
    "grade_scale": Field(str, default="A,B,C", max_len=40),
}

UPDATE_CROP_SCHEMA = {
    "name": Field(str, min_len=2, max_len=120),
    "local_name": Field(str, max_len=120),
    "category": Field(str, choices=CATEGORIES),
    "default_unit": Field(str, choices=UNITS),
    "shelf_life_days": Field(int, min_value=0, max_value=3650),
    "is_perishable": Field(bool),
    "grade_scale": Field(str, max_len=40),
    "is_active": Field(bool),
}
