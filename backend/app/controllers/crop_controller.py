"""Crop master endpoints."""
from flask import request

from app.controllers import body, page_args
from app.middleware.role_middleware import admin_required
from app.schemas.crop_schema import CREATE_CROP_SCHEMA, UPDATE_CROP_SCHEMA
from app.services import crop_service
from app.utils.responses import created, paginated, success


def list_crops():
    page, page_size = page_args()
    items, total = crop_service.list_crops(
        query=request.args.get("q"),
        category=request.args.get("category"),
        include_inactive=request.args.get("include_inactive") == "true",
        page=page,
        page_size=page_size,
        order_by=request.args.get("order_by"),
    )
    return paginated(items, page, page_size, total)


def get_crop(crop_id):
    return success(crop_service.get_crop_dict(crop_id))


def categories():
    return success(crop_service.categories())


@admin_required
def create_crop():
    return created(crop_service.create_crop(body(CREATE_CROP_SCHEMA)), message="Crop added.")


@admin_required
def update_crop(crop_id):
    data = body(UPDATE_CROP_SCHEMA, partial=True)
    return success(crop_service.update_crop(crop_id, data), message="Crop updated.")


@admin_required
def deactivate_crop(crop_id):
    return success(crop_service.deactivate_crop(crop_id), message="Crop deactivated.")
