"""URL map for /api/crops."""
from flask import Blueprint

from app.controllers import crop_controller

crop_bp = Blueprint("crops", __name__, url_prefix="/api/crops")

crop_bp.add_url_rule("", view_func=crop_controller.list_crops, methods=["GET"])
crop_bp.add_url_rule("", view_func=crop_controller.create_crop, methods=["POST"])
crop_bp.add_url_rule("/categories", view_func=crop_controller.categories, methods=["GET"])
crop_bp.add_url_rule("/<int:crop_id>", view_func=crop_controller.get_crop, methods=["GET"])
crop_bp.add_url_rule("/<int:crop_id>", view_func=crop_controller.update_crop, methods=["PUT"])
crop_bp.add_url_rule(
    "/<int:crop_id>", view_func=crop_controller.deactivate_crop, methods=["DELETE"]
)
