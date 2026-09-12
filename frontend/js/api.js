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
    this.baseUrl = (config && config.API_BASE_URL) ||
      (window.location.port === '5000' ? '/api'
        : window.location.protocol + '//' + window.location.hostname + ':5000/api');
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
/**
 * Crop quality — real inference against the project's trained models.
 * Posts the photo to /api/ml/quality-assessment. Returns the model's actual
 * prediction, or an explicit unavailable state. Never a fabricated grade.
 */
async function assessCropQuality(image, crop = '') {
  if (!image) {
    return {
      _placeholder: true, _unavailable: true, crop,
      grade: null, confidence: null, indicators: [],
      reason: 'no_image',
      message: 'Choose or capture a crop photo first.',
    };
  }

  const body = new FormData();
  body.append('image', image);
  body.append('crop', crop || '');

  const headers = {};
  const token = window.apiClient.getAuthToken();
  if (token) headers['Authorization'] = 'Bearer ' + token;

  let res, data;
  try {
    res = await fetch(window.apiClient.baseUrl + '/ml/quality-assessment', {
      method: 'POST', body, headers,
    });
    data = await res.json();
  } catch (err) {
    return {
      _placeholder: true, _unavailable: true, crop,
      grade: null, confidence: null, indicators: [],
      reason: 'network',
      message: 'Could not reach the analysis service. Set the grade manually for now.',
    };
  }

  if (!res.ok || !data || !data.success) {
    return {
      _placeholder: true, _unavailable: true, crop,
      grade: null, confidence: null, indicators: [],
      reason: (data && data.reason) || 'unavailable',
      supported_crops: (data && data.supported_crops) || [],
      message: (data && data.error) ||
        'Photo grading is unavailable. Choose the quality grade yourself when listing.',
    };
  }

  // Real model output.
  return {
    _placeholder: false,
    crop: data.crop_canonical || data.crop || crop,
    // These checkpoints predict a physical condition class, not a market
    // grade. `resultType` lets the UI say so instead of printing "Grade X".
    resultType: data.result_type || 'condition',
    grade: data.label,
    confidence: data.confidence,
    indicators: (data.distribution || []).map(function (d) {
      return { name: d.label, value: Math.round(d.probability * 100) + '%' };
    }),
    distribution: data.distribution || [],
    labels_known: data.labels_known,
    model: {
      name: (data.model && data.model.file) || 'quality model',
      architecture: (data.model && data.model.architecture) || '',
      status: 'connected',
    },
    message: data.note || '',
  };
}

/** Which crops this server can actually grade from a photo. */
async function getCropQualityStatus() {
  try {
    const res = await window.apiClient.get('/ml/quality-status');
    return res.data;
  } catch (err) {
    return { success: false, available: false, supported_crops: [],
             note: 'Could not reach the analysis service.' };
  }
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
window.getCropQualityStatus              = getCropQualityStatus;
window.calculateExpectedNetRealisation   = calculateExpectedNetRealisation;
// Legacy aliases (for any existing code that calls old names)
window.getBuyerDemand                    = getBuyerDemands;

/* =========================================================================
   AUTH + PERSISTENCE API (new endpoints)
   ========================================================================= */

/**
 * 10. Auth — Register a new account.
 * @param {Object} data — { name, phone, password, role, district, state, ... }
 * @returns {Promise<Object>} — { success, token, user }
 */
async function registerUser(data) {
  const res = await window.apiClient.post('/auth/register', data);
  if (res.data && res.data.token) {
    window.apiClient.setAuthToken(res.data.token);
    try { localStorage.setItem('kisanlink_user', JSON.stringify(res.data.user)); } catch(e) {}
  }
  return res.data;
}

/**
 * 11. Auth — Login with username + password.
 * @param {string} username
 * @param {string} password
 * @returns {Promise<Object>} — { success, token, user }
 */
async function loginUser(username, password) {
  const res = await window.apiClient.post('/auth/login', { username, password });
  if (res.data && res.data.token) {
    window.apiClient.setAuthToken(res.data.token);
    try { localStorage.setItem('kisanlink_user', JSON.stringify(res.data.user)); } catch(e) {}
  }
  return res.data;
}

/**
 * 12. Auth — Get current user (requires token).
 * @returns {Promise<Object>} — { success, user, profile, role }
 */
async function getCurrentUser() {
  const res = await window.apiClient.get('/auth/me');
  return res.data;
}

/**
 * 13. Auth — Clear session token.
 */
function logoutUser() {
  window.apiClient.setAuthToken(null);
  try { localStorage.removeItem('kisanlink_user'); } catch(e) {}
}

/**
 * 14. Lots — Create a sale lot (farmer auth required).
 * @param {Object} data — { commodity, quantity_qtl, grade, district, state, ... }
 */
async function createLot(data) {
  const res = await window.apiClient.post('/lots', data);
  return res.data;
}

/**
 * 15. Lots — Get current farmer's lots.
 */
async function getMyLots() {
  const res = await window.apiClient.get('/lots/my');
  return res.data;
}

/**
 * 16. Lots — Get all available lots (public, optionally filter by commodity).
 * @param {string} commodity — optional
 */
async function getAvailableLots(commodity = '') {
  const params = commodity ? '?commodity=' + encodeURIComponent(commodity) : '';
  const res = await window.apiClient.get('/lots' + params);
  return res.data;
}

/**
 * 17. Buyer Requirements — Post a demand (buyer auth required).
 */
async function createBuyerRequirement(data) {
  const res = await window.apiClient.post('/buyer-requirements', data);
  return res.data;
}

/**
 * 18. Buyer Requirements — Get all open requirements (public).
 */
async function getOpenRequirements(commodity = '') {
  const params = commodity ? '?commodity=' + encodeURIComponent(commodity) : '';
  const res = await window.apiClient.get('/buyer-requirements' + params);
  return res.data;
}

/**
 * 19. My transactions.
 */
async function getMyTransactions() {
  const res = await window.apiClient.get('/transactions/my');
  return res.data;
}

/* =========================================================================
   FARMER SUPER-APP APIS (new routes)
   ========================================================================= */

/**
 * 20. Weather — via Open-Meteo (free, no API key).
 * @param {Object} opts — { district, state } OR { lat, lon }
 */
async function getWeather(opts = {}) {
  const params = new URLSearchParams();
  if (opts.lat)      params.set('lat',      opts.lat);
  if (opts.lon)      params.set('lon',      opts.lon);
  if (opts.district) params.set('district', opts.district);
  if (opts.state)    params.set('state',    opts.state);
  // The server retries the upstream once, so allow for that before aborting.
  const res = await window.apiClient.get('/weather?' + params.toString(), { timeout: 30000 });
  return res.data;
}

/**
 * 21. Government Schemes
 * @param {Object} opts — { category, scope }
 */
async function getSchemes(opts = {}) {
  const params = new URLSearchParams();
  if (opts.category) params.set('category', opts.category);
  if (opts.scope)    params.set('scope',    opts.scope);
  const res = await window.apiClient.get('/schemes?' + params.toString());
  return res.data;
}

/**
 * 22. Farming Knowledge
 * @param {Object} opts — { category, q }
 */
async function getKnowledge(opts = {}) {
  const params = new URLSearchParams();
  if (opts.category) params.set('category', opts.category);
  if (opts.q)        params.set('q',        opts.q);
  const res = await window.apiClient.get('/knowledge?' + params.toString());
  return res.data;
}

/**
 * 23. Learning Resources
 * @param {Object} opts — { topic }
 */
async function getLearning(opts = {}) {
  const params = new URLSearchParams();
  if (opts.topic) params.set('topic', opts.topic);
  const res = await window.apiClient.get('/learning?' + params.toString());
  return res.data;
}

/**
 * 24. Helplines
 * @param {Object} opts — { category }
 */
async function getHelplines(opts = {}) {
  const params = new URLSearchParams();
  if (opts.category) params.set('category', opts.category);
  const res = await window.apiClient.get('/helplines?' + params.toString());
  return res.data;
}

/**
 * 25. Seeds / Seed Organizations
 */
async function getSeeds() {
  const res = await window.apiClient.get('/seeds');
  return res.data;
}

/**
 * 26. Latest Market Prices — real mandi data, honest date labeling.
 * @param {Object} opts — { commodity (required), state, district, market, limit }
 */
async function getLatestMarketPrices(opts = {}) {
  if (!opts.commodity) throw new Error('commodity is required');
  const params = new URLSearchParams({ commodity: opts.commodity });
  if (opts.state)    params.set('state',    opts.state);
  if (opts.district) params.set('district', opts.district);
  if (opts.market)   params.set('market',   opts.market);
  if (opts.limit)    params.set('limit',    opts.limit);
  const res = await window.apiClient.get('/market-prices/latest?' + params.toString());
  return res.data;
}

async function getSellNowPlan(opts = {}) {
  const body = {
    commodity: opts.commodity,
    state: opts.state,
    district: opts.district,
    market: opts.market || '',
    quantity_qtl: opts.quantity_qtl || 10,
  };
  if (opts.lat != null && opts.lon != null) {
    body.lat = opts.lat;
    body.lon = opts.lon;
  }
  const res = await window.apiClient.post('/sell-now', body);
  return res.data;
}

async function getLiveMarketPrices(opts = {}) {
  const params = new URLSearchParams();
  if (opts.commodity) params.set('commodity', opts.commodity);
  if (opts.state) params.set('state', opts.state);
  if (opts.district) params.set('district', opts.district);
  if (opts.market) params.set('market', opts.market);
  if (opts.limit) params.set('limit', opts.limit);
  const res = await window.apiClient.get('/market-prices/live?' + params.toString());
  return res.data;
}

async function reverseGeocode(lat, lon) {
  const res = await window.apiClient.get(
    '/location/reverse?lat=' + encodeURIComponent(lat) + '&lon=' + encodeURIComponent(lon)
  );
  return res.data;
}

async function getRoute(origin, destination) {
  const res = await window.apiClient.post('/route', { origin, destination });
  return res.data;
}

// Global exports — auth + persistence
window.registerUser          = registerUser;
window.loginUser             = loginUser;
window.getCurrentUser        = getCurrentUser;
window.logoutUser            = logoutUser;
window.createLot             = createLot;
window.getMyLots             = getMyLots;
window.getAvailableLots      = getAvailableLots;
window.createBuyerRequirement = createBuyerRequirement;
window.getOpenRequirements   = getOpenRequirements;
window.getMyTransactions     = getMyTransactions;

// Global exports — Farmer Super-App
window.getWeather            = getWeather;
window.getSchemes            = getSchemes;
window.getKnowledge          = getKnowledge;
window.getLearning           = getLearning;
window.getHelplines          = getHelplines;
window.getSeeds              = getSeeds;
window.getLatestMarketPrices = getLatestMarketPrices;
window.getLiveMarketPrices = getLiveMarketPrices;
window.getSellNowPlan        = getSellNowPlan;
window.reverseGeocode        = reverseGeocode;
window.getRoute              = getRoute;
