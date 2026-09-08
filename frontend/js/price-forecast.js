/**
 * KisanLink — Price Forecast Module (ML Connected)
 * SIH 2026 — PS SIH26132: Market Linkages & Price Discovery
 *
 * Connects the farmer dashboard "Price Outlook & 7-Day Forecast" section
 * to the Flask backend API which runs the frozen Chronos ML pipeline.
 *
 * Flow:
 *   Cascading selectors (Crop → State → District → Market)
 *   → POST /api/forecast
 *   → Display real 7-day Chronos forecast + evaluation metrics
 */

var KL_PriceForecast = (function () {

  /* ── API base URL ──────────────────────────────────────────────────── */
  var API_BASE = (window.CONFIG && window.CONFIG.API_BASE_URL)
    ? window.CONFIG.API_BASE_URL.replace(/\/api\/?$/, '')
    : 'http://localhost:5000';

  /* ── DOM element IDs ──────────────────────────────────────────────── */
  var IDS = {
    section:        'price-forecast-section',
    cropSelect:     'pf-crop-select',
    stateSelect:    'pf-state-select',
    districtSelect: 'pf-district-select',
    marketSelect:   'pf-market-select',
    fetchBtn:       'pf-fetch-btn',
    idleState:      'pf-idle-state',
    loadingState:   'pf-loading-state',
    resultState:    'pf-result-state',
    errorState:     'pf-error-state',
    errorMsg:       'pf-error-msg',
    selectionInfo:  'pf-selection-info',
    dataInfo:       'pf-data-info',
    sparkContainer: 'pf-sparkline',
    forecastTable:  'pf-forecast-table',
    evalBlock:      'pf-eval-block',
    evalMetrics:    'pf-eval-metrics'
  };

  /* ── State management ──────────────────────────────────────────────── */
  function _setResultState(state) {
    ['idle', 'loading', 'result', 'error'].forEach(function (s) {
      var el = document.getElementById('pf-' + s + '-state');
      if (el) el.hidden = (s !== state);
    });
  }

  function _populateSelect(selectId, items, placeholder) {
    var el = document.getElementById(selectId);
    if (!el) return;
    el.innerHTML = '<option value="">' + placeholder + '</option>';
    items.forEach(function (item) {
      var opt = document.createElement('option');
      opt.value = item;
      opt.textContent = item;
      el.appendChild(opt);
    });
    el.disabled = (items.length === 0);
  }

  function _resetSelect(selectId, placeholder) {
    var el = document.getElementById(selectId);
    if (!el) return;
    el.innerHTML = '<option value="">' + placeholder + '</option>';
    el.disabled = true;
  }

  function _updateFetchButton() {
    var btn = document.getElementById(IDS.fetchBtn);
    var market = document.getElementById(IDS.marketSelect);
    if (btn && market) {
      btn.disabled = !market.value;
    }
  }

  /* ── API helpers ───────────────────────────────────────────────────── */
  function _fetchJSON(url) {
    return fetch(API_BASE + url).then(function (res) {
      if (!res.ok) throw new Error('API error: ' + res.status);
      return res.json();
    });
  }

  /* ── Cascading dropdown loaders ────────────────────────────────────── */
  function loadCrops() {
    _fetchJSON('/api/commodities').then(function (crops) {
      _populateSelect(IDS.cropSelect, crops, '-- Select Commodity --');
    }).catch(function (err) {
      console.error('[PriceForecast] Failed to load commodities:', err);
      _populateSelect(IDS.cropSelect, [], 'API unavailable');
    });
  }

  function onCropChange() {
    var crop = document.getElementById(IDS.cropSelect).value;
    _resetSelect(IDS.stateSelect, '-- Loading... --');
    _resetSelect(IDS.districtSelect, '-- Select State first --');
    _resetSelect(IDS.marketSelect, '-- Select District first --');
    _updateFetchButton();

    if (!crop) {
      _resetSelect(IDS.stateSelect, '-- Select Crop first --');
      return;
    }

    _fetchJSON('/api/states?commodity=' + encodeURIComponent(crop)).then(function (states) {
      _populateSelect(IDS.stateSelect, states, '-- Select State --');
    }).catch(function () {
      _resetSelect(IDS.stateSelect, 'Failed to load');
    });
  }

  function onStateChange() {
    var crop = document.getElementById(IDS.cropSelect).value;
    var state = document.getElementById(IDS.stateSelect).value;
    _resetSelect(IDS.districtSelect, '-- Loading... --');
    _resetSelect(IDS.marketSelect, '-- Select District first --');
    _updateFetchButton();

    if (!state) {
      _resetSelect(IDS.districtSelect, '-- Select State first --');
      return;
    }

    _fetchJSON('/api/districts?commodity=' + encodeURIComponent(crop) +
               '&state=' + encodeURIComponent(state)).then(function (districts) {
      _populateSelect(IDS.districtSelect, districts, '-- Select District --');
    }).catch(function () {
      _resetSelect(IDS.districtSelect, 'Failed to load');
    });
  }

  function onDistrictChange() {
    var crop = document.getElementById(IDS.cropSelect).value;
    var state = document.getElementById(IDS.stateSelect).value;
    var district = document.getElementById(IDS.districtSelect).value;
    _resetSelect(IDS.marketSelect, '-- Loading... --');
    _updateFetchButton();

    if (!district) {
      _resetSelect(IDS.marketSelect, '-- Select District first --');
      return;
    }

    _fetchJSON('/api/markets?commodity=' + encodeURIComponent(crop) +
               '&state=' + encodeURIComponent(state) +
               '&district=' + encodeURIComponent(district)).then(function (markets) {
      _populateSelect(IDS.marketSelect, markets, '-- Select Market --');
    }).catch(function () {
      _resetSelect(IDS.marketSelect, 'Failed to load');
    });
  }

  function onMarketChange() {
    _updateFetchButton();
  }

  /* ── Sparkline renderer ────────────────────────────────────────────── */
  function _renderSparkline(forecast) {
    var container = document.getElementById(IDS.sparkContainer);
    if (!container || !forecast || forecast.length === 0) return;

    var prices = forecast.map(function (f) { return f.price; });
    var maxP = Math.max.apply(null, prices);
    var minP = Math.min.apply(null, prices);
    var range = maxP - minP || 1;

    // Determine trend direction
    var rising = prices[prices.length - 1] > prices[0];
    var color = rising ? '#10B981' : '#E11D48';

    var html = forecast.map(function (f, i) {
      var pct = 30 + ((f.price - minP) / range) * 70; // 30-100% height
      return '<div class="pf-spark-bar" style="height:' + pct + '%;background-color:' + color + ';' +
             'opacity:' + (0.5 + (i / forecast.length) * 0.5) + ';" ' +
             'title="Day ' + f.day + ': Rs.' + f.price.toLocaleString('en-IN') + '"></div>';
    }).join('');
    container.innerHTML = html;
  }

  /* ── Forecast result renderer ──────────────────────────────────────── */
  function _renderResult(data) {
    // Selection info
    var selEl = document.getElementById(IDS.selectionInfo);
    if (selEl) {
      selEl.innerHTML =
        '<strong>' + data.commodity + '</strong><br>' +
        data.state + ' &rarr; ' + data.district + ' &rarr; ' + data.market;
    }

    // Data source info
    var dataEl = document.getElementById(IDS.dataInfo);
    if (dataEl) {
      var lines = data.data_source + '<br>' +
        'Records: ' + data.historical_records;
      if (data.date_range) {
        lines += '<br>' + data.date_range.start + ' to ' + data.date_range.end;
      }
      dataEl.innerHTML = lines;
    }

    // Sparkline
    _renderSparkline(data.forecast);

    // Forecast table
    var tableEl = document.getElementById(IDS.forecastTable);
    if (tableEl) {
      var rows = data.forecast.map(function (f) {
        return '<div style="display:flex;justify-content:space-between;padding:4px 0;border-bottom:1px solid var(--color-slate-100);">' +
          '<span style="font-size:var(--text-xs);color:var(--color-slate-500);">Day ' + f.day + '</span>' +
          '<span style="font-size:var(--text-xs);font-weight:var(--weight-semibold);">Rs.' + f.price.toLocaleString('en-IN', {minimumFractionDigits: 2, maximumFractionDigits: 2}) + '</span>' +
          '</div>';
      }).join('');
      tableEl.innerHTML = rows;
    }

    // Evaluation metrics
    var evalBlock = document.getElementById(IDS.evalBlock);
    var evalMetrics = document.getElementById(IDS.evalMetrics);
    if (evalBlock && evalMetrics) {
      if (data.evaluation) {
        evalBlock.hidden = false;
        evalMetrics.innerHTML =
          _metricCard('MAE', 'Rs.' + data.evaluation.mae.toLocaleString('en-IN', {minimumFractionDigits: 2})) +
          _metricCard('RMSE', 'Rs.' + data.evaluation.rmse.toLocaleString('en-IN', {minimumFractionDigits: 2})) +
          _metricCard('MAPE', data.evaluation.mape.toFixed(2) + '%');
      } else {
        evalBlock.hidden = true;
        evalMetrics.innerHTML = '';
      }
    }

    _setResultState('result');
  }

  function _metricCard(label, value) {
    return '<div style="background:var(--color-slate-50);border-radius:var(--radius-lg);padding:var(--space-3) var(--space-4);min-width:100px;">' +
      '<div style="font-size:var(--text-xs);color:var(--color-slate-500);margin-bottom:2px;">' + label + '</div>' +
      '<div style="font-size:var(--text-sm);font-weight:var(--weight-bold);color:var(--color-slate-800);">' + value + '</div>' +
      '</div>';
  }

  /* ── Forecast request ──────────────────────────────────────────────── */
  function _onFetchClick() {
    var crop     = document.getElementById(IDS.cropSelect).value;
    var state    = document.getElementById(IDS.stateSelect).value;
    var district = document.getElementById(IDS.districtSelect).value;
    var market   = document.getElementById(IDS.marketSelect).value;

    if (!crop || !state || !district || !market) {
      var msgEl = document.getElementById(IDS.errorMsg);
      if (msgEl) msgEl.textContent = 'Please select Commodity, State, District and Market.';
      _setResultState('error');
      return;
    }

    _setResultState('loading');

    // Disable button during request
    var btn = document.getElementById(IDS.fetchBtn);
    if (btn) { btn.disabled = true; btn.textContent = 'Running...'; }

    fetch(API_BASE + '/api/forecast', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        commodity: crop,
        state: state,
        district: district,
        market: market
      })
    })
    .then(function (res) {
      return res.json().then(function (data) {
        return { status: res.status, data: data };
      });
    })
    .then(function (result) {
      if (result.data.success) {
        _renderResult(result.data);
      } else {
        // API returned an error (e.g. insufficient data)
        var errMsg = result.data.error || 'Forecast failed.';
        if (result.data.available_markets && result.data.available_markets.length > 0) {
          errMsg += '\n\nAvailable markets: ' + result.data.available_markets.join(', ');
        }
        var msgEl = document.getElementById(IDS.errorMsg);
        if (msgEl) msgEl.textContent = errMsg;
        _setResultState('error');
      }
    })
    .catch(function (err) {
      var msgEl = document.getElementById(IDS.errorMsg);
      if (msgEl) {
        msgEl.textContent = 'Could not connect to the forecast API. Make sure the backend is running (python backend/app.py). Error: ' + err.message;
      }
      _setResultState('error');
    })
    .finally(function () {
      if (btn) { btn.disabled = false; btn.textContent = 'Generate Forecast'; }
      _updateFetchButton();
    });
  }

  /* ── Initialization ────────────────────────────────────────────────── */
  function init() {
    var section = document.getElementById(IDS.section);
    if (!section) return;

    // Wire cascading selectors
    var cropEl     = document.getElementById(IDS.cropSelect);
    var stateEl    = document.getElementById(IDS.stateSelect);
    var districtEl = document.getElementById(IDS.districtSelect);
    var marketEl   = document.getElementById(IDS.marketSelect);
    var btn        = document.getElementById(IDS.fetchBtn);

    if (cropEl)     cropEl.addEventListener('change', onCropChange);
    if (stateEl)    stateEl.addEventListener('change', onStateChange);
    if (districtEl) districtEl.addEventListener('change', onDistrictChange);
    if (marketEl)   marketEl.addEventListener('change', onMarketChange);
    if (btn)        btn.addEventListener('click', _onFetchClick);

    // Load initial crop list from API
    loadCrops();

    console.info('[KL_PriceForecast] Module initialised (ML API connected).');
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }

  return { loadCrops: loadCrops };
})();

window.KL_PriceForecast = KL_PriceForecast;
