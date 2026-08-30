"""URL map for /api/markets and /api/prices."""
from flask import Blueprint

from app.controllers import market_controller

market_bp = Blueprint("markets", __name__, url_prefix="/api/markets")
price_bp = Blueprint("prices", __name__, url_prefix="/api/prices")

market_bp.add_url_rule("", view_func=market_controller.list_markets, methods=["GET"])
market_bp.add_url_rule("", view_func=market_controller.create_market, methods=["POST"])
market_bp.add_url_rule("/nearby", view_func=market_controller.nearby, methods=["GET"])
market_bp.add_url_rule("/<int:market_id>", view_func=market_controller.get_market, methods=["GET"])
market_bp.add_url_rule(
    "/<int:market_id>/arrivals", view_func=market_controller.arrivals, methods=["GET"]
)

price_bp.add_url_rule("", view_func=market_controller.prices, methods=["GET"])
price_bp.add_url_rule("", view_func=market_controller.record_price, methods=["POST"])
price_bp.add_url_rule("/overview", view_func=market_controller.overview, methods=["GET"])
price_bp.add_url_rule("/trends", view_func=market_controller.trends, methods=["GET"])
price_bp.add_url_rule("/benchmark", view_func=market_controller.benchmark, methods=["GET"])
price_bp.add_url_rule("/bulk", view_func=market_controller.bulk_record_prices, methods=["POST"])
