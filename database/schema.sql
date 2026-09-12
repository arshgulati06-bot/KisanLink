-- KisanLink — Core Application Schema
-- SIH26132: Market Linkages & Price Discovery for Farmers
--
-- Designed to run on both MySQL (production) and SQLite (dev/test/demo).
-- The Python db.py layer translates MySQL-specific syntax to SQLite.
--
-- Historical mandi price data is NOT stored here. It comes from the
-- CSV files in ml/data/ and is handled by the Chronos ML pipeline.
-- This schema covers USER and APPLICATION state only.
-- ===========================================================================

-- ===========================================================================
-- 1. IDENTITY
-- ===========================================================================

-- Every person on the platform — farmers, buyers, FPOs, admins.
-- The 'role' column determines which dashboard they reach after login.
CREATE TABLE IF NOT EXISTS users (
    id            INT AUTO_INCREMENT PRIMARY KEY,
    name          VARCHAR(120)  NOT NULL,
    username      VARCHAR(80)   UNIQUE,
    phone         VARCHAR(15),
    email         VARCHAR(150),
    password_hash VARCHAR(255)  NOT NULL,
    -- FARMER | FPO | BUYER | ADMIN
    role          VARCHAR(20)   NOT NULL,
    language      VARCHAR(10)   NOT NULL DEFAULT 'en',
    is_active     TINYINT(1)    NOT NULL DEFAULT 1,
    created_at    DATETIME      DEFAULT CURRENT_TIMESTAMP,
    updated_at    DATETIME      DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS farmer_profiles (
    id               INT AUTO_INCREMENT PRIMARY KEY,
    user_id          INT          NOT NULL UNIQUE,
    village          VARCHAR(120),
    district         VARCHAR(120),
    state            VARCHAR(120) DEFAULT 'Maharashtra',
    pincode          VARCHAR(10),
    land_size_acres  DOUBLE,
    primary_crops    VARCHAR(255),
    created_at       DATETIME     DEFAULT CURRENT_TIMESTAMP,
    updated_at       DATETIME     DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);

-- Buyers: processors, institutional buyers, aggregators, traders.
CREATE TABLE IF NOT EXISTS buyer_profiles (
    id                  INT AUTO_INCREMENT PRIMARY KEY,
    user_id             INT          NOT NULL UNIQUE,
    business_name       VARCHAR(180) NOT NULL,
    -- PROCESSOR | INSTITUTIONAL | AGGREGATOR | TRADER | EXPORTER | OTHER
    buyer_type          VARCHAR(30)  NOT NULL DEFAULT 'TRADER',
    gst_number          VARCHAR(20),
    address             VARCHAR(255),
    district            VARCHAR(120),
    state               VARCHAR(120) DEFAULT 'Maharashtra',
    -- UNVERIFIED | DOCUMENTS_SUBMITTED | PLATFORM_REVIEWED | REJECTED
    -- Note: verification_status is a PLATFORM status only.
    verification_status VARCHAR(30)  NOT NULL DEFAULT 'UNVERIFIED',
    trust_score         DOUBLE       NOT NULL DEFAULT 40.0,
    created_at          DATETIME     DEFAULT CURRENT_TIMESTAMP,
    updated_at          DATETIME     DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);

-- ===========================================================================
-- 2. SALE LOTS (created by farmers/FPOs)
-- ===========================================================================

CREATE TABLE IF NOT EXISTS lots (
    id                   INT AUTO_INCREMENT PRIMARY KEY,
    farmer_user_id       INT          NOT NULL,
    commodity            VARCHAR(120) NOT NULL,
    variety              VARCHAR(120),
    -- Grade A | Grade B | Grade C
    grade                VARCHAR(20)  NOT NULL DEFAULT 'Grade A',
    quantity_qtl         DOUBLE       NOT NULL,
    -- AVAILABLE | RESERVED | SOLD | CANCELLED | EXPIRED
    status               VARCHAR(20)  NOT NULL DEFAULT 'AVAILABLE',
    expected_price       DOUBLE,
    district             VARCHAR(120),
    state                VARCHAR(120) DEFAULT 'Maharashtra',
    market               VARCHAR(180),
    harvest_date         DATE,
    -- Filename of the farmer's crop photo, served via /api/lots/<id>/image.
    image_file           VARCHAR(120),
    -- True when the lot originated from a Chronos forecast
    has_forecast         TINYINT(1)   NOT NULL DEFAULT 0,
    forecast_sale_day    INT,
    forecast_price_p50   DOUBLE,
    notes                VARCHAR(500),
    created_at           DATETIME     DEFAULT CURRENT_TIMESTAMP,
    updated_at           DATETIME     DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (farmer_user_id) REFERENCES users(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_lots_farmer ON lots (farmer_user_id, status);
CREATE INDEX IF NOT EXISTS idx_lots_commodity ON lots (commodity, status);

-- ===========================================================================
-- 3. BUYER DEMANDS (declared by buyers)
-- ===========================================================================

CREATE TABLE IF NOT EXISTS buyer_requirements (
    id                INT AUTO_INCREMENT PRIMARY KEY,
    buyer_user_id     INT          NOT NULL,
    commodity         VARCHAR(120) NOT NULL,
    grade             VARCHAR(20)  NOT NULL DEFAULT 'Grade A',
    quantity_qtl_min  DOUBLE       NOT NULL DEFAULT 10,
    quantity_qtl_max  DOUBLE,
    price_per_qtl     DOUBLE,
    preferred_state   VARCHAR(120),
    preferred_district VARCHAR(120),
    -- OPEN | PAUSED | FULFILLED | CANCELLED | EXPIRED
    status            VARCHAR(20)  NOT NULL DEFAULT 'OPEN',
    valid_until       DATE,
    notes             VARCHAR(500),
    created_at        DATETIME     DEFAULT CURRENT_TIMESTAMP,
    updated_at        DATETIME     DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (buyer_user_id) REFERENCES users(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_req_buyer ON buyer_requirements (buyer_user_id, status);
CREATE INDEX IF NOT EXISTS idx_req_commodity ON buyer_requirements (commodity, status);

-- ===========================================================================
-- 4. OFFERS (sent by buyers to farmers)
-- ===========================================================================

CREATE TABLE IF NOT EXISTS offers (
    id                INT AUTO_INCREMENT PRIMARY KEY,
    lot_id            INT          NOT NULL,
    requirement_id    INT,
    buyer_user_id     INT          NOT NULL,
    seller_user_id    INT          NOT NULL,
    price_per_qtl     DOUBLE       NOT NULL,
    quantity_qtl      DOUBLE       NOT NULL,
    -- PENDING | ACCEPTED | COUNTERED | REJECTED | WITHDRAWN | EXPIRED
    status            VARCHAR(20)  NOT NULL DEFAULT 'PENDING',
    -- BUYER | FARMER
    initiated_by      VARCHAR(10)  NOT NULL DEFAULT 'BUYER',
    message           VARCHAR(500),
    responded_at      DATETIME,
    created_at        DATETIME     DEFAULT CURRENT_TIMESTAMP,
    updated_at        DATETIME     DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (lot_id)           REFERENCES lots(id)                ON DELETE CASCADE,
    FOREIGN KEY (requirement_id)   REFERENCES buyer_requirements(id)  ON DELETE SET NULL,
    FOREIGN KEY (buyer_user_id)    REFERENCES users(id)               ON DELETE CASCADE,
    FOREIGN KEY (seller_user_id)   REFERENCES users(id)               ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_offers_lot ON offers (lot_id, status);
CREATE INDEX IF NOT EXISTS idx_offers_buyer ON offers (buyer_user_id, status);

-- ===========================================================================
-- 5. TRANSACTIONS (accepted deals)
-- ===========================================================================

CREATE TABLE IF NOT EXISTS transactions (
    id                  INT AUTO_INCREMENT PRIMARY KEY,
    transaction_code    VARCHAR(30)  NOT NULL UNIQUE,
    offer_id            INT          NOT NULL UNIQUE,
    lot_id              INT          NOT NULL,
    buyer_user_id       INT          NOT NULL,
    seller_user_id      INT          NOT NULL,
    commodity           VARCHAR(120) NOT NULL,
    quantity_qtl        DOUBLE       NOT NULL,
    price_per_qtl       DOUBLE       NOT NULL,
    gross_amount        DOUBLE       NOT NULL,
    transport_cost      DOUBLE       NOT NULL DEFAULT 0,
    net_amount          DOUBLE       NOT NULL,
    -- ACCEPTED | IN_TRANSIT | DELIVERED | PAYMENT_PENDING | PAID
    -- | COMPLETED | CANCELLED | DISPUTED
    status              VARCHAR(30)  NOT NULL DEFAULT 'ACCEPTED',
    expected_delivery_date DATE,
    completed_at        DATETIME,
    created_at          DATETIME     DEFAULT CURRENT_TIMESTAMP,
    updated_at          DATETIME     DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (offer_id)        REFERENCES offers(id)  ON DELETE CASCADE,
    FOREIGN KEY (lot_id)          REFERENCES lots(id)    ON DELETE CASCADE,
    FOREIGN KEY (buyer_user_id)   REFERENCES users(id)   ON DELETE CASCADE,
    FOREIGN KEY (seller_user_id)  REFERENCES users(id)   ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_tx_parties ON transactions (seller_user_id, buyer_user_id, status);
