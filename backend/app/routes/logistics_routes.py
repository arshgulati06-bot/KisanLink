"""URL map for /api/logistics."""
from flask import Blueprint

from app.controllers import logistics_controller as controller

logistics_bp = Blueprint("logistics", __name__, url_prefix="/api/logistics")

logistics_bp.add_url_rule("/estimate", view_func=controller.estimate, methods=["POST"])
logistics_bp.add_url_rule("/requests", view_func=controller.list_requests, methods=["GET"])
logistics_bp.add_url_rule("/requests", view_func=controller.create_request, methods=["POST"])
logistics_bp.add_url_rule(
    "/requests/<int:request_id>", view_func=controller.get_request, methods=["GET"]
)
logistics_bp.add_url_rule(
    "/requests/<int:request_id>/status", view_func=controller.update_status, methods=["PUT"]
)
logistics_bp.add_url_rule(
    "/requests/<int:request_id>/provider", view_func=controller.assign_provider, methods=["PUT"]
)
