USE kisanlink_db;

-- ============================================================
-- KISANLINK TRANSPORTATION FEATURE MIGRATION
-- ============================================================

-- ------------------------------------------------------------
-- 1. Create transporters table
-- ------------------------------------------------------------

CREATE TABLE IF NOT EXISTS transporters (
    id INT AUTO_INCREMENT PRIMARY KEY,
    user_id INT NOT NULL UNIQUE,
    business_name VARCHAR(180) NOT NULL,
    phone VARCHAR(20),
    district VARCHAR(120),
    state VARCHAR(120) DEFAULT 'Maharashtra',
    verification_status VARCHAR(30) NOT NULL DEFAULT 'UNVERIFIED',
    rating DECIMAL(3, 2) NOT NULL DEFAULT 0,
    reliability_score DECIMAL(5, 2) NOT NULL DEFAULT 40.00,
    total_trips INT NOT NULL DEFAULT 0,
    completed_trips INT NOT NULL DEFAULT 0,
    is_available TINYINT(1) NOT NULL DEFAULT 1,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,

    FOREIGN KEY (user_id)
        REFERENCES users(id)
        ON DELETE CASCADE
);


-- ------------------------------------------------------------
-- 2. Create vehicles table
-- ------------------------------------------------------------

CREATE TABLE IF NOT EXISTS vehicles (
    id INT AUTO_INCREMENT PRIMARY KEY,
    transporter_id INT NOT NULL,
    vehicle_type VARCHAR(30) NOT NULL,
    vehicle_number VARCHAR(30) NOT NULL UNIQUE,
    capacity_tonnes DECIMAL(8, 2) NOT NULL,
    service_area VARCHAR(255),
    rate_per_km DECIMAL(10, 2),
    verification_status VARCHAR(30) NOT NULL DEFAULT 'UNVERIFIED',
    is_available TINYINT(1) NOT NULL DEFAULT 1,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,

    FOREIGN KEY (transporter_id)
        REFERENCES transporters(id)
        ON DELETE CASCADE
);


-- ------------------------------------------------------------
-- 3. Add transportation columns to existing logistics_requests
-- ------------------------------------------------------------

ALTER TABLE logistics_requests
    ADD COLUMN transporter_id INT NULL,
    ADD COLUMN vehicle_id INT NULL,
    ADD COLUMN eta_minutes DECIMAL(10, 2) NULL,
    ADD COLUMN route_status VARCHAR(30) NOT NULL DEFAULT 'NOT_STARTED',
    ADD COLUMN route_progress_percent DECIMAL(5, 2) NOT NULL DEFAULT 0,
    ADD COLUMN incident_status VARCHAR(20) NOT NULL DEFAULT 'NONE',
    ADD COLUMN reliability_score DECIMAL(5, 2) NULL;


-- ------------------------------------------------------------
-- 4. Add foreign keys to logistics_requests
-- ------------------------------------------------------------

ALTER TABLE logistics_requests
    ADD CONSTRAINT fk_logistics_transporter
        FOREIGN KEY (transporter_id)
        REFERENCES transporters(id)
        ON DELETE SET NULL,

    ADD CONSTRAINT fk_logistics_vehicle
        FOREIGN KEY (vehicle_id)
        REFERENCES vehicles(id)
        ON DELETE SET NULL;


-- ------------------------------------------------------------
-- 5. Create logistics_incidents table
-- ------------------------------------------------------------

CREATE TABLE IF NOT EXISTS logistics_incidents (
    id INT AUTO_INCREMENT PRIMARY KEY,
    logistics_request_id INT NOT NULL,
    incident_type VARCHAR(40) NOT NULL,
    description VARCHAR(500) NOT NULL,
    status VARCHAR(20) NOT NULL DEFAULT 'OPEN',
    reported_by_user_id INT NOT NULL,
    reported_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    resolved_at DATETIME,
    resolution_notes VARCHAR(500),
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,

    FOREIGN KEY (logistics_request_id)
        REFERENCES logistics_requests(id)
        ON DELETE CASCADE,

    FOREIGN KEY (reported_by_user_id)
        REFERENCES users(id)
        ON DELETE CASCADE
);