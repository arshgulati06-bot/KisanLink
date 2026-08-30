"""Registration, login and profile resolution."""
from app.models.buyer_profile import BUYER_TYPES
from app.models.user import ADMIN, BUYER, FARMER, FPO
from app.repositories.user_repository import (
    buyer_profile_repository,
    farmer_profile_repository,
    fpo_profile_repository,
    user_repository,
)
from app.utils.responses import ConflictError, NotFoundError, UnauthorizedError, ValidationError
from app.utils.security import create_access_token, hash_password, token_expiry_seconds, verify_password


def register(data):
    """
    Create an account and the profile row that matches its role.

    A BUYER account gets a buyer profile immediately (with an unverified
    status) so the buyer can start declaring demand without a second step.
    """
    phone = data["phone"]
    if user_repository.phone_taken(phone):
        raise ConflictError("An account with this mobile number already exists.")
    email = data.get("email")
    if email and user_repository.email_taken(email):
        raise ConflictError("An account with this email address already exists.")

    role = data["role"].upper()
    user_id = user_repository.insert(
        {
            "name": data["name"],
            "phone": phone,
            "email": email,
            "password_hash": hash_password(data["password"]),
            "role": role,
            "language": data.get("language", "en"),
            "is_active": 1,
        }
    )

    _create_role_profile(user_id, role, data)
    user = user_repository.find_by_id(user_id)
    return _session_payload(user)


def _create_role_profile(user_id, role, data):
    """Seed the role-specific profile with whatever was supplied at signup."""
    if role == FARMER:
        farmer_profile_repository.upsert(
            user_id,
            {
                "village": data.get("village"),
                "district": data.get("district"),
                "state": data.get("state", "Maharashtra"),
                "pincode": data.get("pincode"),
                "latitude": data.get("latitude"),
                "longitude": data.get("longitude"),
                "land_size_acres": data.get("land_size_acres"),
            },
        )
    elif role == BUYER:
        buyer_type = (data.get("buyer_type") or "TRADER").upper()
        if buyer_type not in BUYER_TYPES:
            raise ValidationError(
                f"'buyer_type' must be one of: {', '.join(BUYER_TYPES)}."
            )
        buyer_profile_repository.upsert(
            user_id,
            {
                "business_name": data.get("business_name") or data["name"],
                "buyer_type": buyer_type,
                "gst_number": data.get("gst_number"),
                "district": data.get("district"),
                "state": data.get("state", "Maharashtra"),
                "latitude": data.get("latitude"),
                "longitude": data.get("longitude"),
                # Everyone starts unverified. Verification is a deliberate,
                # reviewed action - never a side effect of signing up.
                "verification_status": "UNVERIFIED",
            },
        )
    elif role == FPO:
        fpo_profile_repository.upsert(
            user_id,
            {
                "fpo_name": data.get("fpo_name") or data["name"],
                "registration_number": data.get("registration_number"),
                "district": data.get("district"),
                "state": data.get("state", "Maharashtra"),
                "latitude": data.get("latitude"),
                "longitude": data.get("longitude"),
                "contact_person": data.get("name"),
            },
        )


def login(phone, password):
    user = user_repository.find_by_phone(phone)
    if not user or not verify_password(password, user.password_hash):
        # Same message either way, so the response cannot be used to discover
        # which mobile numbers are registered.
        raise UnauthorizedError("Incorrect mobile number or password.")
    if not user.is_active:
        raise UnauthorizedError("This account has been deactivated. Please contact support.")
    return _session_payload(user)


def _session_payload(user):
    return {
        "token": create_access_token(user.id, user.role),
        "token_type": "Bearer",
        "expires_in": token_expiry_seconds(),
        "user": user.to_dict(),
        "profile": get_profile(user).get("profile"),
    }


def get_profile(user):
    """Return the account plus whichever profile table its role uses."""
    profile = None
    if user.role == FARMER:
        record = farmer_profile_repository.find_by_user_id(user.id)
        profile = record.to_dict() if record else None
    elif user.role == BUYER:
        record = buyer_profile_repository.find_by_user_id(user.id)
        profile = record.to_dict() if record else None
    elif user.role == FPO:
        record = fpo_profile_repository.find_by_user_id(user.id)
        profile = record.to_dict() if record else None
    return {"user": user.to_dict(), "profile": profile, "role": user.role}


def update_account(user, data):
    if "phone" in data and user_repository.phone_taken(data["phone"], exclude_id=user.id):
        raise ConflictError("That mobile number is already registered to another account.")
    if data.get("email") and user_repository.email_taken(data["email"], exclude_id=user.id):
        raise ConflictError("That email address is already registered to another account.")
    user_repository.update(user.id, data)
    return get_profile(user_repository.find_by_id(user.id))


def change_password(user, current_password, new_password):
    if not verify_password(current_password, user.password_hash):
        raise UnauthorizedError("Your current password is incorrect.")
    if current_password == new_password:
        raise ValidationError("The new password must be different from the current one.")
    user_repository.update(user.id, {"password_hash": hash_password(new_password)})
    return True


def get_user_or_404(user_id):
    user = user_repository.find_by_id(user_id)
    if not user:
        raise NotFoundError("User not found.")
    return user


def require_farmer_profile(user):
    """
    Fetch the farmer profile a lot needs, creating an empty one if missing.

    A farmer who registered before the profile step should still be able to
    create a lot; the profile fills in from the lot's own location fields.
    """
    profile = farmer_profile_repository.find_by_user_id(user.id)
    if not profile:
        profile = farmer_profile_repository.upsert(user.id, {"state": "Maharashtra"})
    return profile


def require_buyer_profile(user):
    profile = buyer_profile_repository.find_by_user_id(user.id)
    if not profile:
        raise NotFoundError(
            "No buyer profile found for this account. Complete your buyer profile first."
        )
    return profile


def require_fpo_profile(user):
    profile = fpo_profile_repository.find_by_user_id(user.id)
    if not profile:
        raise NotFoundError(
            "No FPO profile found for this account. Complete your FPO profile first."
        )
    return profile


def is_admin(user):
    return user is not None and user.role == ADMIN
