"""URL map for /api/logistics."""
from flask import Blueprint

from app.controllers import logistics_controller as controller


logistics_bp = Blueprint(
    "logistics",
    __name__,
    url_prefix="/api/logistics",
)


# ---------------------------------------------------------------------------
# Transport estimate
# ---------------------------------------------------------------------------

logistics_bp.add_url_rule(
    "/estimate",
    view_func=controller.estimate,
    methods=["POST"],
)


# ---------------------------------------------------------------------------
# Logistics requests
# ---------------------------------------------------------------------------

logistics_bp.add_url_rule(
    "/requests",
    view_func=controller.list_requests,
    methods=["GET"],
)

logistics_bp.add_url_rule(
    "/requests",
    view_func=controller.create_request,
    methods=["POST"],
)

logistics_bp.add_url_rule(
    "/requests/<int:request_id>",
    view_func=controller.get_request,
    methods=["GET"],
)

logistics_bp.add_url_rule(
    "/requests/<int:request_id>/status",
    view_func=controller.update_status,
    methods=["PUT"],
)

logistics_bp.add_url_rule(
    "/requests/<int:request_id>/provider",
    view_func=controller.assign_provider,
    methods=["PUT"],
)


# ---------------------------------------------------------------------------
# Transporter management
# ---------------------------------------------------------------------------

logistics_bp.add_url_rule(
    "/transporters",
    view_func=controller.list_transporters,
    methods=["GET"],
)

logistics_bp.add_url_rule(
    "/transporters",
    view_func=controller.create_transporter,
    methods=["POST"],
)


# ---------------------------------------------------------------------------
# Vehicle management
# ---------------------------------------------------------------------------

logistics_bp.add_url_rule(
    "/vehicles",
    view_func=controller.list_available_vehicles,
    methods=["GET"],
)

logistics_bp.add_url_rule(
    "/vehicles",
    view_func=controller.create_vehicle,
    methods=["POST"],
)


# ---------------------------------------------------------------------------
# Transport assignment and backup
# ---------------------------------------------------------------------------

logistics_bp.add_url_rule(
    "/requests/<int:request_id>/transporter",
    view_func=controller.assign_transporter,
    methods=["PUT"],
)

logistics_bp.add_url_rule(
    "/requests/<int:request_id>/backup-options",
    view_func=controller.backup_options,
    methods=["GET"],
)

logistics_bp.add_url_rule(
    "/requests/<int:request_id>/reassign",
    view_func=controller.reassign_transport,
    methods=["PUT"],
)


# ---------------------------------------------------------------------------
# ETA and route progress
# ---------------------------------------------------------------------------

logistics_bp.add_url_rule(
    "/requests/<int:request_id>/eta",
    view_func=controller.update_eta_progress,
    methods=["PUT"],
)


# ---------------------------------------------------------------------------
# Logistics incidents
# ---------------------------------------------------------------------------

logistics_bp.add_url_rule(
    "/requests/<int:request_id>/incidents",
    view_func=controller.create_incident,
    methods=["POST"],
)

logistics_bp.add_url_rule(
    "/requests/<int:request_id>/incidents",
    view_func=controller.list_incidents,
    methods=["GET"],
)

logistics_bp.add_url_rule(
    "/incidents/<int:incident_id>",
    view_func=controller.update_incident,
    methods=["PUT"],
)