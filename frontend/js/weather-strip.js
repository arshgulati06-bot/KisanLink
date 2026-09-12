/**
 * KisanLink — top-of-dashboard weather strip
 * ==========================================
 *
 * Weather was buried behind a sidebar link, so a farmer deciding whether to
 * harvest or hold never saw it. This puts a compact, visual summary at the top
 * of the dashboard.
 *
 * Rules it follows:
 *   - never blocks the dashboard: it fails quietly into an honest message
 *   - never asks for GPS on load; browser location is requested only after
 *     "Use my location" is clicked
 *   - falls back to the district/state on the signed-in account
 *   - says plainly when live weather could not be fetched, and never invents it
 *
 * Data comes from /api/weather, which is backed by Open-Meteo (keyless).
 */
(function () {
  'use strict';

  // WMO weather codes -> a glyph a farmer reads at a glance.
  function icon(code) {
    var c = Number(code);
    if (c === 0) return '☀️';
    if (c === 1 || c === 2) return '🌤️';
    if (c === 3) return '☁️';
    if (c === 45 || c === 48) return '🌫️';
    if (c >= 51 && c <= 57) return '🌦️';
    if (c >= 61 && c <= 67) return '🌧️';
    if (c >= 71 && c <= 77) return '🌨️';
    if (c >= 80 && c <= 82) return '🌧️';
    if (c >= 95) return '⛈️';
    return '🌡️';
  }

  function el(id) { return document.getElementById(id); }
  function set(id, text) { var e = el(id); if (e) e.textContent = text; }

  function status(msg, isError) {
    var e = el('wx-strip-status');
    if (!e) return;
    e.textContent = msg || '';
    e.hidden = !msg;
    e.classList.toggle('is-error', !!isError);
  }

  function dayName(iso, index) {
    if (index === 0) return 'Today';
    if (index === 1) return 'Tomorrow';
    try {
      return new Date(iso).toLocaleDateString('en-IN', { weekday: 'short' });
    } catch (e) {
      return 'Day ' + (index + 1);
    }
  }

  function render(data) {
    var cur = data.current || {};
    var days = data.forecast || [];
    var today = days[0] || {};

    set('wx-strip-temp', cur.temperature_c != null ? Math.round(cur.temperature_c) + '°C' : '—');
    set('wx-strip-cond', cur.condition || 'Weather');
    var ico = el('wx-strip-icon');
    if (ico) ico.textContent = icon(cur.weather_code);

    var hi = today.temp_max != null ? Math.round(today.temp_max) + '°' : null;
    var lo = today.temp_min != null ? Math.round(today.temp_min) + '°' : null;
    set('wx-strip-range', hi && lo ? 'High ' + hi + '  Low ' + lo : '—');
    set('wx-strip-hum', cur.humidity_pct != null ? Math.round(cur.humidity_pct) + '%' : '—');
    set('wx-strip-rain', today.rain_probability_pct != null
      ? Math.round(today.rain_probability_pct) + '%' : '—');
    set('wx-strip-wind', cur.wind_kmh != null ? Math.round(cur.wind_kmh) + ' km/h' : '—');

    var wrap = el('wx-strip-days');
    if (wrap) {
      var three = days.slice(0, 3);
      if (three.length) {
        wrap.innerHTML = three.map(function (d, i) {
          return '<div class="wx-strip-day">' +
            '<div class="d-name">' + dayName(d.date, i) + '</div>' +
            '<div class="d-icon">' + icon(d.weather_code) + '</div>' +
            '<div class="d-temp">' +
              (d.temp_max != null ? Math.round(d.temp_max) + '°' : '—') + ' / ' +
              (d.temp_min != null ? Math.round(d.temp_min) + '°' : '—') + '</div>' +
            '<div class="d-rain">🌧 ' +
              (d.rain_probability_pct != null ? Math.round(d.rain_probability_pct) + '%' : '—') +
            '</div></div>';
        }).join('');
        wrap.hidden = false;
      } else {
        wrap.hidden = true;
      }
    }

    var tip = el('wx-strip-tip');
    if (tip) {
      tip.textContent = data.farmer_tip || '';
      tip.hidden = !data.farmer_tip;
    }

    var loc = data.location || {};
    var place = data.location_note && loc.precision === 'browser_gps'
      ? 'Your current location'
      : [loc.district, loc.state].filter(Boolean).join(', ');
    set('wx-strip-place', (place || 'Location not set') + ' · Source: Open-Meteo');
    var stale = el('wx-strip-retry');
    if (stale) stale.remove();
    status('');
  }

  function failed(message, reason) {
    set('wx-strip-temp', '—');
    set('wx-strip-cond', 'Weather unavailable');
    var ico = el('wx-strip-icon');
    if (ico) ico.textContent = '⚠️';
    ['wx-strip-range', 'wx-strip-hum', 'wx-strip-rain', 'wx-strip-wind']
      .forEach(function (id) { set(id, '—'); });
    var wrap = el('wx-strip-days'); if (wrap) wrap.hidden = true;
    var tip = el('wx-strip-tip'); if (tip) tip.hidden = true;
    status((message || 'Live weather could not be fetched right now.') +
           (reason ? ' [' + reason + ']' : '') +
           ' Everything else on this page still works.', true);
    var gps = el('wx-strip-gps');
    if (gps && !el('wx-strip-retry')) {
      var retry = document.createElement('button');
      retry.type = 'button';
      retry.id = 'wx-strip-retry';
      retry.className = 'btn btn-ghost btn-sm';
      retry.textContent = 'Retry';
      retry.addEventListener('click', function () {
        retry.remove();
        // Re-resolve rather than replaying the query that just failed: the
        // profile may have arrived since, or GPS may now be available. An
        // empty query used to be stored and replayed forever, so one bad
        // first attempt poisoned every later retry.
        bestLocation().then(function (where) {
          if (where) { load(where, false, true); return; }
          status('Set your district in your profile, or tap "Use my location".', true);
        });
      });
      gps.parentNode.insertBefore(retry, gps);
    }
  }

  function load(opts, isRetry, noAutoRetry) {
    if (typeof window.getWeather !== 'function') { failed('Weather module not loaded.'); return; }
    set('wx-strip-cond', 'Loading weather…');
    var ico = el('wx-strip-icon');
    if (ico) ico.textContent = '⏳';
    if (isRetry) status('Weather service was slow — trying once more…');

    window.getWeather(opts || {}).then(function (data) {
      if (!data || !data.success) {
        if (!isRetry && !noAutoRetry) {
          setTimeout(function () { load(opts, true); }, 1200); return;
        }
        // Show what the server actually reported — a timeout, a DNS failure
        // and a blocked firewall need different actions from the operator.
        failed((data && data.error) || 'Live weather is unavailable right now.',
               data && data.reason);
        return;
      }
      render(data);
    }).catch(function (err) {
      if (!isRetry && !noAutoRetry) {
        setTimeout(function () { load(opts, true); }, 1200); return;
      }
      // Never surface the generic API timeout copy here — it mentions the ML
      // forecast, which has nothing to do with weather.
      var aborted = err && (err.name === 'AbortError' || /abort|timeout/i.test(String(err.message || '')));
      failed(aborted
        ? 'The weather request timed out before the server answered. This is ' +
          'usually a slow network on this machine — press Retry.'
        : 'Could not reach the KisanLink server for weather. Check that the ' +
          'backend is running, then press Retry.',
        aborted ? 'client_timeout' : 'server_unreachable');
    });
    // Remember the last USABLE query only. Storing {} meant the retry button
    // replayed a request that could never succeed.
    if (hasLocation(opts)) LAST_QUERY = opts;
  }

  var LAST_QUERY = null;

  /** A query is only usable if it carries coordinates or a place name. */
  function hasLocation(o) {
    if (!o) return false;
    if (o.lat != null && o.lon != null) return true;
    return !!(o.district || o.state);
  }

  /**
   * The best location available right now, in order of precision.
   * Auto-load and Retry both go through this, so they cannot diverge.
   * @returns {Promise<Object|null>}
   */
  function bestLocation() {
    if (window.__klGps && window.__klGps.lat != null) {
      return Promise.resolve({ lat: window.__klGps.lat, lon: window.__klGps.lon });
    }
    var cached = accountLocation();
    if (hasLocation(cached)) return Promise.resolve(cached);
    return fetchAccountLocation().then(function (where) {
      return hasLocation(where) ? where : null;
    });
  }

  /** Location from the signed-in account — no browser permission needed. */
  function accountLocation() {
    try {
      var u = JSON.parse(localStorage.getItem('kisanlink_user') || 'null') || {};
      if (u.district || u.state) return { district: u.district || '', state: u.state || '' };
    } catch (e) {}
    return null;
  }

  /**
   * The register/login response carries the user row but not the farmer
   * profile, so the cached user often has no district on a first visit. Ask
   * the API directly rather than depending on another script having run.
   */
  function fetchAccountLocation() {
    var token = null;
    try { token = localStorage.getItem('kisanlink_auth_token'); } catch (e) {}
    if (!token || typeof window.apiClient === 'undefined') return Promise.resolve(null);
    return window.apiClient.get('/auth/me').then(function (r) {
      var d = r.data || {};
      var prof = d.profile || {};
      var user = d.user || {};
      var district = prof.district || user.district || '';
      var state = prof.state || user.state || '';
      if (!district && !state) return null;
      // Cache it so the next load is instant.
      try {
        var cached = JSON.parse(localStorage.getItem('kisanlink_user') || '{}') || {};
        cached.district = district;
        cached.state = state;
        localStorage.setItem('kisanlink_user', JSON.stringify(cached));
      } catch (e) {}
      return { district: district, state: state };
    }).catch(function () { return null; });
  }

  function useMyLocation() {
    var btn = el('wx-strip-gps');
    if (!navigator.geolocation) {
      status('This browser cannot provide location. Showing your saved district instead.', true);
      return;
    }
    if (btn) { btn.disabled = true; btn.textContent = 'Locating…'; }
    status('Asking your browser for permission…');
    navigator.geolocation.getCurrentPosition(function (pos) {
      if (btn) { btn.disabled = false; btn.textContent = 'Use my location'; }
      window.__klGps = { lat: pos.coords.latitude, lon: pos.coords.longitude };
      status('Location found — updating weather.');
      load({ lat: pos.coords.latitude, lon: pos.coords.longitude });
    }, function (err) {
      if (btn) { btn.disabled = false; btn.textContent = 'Try again'; }
      var code = err && err.code;
      if (code === 1) {
        status('Location permission denied. Showing weather for your saved district.', true);
      } else if (code === 3) {
        status('Timed out getting your location. Try again outdoors.', true);
      } else {
        status('Location is unavailable on this device right now.', true);
      }
    }, { enableHighAccuracy: true, timeout: 15000, maximumAge: 0 });
  }

  function init() {
    if (!el('wx-strip')) return;
    var gps = el('wx-strip-gps');
    if (gps) gps.addEventListener('click', useMyLocation);

    // Deliberately does NOT ask for GPS here.
    var loaded = false;
    function tryLoad(where) {
      if (loaded || !hasLocation(where)) return;
      loaded = true;
      load(where);
    }

    // Auto-load and Retry resolve the location the same way, so the two paths
    // can never diverge — "works when I click, not on load" was exactly that.
    bestLocation().then(function (where) {
      if (where) { tryLoad(where); return; }
      if (loaded) return;
      set('wx-strip-cond', 'Choose a location');
      var ico = el('wx-strip-icon');
      if (ico) ico.textContent = '📍';
      status('Set your district in your profile, or tap "Use my location".');
    });

    // /auth/me may resolve after first paint; take the district as soon as it
    // lands, in case the cached user had none.
    document.addEventListener('kl:profileReady', function (e) {
      var d = e && e.detail;
      if (d && (d.district || d.state)) {
        tryLoad({ district: d.district || '', state: d.state || '' });
      }
    });
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    setTimeout(init, 0);
  }

  window.KLWeatherStrip = { load: load, useMyLocation: useMyLocation };
})();
