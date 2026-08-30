"""URL map for /api/storage."""
from flask import Blueprint

from app.controllers import storage_controller as controller

storage_bp = Blueprint("storage", __name__, url_prefix="/api/storage")

storage_bp.add_url_rule("/facilities", view_func=controller.list_facilities, methods=["GET"])
storage_bp.add_url_rule("/facilities", view_func=controller.create_facility, methods=["POST"])
storage_bp.add_url_rule("/nearby", view_func=controller.nearby, methods=["GET"])
storage_bp.add_url_rule("/estimate", view_func=controller.estimate, methods=["POST"])
storage_bp.add_url_rule(
    "/facilities/<int:facility_id>", view_func=controller.get_facility, methods=["GET"]
)
