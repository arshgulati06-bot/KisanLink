/**
 * KisanLink - Frontend API Client
 * SIH 2026 — PS SIH26132: Market Linkages & Price Discovery
 *
 * All functions call the real Flask backend API.
 * NO hardcoded prices, forecasts, markets, buyer scores, or demo data.
 * If backend is unavailable, functions throw ApiError with a real message.
 */

class ApiError extends Error {
  constructor(message, status = 500, data = null) {
    super(message);
    this.name   = 'ApiError';
    this.status = status;
    this.data   = data;
  }
}

class ApiClient {
  constructor(config = window.CONFIG) {
    this.baseUrl = (config && config.API_BASE_URL) || 'http://localhost:5000/api';
    this.timeout = (config && config.REQUEST_TIMEOUT_MS) || 60000; // 60s for ML inference
  }

  getAuthToken() {
    try { return localStorage.getItem('kisanlink_auth_token'); }
    catch (e) { return null; }
  }

  setAuthToken(token) {
    try {
      if (token) localStorage.setItem('kisanlink_auth_token', token);
      else        localStorage.removeItem('kisanlink_auth_token');
    } catch (e) {}
  }

  getDefaultHeaders(customHeaders = {}) {
    const headers = { 'Content-Type': 'application/json', 'Accept': 'application/json', ...customHeaders };
    const token = this.getAuthToken();
    if (token) headers['Authorization'] = `Bearer ${token}`;
    return headers;
  }

  async request(endpoint, options = {}) {
    const url        = endpoint.startsWith('http') ? endpoint : `${this.baseUrl}${endpoint}`;
    const headers    = this.getDefaultHeaders(options.headers);
    const controller = new AbortController();
    const timeoutId  = setTimeout(() => controller.abort(), options.timeout || this.timeout);

    const fetchConfig = { method: options.method || 'GET', headers, signal: controller.signal, ...options };
    if (options.body && typeof options.body === 'object' && !(options.body instanceof FormData)) {
      fetchConfig.body = JSON.stringify(options.body);
    }

    try {
      const response = await fetch(url, fetchConfig);
      clearTimeout(timeoutId);
      let responseData = null;
      const ct = response.headers.get('content-type');
      if (ct && ct.includes('application/json')) {
        responseData = await response.json();
      } else {
        responseData = await response.text();
      }
      if (!response.ok) {
        const errMsg = (responseData && responseData.error) ||
                       (responseData && responseData.message) ||
                       `HTTP ${response.status}: ${response.statusText}`;
        throw new ApiError(errMsg, response.status, responseData);
      }
      return { success: true, status: response.status, data: responseData };
    } catch (error) {
      clearTimeout(timeoutId);
      if (error.name === 'AbortError') {
        throw new ApiError(
          'Request timed out. The ML forecast may still be running — try again in a moment.',
          408
        );
      }
      if (error instanceof ApiError) throw error;
      throw new ApiError(
        'Cannot connect to KisanLink backend. Make sure the server is running: python backend/app.py',
        0, error
      );
    }
  }

  get(endpoint, options = {})          { return this.request(endpoint, { ...options, method: 'GET'  }); }
  post(endpoint, body, options = {})   { return this.request(endpoint, { ...options, method: 'POST', body }); }
  put(endpoint, body, options = {})    { return this.request(endpoint, { ...options, method: 'PUT',  body }); }
  delete(endpoint, options = {})       { return this.request(endpoint, { ...options, method: 'DELETE' }); }
}

// Global Singleton
window.apiClient = new ApiClient();
window.ApiError  = ApiError;

/* =========================================================================
   INTEGRATION BOUNDARY FUNCTIONS
   All functions call the REAL backend API.
   No hardcoded values anywhere in this file.
   ========================================================================= */

/**
 * 1. Price Forecast — calls real Chronos pipeline via /api/forecast
 *
 * @param {string} commodity
 * @param {string} state
 * @param {string} district
 * @param {string} market
 * @param {Object} opts — { quantity_qtl, storage_cost_per_day }
 * @returns {Promise<Object>} — real API response including quantiles + sale_window
 */
async function getPriceForecast(commodity, state, district, market, opts = {}) {
  const body = {
    commodity,
    state,
    district,
    market,
    quantity_qtl:         opts.quantity_qtl         || 10,
    storage_cost_per_day: opts.storage_cost_per_day || 0,
  };
  const res = await window.apiClient.post('/forecast', body, { timeout: 90000 });
  return res.data;
}

/**
 * 2. Market Intelligence — metadata for a specific market selection
 *
 * @param {string} commodity, state, district, market
 * @returns {Promise<Object>} — record_count, date_range, latest_price, confidence, etc.
 */
async function getMarketIntel(commodity, state, district, market) {
  const params = new URLSearchParams({ commodity, state, district, market });
  const res = await window.apiClient.get('/market-intel?' + params.toString());
  return res.data;
}

/**
 * 3. Market Comparison — real prices for all markets in a district
 *
 * @param {string} commodity, state, district
 * @returns {Promise<Object>} — { markets: [...] } with latest price, record count, date
 */
async function compareMarkets(commodity, state, district) {
  const params = new URLSearchParams({ commodity, state, district });
  const res = await window.apiClient.get('/market-compare?' + params.toString());
  return res.data;
}

/**
 * 4. Buyer Demands — server-side seed demands
 *
 * @param {string} commodity (optional filter)
 * @returns {Promise<Object>} — { demands: [...] }
 */
async function getBuyerDemands(commodity = '') {
  const params = new URLSearchParams();
  if (commodity) params.set('commodity', commodity);
  const res = await window.apiClient.get('/buyer-demands?' + params.toString());
  return res.data;
}

/**
 * 5. Buyer Match — score demands against a lot
 *
 * @param {Object} lot — { commodity, state, quantity_qtl, grade, expected_price }
 * @returns {Promise<Object>} — { matches: [...] } sorted by match_score desc
 */
async function matchBuyers(lot) {
  const res = await window.apiClient.post('/buyer-match', lot);
  return res.data;
}

/**
 * 6. Sale Window Decision (standalone)
 *
 * @param {Object} params — { commodity, state, district, market, quantity_qtl, storage_cost_per_day }
 * @returns {Promise<Object>} — decision engine result
 */
async function getSaleWindow(params) {
  const res = await window.apiClient.post('/sale-window', params);
  return res.data;
}

/**
 * 7. Data Ingestion Status
 *
 * @returns {Promise<Object>} — { total_records, latest_date_in_dataset, sources, live_api_connected }
 */
async function getIngestStatus() {
  const res = await window.apiClient.get('/ingest/status');
  return res.data;
}

/**
 * 8. Crop Quality Assessment
 * ML model not yet connected — returns clear "not connected" status.
 * Does NOT fake a grade or confidence.
 */
async function assessCropQuality(image, crop = '') {
  // No ML quality model is connected yet.
  // Return explicit not-connected status rather than fake data.
  return {
    _placeholder: false,
    _not_connected: true,
    crop,
    grade:      null,
    confidence: null,
    indicators: [],
    model:      { name: 'CropQualityNet-v1', status: 'not_connected' },
    message:    'Crop quality ML model is not yet integrated. Results will appear when connected.',
  };
}

/**
 * 9. Net Realisation Calculator (local arithmetic — no fakes)
 * @param {Object} data — { mandiPrice, freightCost, handlingFee, mandiTax, quantity }
 */
function calculateExpectedNetRealisation(data = {}) {
  const price    = Number(data.mandiPrice)   || 0;
  const freight  = Number(data.freightCost)  || 0;
  const handling = Number(data.handlingFee)  || 0;
  const tax      = Number(data.mandiTax)     || 0;
  const qty      = Number(data.quantity)     || 1;

  const total_deductions = freight + handling + tax;
  const net_per_unit     = Math.max(0, price - total_deductions);

  return {
    grossPricePerUnit:      price,
    freightPerUnit:         freight,
    handlingPerUnit:        handling,
    taxPerUnit:             tax,
    totalDeductionsPerUnit: total_deductions,
    netRealisationPerUnit:  net_per_unit,
    quantity:               qty,
    totalExpectedNet:       net_per_unit * qty,
  };
}

// Global exports
window.getPriceForecast                  = getPriceForecast;
window.getMarketIntel                    = getMarketIntel;
window.compareMarkets                    = compareMarkets;
window.getBuyerDemands                   = getBuyerDemands;
window.matchBuyers                       = matchBuyers;
window.getSaleWindow                     = getSaleWindow;
window.getIngestStatus                   = getIngestStatus;
window.assessCropQuality                 = assessCropQuality;
window.calculateExpectedNetRealisation   = calculateExpectedNetRealisation;
// Legacy aliases (for any existing code that calls old names)
window.getBuyerDemand                    = getBuyerDemands;
