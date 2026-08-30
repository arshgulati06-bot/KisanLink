"""Registration, login and account endpoints."""
from app.controllers import body
from app.middleware.auth_middleware import login_required, require_current_user
from app.repositories.user_repository import farmer_profile_repository
from app.schemas.auth_schema import (
    CHANGE_PASSWORD_SCHEMA,
    FARMER_PROFILE_SCHEMA,
    LOGIN_SCHEMA,
    REGISTER_SCHEMA,
    UPDATE_ACCOUNT_SCHEMA,
)
from app.services import auth_service
from app.utils.responses import created, success


def register():
    data = body(REGISTER_SCHEMA)
    result = auth_service.register(data)
    return created(result, message="Account created. You are now signed in.")


def login():
    data = body(LOGIN_SCHEMA)
    return success(auth_service.login(data["phone"], data["password"]), message="Signed in.")


@login_required
def me():
    return success(auth_service.get_profile(require_current_user()))


@login_required
def update_me():
    data = body(UPDATE_ACCOUNT_SCHEMA, partial=True)
    return success(
        auth_service.update_account(require_current_user(), data), message="Account updated."
    )


@login_required
def change_password():
    data = body(CHANGE_PASSWORD_SCHEMA)
    auth_service.change_password(
        require_current_user(), data["current_password"], data["new_password"]
    )
    return success(message="Password changed.")


@login_required
def save_farmer_profile():
    user = require_current_user()
    data = body(FARMER_PROFILE_SCHEMA, partial=True)
    profile = farmer_profile_repository.upsert(user.id, data)
    return success(profile.to_dict(), message="Profile saved.")
