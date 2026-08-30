"""URL map for /api/auth."""
from flask import Blueprint

from app.controllers import auth_controller

auth_bp = Blueprint("auth", __name__, url_prefix="/api/auth")

auth_bp.add_url_rule("/register", view_func=auth_controller.register, methods=["POST"])
auth_bp.add_url_rule("/login", view_func=auth_controller.login, methods=["POST"])
auth_bp.add_url_rule("/me", view_func=auth_controller.me, methods=["GET"])
auth_bp.add_url_rule("/me", view_func=auth_controller.update_me, methods=["PUT"])
auth_bp.add_url_rule(
    "/change-password", view_func=auth_controller.change_password, methods=["POST"]
)
auth_bp.add_url_rule(
    "/farmer-profile", view_func=auth_controller.save_farmer_profile, methods=["PUT"]
)
