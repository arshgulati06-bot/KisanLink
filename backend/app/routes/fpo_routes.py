"""URL map for /api/fpo."""
from flask import Blueprint

from app.controllers import fpo_controller

fpo_bp = Blueprint("fpo", __name__, url_prefix="/api/fpo")

fpo_bp.add_url_rule("", view_func=fpo_controller.list_fpos, methods=["GET"])
fpo_bp.add_url_rule("/profile", view_func=fpo_controller.save_profile, methods=["PUT"])
fpo_bp.add_url_rule("/dashboard", view_func=fpo_controller.dashboard, methods=["GET"])
fpo_bp.add_url_rule("/<int:fpo_id>", view_func=fpo_controller.get_fpo, methods=["GET"])
fpo_bp.add_url_rule("/<int:fpo_id>/members", view_func=fpo_controller.list_members, methods=["GET"])
fpo_bp.add_url_rule("/<int:fpo_id>/members", view_func=fpo_controller.add_member, methods=["POST"])
fpo_bp.add_url_rule(
    "/<int:fpo_id>/members/<int:member_id>", view_func=fpo_controller.update_member, methods=["PUT"]
)
fpo_bp.add_url_rule(
    "/<int:fpo_id>/members/<int:member_id>",
    view_func=fpo_controller.remove_member,
    methods=["DELETE"],
)
fpo_bp.add_url_rule(
    "/<int:fpo_id>/aggregation-candidates",
    view_func=fpo_controller.aggregation_candidates,
    methods=["GET"],
)
fpo_bp.add_url_rule("/<int:fpo_id>/aggregate", view_func=fpo_controller.aggregate, methods=["POST"])
fpo_bp.add_url_rule(
    "/<int:fpo_id>/lots/<int:lot_id>/payouts", view_func=fpo_controller.payouts, methods=["GET"]
)
