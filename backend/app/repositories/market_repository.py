"""Markets, observed prices/arrivals, and cached forecasts."""
from app.config import db
from app.models import row_to_dict, rows_to_dicts
from app.models.market import Market
from app.models.market_data import MarketData
from app.models.price_forecast import PriceForecast
from app.repositories import BaseRepository, Filter


class MarketRepository(BaseRepository):
    table = "markets"
    model = Market
    sortable_columns = ("id", "name", "district")
    default_order = "name ASC"
    has_updated_at = False

    def search(self, query=None, district=None, state=None, market_type=None,
               active_only=True, page=1, page_size=50, order_by=None):
        filters = Filter()
        filters.like("name", query)
        filters.eq("district", district)
        filters.eq("state", state)
        filters.eq("market_type", market_type)
        if active_only:
            filters.eq("is_active", 1)
        total = self.count_where(filters)
        rows = self.find_where(
            filters, order_by=order_by, limit=page_size, offset=(page - 1) * page_size
        )
        return rows, total

    def with_coordinates(self, state=None):
        """Only markets we can actually measure a distance to."""
        filters = Filter().add("latitude IS NOT NULL").add("longitude IS NOT NULL")
        filters.eq("is_active", 1)
        filters.eq("state", state)
        return self.find_where(filters)

    def markets_trading_crop(self, crop_id, since_date=None, limit=100):
        """
        Markets that have actually reported a price for this crop.

        Sorted by how recently they reported, because a market that stopped
        publishing is not a live option for the farmer.
        """
        sql = """
            SELECT m.*, MAX(md.price_date) AS last_price_date, COUNT(md.id) AS observation_count
            FROM markets m
            JOIN market_data md ON md.market_id = m.id
            WHERE md.crop_id = ? AND m.is_active = 1
        """
        params = [crop_id]
        if since_date:
            sql += " AND md.price_date >= ?"
            params.append(since_date)
        sql += " GROUP BY m.id ORDER BY last_price_date DESC LIMIT ?"
        params.append(int(limit))
        return rows_to_dicts(db.query_all(sql, params))


class MarketDataRepository(BaseRepository):
    table = "market_data"
    model = MarketData
    sortable_columns = ("id", "price_date", "modal_price")
    default_order = "price_date DESC, id DESC"
    has_updated_at = False

    def latest_for(self, market_id, crop_id, variety=None):
        sql = "SELECT * FROM market_data WHERE market_id = ? AND crop_id = ?"
        params = [market_id, crop_id]
        if variety:
            sql += " AND variety = ?"
            params.append(variety)
        sql += " ORDER BY price_date DESC LIMIT 1"
        row = db.query_one(sql, params)
        return self.model.from_row(row) if row else None

    def history(self, market_id, crop_id, days=90, variety=None):
        """Oldest-first series, which is what the forecasting model expects."""
        sql = """
            SELECT * FROM market_data
            WHERE market_id = ? AND crop_id = ?
        """
        params = [market_id, crop_id]
        if variety:
            sql += " AND variety = ?"
            params.append(variety)
        sql += " ORDER BY price_date DESC LIMIT ?"
        params.append(int(days))
        rows = db.query_all(sql, params)
        return list(reversed(self.model.from_rows(rows)))

    def crop_history_all_markets(self, crop_id, days=90):
        """Daily average across every market - used when one market is too sparse."""
        sql = """
            SELECT price_date,
                   AVG(modal_price) AS modal_price,
                   SUM(arrival_quantity) AS arrival_quantity,
                   COUNT(*) AS market_count
            FROM market_data
            WHERE crop_id = ?
            GROUP BY price_date
            ORDER BY price_date DESC
            LIMIT ?
        """
        rows = db.query_all(sql, (crop_id, int(days)))
        return list(reversed(rows_to_dicts(rows)))

    def latest_prices_for_crop(self, crop_id, district=None, state=None, limit=50):
        """
        The newest observation per market for one crop.

        The correlated subquery picks each market's own latest date, so a
        market that reported yesterday is not hidden by one that reported today.
        """
        sql = """
            SELECT md.*, m.name AS market_name, m.district AS market_district,
                   m.state AS market_state, m.market_type,
                   m.latitude AS market_latitude, m.longitude AS market_longitude,
                   c.name AS crop_name
            FROM market_data md
            JOIN markets m ON m.id = md.market_id
            JOIN crops c ON c.id = md.crop_id
            WHERE md.crop_id = ?
              AND md.price_date = (
                    SELECT MAX(md2.price_date) FROM market_data md2
                    WHERE md2.market_id = md.market_id AND md2.crop_id = md.crop_id
              )
        """
        params = [crop_id]
        if district:
            sql += " AND m.district = ?"
            params.append(district)
        if state:
            sql += " AND m.state = ?"
            params.append(state)
        sql += " ORDER BY md.modal_price DESC LIMIT ?"
        params.append(int(limit))
        return rows_to_dicts(db.query_all(sql, params))

    def benchmark_price(self, crop_id, district=None, days=7):
        """
        A single reference price for the crop, used to judge whether an offer
        is good. Averaged over recent days so one odd day cannot skew it.
        """
        sql = """
            SELECT AVG(md.modal_price) AS avg_price, COUNT(*) AS observations,
                   MAX(md.price_date) AS latest_date
            FROM market_data md
            JOIN markets m ON m.id = md.market_id
            WHERE md.crop_id = ?
              AND md.price_date >= (
                    SELECT MAX(price_date) FROM market_data WHERE crop_id = ?
              )
        """
        params = [crop_id, crop_id]
        if district:
            sql += " AND m.district = ?"
            params.append(district)
        row = db.query_one(sql, params)
        result = row_to_dict(row) or {}
        if not result.get("avg_price"):
            # Nothing for the latest date in that district - widen to the crop.
            row = db.query_one(
                """
                SELECT AVG(modal_price) AS avg_price, COUNT(*) AS observations,
                       MAX(price_date) AS latest_date
                FROM market_data WHERE crop_id = ?
                """,
                (crop_id,),
            )
            result = row_to_dict(row) or {}
        return result

    def upsert_observation(self, data):
        """
        Insert a price observation, or refresh it if that day was already loaded.

        Re-running an ingest should correct data, not duplicate it.
        """
        existing = db.query_one(
            """
            SELECT id FROM market_data
            WHERE market_id = ? AND crop_id = ? AND variety = ? AND price_date = ?
            """,
            (
                data["market_id"],
                data["crop_id"],
                data.get("variety") or "General",
                data["price_date"],
            ),
        )
        if existing:
            self.update(existing["id"], data)
            return existing["id"], False
        return self.insert(data), True

    def arrivals_series(self, market_id, crop_id, days=30):
        rows = db.query_all(
            """
            SELECT price_date, arrival_quantity, arrival_unit, modal_price
            FROM market_data
            WHERE market_id = ? AND crop_id = ?
            ORDER BY price_date DESC LIMIT ?
            """,
            (market_id, crop_id, int(days)),
        )
        return list(reversed(rows_to_dicts(rows)))


class PriceForecastRepository(BaseRepository):
    table = "price_forecasts"
    model = PriceForecast
    sortable_columns = ("id", "generated_at", "forecast_date")
    default_order = "generated_at DESC"
    has_updated_at = False

    def latest_for(self, market_id, crop_id, horizon_days):
        row = db.query_one(
            """
            SELECT * FROM price_forecasts
            WHERE market_id = ? AND crop_id = ? AND horizon_days = ?
            ORDER BY generated_at DESC LIMIT 1
            """,
            (market_id, crop_id, horizon_days),
        )
        return self.model.from_row(row) if row else None


market_repository = MarketRepository()
market_data_repository = MarketDataRepository()
price_forecast_repository = PriceForecastRepository()
