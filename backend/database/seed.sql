-- ===========================================================================
-- KisanLink - reference and demonstration data
--
-- WHAT IS IN HERE
--   * Crops and market yards: real names and approximate coordinates for
--     Maharashtra APMC markets. Coordinates are city-level approximations, not
--     surveyed gate locations.
--   * Storage facilities and buyer accounts: PROTOTYPE / DEMONSTRATION DATA.
--     They are flagged is_seed_data = 1 in the database.
--
-- These demo buyers are NOT real verified commercial buyers, and nothing in
-- this project may present them as such.
--
-- Load with:  python -m scripts.init_db --seed
-- ===========================================================================

-- ---------------------------------------------------------------------------
-- Crops
-- ---------------------------------------------------------------------------
INSERT INTO crops (name, local_name, category, default_unit, shelf_life_days, is_perishable, grade_scale) VALUES
('Tomato', 'Tamatar', 'VEGETABLE', 'QUINTAL', 10, 1, 'A,B,C'),
('Onion', 'Kanda', 'VEGETABLE', 'QUINTAL', 120, 0, 'A,B,C'),
('Potato', 'Batata', 'VEGETABLE', 'QUINTAL', 90, 0, 'A,B,C'),
('Soybean', 'Soyabean', 'OILSEED', 'QUINTAL', 240, 0, 'A,B,C'),
('Cotton', 'Kapus', 'FIBRE', 'QUINTAL', 365, 0, 'A,B,C'),
('Wheat', 'Gahu', 'CEREAL', 'QUINTAL', 300, 0, 'A,B,C'),
('Bajra', 'Bajri', 'CEREAL', 'QUINTAL', 240, 0, 'A,B,C'),
('Jowar', 'Jwari', 'CEREAL', 'QUINTAL', 240, 0, 'A,B,C'),
('Tur (Arhar)', 'Tur Dal', 'PULSE', 'QUINTAL', 300, 0, 'A,B,C'),
('Gram (Chana)', 'Harbhara', 'PULSE', 'QUINTAL', 300, 0, 'A,B,C'),
('Sugarcane', 'Us', 'OTHER', 'TONNE', 15, 1, 'A,B,C'),
('Grapes', 'Draksha', 'FRUIT', 'QUINTAL', 21, 1, 'A,B,C'),
('Pomegranate', 'Dalimb', 'FRUIT', 'QUINTAL', 45, 1, 'A,B,C'),
('Banana', 'Kela', 'FRUIT', 'QUINTAL', 14, 1, 'A,B,C'),
('Green Chilli', 'Hirvi Mirchi', 'SPICE', 'QUINTAL', 12, 1, 'A,B,C'),
('Turmeric', 'Halad', 'SPICE', 'QUINTAL', 365, 0, 'A,B,C');

-- ---------------------------------------------------------------------------
-- Market yards
-- Coordinates are approximate city-level positions, adequate for distance
-- comparison but not for navigation.
-- ---------------------------------------------------------------------------
INSERT INTO markets (name, market_code, market_type, district, state, latitude, longitude, address) VALUES
('Pune Gultekdi', 'MH-PUN-01', 'APMC', 'Pune', 'Maharashtra', 18.496600, 73.856700, 'Market Yard, Gultekdi, Pune'),
('Nashik Panchavati', 'MH-NSK-01', 'APMC', 'Nashik', 'Maharashtra', 19.997500, 73.789800, 'Panchavati Market Yard, Nashik'),
('Lasalgaon', 'MH-NSK-02', 'APMC', 'Nashik', 'Maharashtra', 20.144000, 74.238000, 'Lasalgaon APMC, Niphad'),
('Navi Mumbai Vashi', 'MH-MUM-01', 'APMC', 'Thane', 'Maharashtra', 19.076800, 73.016900, 'APMC Market Complex, Vashi'),
('Nagpur Kalamna', 'MH-NAG-01', 'APMC', 'Nagpur', 'Maharashtra', 21.170200, 79.160000, 'Kalamna Market Yard, Nagpur'),
('Chhatrapati Sambhajinagar', 'MH-CSN-01', 'APMC', 'Chhatrapati Sambhajinagar', 'Maharashtra', 19.876200, 75.343300, 'Jadhavwadi Market Yard'),
('Kolhapur Shahu', 'MH-KOL-01', 'APMC', 'Kolhapur', 'Maharashtra', 16.705000, 74.243300, 'Shahu Market Yard, Kolhapur'),
('Solapur', 'MH-SOL-01', 'APMC', 'Solapur', 'Maharashtra', 17.659900, 75.906400, 'Solapur Market Yard'),
('Ahmednagar', 'MH-AHM-01', 'APMC', 'Ahmednagar', 'Maharashtra', 19.094800, 74.748000, 'Ahmednagar Market Yard'),
('Jalgaon', 'MH-JAL-01', 'APMC', 'Jalgaon', 'Maharashtra', 21.007700, 75.562600, 'Jalgaon Market Yard'),
('Latur', 'MH-LAT-01', 'APMC', 'Latur', 'Maharashtra', 18.408800, 76.560400, 'Latur Market Yard'),
('Amravati', 'MH-AMR-01', 'APMC', 'Amravati', 'Maharashtra', 20.937400, 77.779600, 'Amravati Market Yard'),
('Sangli', 'MH-SAN-01', 'APMC', 'Sangli', 'Maharashtra', 16.852400, 74.581500, 'Sangli Market Yard'),
('Maharashtra e-NAM Pool', 'MH-ENAM-01', 'ENAM', 'Pune', 'Maharashtra', 18.520400, 73.856700, 'Electronic trading platform');

-- ---------------------------------------------------------------------------
-- Storage facilities - PROTOTYPE DATA
-- Representative of what exists in these districts; not a verified directory.
-- ---------------------------------------------------------------------------
INSERT INTO storage_facilities (name, facility_type, operator_name, district, state, latitude, longitude, capacity_tonnes, available_capacity_tonnes, cost_per_tonne_per_day, has_cold_storage, offers_warehouse_receipt, contact_phone, is_seed_data) VALUES
('Pune Agri Warehouse', 'WAREHOUSE', 'Demo Warehousing Co.', 'Pune', 'Maharashtra', 18.520000, 73.900000, 5000, 2400, 9.50, 0, 1, '9876500001', 1),
('Nashik Cold Chain Hub', 'COLD_STORAGE', 'Demo Cold Chain Pvt Ltd', 'Nashik', 'Maharashtra', 20.010000, 73.800000, 2000, 850, 22.00, 1, 0, '9876500002', 1),
('Lasalgaon Onion Godown', 'WAREHOUSE', 'Demo Storage LLP', 'Nashik', 'Maharashtra', 20.150000, 74.240000, 8000, 5200, 7.00, 0, 1, '9876500003', 1),
('Ahmednagar FPO Godown', 'FPO_GODOWN', 'Demo Farmer Producer Co.', 'Ahmednagar', 'Maharashtra', 19.100000, 74.750000, 1200, 900, 5.50, 0, 0, '9876500004', 1),
('Nagpur Central Warehouse', 'WDRA_WAREHOUSE', 'Demo Warehousing Corp', 'Nagpur', 'Maharashtra', 21.150000, 79.100000, 10000, 6100, 8.25, 0, 1, '9876500005', 1),
('Solapur Multi-Commodity Store', 'WAREHOUSE', 'Demo Agri Logistics', 'Solapur', 'Maharashtra', 17.670000, 75.900000, 3500, 1800, 8.00, 0, 0, '9876500006', 1),
('Kolhapur Cold Storage', 'COLD_STORAGE', 'Demo Freshkeep', 'Kolhapur', 'Maharashtra', 16.710000, 74.250000, 1500, 600, 20.00, 1, 0, '9876500007', 1);
