"""URL map for /api/transactions."""
from flask import Blueprint

from app.controllers import transaction_controller as controller

transaction_bp = Blueprint("transactions", __name__, url_prefix="/api/transactions")

transaction_bp.add_url_rule("", view_func=controller.list_transactions, methods=["GET"])
transaction_bp.add_url_rule("/summary", view_func=controller.summary, methods=["GET"])
transaction_bp.add_url_rule(
    "/<int:transaction_id>", view_func=controller.get_transaction, methods=["GET"]
)
transaction_bp.add_url_rule(
    "/<int:transaction_id>/status", view_func=controller.update_status, methods=["PUT"]
)
transaction_bp.add_url_rule(
    "/<int:transaction_id>/history", view_func=controller.history, methods=["GET"]
)
transaction_bp.add_url_rule(
    "/<int:transaction_id>/payments", view_func=controller.record_payment, methods=["POST"]
)
transaction_bp.add_url_rule(
    "/<int:transaction_id>/realization", view_func=controller.realization, methods=["GET"]
)
