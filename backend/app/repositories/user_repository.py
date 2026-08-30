"""Accounts and the three profile tables hanging off them."""
from app.config import db
from app.models import row_to_dict
from app.models.buyer_profile import BuyerProfile
from app.models.farmer_profile import FarmerProfile
from app.models.fpo_profile import FpoProfile
from app.models.user import User
from app.repositories import BaseRepository, Filter, utcnow


class UserRepository(BaseRepository):
    table = "users"
    model = User
    sortable_columns = ("id", "name", "created_at")

    def find_by_phone(self, phone):
        return self.find_one_by("phone", phone)

    def find_by_email(self, email):
        return self.find_one_by("email", email)

    def phone_taken(self, phone, exclude_id=None):
        return self.exists("phone", phone, exclude_id)

    def email_taken(self, email, exclude_id=None):
        if not email:
            return False
        return self.exists("email", email, exclude_id)

    def list_by_role(self, role, limit=None, offset=None):
        filters = Filter().eq("role", role).eq("is_active", 1)
        return self.find_where(filters, limit=limit, offset=offset)


class FarmerProfileRepository(BaseRepository):
    table = "farmer_profiles"
    model = FarmerProfile

    def find_by_user_id(self, user_id):
        return self.find_one_by("user_id", user_id)

    def upsert(self, user_id, data):
        """Create the profile on first save, update it on every save after."""
        existing = self.find_by_user_id(user_id)
        if existing:
            self.update(existing.id, data)
            return self.find_by_id(existing.id)
        payload = dict(data)
        payload["user_id"] = user_id
        new_id = self.insert(payload)
        return self.find_by_id(new_id)

    def list_by_fpo(self, fpo_id):
        return self.find_where(Filter().eq("fpo_id", fpo_id))

    def with_user(self, farmer_id):
        row = db.query_one(
            """
            SELECT f.*, u.name AS farmer_name, u.phone AS farmer_phone
            FROM farmer_profiles f
            JOIN users u ON u.id = f.user_id
            WHERE f.id = ?
            """,
            (farmer_id,),
        )
        return row_to_dict(row)


class BuyerProfileRepository(BaseRepository):
    table = "buyer_profiles"
    model = BuyerProfile
    sortable_columns = ("id", "business_name", "trust_score", "created_at")
    default_order = "trust_score DESC, id DESC"

    def find_by_user_id(self, user_id):
        return self.find_one_by("user_id", user_id)

    def upsert(self, user_id, data):
        existing = self.find_by_user_id(user_id)
        if existing:
            self.update(existing.id, data)
            return self.find_by_id(existing.id)
        payload = dict(data)
        payload["user_id"] = user_id
        new_id = self.insert(payload)
        return self.find_by_id(new_id)

    def search(self, buyer_type=None, verification_status=None, district=None,
               query=None, page=1, page_size=20, order_by=None):
        filters = Filter()
        filters.eq("buyer_type", buyer_type)
        filters.eq("verification_status", verification_status)
        filters.eq("district", district)
        filters.like("business_name", query)
        total = self.count_where(filters)
        rows = self.find_where(
            filters, order_by=order_by, limit=page_size, offset=(page - 1) * page_size
        )
        return rows, total

    def profile_with_contact(self, buyer_id):
        """Buyer row plus the contact details from the linked account."""
        row = db.query_one(
            """
            SELECT b.*, u.name AS contact_name, u.phone AS contact_phone, u.email AS contact_email
            FROM buyer_profiles b
            JOIN users u ON u.id = b.user_id
            WHERE b.id = ?
            """,
            (buyer_id,),
        )
        return row_to_dict(row)

    def refresh_transaction_counters(self, buyer_id):
        """Recount deals from the transactions table rather than trusting a running total."""
        row = db.query_one(
            """
            SELECT COUNT(*) AS total,
                   SUM(CASE WHEN status = 'COMPLETED' THEN 1 ELSE 0 END) AS completed
            FROM transactions WHERE buyer_id = ?
            """,
            (buyer_id,),
        )
        total = int((row or {}).get("total") or 0)
        completed = int((row or {}).get("completed") or 0)
        self.update(buyer_id, {"total_transactions": total, "completed_transactions": completed})
        return total, completed

    def set_verification(self, buyer_id, status, notes=None):
        return self.update(
            buyer_id,
            {
                "verification_status": status,
                "verification_notes": notes,
                "verified_at": utcnow(),
            },
        )


class FpoProfileRepository(BaseRepository):
    table = "fpo_profiles"
    model = FpoProfile
    sortable_columns = ("id", "fpo_name", "member_count", "created_at")

    def find_by_user_id(self, user_id):
        return self.find_one_by("user_id", user_id)

    def upsert(self, user_id, data):
        existing = self.find_by_user_id(user_id)
        if existing:
            self.update(existing.id, data)
            return self.find_by_id(existing.id)
        payload = dict(data)
        payload["user_id"] = user_id
        new_id = self.insert(payload)
        return self.find_by_id(new_id)

    def recount_members(self, fpo_id):
        count = db.query_scalar(
            "SELECT COUNT(*) AS c FROM fpo_members WHERE fpo_id = ? AND status = 'ACTIVE'",
            (fpo_id,),
            0,
        )
        self.update(fpo_id, {"member_count": int(count or 0)})
        return int(count or 0)


user_repository = UserRepository()
farmer_profile_repository = FarmerProfileRepository()
buyer_profile_repository = BuyerProfileRepository()
fpo_profile_repository = FpoProfileRepository()
