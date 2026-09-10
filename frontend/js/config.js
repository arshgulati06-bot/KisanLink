/**
 * KisanLink - Frontend Configuration & Prototype State Store
 * SIH 2026 — PS SIH26132: Market Linkages & Price Discovery
 * Centralized settings, REST routes, and prototype datasets
 */

const CONFIG = {
  // Application Metadata
  APP_NAME: 'KisanLink',
  PS_CODE: 'SIH26132',
  THEME: 'Agriculture, FoodTech & Rural Development',
  VERSION: '1.2.0-step2',
  IS_PROTOTYPE: true,

  // Backend API Base URL (Configurable for local vs production environments)
  API_BASE_URL: window.KISANLINK_API_URL || 'http://localhost:5000/api',

  // Request Timeout in milliseconds
  REQUEST_TIMEOUT_MS: 90000,

  // REST API endpoints implemented by the Flask service.
  ENDPOINTS: {
    COMMODITIES: '/commodities',
    STATES: '/states',
    DISTRICTS: '/districts',
    MARKETS: '/markets',
    FORECAST: '/forecast',
    MARKET_COMPARE: '/market-compare',
    MARKET_INTEL: '/market-intel',
    BUYER_DEMANDS: '/buyer-demands',
    BUYER_MATCH: '/buyer-match',
    BUYER_MATCHES: '/buyer-matches',
    SALE_WINDOW: '/sale-window',
    INGEST_STATUS: '/ingest/status',
    INGEST_UPDATE: '/ingest/update',
  },

  // Prototype Initial Seed Data (Demo Datasets)
  INITIAL_DATA: {
    FARMER_PROFILE: {
      id: 'FARMER_001',
      name: 'Ramesh Patil',
      type: 'Individual Farmer / Producer',
      location: 'Dindori Taluka, Nashik District, Maharashtra',
      apmcZone: 'Nashik APMC',
      landHolding: '4.5 Acres',
      phone: '+91 98220 XXXXX',
      verified: true
    },

    BUYER_PROFILE: {
      id: 'BUYER_001',
      name: 'Sahyadri Agro Processors Ltd.',
      type: 'Food Processor',
      location: 'Sanaswadi Industrial Zone, Pune, Maharashtra',
      procurementZone: 'Western Maharashtra Hub',
      contactPerson: 'Vikram Joshi (Procurement Head)',
      phone: '+91 98450 XXXXX',
      trustStatus: 'Platform-Reviewed Processor',
      reliabilityScore: '95%'
    },

    LOTS: [],
    BUYER_DEMANDS: [],
    OFFERS: [],
    TRANSACTIONS: []
  }
};

// Freeze endpoint definitions
if (typeof Object.freeze === 'function') {
  Object.freeze(CONFIG.ENDPOINTS);
}

// Make accessible globally
window.CONFIG = CONFIG;
