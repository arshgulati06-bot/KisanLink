"""URL map for /api/offers."""
from flask import Blueprint

from app.controllers import offer_controller

offer_bp = Blueprint("offers", __name__, url_prefix="/api/offers")

offer_bp.add_url_rule("", view_func=offer_controller.list_offers, methods=["GET"])
offer_bp.add_url_rule("", view_func=offer_controller.create_offer, methods=["POST"])
offer_bp.add_url_rule("/lot/<int:lot_id>", view_func=offer_controller.offers_for_lot, methods=["GET"])
offer_bp.add_url_rule("/<int:offer_id>", view_func=offer_controller.get_offer, methods=["GET"])
offer_bp.add_url_rule(
    "/<int:offer_id>/accept", view_func=offer_controller.accept_offer, methods=["POST"]
)
offer_bp.add_url_rule(
    "/<int:offer_id>/reject", view_func=offer_controller.reject_offer, methods=["POST"]
)
offer_bp.add_url_rule(
    "/<int:offer_id>/counter", view_func=offer_controller.counter_offer, methods=["POST"]
)
offer_bp.add_url_rule(
    "/<int:offer_id>/withdraw", view_func=offer_controller.withdraw_offer, methods=["POST"]
)
