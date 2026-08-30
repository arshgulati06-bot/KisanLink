-- ===========================================================================
-- KisanLink - MySQL schema
-- SIH26132: Strengthening market linkages and price discovery for farmers
--
-- Load it directly with:   mysql -u root -p < database/schema.sql
-- or from the app with:    python -m scripts.init_db   (see backend/README.md)
--
-- Written in a portable SQL subset so the same file also drives the SQLite
-- fallback used by the test suite (see app/config/db.py).
-- ===========================================================================

CREATE DATABASE IF NOT EXISTS kisanlink_db;
USE kisanlink_db;

-- ---------------------------------------------------------------------------
-- 1. IDENTITY
-- ---------------------------------------------------------------------------

-- Every human on the platform. role decides which dashboard they land on.
CREATE TABLE IF NOT EXISTS users (
    id INT AUTO_INCREMENT PRIMARY KEY,
    name VARCHAR(120) NOT NULL,
    phone VARCHAR(15) NOT NULL UNIQUE,
    email VARCHAR(150),
    password_hash VARCHAR(255) NOT NULL,
    -- FARMER | FPO | BUYER | ADMIN
    role VARCHAR(20) NOT NULL,
    language VARCHAR(10) NOT NULL DEFAULT 'en',
    is_active TINYINT(1) NOT NULL DEFAULT 1,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS farmer_profiles (
    id INT AUTO_INCREMENT PRIMARY KEY,
    user_id INT NOT NULL UNIQUE,
    village VARCHAR(120),
    district VARCHAR(120),
    state VARCHAR(120) DEFAULT 'Maharashtra',
    pincode VARCHAR(10),
    latitude DECIMAL(10, 6),
    longitude DECIMAL(10, 6),
    land_size_acres DECIMAL(10, 2),
    primary_crops VARCHAR(255),
    fpo_id INT,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);

-- Buyers include processors, institutional buyers, aggregators and traders.
-- verification_status is a PLATFORM status only - it is never a claim of
-- government KYC/GST verification.
CREATE TABLE IF NOT EXISTS buyer_profiles (
    id INT AUTO_INCREMENT PRIMARY KEY,
    user_id INT NOT NULL UNIQUE,
    business_name VARCHAR(180) NOT NULL,
    -- PROCESSOR | INSTITUTIONAL | AGGREGATOR | TRADER | EXPORTER | OTHER
    buyer_type VARCHAR(30) NOT NULL DEFAULT 'TRADER',
    gst_number VARCHAR(20),
    license_number VARCHAR(60),
    address VARCHAR(255),
    district VARCHAR(120),
    state VARCHAR(120) DEFAULT 'Maharashtra',
    latitude DECIMAL(10, 6),
    longitude DECIMAL(10, 6),
    -- UNVERIFIED | DOCUMENTS_SUBMITTED | PLATFORM_REVIEWED | REJECTED
    verification_status VARCHAR(30) NOT NULL DEFAULT 'UNVERIFIED',
    verification_notes VARCHAR(255),
    verified_at DATETIME,
    -- 0-100, recomputed by trust_service from ratings and payment history
    trust_score DECIMAL(5, 2) NOT NULL DEFAULT 40.00,
    total_transactions INT NOT NULL DEFAULT 0,
    completed_transactions INT NOT NULL DEFAULT 0,
    on_time_payment_rate DECIMAL(5, 2),
    is_seed_data TINYINT(1) NOT NULL DEFAULT 0,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS fpo_profiles (
    id INT AUTO_INCREMENT PRIMARY KEY,
    user_id INT NOT NULL UNIQUE,
    fpo_name VARCHAR(180) NOT NULL,
    registration_number VARCHAR(80),
    district VARCHAR(120),
    state VARCHAR(120) DEFAULT 'Maharashtra',
    latitude DECIMAL(10, 6),
    longitude DECIMAL(10, 6),
    contact_person VARCHAR(120),
    member_count INT NOT NULL DEFAULT 0,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);

-- Which farmers belong to which producer group.
CREATE TABLE IF NOT EXISTS fpo_members (
    id INT AUTO_INCREMENT PRIMARY KEY,
    fpo_id INT NOT NULL,
    farmer_id INT NOT NULL,
    -- MEMBER | BOARD_MEMBER | CHAIRPERSON
    member_role VARCHAR(30) NOT NULL DEFAULT 'MEMBER',
    -- PENDING | ACTIVE | INACTIVE | REMOVED
    status VARCHAR(20) NOT NULL DEFAULT 'ACTIVE',
    joined_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (fpo_id, farmer_id),
    FOREIGN KEY (fpo_id) REFERENCES fpo_profiles(id) ON DELETE CASCADE,
    FOREIGN KEY (farmer_id) REFERENCES farmer_profiles(id) ON DELETE CASCADE
);

-- ---------------------------------------------------------------------------
-- 2. REFERENCE DATA
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS crops (
    id INT AUTO_INCREMENT PRIMARY KEY,
    name VARCHAR(120) NOT NULL UNIQUE,
    local_name VARCHAR(120),
    -- VEGETABLE | FRUIT | CEREAL | PULSE | OILSEED | SPICE | FIBRE | OTHER
    category VARCHAR(40) NOT NULL DEFAULT 'OTHER',
    default_unit VARCHAR(20) NOT NULL DEFAULT 'QUINTAL',
    -- Perishability drives how aggressively we suggest selling now.
    shelf_life_days INT,
    is_perishable TINYINT(1) NOT NULL DEFAULT 0,
    grade_scale VARCHAR(40) NOT NULL DEFAULT 'A,B,C',
    is_active TINYINT(1) NOT NULL DEFAULT 1,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS markets (
    id INT AUTO_INCREMENT PRIMARY KEY,
    name VARCHAR(180) NOT NULL,
    market_code VARCHAR(60),
    -- APMC | PRIVATE | ENAM | FARMER_MARKET | OTHER
    market_type VARCHAR(30) NOT NULL DEFAULT 'APMC',
    district VARCHAR(120),
    state VARCHAR(120) DEFAULT 'Maharashtra',
    latitude DECIMAL(10, 6),
    longitude DECIMAL(10, 6),
    address VARCHAR(255),
    contact_phone VARCHAR(20),
    is_active TINYINT(1) NOT NULL DEFAULT 1,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (name, district, state)
);

-- ---------------------------------------------------------------------------
-- 3. MARKET INTELLIGENCE
-- ---------------------------------------------------------------------------

-- One row per market + crop + variety + day.
-- source records where the number came from so the UI can label it honestly.
CREATE TABLE IF NOT EXISTS market_data (
    id INT AUTO_INCREMENT PRIMARY KEY,
    market_id INT NOT NULL,
    crop_id INT NOT NULL,
    variety VARCHAR(120) NOT NULL DEFAULT 'General',
    price_date DATE NOT NULL,
    min_price DECIMAL(12, 2),
    max_price DECIMAL(12, 2),
    modal_price DECIMAL(12, 2) NOT NULL,
    -- Arrival volume is explicitly called for by the problem statement.
    -- NULL means "not published by the source", never zero.
    arrival_quantity DECIMAL(14, 2),
    arrival_unit VARCHAR(20) DEFAULT 'TONNE',
    price_unit VARCHAR(20) NOT NULL DEFAULT 'QUINTAL',
    -- AGMARKNET | DATA_GOV_IN | ENAM | MANUAL | SEED_DEMO
    source VARCHAR(40) NOT NULL DEFAULT 'MANUAL',
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (market_id, crop_id, variety, price_date),
    FOREIGN KEY (market_id) REFERENCES markets(id) ON DELETE CASCADE,
    FOREIGN KEY (crop_id) REFERENCES crops(id) ON DELETE CASCADE
);

CREATE INDEX idx_market_data_lookup ON market_data (crop_id, market_id, price_date);
CREATE INDEX idx_market_data_date ON market_data (price_date);

-- Cached output of the forecasting model. Kept so a recommendation can be
-- reproduced later exactly as the farmer saw it.
CREATE TABLE IF NOT EXISTS price_forecasts (
    id INT AUTO_INCREMENT PRIMARY KEY,
    market_id INT NOT NULL,
    crop_id INT NOT NULL,
    generated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    forecast_date DATE NOT NULL,
    horizon_days INT NOT NULL,
    forecast_price DECIMAL(12, 2) NOT NULL,
    lower_bound DECIMAL(12, 2),
    upper_bound DECIMAL(12, 2),
    -- LOW | MEDIUM | HIGH
    confidence VARCHAR(10) NOT NULL DEFAULT 'LOW',
    -- LINEAR_TREND | MOVING_AVERAGE | INSUFFICIENT_DATA
    method VARCHAR(40) NOT NULL,
    data_points INT NOT NULL DEFAULT 0,
    notes VARCHAR(255),
    FOREIGN KEY (market_id) REFERENCES markets(id) ON DELETE CASCADE,
    FOREIGN KEY (crop_id) REFERENCES crops(id) ON DELETE CASCADE
);

-- ---------------------------------------------------------------------------
-- 4. SUPPLY SIDE - LOTS
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS lots (
    id INT AUTO_INCREMENT PRIMARY KEY,
    lot_code VARCHAR(30) NOT NULL UNIQUE,
    seller_user_id INT NOT NULL,
    -- FARMER | FPO  (aggregation-ready without a separate application)
    seller_type VARCHAR(10) NOT NULL DEFAULT 'FARMER',
    fpo_id INT,
    crop_id INT NOT NULL,
    variety VARCHAR(120),
    quantity DECIMAL(14, 2) NOT NULL,
    unit VARCHAR(20) NOT NULL DEFAULT 'QUINTAL',
    -- Self-declared grade for the prototype: A | B | C
    grade VARCHAR(5) NOT NULL DEFAULT 'B',
    moisture_percent DECIMAL(5, 2),
    expected_price DECIMAL(12, 2),
    harvest_date DATE,
    available_from DATE,
    available_until DATE,
    village VARCHAR(120),
    district VARCHAR(120),
    state VARCHAR(120) DEFAULT 'Maharashtra',
    latitude DECIMAL(10, 6),
    longitude DECIMAL(10, 6),
    -- DRAFT | LISTED | OFFER_RECEIVED | RESERVED | SOLD | EXPIRED | CANCELLED
    status VARCHAR(20) NOT NULL DEFAULT 'DRAFT',
    is_aggregated TINYINT(1) NOT NULL DEFAULT 0,
    notes VARCHAR(500),
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (seller_user_id) REFERENCES users(id) ON DELETE CASCADE,
    FOREIGN KEY (crop_id) REFERENCES crops(id),
    FOREIGN KEY (fpo_id) REFERENCES fpo_profiles(id) ON DELETE SET NULL
);

CREATE INDEX idx_lots_status ON lots (status, crop_id);
CREATE INDEX idx_lots_seller ON lots (seller_user_id);

-- Which member farmer contributed how much to an aggregated FPO lot.
CREATE TABLE IF NOT EXISTS lot_contributions (
    id INT AUTO_INCREMENT PRIMARY KEY,
    lot_id INT NOT NULL,
    farmer_id INT NOT NULL,
    quantity DECIMAL(14, 2) NOT NULL,
    grade VARCHAR(5) NOT NULL DEFAULT 'B',
    -- Filled once the transaction is paid, so payouts stay traceable.
    payout_amount DECIMAL(14, 2),
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (lot_id) REFERENCES lots(id) ON DELETE CASCADE,
    FOREIGN KEY (farmer_id) REFERENCES farmer_profiles(id) ON DELETE CASCADE
);

-- ---------------------------------------------------------------------------
-- 5. DEMAND SIDE - BUYER REQUIREMENTS
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS buyer_requirements (
    id INT AUTO_INCREMENT PRIMARY KEY,
    buyer_id INT NOT NULL,
    crop_id INT NOT NULL,
    variety VARCHAR(120),
    required_quantity DECIMAL(14, 2) NOT NULL,
    fulfilled_quantity DECIMAL(14, 2) NOT NULL DEFAULT 0,
    unit VARCHAR(20) NOT NULL DEFAULT 'QUINTAL',
    min_grade VARCHAR(5) NOT NULL DEFAULT 'C',
    max_moisture_percent DECIMAL(5, 2),
    quality_notes VARCHAR(500),
    price_min DECIMAL(12, 2),
    price_max DECIMAL(12, 2),
    -- FARM_GATE | BUYER_PICKUP | DELIVERED_AT_BUYER
    delivery_mode VARCHAR(30) NOT NULL DEFAULT 'DELIVERED_AT_BUYER',
    delivery_district VARCHAR(120),
    delivery_state VARCHAR(120) DEFAULT 'Maharashtra',
    latitude DECIMAL(10, 6),
    longitude DECIMAL(10, 6),
    payment_terms_days INT NOT NULL DEFAULT 7,
    valid_from DATE,
    valid_until DATE,
    -- OPEN | PARTIALLY_FULFILLED | FULFILLED | CLOSED | EXPIRED
    status VARCHAR(25) NOT NULL DEFAULT 'OPEN',
    notes VARCHAR(500),
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (buyer_id) REFERENCES buyer_profiles(id) ON DELETE CASCADE,
    FOREIGN KEY (crop_id) REFERENCES crops(id)
);

CREATE INDEX idx_requirements_open ON buyer_requirements (status, crop_id);

-- ---------------------------------------------------------------------------
-- 6. RECOMMENDATIONS
-- ---------------------------------------------------------------------------

-- A stored snapshot of what the engine advised, including the full ranked
-- comparison and the reasons shown to the farmer.
CREATE TABLE IF NOT EXISTS recommendations (
    id INT AUTO_INCREMENT PRIMARY KEY,
    lot_id INT NOT NULL,
    generated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    -- BUYER | MARKET | OFFER
    recommended_option_type VARCHAR(20),
    recommended_option_id INT,
    recommended_label VARCHAR(180),
    estimated_net_realization DECIMAL(14, 2),
    -- SELL_NOW | CONSIDER_WAITING | MONITOR | INSUFFICIENT_DATA
    sale_window VARCHAR(30),
    sale_window_confidence VARCHAR(10),
    option_count INT NOT NULL DEFAULT 0,
    payload_json TEXT,
    FOREIGN KEY (lot_id) REFERENCES lots(id) ON DELETE CASCADE
);

-- ---------------------------------------------------------------------------
-- 7. OFFERS
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS offers (
    id INT AUTO_INCREMENT PRIMARY KEY,
    lot_id INT NOT NULL,
    requirement_id INT,
    buyer_id INT NOT NULL,
    seller_user_id INT NOT NULL,
    price_per_unit DECIMAL(12, 2) NOT NULL,
    quantity DECIMAL(14, 2) NOT NULL,
    unit VARCHAR(20) NOT NULL DEFAULT 'QUINTAL',
    delivery_mode VARCHAR(30) NOT NULL DEFAULT 'DELIVERED_AT_BUYER',
    -- BUYER | FARMER : decides who carries the transport cost in net realization
    transport_borne_by VARCHAR(10) NOT NULL DEFAULT 'FARMER',
    payment_terms_days INT NOT NULL DEFAULT 7,
    valid_until DATE,
    -- PENDING | ACCEPTED | REJECTED | WITHDRAWN | COUNTERED | EXPIRED
    status VARCHAR(20) NOT NULL DEFAULT 'PENDING',
    -- BUYER | FARMER : counter-offers let the farmer negotiate back
    initiated_by VARCHAR(10) NOT NULL DEFAULT 'BUYER',
    parent_offer_id INT,
    message VARCHAR(500),
    responded_at DATETIME,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (lot_id) REFERENCES lots(id) ON DELETE CASCADE,
    FOREIGN KEY (requirement_id) REFERENCES buyer_requirements(id) ON DELETE SET NULL,
    FOREIGN KEY (buyer_id) REFERENCES buyer_profiles(id) ON DELETE CASCADE,
    FOREIGN KEY (seller_user_id) REFERENCES users(id) ON DELETE CASCADE,
    FOREIGN KEY (parent_offer_id) REFERENCES offers(id) ON DELETE SET NULL
);

CREATE INDEX idx_offers_lot ON offers (lot_id, status);
CREATE INDEX idx_offers_buyer ON offers (buyer_id, status);

-- ---------------------------------------------------------------------------
-- 8. FULFILMENT - STORAGE, LOGISTICS, TRANSACTIONS, PAYMENTS
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS storage_facilities (
    id INT AUTO_INCREMENT PRIMARY KEY,
    name VARCHAR(180) NOT NULL,
    -- WAREHOUSE | COLD_STORAGE | FPO_GODOWN | WDRA_WAREHOUSE | OTHER
    facility_type VARCHAR(30) NOT NULL DEFAULT 'WAREHOUSE',
    operator_name VARCHAR(180),
    district VARCHAR(120),
    state VARCHAR(120) DEFAULT 'Maharashtra',
    address VARCHAR(255),
    latitude DECIMAL(10, 6),
    longitude DECIMAL(10, 6),
    capacity_tonnes DECIMAL(12, 2),
    available_capacity_tonnes DECIMAL(12, 2),
    cost_per_tonne_per_day DECIMAL(10, 2),
    has_cold_storage TINYINT(1) NOT NULL DEFAULT 0,
    -- Warehouse receipt financing is what actually relieves the liquidity
    -- pressure that forces distress selling.
    offers_warehouse_receipt TINYINT(1) NOT NULL DEFAULT 0,
    contact_phone VARCHAR(20),
    is_seed_data TINYINT(1) NOT NULL DEFAULT 0,
    is_active TINYINT(1) NOT NULL DEFAULT 1,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS transactions (
    id INT AUTO_INCREMENT PRIMARY KEY,
    transaction_code VARCHAR(30) NOT NULL UNIQUE,
    offer_id INT NOT NULL UNIQUE,
    lot_id INT NOT NULL,
    buyer_id INT NOT NULL,
    seller_user_id INT NOT NULL,
    crop_id INT NOT NULL,
    quantity DECIMAL(14, 2) NOT NULL,
    unit VARCHAR(20) NOT NULL DEFAULT 'QUINTAL',
    price_per_unit DECIMAL(12, 2) NOT NULL,
    -- Raw price and effective price are stored separately, on purpose.
    gross_amount DECIMAL(14, 2) NOT NULL,
    transport_cost DECIMAL(14, 2) NOT NULL DEFAULT 0,
    storage_cost DECIMAL(14, 2) NOT NULL DEFAULT 0,
    commission_cost DECIMAL(14, 2) NOT NULL DEFAULT 0,
    other_deductions DECIMAL(14, 2) NOT NULL DEFAULT 0,
    net_amount DECIMAL(14, 2) NOT NULL,
    -- OFFERED | ACCEPTED | LOGISTICS_PENDING | IN_TRANSIT | DELIVERED
    -- | PAYMENT_PENDING | PAID | COMPLETED | CANCELLED | DISPUTED
    status VARCHAR(30) NOT NULL DEFAULT 'ACCEPTED',
    expected_delivery_date DATE,
    delivered_at DATETIME,
    completed_at DATETIME,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (offer_id) REFERENCES offers(id) ON DELETE CASCADE,
    FOREIGN KEY (lot_id) REFERENCES lots(id) ON DELETE CASCADE,
    FOREIGN KEY (buyer_id) REFERENCES buyer_profiles(id) ON DELETE CASCADE,
    FOREIGN KEY (seller_user_id) REFERENCES users(id) ON DELETE CASCADE,
    FOREIGN KEY (crop_id) REFERENCES crops(id)
);

CREATE INDEX idx_transactions_parties ON transactions (seller_user_id, buyer_id, status);

-- Append-only audit trail: this is what makes the record transparent.
CREATE TABLE IF NOT EXISTS transaction_status_history (
    id INT AUTO_INCREMENT PRIMARY KEY,
    transaction_id INT NOT NULL,
    from_status VARCHAR(30),
    to_status VARCHAR(30) NOT NULL,
    changed_by_user_id INT,
    remarks VARCHAR(500),
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (transaction_id) REFERENCES transactions(id) ON DELETE CASCADE,
    FOREIGN KEY (changed_by_user_id) REFERENCES users(id) ON DELETE SET NULL
);

CREATE TABLE IF NOT EXISTS logistics_requests (
    id INT AUTO_INCREMENT PRIMARY KEY,
    transaction_id INT,
    lot_id INT,
    requested_by_user_id INT NOT NULL,
    pickup_address VARCHAR(255),
    pickup_district VARCHAR(120),
    pickup_latitude DECIMAL(10, 6),
    pickup_longitude DECIMAL(10, 6),
    drop_address VARCHAR(255),
    drop_district VARCHAR(120),
    drop_latitude DECIMAL(10, 6),
    drop_longitude DECIMAL(10, 6),
    distance_km DECIMAL(10, 2),
    -- TEMPO | PICKUP | TRUCK_9T | TRUCK_16T | TRACTOR_TROLLEY
    vehicle_type VARCHAR(30),
    quantity DECIMAL(14, 2),
    unit VARCHAR(20) DEFAULT 'QUINTAL',
    estimated_cost DECIMAL(12, 2),
    actual_cost DECIMAL(12, 2),
    scheduled_date DATE,
    -- REQUESTED | ASSIGNED | IN_TRANSIT | DELIVERED | CANCELLED
    status VARCHAR(20) NOT NULL DEFAULT 'REQUESTED',
    provider_name VARCHAR(180),
    provider_phone VARCHAR(20),
    notes VARCHAR(500),
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (transaction_id) REFERENCES transactions(id) ON DELETE CASCADE,
    FOREIGN KEY (lot_id) REFERENCES lots(id) ON DELETE SET NULL,
    FOREIGN KEY (requested_by_user_id) REFERENCES users(id) ON DELETE CASCADE
);

-- Payment tracking only. No payment gateway is integrated in this prototype.
CREATE TABLE IF NOT EXISTS payments (
    id INT AUTO_INCREMENT PRIMARY KEY,
    transaction_id INT NOT NULL,
    amount DECIMAL(14, 2) NOT NULL,
    -- UPI | BANK_TRANSFER | CASH | CHEQUE | OTHER
    mode VARCHAR(30) NOT NULL DEFAULT 'BANK_TRANSFER',
    reference_no VARCHAR(80),
    -- PENDING | PARTIAL | PAID | FAILED | REFUNDED
    status VARCHAR(20) NOT NULL DEFAULT 'PENDING',
    due_date DATE,
    paid_at DATETIME,
    recorded_by_user_id INT,
    remarks VARCHAR(500),
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (transaction_id) REFERENCES transactions(id) ON DELETE CASCADE,
    FOREIGN KEY (recorded_by_user_id) REFERENCES users(id) ON DELETE SET NULL
);

-- ---------------------------------------------------------------------------
-- 9. TRUST - RATINGS AND GRIEVANCES
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS ratings (
    id INT AUTO_INCREMENT PRIMARY KEY,
    transaction_id INT NOT NULL,
    rater_user_id INT NOT NULL,
    rated_user_id INT NOT NULL,
    score DECIMAL(3, 1) NOT NULL,
    payment_score DECIMAL(3, 1),
    quality_score DECIMAL(3, 1),
    punctuality_score DECIMAL(3, 1),
    comment VARCHAR(500),
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (transaction_id, rater_user_id),
    FOREIGN KEY (transaction_id) REFERENCES transactions(id) ON DELETE CASCADE,
    FOREIGN KEY (rater_user_id) REFERENCES users(id) ON DELETE CASCADE,
    FOREIGN KEY (rated_user_id) REFERENCES users(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS grievances (
    id INT AUTO_INCREMENT PRIMARY KEY,
    ticket_no VARCHAR(30) NOT NULL UNIQUE,
    transaction_id INT,
    raised_by_user_id INT NOT NULL,
    against_user_id INT,
    -- PAYMENT_DELAY | QUALITY_DISPUTE | QUANTITY_MISMATCH | DELIVERY_ISSUE
    -- | PRICE_DISPUTE | OTHER
    category VARCHAR(40) NOT NULL DEFAULT 'OTHER',
    subject VARCHAR(180) NOT NULL,
    description VARCHAR(2000) NOT NULL,
    -- OPEN | UNDER_REVIEW | RESOLVED | REJECTED | WITHDRAWN
    status VARCHAR(20) NOT NULL DEFAULT 'OPEN',
    resolution VARCHAR(2000),
    handled_by_user_id INT,
    resolved_at DATETIME,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (transaction_id) REFERENCES transactions(id) ON DELETE SET NULL,
    FOREIGN KEY (raised_by_user_id) REFERENCES users(id) ON DELETE CASCADE,
    FOREIGN KEY (against_user_id) REFERENCES users(id) ON DELETE SET NULL,
    FOREIGN KEY (handled_by_user_id) REFERENCES users(id) ON DELETE SET NULL
);
