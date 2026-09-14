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
  // Flask serves both the API and these pages on :5000, so when the page is
  // already on that origin we use a same-origin relative path (no CORS, and it
  // keeps working behind a tunnel or on another host). If the pages are served
  // from a separate static server (commonly :3000 during development), fall
  // back to the Flask origin on the same hostname. Override either with
  //   <script>window.KISANLINK_API_URL = 'http://192.168.1.5:5000/api'</script>
  API_BASE_URL: (function () {
    if (window.KISANLINK_API_URL) return window.KISANLINK_API_URL;
    var loc = window.location;
    if (loc.protocol === 'file:') return 'http://127.0.0.1:5000/api';
    if (loc.port === '5000') return '/api';          // served by Flask itself
    return loc.protocol + '//' + loc.hostname + ':5000/api';
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
