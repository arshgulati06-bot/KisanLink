"""URL map for /api/trust and /api/grievances."""
from flask import Blueprint

from app.controllers import trust_controller as controller

trust_bp = Blueprint("trust", __name__, url_prefix="/api/trust")
grievance_bp = Blueprint("grievances", __name__, url_prefix="/api/grievances")

trust_bp.add_url_rule("/buyers/<int:buyer_id>", view_func=controller.buyer_trust, methods=["GET"])
trust_bp.add_url_rule(
    "/buyers/<int:buyer_id>/verify", view_func=controller.verify_buyer, methods=["PUT"]
)
trust_bp.add_url_rule(
    "/verifications/pending", view_func=controller.pending_verifications, methods=["GET"]
)
trust_bp.add_url_rule("/ratings", view_func=controller.rate, methods=["POST"])
trust_bp.add_url_rule(
    "/ratings/user/<int:user_id>", view_func=controller.user_ratings, methods=["GET"]
)

grievance_bp.add_url_rule("", view_func=controller.list_grievances, methods=["GET"])
grievance_bp.add_url_rule("", view_func=controller.create_grievance, methods=["POST"])
grievance_bp.add_url_rule("/dashboard", view_func=controller.grievance_dashboard, methods=["GET"])
grievance_bp.add_url_rule(
    "/<int:grievance_id>", view_func=controller.get_grievance, methods=["GET"]
)
grievance_bp.add_url_rule(
    "/<int:grievance_id>", view_func=controller.update_grievance, methods=["PUT"]
)
