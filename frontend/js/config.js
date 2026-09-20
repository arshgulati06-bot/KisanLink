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

  // Backend API Base URL.
  // In production (Vercel deployment), requests route to your live Render backend API.
  // You can also override at runtime with: window.KISANLINK_API_URL = 'https://<app>.onrender.com/api'
  RENDER_BACKEND_URL: 'https://kisanlink-backend-42qd.onrender.com/api',

  API_BASE_URL: (function () {
    if (typeof window !== 'undefined' && window.KISANLINK_API_URL) {
      return window.KISANLINK_API_URL;
    }
    var loc = window.location;
    if (loc.protocol === 'file:') return 'http://127.0.0.1:5000/api';
    if (loc.port === '5000') return '/api';          // served by Flask itself
    if (loc.hostname === 'localhost' || loc.hostname === '127.0.0.1') {
      return 'http://127.0.0.1:5000/api';          // local development
    }
    // Deployed frontend (e.g. https://kisan-link-two.vercel.app/)
    return 'https://kisanlink-backend-42qd.onrender.com/api';
  })(),

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
    // Empty shell only. Every field is filled from /auth/me for the signed-in
    // account; no placeholder name, district or APMC zone is ever displayed.
    FARMER_PROFILE: {
      id: '',
      name: '',
      type: '',
      location: '',
      apmcZone: '',
      landHolding: '',
      phone: '',
      verified: false
    },

    BUYER_PROFILE: {
      id: '',
      name: '',
      type: 'Buyer',
      location: '',
      procurementZone: '',
      contactPerson: '',
      phone: '',
      trustStatus: '',
      reliabilityScore: ''
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
