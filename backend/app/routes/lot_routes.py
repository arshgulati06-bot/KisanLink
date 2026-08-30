"""URL map for /api/lots."""
from flask import Blueprint

from app.controllers import lot_controller

lot_bp = Blueprint("lots", __name__, url_prefix="/api/lots")

lot_bp.add_url_rule("", view_func=lot_controller.list_lots, methods=["GET"])
lot_bp.add_url_rule("", view_func=lot_controller.create_lot, methods=["POST"])
lot_bp.add_url_rule("/dashboard", view_func=lot_controller.dashboard, methods=["GET"])
lot_bp.add_url_rule("/<int:lot_id>", view_func=lot_controller.get_lot, methods=["GET"])
lot_bp.add_url_rule("/<int:lot_id>", view_func=lot_controller.update_lot, methods=["PUT"])
lot_bp.add_url_rule("/<int:lot_id>", view_func=lot_controller.delete_lot, methods=["DELETE"])
lot_bp.add_url_rule(
    "/<int:lot_id>/publish", view_func=lot_controller.publish_lot, methods=["POST"]
)
lot_bp.add_url_rule(
    "/<int:lot_id>/withdraw", view_func=lot_controller.withdraw_lot, methods=["POST"]
)
lot_bp.add_url_rule("/<int:lot_id>/status", view_func=lot_controller.set_status, methods=["PUT"])
lot_bp.add_url_rule("/<int:lot_id>/matches", view_func=lot_controller.lot_matches, methods=["GET"])
lot_bp.add_url_rule(
    "/<int:lot_id>/recommendation",
    view_func=lot_controller.lot_recommendation,
    methods=["GET"],
)
