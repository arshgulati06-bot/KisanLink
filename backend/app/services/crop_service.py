"""Commodity master data."""
from app.repositories.crop_repository import crop_repository
from app.utils.responses import ConflictError, NotFoundError


def list_crops(query=None, category=None, include_inactive=False, page=1, page_size=50,
               order_by=None):
    crops, total = crop_repository.search(
        query=query,
        category=category,
        active_only=not include_inactive,
        page=page,
        page_size=page_size,
        order_by=order_by,
    )
    return [crop.to_dict() for crop in crops], total


def get_crop(crop_id):
    crop = crop_repository.find_by_id(crop_id)
    if not crop:
        raise NotFoundError("Crop not found.")
    return crop


def get_crop_dict(crop_id):
    return get_crop(crop_id).to_dict()


def create_crop(data):
    if crop_repository.name_taken(data["name"]):
        raise ConflictError(f"A crop named '{data['name']}' already exists.")
    crop_id = crop_repository.insert(data)
    return crop_repository.find_by_id(crop_id).to_dict()


def update_crop(crop_id, data):
    get_crop(crop_id)
    if data.get("name") and crop_repository.name_taken(data["name"], exclude_id=crop_id):
        raise ConflictError(f"A crop named '{data['name']}' already exists.")
    crop_repository.update(crop_id, data)
    return crop_repository.find_by_id(crop_id).to_dict()


def deactivate_crop(crop_id):
    """
    Crops are retired, never deleted.

    Historical lots and transactions reference them, so removing a row would
    break records that must stay readable.
    """
    get_crop(crop_id)
    crop_repository.update(crop_id, {"is_active": 0})
    return crop_repository.find_by_id(crop_id).to_dict()


def valid_grades(crop_id):
    return get_crop(crop_id).grades


def categories():
    from app.models.crop import CATEGORIES

    return list(CATEGORIES)
