"""Repositories for transporter and vehicle records."""
from app.config import db
from app.models import row_to_dict
from app.models.transporter import Transporter
from app.models.vehicle import Vehicle
from app.repositories import BaseRepository, Filter


class TransporterRepository(BaseRepository):
    table = "transporters"
    model = Transporter
    sortable_columns = (
        "id",
        "business_name",
        "rating",
        "reliability_score",
        "total_trips",
        "completed_trips",
    )
    default_order = "reliability_score DESC, id DESC"

    def find_by_user_id(self, user_id):
        return self.find_one_by("user_id", user_id)

    def search(self, district=None, available_only=True,
               verification_status=None, query=None,
               page=1, page_size=20):
        filters = Filter()
        filters.eq("district", district)
        filters.eq("verification_status", verification_status)
        filters.eq("is_available", 1 if available_only else None)
        filters.like("business_name", query)

        total = self.count_where(filters)
        rows = self.find_where(
            filters,
            limit=page_size,
            offset=(page - 1) * page_size,
        )
        return rows, total

    def refresh_score(self, transporter_id):
        row = db.query_one(
            """
            SELECT
                t.id,
                t.user_id,
                t.verification_status,
                COUNT(lr.id) AS total_trips,
                SUM(
                    CASE
                        WHEN lr.status = 'DELIVERED' THEN 1
                        ELSE 0
                    END
                ) AS completed_trips,
                COALESCE(
                    (
                        SELECT AVG(r.score)
                        FROM ratings r
                        WHERE r.rated_user_id = t.user_id
                    ),
                    0
                ) AS avg_rating
            FROM transporters t
            LEFT JOIN logistics_requests lr
                ON lr.transporter_id = t.id
            WHERE t.id = ?
            GROUP BY
                t.id,
                t.user_id,
                t.verification_status
            """,
            (transporter_id,),
        )

        if not row:
            return None

        total_trips = int(row.get("total_trips") or 0)
        completed_trips = int(row.get("completed_trips") or 0)
        avg_rating = float(row.get("avg_rating") or 0)

        rating_component = min(avg_rating / 5.0, 1.0) * 100
        completion_component = (
            completed_trips / total_trips * 100
            if total_trips
            else 0
        )
        verification_component = (
            100
            if row.get("verification_status") == "VERIFIED"
            else 0
        )

        reliability_score = (
            0.45 * rating_component
            + 0.40 * completion_component
            + 0.15 * verification_component
        )

        self.update(
            transporter_id,
            {
                "total_trips": total_trips,
                "completed_trips": completed_trips,
                "rating": round(avg_rating, 2),
                "reliability_score": round(reliability_score, 2),
            },
        )

        return self.find_by_id(transporter_id)


class VehicleRepository(BaseRepository):
    table = "vehicles"
    model = Vehicle
    sortable_columns = (
        "id",
        "vehicle_type",
        "vehicle_number",
        "capacity_tonnes",
        "rate_per_km",
    )
    default_order = "capacity_tonnes ASC, id ASC"

    def search_available(self, vehicle_type=None,
                         min_capacity=None, transporter_id=None):
        filters = Filter()
        filters.eq("vehicle_type", vehicle_type)
        filters.eq("transporter_id", transporter_id)
        filters.eq("is_available", 1)

        rows = self.find_where(filters)

        if min_capacity is not None:
            rows = [
                vehicle for vehicle in rows
                if vehicle.capacity_tonnes >= min_capacity
            ]

        return rows

    def detail_with_transporter(self, vehicle_id):
        row = db.query_one(
            """
            SELECT
                v.*,
                t.business_name AS transporter_name,
                t.rating AS transporter_rating,
                t.reliability_score AS transporter_reliability_score
            FROM vehicles v
            JOIN transporters t
                ON t.id = v.transporter_id
            WHERE v.id = ?
            """,
            (vehicle_id,),
        )
        return row_to_dict(row)


transporter_repository = TransporterRepository()
vehicle_repository = VehicleRepository()