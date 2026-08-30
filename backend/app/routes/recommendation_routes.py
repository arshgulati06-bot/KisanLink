"""URL map for /api/recommendations, /api/matching and /api/forecast."""
from flask import Blueprint

from app.controllers import recommendation_controller as controller

recommendation_bp = Blueprint("recommendations", __name__, url_prefix="/api/recommendations")
matching_bp = Blueprint("matching", __name__, url_prefix="/api/matching")
forecast_bp = Blueprint("forecast", __name__, url_prefix="/api/forecast")

recommendation_bp.add_url_rule("", view_func=controller.recommend, methods=["POST"])
recommendation_bp.add_url_rule("/lot/<int:lot_id>", view_func=controller.for_lot, methods=["GET"])
recommendation_bp.add_url_rule(
    "/lot/<int:lot_id>/latest", view_func=controller.latest, methods=["GET"]
)
recommendation_bp.add_url_rule(
    "/lot/<int:lot_id>/history", view_func=controller.history, methods=["GET"]
)
recommendation_bp.add_url_rule("/sale-window", view_func=controller.sale_window, methods=["POST"])

matching_bp.add_url_rule("", view_func=controller.match, methods=["POST"])

forecast_bp.add_url_rule("", view_func=controller.forecast, methods=["GET"])
forecast_bp.add_url_rule("/readiness", view_func=controller.readiness, methods=["GET"])
