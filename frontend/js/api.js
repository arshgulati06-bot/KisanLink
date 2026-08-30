/**
 * KisanLink - Frontend API Client Layer
 * SIH 2026 — PS SIH26132: Market Linkages & Price Discovery
 * A robust, modular HTTP client for clean communication with Flask REST backend
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

    if (options.body && typeof options.body === 'object') {
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

      // Network level failure (e.g. backend server not started)
      throw new ApiError(error.message || 'Network error occurred while connecting to KisanLink API.', 0, error);
    }
  }

  /**
   * Convenience HTTP Methods
   */
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

// Global Singleton Instance for clean consumption across pages
window.apiClient = new ApiClient();
window.ApiError = ApiError;
