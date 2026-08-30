"""
HTTP handlers.

A controller does three things and nothing else: validate the request, call a
service, and wrap the result in the standard response envelope. Business rules
live in services; SQL lives in repositories.
"""
from flask import request

from app.config.settings import settings
from app.schemas import pagination_args, validate


def body(schema, partial=False):
    """Validate the JSON body against a schema."""
    return validate(request.get_json(silent=True) or {}, schema, partial=partial)


def query(schema):
    """Validate the query string against a schema."""
    return validate(request.args.to_dict(), schema, partial=True)


def page_args():
    return pagination_args(
        request.args,
        default_size=settings.DEFAULT_PAGE_SIZE,
        max_size=settings.MAX_PAGE_SIZE,
    )


def as_dicts(items):
    """Model list to JSON list, tolerating rows that are already dicts."""
    return [item if isinstance(item, dict) else item.to_dict() for item in items or []]
