"""
Blueprint registry.

Every URL the API serves is registered from here, so one file answers the
question "what endpoints exist?".
"""
from app.routes.auth_routes import auth_bp
from app.routes.buyer_routes import buyer_bp, demand_bp
from app.routes.crop_routes import crop_bp
from app.routes.fpo_routes import fpo_bp
from app.routes.health import health_bp
from app.routes.logistics_routes import logistics_bp
from app.routes.lot_routes import lot_bp
from app.routes.market_routes import market_bp, price_bp
from app.routes.offer_routes import offer_bp
from app.routes.recommendation_routes import forecast_bp, matching_bp, recommendation_bp
from app.routes.storage_routes import storage_bp
from app.routes.transaction_routes import transaction_bp
from app.routes.trust_routes import grievance_bp, trust_bp

ALL_BLUEPRINTS = (
    health_bp,
    auth_bp,
    crop_bp,
    lot_bp,
    market_bp,
    price_bp,
    recommendation_bp,
    matching_bp,
    forecast_bp,
    buyer_bp,
    demand_bp,
    offer_bp,
    fpo_bp,
    logistics_bp,
    storage_bp,
    transaction_bp,
    trust_bp,
    grievance_bp,
)


def register_routes(app):
    for blueprint in ALL_BLUEPRINTS:
        app.register_blueprint(blueprint)
    return app
