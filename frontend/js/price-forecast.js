/**
 * KisanLink — Price Forecast / Price Outlook Module
 * SIH 2026 — PS SIH26132: Market Linkages & Price Discovery
 * Frontend Step 4
 *
 * Integration boundary: getPriceForecast(crop, location)
 *   → Will call GET /api/ml/price-forecast?crop=...&location=... (NOT YET CONNECTED)
 *
 * Current behaviour: renders demo data from CONFIG.DEMO_DATA with a
 * clear "Forecast service pending" message. No fake ML predictions.
 */

var KL_PriceForecast = (function () {

  /* ── Demo sparkline data (illustrative bar heights, NOT real predictions) ── */
  var DEMO_TRENDS = {
    'Onion': {
      bars:      [60, 65, 68, 72, 70, 75, 78],   // relative heights 0-100
      direction: 'rising',
      label:     'Gradual upward trend over 7 days (demo)',
      current:   3200,
      unit:      'QTL'
    },
    'Tomato': {
      bars:      [70, 68, 65, 72, 74, 76, 75],
      direction: 'rising',
      label:     'Recovering after mid-week dip (demo)',
      current:   2650,
      unit:      'QTL'
    },
    'Soybean': {
      bars:      [80, 82, 81, 83, 85, 84, 86],
      direction: 'rising',
      label:     'Steady upward momentum (demo)',
      current:   4850,
      unit:      'QTL'
    }
  };

  /* ── DOM element IDs ──────────────────────────────────────────────────── */
  var IDS = {
    section:        'price-forecast-section',
    cropSelect:     'pf-crop-select',
    locationInput:  'pf-location-input',
    fetchBtn:       'pf-fetch-btn',
    resultArea:     'pf-result-area',
    idleState:      'pf-idle-state',
    loadingState:   'pf-loading-state',
    resultState:    'pf-result-state',
    errorState:     'pf-error-state',
    errorMsg:       'pf-error-msg',
    currentPrice:   'pf-current-price',
    directionIcon:  'pf-direction-icon',
    directionLabel: 'pf-direction-label',
    trendLabel:     'pf-trend-label',
    sparkContainer: 'pf-sparkline',
    apiStatus:      'pf-api-status'
  };

  function _setResultState(state) {
    ['idle', 'loading', 'result', 'error'].forEach(function (s) {
      var el = document.getElementById('pf-' + s + '-state');
      if (el) el.hidden = (s !== state);
    });
  }

  function _renderSparkline(bars, direction) {
    var container = document.getElementById(IDS.sparkContainer);
    if (!container) return;
    var color = direction === 'rising' ? '#10B981' : direction === 'falling' ? '#E11D48' : '#94A3B8';
    var html = bars.map(function (h, i) {
      return '<div class="pf-spark-bar" style="height:' + h + '%;background-color:' + color + ';' +
             'opacity:' + (0.5 + (i / bars.length) * 0.5) + ';" ' +
             'title="Day ' + (i + 1) + '"></div>';
    }).join('');
    container.innerHTML = html;
  }

  function _renderResult(data) {
    var priceEl  = document.getElementById(IDS.currentPrice);
    var dirIcon  = document.getElementById(IDS.directionIcon);
    var dirLabel = document.getElementById(IDS.directionLabel);
    var trendLbl = document.getElementById(IDS.trendLabel);
    var statusEl = document.getElementById(IDS.apiStatus);

    if (priceEl)  priceEl.textContent  = '\u20b9' + data.current.toLocaleString('en-IN') + ' / ' + data.unit;
    if (dirLabel) dirLabel.textContent = data.direction === 'rising' ? 'Rising' : data.direction === 'falling' ? 'Falling' : 'Stable';
    if (dirLabel) {
      dirLabel.className = 'pf-direction-label';
      if (data.direction === 'rising')  dirLabel.classList.add('pf-dir-rising');
      if (data.direction === 'falling') dirLabel.classList.add('pf-dir-falling');
    }
    if (dirIcon) {
      dirIcon.textContent = data.direction === 'rising' ? '\u2197' : data.direction === 'falling' ? '\u2198' : '\u2192';
    }
    if (trendLbl) trendLbl.textContent = data.label;
    if (statusEl) statusEl.textContent = 'Forecast service not yet connected — showing demo data only.';

    _renderSparkline(data.bars, data.direction);
    _setResultState('result');
  }

  /* ════════════════════════════════════════════════════════════════════════
     ML INTEGRATION PLACEHOLDER — getPriceForecast(crop, location)
     ════════════════════════════════════════════════════════════════════════

     PURPOSE:
       Single integration boundary for the 7-day price forecast service.

     WHEN THE ML API IS READY, replace the function body to call:
       GET /api/ml/price-forecast?crop=<crop>&location=<location>

     EXPECTED RESPONSE FORMAT:
       {
         crop:      "Onion",
         location:  "Nashik",
         current:   3200,       // current modal price ₹/QTL
         unit:      "QTL",
         direction: "rising",   // "rising" | "falling" | "stable"
         label:     "Short trend description",
         bars:      [60,65,...] // 7 relative bar heights 0-100
       }

     CURRENT BEHAVIOUR:
       Returns demo data from CONFIG with a 1 s simulated delay.
       No fake ML predictions — data is clearly labelled "(demo)".
  ════════════════════════════════════════════════════════════════════════ */
  function getPriceForecast(crop, location) {
    /* ── INTEGRATION POINT ────────────────────────────────────────────────
       When ML API is ready, replace with:

       var params = new URLSearchParams({ crop: crop, location: location });
       return fetch(
         (window.CONFIG ? window.CONFIG.API_BASE_URL : 'http://localhost:5000/api') +
         '/ml/price-forecast?' + params.toString()
       ).then(function (res) {
         if (!res.ok) throw new Error('Forecast service error: ' + res.status);
         return res.json();
       });
    ──────────────────────────────────────────────────────────────────────── */

    return new Promise(function (resolve, reject) {
      setTimeout(function () {
        var key = crop ? crop.split(' ')[0] : 'Onion';  // extract base crop name
        var demo = DEMO_TRENDS[key];
        if (!demo) {
          reject(new Error('No demo data available for crop: ' + crop + '. Connect ML API for live forecast.'));
          return;
        }
        resolve(Object.assign({}, demo, { crop: crop, location: location || 'Nashik', _placeholder: true }));
      }, 900);
    });
  }

  /* ── UI wiring ──────────────────────────────────────────────────────── */
  function _onFetchClick() {
    var cropEl = document.getElementById(IDS.cropSelect);
    var locEl  = document.getElementById(IDS.locationInput);
    var crop   = cropEl ? cropEl.value : 'Onion';
    var loc    = locEl  ? locEl.value  : 'Nashik';

    _setResultState('loading');

    getPriceForecast(crop, loc).then(function (data) {
      _renderResult(data);
    }).catch(function (err) {
      var msgEl = document.getElementById(IDS.errorMsg);
      if (msgEl) msgEl.textContent = err.message;
      _setResultState('error');
    });
  }

  function init() {
    var section = document.getElementById(IDS.section);
    if (!section) return;

    var btn = document.getElementById(IDS.fetchBtn);
    if (btn) btn.addEventListener('click', _onFetchClick);

    // Auto-load for the default crop on page load
    _onFetchClick();
    console.info('[KL_PriceForecast] Module initialised (ML placeholder active).');
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }

  return { getPriceForecast: getPriceForecast };
})();

window.KL_PriceForecast = KL_PriceForecast;
window.getPriceForecast  = KL_PriceForecast.getPriceForecast;
