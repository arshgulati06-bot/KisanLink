"""URL map for /api/buyers and /api/buyer-demands."""
from flask import Blueprint

from app.controllers import buyer_controller

buyer_bp = Blueprint("buyers", __name__, url_prefix="/api/buyers")
demand_bp = Blueprint("buyer_demands", __name__, url_prefix="/api/buyer-demands")

buyer_bp.add_url_rule("", view_func=buyer_controller.list_buyers, methods=["GET"])
buyer_bp.add_url_rule("/profile", view_func=buyer_controller.save_profile, methods=["PUT"])
buyer_bp.add_url_rule("/dashboard", view_func=buyer_controller.dashboard, methods=["GET"])
buyer_bp.add_url_rule("/<int:buyer_id>", view_func=buyer_controller.get_buyer, methods=["GET"])

demand_bp.add_url_rule("", view_func=buyer_controller.list_requirements, methods=["GET"])
demand_bp.add_url_rule("", view_func=buyer_controller.create_requirement, methods=["POST"])
demand_bp.add_url_rule(
    "/<int:requirement_id>", view_func=buyer_controller.get_requirement, methods=["GET"]
)
demand_bp.add_url_rule(
    "/<int:requirement_id>", view_func=buyer_controller.update_requirement, methods=["PUT"]
)
demand_bp.add_url_rule(
    "/<int:requirement_id>/close", view_func=buyer_controller.close_requirement, methods=["POST"]
)
demand_bp.add_url_rule(
    "/<int:requirement_id>/matches",
    view_func=buyer_controller.requirement_matches,
    methods=["GET"],
)
