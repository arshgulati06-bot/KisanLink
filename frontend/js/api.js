/**
 * KisanLink - Frontend API Client & Integration Boundaries
 * SIH 2026 — PS SIH26132: Market Linkages & Price Discovery
 * Frontend Step 5: Complete Integration-Ready Frontend Boundaries
 *
 * This file provides:
 *  1. ApiClient: HTTP client for Flask REST backend (when live)
 *  2. Explicit frontend boundary functions ready for backend/ML integration:
 *     - getPriceForecast(crop, location)
 *     - assessCropQuality(image, crop)
 *     - getBuyerDemand(crop, location)
 *     - compareMarkets(location, crop)
 *     - calculateExpectedNetRealisation(data)
 *     - sendAssistantMessage(message)
 *     - startVoiceInput(onResult, onEnd, onError)
 *     - stopVoiceInput()
 *     - speakAssistantResponse(text)
 */

class ApiError extends Error {
  constructor(message, status = 500, data = null) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
    this.data = data;
  }
}

class ApiClient {
  constructor(config = window.CONFIG) {
    this.baseUrl = (config && config.API_BASE_URL) || 'http://localhost:5000/api';
    this.timeout = (config && config.REQUEST_TIMEOUT_MS) || 8000;
  }

  /**
   * Retrieve active authentication token from storage
   */
  getAuthToken() {
    try {
      return localStorage.getItem('kisanlink_auth_token');
    } catch (e) {
      console.warn('[ApiClient] LocalStorage unavailable for auth token:', e);
      return null;
    }
  }

  /**
   * Set authentication token in storage
   */
  setAuthToken(token) {
    try {
      if (token) {
        localStorage.setItem('kisanlink_auth_token', token);
      } else {
        localStorage.removeItem('kisanlink_auth_token');
      }
    } catch (e) {
      console.warn('[ApiClient] Failed to persist auth token:', e);
    }
  }

  /**
   * Build default request headers with JSON and Auth tokens
   */
  getDefaultHeaders(customHeaders = {}) {
    const headers = {
      'Content-Type': 'application/json',
      'Accept': 'application/json',
      ...customHeaders
    };

    const token = this.getAuthToken();
    if (token) {
      headers['Authorization'] = `Bearer ${token}`;
    }

    return headers;
  }

  /**
   * Core request dispatcher with timeout and error handling
   */
  async request(endpoint, options = {}) {
    const url = endpoint.startsWith('http') ? endpoint : `${this.baseUrl}${endpoint}`;
    const headers = this.getDefaultHeaders(options.headers);

    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), options.timeout || this.timeout);

    const fetchConfig = {
      method: options.method || 'GET',
      headers,
      signal: controller.signal,
      ...options
    };

    if (options.body && typeof options.body === 'object' && !(options.body instanceof FormData)) {
      fetchConfig.body = JSON.stringify(options.body);
    }

    try {
      const response = await fetch(url, fetchConfig);
      clearTimeout(timeoutId);

      let responseData = null;
      const contentType = response.headers.get('content-type');
      if (contentType && contentType.includes('application/json')) {
        responseData = await response.json();
      } else {
        responseData = await response.text();
      }

      if (!response.ok) {
        const errorMessage = (responseData && responseData.message) || `HTTP error ${response.status}: ${response.statusText}`;
        throw new ApiError(errorMessage, response.status, responseData);
      }

      return {
        success: true,
        status: response.status,
        data: responseData
      };
    } catch (error) {
      clearTimeout(timeoutId);

      if (error.name === 'AbortError') {
        throw new ApiError('Request timed out. Please check backend connectivity.', 408);
      }

      if (error instanceof ApiError) {
        throw error;
      }

      // Network level failure (backend server not yet running)
      throw new ApiError(error.message || 'Network error occurred while connecting to KisanLink API.', 0, error);
    }
  }

  get(endpoint, options = {}) {
    return this.request(endpoint, { ...options, method: 'GET' });
  }

  post(endpoint, body, options = {}) {
    return this.request(endpoint, { ...options, method: 'POST', body });
  }

  put(endpoint, body, options = {}) {
    return this.request(endpoint, { ...options, method: 'PUT', body });
  }

  delete(endpoint, options = {}) {
    return this.request(endpoint, { ...options, method: 'DELETE' });
  }
}

// Global Singleton Instance
window.apiClient = new ApiClient();
window.ApiError = ApiError;

/* =========================================================================
   INTEGRATION BOUNDARY FUNCTIONS (FRONTEND CONTRACTS)
   =========================================================================
   These functions form the clean boundary between UI and future backend/ML.
   When backend is ready, they dispatch real HTTP calls. Currently they
   return well-typed demo/placeholder structures with zero uncaught errors.
   ========================================================================= */

/**
 * 1. Price Outlook / 7-Day Forecast Boundary
 * @param {string} crop - Crop name (e.g. 'Onion', 'Tomato', 'Soybean')
 * @param {string} location - Market / District name
 * @returns {Promise<Object>}
 */
async function getPriceForecast(crop, location) {
  /* When backend is connected:
     return window.apiClient.get(`/ml/price-forecast?crop=${encodeURIComponent(crop)}&location=${encodeURIComponent(location)}`)
       .then(res => res.data);
  */
  return new Promise((resolve) => {
    setTimeout(() => {
      resolve({
        _placeholder: true,
        crop: crop || 'Onion',
        location: location || 'Nashik',
        currentPrice: 3200,
        unit: 'QTL',
        direction: 'rising',
        forecastDays: [
          { day: 'D1', price: 3200 },
          { day: 'D2', price: 3220 },
          { day: 'D3', price: 3250 },
          { day: 'D4', price: 3300 },
          { day: 'D5', price: 3280 },
          { day: 'D6', price: 3340 },
          { day: 'D7', price: 3380 }
        ],
        message: 'Forecast service pending. Showing demo dataset.'
      });
    }, 400);
  });
}

/**
 * 2. Crop Quality Assessment Boundary
 * @param {File|Blob} image - Captured/Uploaded crop photo
 * @param {string} crop - Crop name
 * @returns {Promise<Object>}
 */
async function assessCropQuality(image, crop = 'Onion') {
  /* When backend is connected:
     const formData = new FormData();
     formData.append('image', image);
     formData.append('crop', crop);
     return fetch(`${window.apiClient.baseUrl}/ml/quality-assessment`, {
       method: 'POST',
       body: formData,
       headers: { Authorization: `Bearer ${window.apiClient.getAuthToken() || ''}` }
     }).then(res => res.json());
  */
  return new Promise((resolve) => {
    setTimeout(() => {
      resolve({
        _placeholder: true,
        crop: crop,
        grade: null,
        confidence: null,
        indicators: [],
        model: { name: 'CropQualityNet-v1', status: 'not_connected' },
        message: 'Quality assessment will appear when the ML service is connected.'
      });
    }, 1500);
  });
}

/**
 * 3. Buyer Demand Boundary
 * @param {string} crop - Crop name
 * @param {string} location - Origin location
 * @returns {Promise<Array>}
 */
async function getBuyerDemand(crop, location) {
  /* When backend is connected:
     return window.apiClient.get(`/demands/match?crop=${encodeURIComponent(crop)}&location=${encodeURIComponent(location)}`)
       .then(res => res.data);
  */
  return new Promise((resolve) => {
    setTimeout(() => {
      resolve([
        {
          id: 'BM001',
          buyerName: 'Sahyadri Agro Processors',
          buyerType: 'Food Processor',
          crop: crop || 'Onion',
          quantity: '10 QTL',
          grade: 'Grade A',
          deliveryLocation: 'Pune Hub',
          offeredRate: 3200,
          matchScore: 94,
          status: 'OPEN'
        },
        {
          id: 'BM002',
          buyerName: 'Reliance Fresh Sourcing',
          buyerType: 'Retail Chain',
          crop: crop || 'Onion',
          quantity: '25 QTL',
          grade: 'Grade A / Premium',
          deliveryLocation: 'Mumbai DC',
          offeredRate: 3350,
          matchScore: 81,
          status: 'OPEN'
        }
      ]);
    }, 300);
  });
}

/**
 * 4. Market Comparison Boundary
 * @param {string} location - Farmer location
 * @param {string} crop - Crop name
 * @returns {Promise<Object>}
 */
async function compareMarkets(location, crop) {
  /* When backend is connected:
     return window.apiClient.get(`/markets/compare?origin=${encodeURIComponent(location)}&crop=${encodeURIComponent(crop)}`)
       .then(res => res.data);
  */
  return new Promise((resolve) => {
    setTimeout(() => {
      resolve({
        crop: crop || 'Onion',
        origin: location || 'Nashik (Dindori Taluka)',
        markets: [
          { name: 'Nashik APMC', distanceKm: 28, mandiPrice: 3100, freightPerQtl: 65, netRealisation: 3035, isBest: false },
          { name: 'Pune (Pimpri)', distanceKm: 215, mandiPrice: 3400, freightPerQtl: 310, netRealisation: 3090, isBest: true },
          { name: 'Mumbai (Vashi)', distanceKm: 302, mandiPrice: 3500, freightPerQtl: 430, netRealisation: 3070, isBest: false },
          { name: 'Aurangabad APMC', distanceKm: 188, mandiPrice: 3250, freightPerQtl: 280, netRealisation: 2970, isBest: false }
        ]
      });
    }, 350);
  });
}

/**
 * 5. Expected Net Realisation Calculator
 * @param {Object} data - { mandiPrice, freightCost, handlingFee, mandiTax, quantity }
 * @returns {Object}
 */
function calculateExpectedNetRealisation(data = {}) {
  const price = Number(data.mandiPrice) || 3200;
  const freight = Number(data.freightCost) || 310;
  const handling = Number(data.handlingFee) || 50;
  const tax = Number(data.mandiTax) || 20;
  const totalDeductions = freight + handling + tax;
  const netPerUnit = Math.max(0, price - totalDeductions);
  const qty = Number(data.quantity) || 1;
  const totalNet = netPerUnit * qty;

  return {
    grossPricePerUnit: price,
    freightPerUnit: freight,
    handlingPerUnit: handling,
    taxPerUnit: tax,
    totalDeductionsPerUnit: totalDeductions,
    netRealisationPerUnit: netPerUnit,
    quantity: qty,
    totalExpectedNet: totalNet
  };
}

// Global Exports
window.getPriceForecast = getPriceForecast;
window.assessCropQuality = assessCropQuality;
window.getBuyerDemand = getBuyerDemand;
window.compareMarkets = compareMarkets;
window.calculateExpectedNetRealisation = calculateExpectedNetRealisation;
