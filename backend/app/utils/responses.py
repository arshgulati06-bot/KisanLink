"""
One response envelope for the whole API.

Every endpoint answers with the same shape so the frontend never has to guess:

    success: {"success": true,  "data": <payload>, "message": "..."}
    failure: {"success": false, "error": {"code": "...", "message": "...", "details": {...}}}
"""
from flask import jsonify


class AppError(Exception):
    """
    An error that is safe to show the caller.

    Services raise these; a single Flask error handler turns them into JSON,
    so controllers stay free of try/except noise.
    """

    status_code = 400
    code = "BAD_REQUEST"

    def __init__(self, message, status_code=None, code=None, details=None):
        super().__init__(message)
        self.message = message
        if status_code is not None:
            self.status_code = status_code
        if code is not None:
            self.code = code
        self.details = details or {}

    def to_payload(self):
        payload = {"code": self.code, "message": self.message}
        if self.details:
            payload["details"] = self.details
        return payload


class ValidationError(AppError):
    status_code = 422
    code = "VALIDATION_ERROR"


class NotFoundError(AppError):
    status_code = 404
    code = "NOT_FOUND"


class UnauthorizedError(AppError):
    status_code = 401
    code = "UNAUTHORIZED"


class ForbiddenError(AppError):
    status_code = 403
    code = "FORBIDDEN"


class ConflictError(AppError):
    status_code = 409
    code = "CONFLICT"


def success(data=None, message=None, status_code=200, **extra):
    body = {"success": True, "data": data}
    if message:
        body["message"] = message
    body.update(extra)
    return jsonify(body), status_code


def created(data=None, message="Created successfully.", **extra):
    return success(data=data, message=message, status_code=201, **extra)


def failure(message, status_code=400, code="BAD_REQUEST", details=None):
    body = {"success": False, "error": {"code": code, "message": message}}
    if details:
        body["error"]["details"] = details
    return jsonify(body), status_code


def paginated(items, page, page_size, total, message=None, **extra):
    """Standard list envelope: rows plus everything needed to page through."""
    total_pages = (total + page_size - 1) // page_size if page_size else 0
    return success(
        data=items,
        message=message,
        meta={
            "page": page,
            "page_size": page_size,
            "total": total,
            "total_pages": total_pages,
            "has_next": page < total_pages,
            "has_previous": page > 1,
        },
        **extra,
    )


def register_error_handlers(app):
    """Attach the handlers that keep every error response in the envelope."""

    @app.errorhandler(AppError)
    def _handle_app_error(exc):
        return failure(
            exc.message, status_code=exc.status_code, code=exc.code, details=exc.details
        )

    @app.errorhandler(404)
    def _handle_404(_exc):
        return failure("The requested endpoint does not exist.", 404, "NOT_FOUND")

    @app.errorhandler(405)
    def _handle_405(_exc):
        return failure("This method is not allowed on that endpoint.", 405, "METHOD_NOT_ALLOWED")

    @app.errorhandler(Exception)
    def _handle_unexpected(exc):
        app.logger.exception("Unhandled error: %s", exc)
        detail = str(exc) if app.config.get("DEBUG") else None
        return failure(
            "An unexpected server error occurred.",
            500,
            "INTERNAL_ERROR",
            details={"reason": detail} if detail else None,
        )
