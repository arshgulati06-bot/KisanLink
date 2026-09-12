/**
 * KisanLink — Price Forecast Module (ML Connected)
 * SIH 2026 — PS SIH26132: Market Linkages & Price Discovery
 *
 * Connects the farmer dashboard "Price Outlook & 7-Day Forecast" section
 * to the Flask backend API (Chronos ML pipeline).
 *
 * Features:
 *  - Cascading dropdowns (Crop → State → District → Market) from real dataset
 *  - 7-day Chronos forecast with q10/q50/q90 quantile display
 *  - Backtest evaluation (Chronos vs Naive vs MA7)
 *  - Sale-window decision (SELL_NOW vs WAIT_N_DAYS with reasoning)
 *  - Data quality / gap detection notes
 *  - Market comparison panel (real district prices)
 *  - No hardcoded prices, no demo data, no fake forecasts
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
    evalMetrics:    'pf-eval-metrics',
    mlBadge:        'pf-ml-badge',
  };

  var requestState = {
    epoch: 0,
    forecastController: null,
    comparisonController: null,
    intelligenceController: null,
    cascadeController: null,
    selection: null,
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
      opt.value = item; opt.textContent = item;
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
    var btn    = document.getElementById(IDS.fetchBtn);
    var market = document.getElementById(IDS.marketSelect);
    if (btn && market) btn.disabled = !market.value;
  }

  function _readSelection() {
    return {
      commodity: (document.getElementById(IDS.cropSelect) || {}).value || '',
      state:     (document.getElementById(IDS.stateSelect) || {}).value || '',
      district:  (document.getElementById(IDS.districtSelect) || {}).value || '',
      market:    (document.getElementById(IDS.marketSelect) || {}).value || '',
    };
  }

  function _selectionKey(selection) {
    return ['commodity', 'state', 'district', 'market']
      .map(function (key) { return selection[key] || ''; })
      .join('\u001f');
  }

  function _isCurrent(token, selection) {
    return token === requestState.epoch &&
      _selectionKey(selection) === _selectionKey(_readSelection());
  }

  function _abort(controllerName) {
    if (requestState[controllerName]) {
      requestState[controllerName].abort();
      requestState[controllerName] = null;
    }
  }

  function _clearForecastDependentUi(message) {
    var dataEl = document.getElementById(IDS.dataInfo);
    var tableEl = document.getElementById(IDS.forecastTable);
    var sparkEl = document.getElementById(IDS.sparkContainer);
    var evalBlock = document.getElementById(IDS.evalBlock);
    var selectionEl = document.getElementById(IDS.selectionInfo);
    if (dataEl) dataEl.textContent = message || '';
    if (tableEl) tableEl.textContent = '';
    if (sparkEl) sparkEl.textContent = '';
    if (evalBlock) evalBlock.hidden = true;
    if (selectionEl) selectionEl.textContent = '';
    document.dispatchEvent(new CustomEvent('kl:forecastCleared'));
  }

  function _beginSelectionChange() {
    requestState.epoch += 1;
    _abort('forecastController');
    _abort('comparisonController');
    _abort('intelligenceController');
    _abort('cascadeController');
    requestState.selection = _readSelection();
    _clearForecastDependentUi('Selection changed. Generate a forecast for the current market.');
    _setResultState('idle');
    var btn = document.getElementById(IDS.fetchBtn);
    if (btn) { btn.disabled = true; btn.textContent = 'Generate Forecast'; }
    _updateFetchButton();
  }

  function _setCurrentSelection(selection) {
    requestState.selection = {
      commodity: selection.commodity,
      state: selection.state,
      district: selection.district,
      market: selection.market,
    };
  }

  /* ── API helpers ───────────────────────────────────────────────────── */
  function _fetchJSON(url, signal) {
    return fetch(API_BASE + url, { signal: signal }).then(function (res) {
      if (!res.ok) throw new Error('API error: ' + res.status);
      return res.json();
    });
  }

  /* ── Cascading dropdown loaders ────────────────────────────────────── */
  function loadCrops(isRetry) {
    var controller = new AbortController();
    requestState.cascadeController = controller;
    _fetchJSON('/api/commodities', controller.signal).then(function (crops) {
      window.__klCommodities = Array.isArray(crops) ? crops : [];
      _populateSelect(IDS.cropSelect, window.__klCommodities, '-- Select Commodity --');
      _wireCropSearch();
    }).catch(function (err) {
      if (err.name === 'AbortError') return;
      // The mandi archive loads in the background after a cold start, so this
      // legitimately 503s for the first moments. Wait for it instead of
      // telling the farmer the backend is down.
      var warming = /503|warming/i.test(String(err && err.message));
      if (warming && !isRetry && typeof window.waitForMarketData === 'function') {
        _populateSelect(IDS.cropSelect, [], 'Loading market data…');
        window.waitForMarketData().then(function (ok) {
          if (ok) { loadCrops(true); return; }
          _populateSelect(IDS.cropSelect, [], 'Market data unavailable');
        });
        return;
      }
      console.error('[PriceForecast] Failed to load commodities:', err);
      _populateSelect(IDS.cropSelect, [],
        warming ? 'Market data still loading — retry shortly'
                : 'Backend unavailable — start server');
    }).finally(function () {
      if (requestState.cascadeController === controller) requestState.cascadeController = null;
    });
  }

  function _wireCropSearch() {
    var search = document.getElementById('pf-crop-search');  // removed: combobox now provides search
    var select = document.getElementById(IDS.cropSelect);
    if (!search || !select || search.dataset.wired) return;
    search.dataset.wired = '1';
    search.addEventListener('input', function () {
      var q = search.value.toLowerCase();
      var crops = window.__klCommodities || [];
      var current = select.value;
      var filtered = crops.filter(function (c) { return !q || String(c).toLowerCase().indexOf(q) >= 0; });
      _populateSelect(IDS.cropSelect, filtered, '-- Select Commodity --');
      if (current) select.value = current;
    });
  }

  function onCropChange() {
    _beginSelectionChange();
    var crop = document.getElementById(IDS.cropSelect).value;
    _resetSelect(IDS.stateSelect,    '-- Loading... --');
    _resetSelect(IDS.districtSelect, '-- Select State first --');
    _resetSelect(IDS.marketSelect,   '-- Select District first --');
    _updateFetchButton();
    if (!crop) { _resetSelect(IDS.stateSelect, '-- Select Crop first --'); return; }
    var token = requestState.epoch;
    var controller = new AbortController();
    requestState.cascadeController = controller;
    _fetchJSON('/api/states?commodity=' + encodeURIComponent(crop), controller.signal)
      .then(function (states) {
        if (token === requestState.epoch) _populateSelect(IDS.stateSelect, states, '-- Select State --');
      })
      .catch(function (err) {
        if (err.name !== 'AbortError' && token === requestState.epoch) _resetSelect(IDS.stateSelect, 'Failed to load states');
      });
  }

  function onStateChange() {
    _beginSelectionChange();
    var crop  = document.getElementById(IDS.cropSelect).value;
    var state = document.getElementById(IDS.stateSelect).value;
    _resetSelect(IDS.districtSelect, '-- Loading... --');
    _resetSelect(IDS.marketSelect,   '-- Select District first --');
    _updateFetchButton();
    if (!state) { _resetSelect(IDS.districtSelect, '-- Select State first --'); return; }
    var token = requestState.epoch;
    var controller = new AbortController();
    requestState.cascadeController = controller;
    _fetchJSON('/api/districts?commodity=' + encodeURIComponent(crop) + '&state=' + encodeURIComponent(state), controller.signal)
      .then(function (districts) {
        if (token === requestState.epoch) _populateSelect(IDS.districtSelect, districts, '-- Select District --');
      })
      .catch(function (err) {
        if (err.name !== 'AbortError' && token === requestState.epoch) _resetSelect(IDS.districtSelect, 'Failed to load districts');
      });
  }

  function onDistrictChange() {
    _beginSelectionChange();
    var crop     = document.getElementById(IDS.cropSelect).value;
    var state    = document.getElementById(IDS.stateSelect).value;
    var district = document.getElementById(IDS.districtSelect).value;
    _resetSelect(IDS.marketSelect, '-- Loading... --');
    _updateFetchButton();
    if (!district) { _resetSelect(IDS.marketSelect, '-- Select District first --'); return; }
    var token = requestState.epoch;
    var controller = new AbortController();
    requestState.cascadeController = controller;
    _fetchJSON('/api/markets?commodity=' + encodeURIComponent(crop) +
               '&state=' + encodeURIComponent(state) +
               '&district=' + encodeURIComponent(district), controller.signal)
      .then(function (markets) {
        if (token === requestState.epoch) _populateSelect(IDS.marketSelect, markets, '-- Select Market --');
      })
      .catch(function (err) {
        if (err.name !== 'AbortError' && token === requestState.epoch) _resetSelect(IDS.marketSelect, 'Failed to load markets');
      });
  }

  function onMarketChange() { _beginSelectionChange(); }

  /* ── Helpers ───────────────────────────────────────────────────────── */
  function _esc(s) {
    return String(s == null ? '' : s)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;');
  }

  function _fmt(v) {
    return (typeof v === 'number')
      ? v.toLocaleString('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
      : String(v || '—');
  }

  function _metricCard(label, value, sub) {
    return '<div style="background:var(--color-slate-50);border-radius:var(--radius-lg);padding:var(--space-3) var(--space-4);min-width:90px;flex:1;">' +
      '<div style="font-size:var(--text-xs);color:var(--color-slate-500);margin-bottom:2px;">' + label + '</div>' +
      '<div style="font-size:var(--text-sm);font-weight:var(--weight-bold);color:var(--color-slate-800);">' + value + '</div>' +
      (sub ? '<div style="font-size:0.67rem;color:var(--color-slate-400);">' + sub + '</div>' : '') +
    '</div>';
  }

  /* ── Sparkline renderer (shows trend + range as opacity variation) ── */
  function _renderSparkline(forecast) {
    var container = document.getElementById(IDS.sparkContainer);
    if (!container || !forecast || !forecast.length) return;

    var prices = forecast.map(function (f) { return f.price; });
    var lows   = forecast.map(function (f) { return f.price_low  || f.price; });
    var highs  = forecast.map(function (f) { return f.price_high || f.price; });

    var allVals = prices.concat(lows).concat(highs);
    var maxP    = Math.max.apply(null, allVals);
    var minP    = Math.min.apply(null, allVals);
    var range   = maxP - minP || 1;

    var rising  = prices[prices.length - 1] > prices[0];
    var color   = rising ? '#10B981' : '#E11D48';
    var colorLt = rising ? 'rgba(16,185,129,0.18)' : 'rgba(225,29,72,0.12)';

    var html = forecast.map(function (f, i) {
      var pct    = 20 + ((f.price - minP) / range) * 80;
      var pctLo  = 20 + (((f.price_low  || f.price) - minP) / range) * 80;
      var pctHi  = 20 + (((f.price_high || f.price) - minP) / range) * 80;
      var tip    = 'Day ' + f.day + ' (' + (f.date || '') + '): ₹' + _fmt(f.price) +
                   '\nRange: ₹' + _fmt(f.price_low || f.price) + ' – ₹' + _fmt(f.price_high || f.price);
      return '<div style="display:flex;flex-direction:column;align-items:center;flex:1;height:100%;position:relative;" title="' + tip + '">' +
               '<div style="position:absolute;bottom:' + pctLo + '%;top:' + (100-pctHi) + '%;left:1px;right:1px;background:' + colorLt + ';border-radius:2px;"></div>' +
               '<div class="pf-spark-bar" style="height:' + pct + '%;background-color:' + color + ';opacity:' + (0.5 + (i / forecast.length) * 0.5) + ';position:absolute;bottom:0;left:4px;right:4px;border-radius:3px 3px 0 0;"></div>' +
             '</div>';
    }).join('');
    container.innerHTML = html;
  }

  /* ── Sale-window chip renderer ─────────────────────────────────────── */
  function _renderSaleWindow(sw) {
    if (!sw) return '';
    var action = sw.action || 'UNKNOWN';
    var isWait = action.startsWith('WAIT');
    var chipColor = isWait ? '#D97706' : '#10B981';
    var chipLabel = isWait
      ? ('Wait ' + sw.wait_days + ' Day' + (sw.wait_days > 1 ? 's' : ''))
      : 'Sell Now';
    var confColor = sw.uncertainty === 'High' ? '#E11D48' : sw.uncertainty === 'Medium' ? '#D97706' : '#10B981';

    var html = '<div style="background:var(--color-slate-50);border-radius:var(--radius-xl);padding:var(--space-4);margin-top:var(--space-4);">' +
      '<div style="font-size:var(--text-xs);font-weight:var(--weight-bold);color:var(--color-slate-500);text-transform:uppercase;letter-spacing:0.08em;margin-bottom:var(--space-2);">💡 Sale-Window Recommendation</div>' +
      '<div style="display:flex;align-items:center;gap:var(--space-3);margin-bottom:var(--space-2);">' +
        '<span style="display:inline-flex;align-items:center;padding:6px 16px;border-radius:999px;background:' + chipColor + ';color:#fff;font-weight:var(--weight-bold);font-size:var(--text-sm);">' + chipLabel + '</span>' +
        '<span style="font-size:var(--text-xs);color:' + confColor + ';font-weight:var(--weight-semibold);">Uncertainty: ' + (sw.uncertainty || '—') + '</span>' +
      '</div>' +
      '<p style="font-size:var(--text-xs);color:var(--color-slate-600);margin-bottom:var(--space-2);">' + (sw.reason || '') + '</p>';

    if (isWait && sw.expected_price) {
      html += '<div style="display:flex;gap:var(--space-3);flex-wrap:wrap;">' +
        _metricCard('Expected Price', '₹' + _fmt(sw.expected_price), 'on Day ' + sw.wait_days) +
        _metricCard('Est. Gain/QTL', '₹' + _fmt(sw.expected_gain_per_qtl), 'before storage') +
        _metricCard('Net Benefit/QTL', '₹' + _fmt(sw.net_benefit_per_qtl), 'after storage cost') +
      '</div>';
    }

    if (sw.data_quality_note) {
      html += '<p style="font-size:0.7rem;color:#D97706;margin-top:var(--space-2);padding:var(--space-2);background:rgba(217,119,6,0.07);border-radius:var(--radius-md);">⚠ ' + sw.data_quality_note + '</p>';
    }

    html += '<p style="font-size:0.67rem;color:var(--color-slate-400);margin-top:var(--space-2);">Based on available historical data from government mandi records. Not financial advice.</p>';
    html += '</div>';
    return html;
  }

  /* ── Main result renderer ──────────────────────────────────────────── */
  function _renderResult(data) {
    // Selection info
    var selEl = document.getElementById(IDS.selectionInfo);
    if (selEl) {
      selEl.innerHTML =
        '<strong>' + _esc(data.commodity) + '</strong><br>' +
        _esc(data.state) + ' → ' + _esc(data.district) + ' → ' + _esc(data.market);
    }

    // Data source info
    var dataEl = document.getElementById(IDS.dataInfo);
    if (dataEl) {
      var latestPrice = data.latest_price
        ? '<br><strong>Latest actual in dataset: ₹' + _fmt(data.latest_price) + '/QTL</strong> on ' + _esc(data.date_range.end) +
          (data.confidence && data.confidence.stale_data ? ' <span style="color:#D97706;">(not today&rsquo;s live quote — data is ' + data.confidence.days_since_last_record + ' days old)</span>' : '')
        : '';
      var lines = '<span style="color:var(--color-slate-400);font-size:0.68rem;">Source: ' + _esc(data.data_source || 'Historical mandi CSVs') + '</span>' +
        latestPrice +
        '<br>Historical records: <strong>' + _esc(data.historical_records) + '</strong>' +
        (data.date_range ? '<br>Date range: ' + _esc(data.date_range.start) + ' – ' + _esc(data.date_range.end) : '') +
        (data.context_length ? '<br>Forecast context: ' + data.context_length + ' observations' : '') +
        (data.confidence ? '<br>Confidence: <strong>' + _esc(data.confidence.label) + '</strong>' : '');

      if (data.gap_info) {
        lines += '<br><span style="color:#D97706;font-size:0.68rem;">⚠ ' + data.gap_info + '</span>';
      }
      if (data.n_winsorized && data.n_winsorized > 0) {
        lines += '<br><span style="color:var(--color-slate-400);font-size:0.68rem;">' + data.n_winsorized + ' extreme value(s) corrected (data quality).</span>';
      }
      if (data.forecast_sanity && data.forecast_sanity.applied) {
        lines += '<br><span class="badge">FORECAST ADJUSTED</span> <span style="color:#9F1239;font-size:0.72rem;">Model forecast was outside the recent market range, so the latest validated market value is being used. Unit: INR/quintal.</span>';
      }
      dataEl.innerHTML = lines;
    }

    // Sparkline
    _renderSparkline(data.forecast);

    // Forecast table with quantiles
    var tableEl = document.getElementById(IDS.forecastTable);
    if (tableEl && data.forecast) {
      var header = '<div style="display:grid;grid-template-columns:50px 1fr 1fr 1fr 1fr;gap:2px;padding:4px 0;border-bottom:2px solid var(--color-slate-200);font-size:0.68rem;font-weight:var(--weight-bold);color:var(--color-slate-500);">' +
        '<span>Day</span><span>Date</span><span>P10</span><span>P50</span><span>P90</span></div>';

      var rows = data.forecast.map(function (f) {
        var isRising = data.forecast.length > 1 && f.price > data.latest_price;
        var priceColor = isRising ? '#10B981' : '#E11D48';
        return '<div style="display:grid;grid-template-columns:60px 1fr 1fr 1fr 1fr;gap:2px;padding:5px 0;border-bottom:1px solid var(--color-slate-100);font-size:var(--text-xs);">' +
          '<span style="color:var(--color-slate-400);">Day ' + f.day + '</span>' +
          '<span style="color:var(--color-slate-600);">' + _esc(f.date || '') + '</span>' +
          '<span style="color:var(--color-slate-500);">₹' + _fmt(f.p10 != null ? f.p10 : f.price_low || f.price) + '</span>' +
          '<span style="font-weight:var(--weight-bold);color:' + priceColor + ';">₹' + _fmt(f.p50 != null ? f.p50 : f.price) + '</span>' +
          '<span style="color:var(--color-slate-500);">₹' + _fmt(f.p90 != null ? f.p90 : f.price_high || f.price) + '</span>' +
        '</div>';
      }).join('');

      tableEl.innerHTML = header + rows +
        '<div style="font-size:0.65rem;color:var(--color-slate-400);margin-top:4px;">P10 / P50 / P90 are model outputs (INR/quintal), not live mandi quotes.' +
        (data.forecast_sanity && data.forecast_sanity.applied ? ' Displayed path uses the latest validated modal after scale check.' : '') +
        '</div>';
    }

    // Sale-window recommendation
    var evalBlock   = document.getElementById(IDS.evalBlock);
    var evalMetrics = document.getElementById(IDS.evalMetrics);
    if (evalBlock && evalMetrics) {
      evalBlock.hidden = false;
      var ehtml = '';

      // Sale window section
      if (data.sale_window) {
        ehtml += _renderSaleWindow(data.sale_window);
      }

      // Evaluation metrics (divider)
      ehtml += '<div style="font-size:var(--text-xs);font-weight:var(--weight-bold);color:var(--color-slate-500);text-transform:uppercase;letter-spacing:0.08em;margin-top:var(--space-4);margin-bottom:var(--space-2);">📊 Model Evaluation (Holdout Backtest)</div>';

      if (data.evaluation) {
        var ev = data.evaluation;
        var vsNaive = ev.chronos_vs_naive_pct;
        var vsColor = vsNaive > 0 ? '#10B981' : '#E11D48';
        ehtml += '<div style="display:flex;flex-wrap:wrap;gap:var(--space-2);margin-bottom:var(--space-3);">' +
          _metricCard('Chronos MAE',  '₹' + _fmt(ev.mae),  'Lower = better') +
          _metricCard('Chronos RMSE', '₹' + _fmt(ev.rmse), '') +
          _metricCard('Chronos MAPE', ev.mape.toFixed(1) + '%', '') +
        '</div>';
        if (ev.baseline_naive) {
          ehtml += '<div style="font-size:0.68rem;color:var(--color-slate-500);margin-bottom:4px;">Baseline comparison (7-day holdout):</div>' +
          '<div style="display:flex;flex-wrap:wrap;gap:var(--space-2);">' +
            _metricCard('Naive MAE',  '₹' + _fmt(ev.baseline_naive.mae),  'Last-price baseline') +
            _metricCard('MA7 MAE',    '₹' + _fmt(ev.baseline_ma7.mae),    '7-day avg baseline') +
          '</div>';
          if (vsNaive !== undefined) {
            ehtml += '<div style="font-size:0.68rem;margin-top:6px;color:' + vsColor + ';">' +
              (vsNaive > 0 ? '✓ Chronos outperforms naive by ' : '✗ Chronos underperforms naive by ') +
              Math.abs(vsNaive).toFixed(1) + '% on MAE in this holdout window.</div>';
          }
        }
      } else {
        ehtml += '<span style="font-size:var(--text-xs);color:var(--color-slate-500);font-style:italic;">' +
          'Insufficient historical observations for a reliable holdout backtest.' +
          '</span>';
      }

      evalMetrics.innerHTML = ehtml;
    }

    // Update ML badge
    var badge = document.getElementById(IDS.mlBadge);
    if (badge) { badge.textContent = 'Chronos Connected'; badge.className = 'badge badge-success'; }

    _setResultState('result');

    // Fire custom event so other modules (Best Action, etc.) can react
    document.dispatchEvent(new CustomEvent('kl:forecastReady', { detail: data }));
  }

  /* ── Forecast request ──────────────────────────────────────────────── */
  function _onFetchClick() {
    var selection = _readSelection();
    var crop = selection.commodity;
    var state = selection.state;
    var district = selection.district;
    var market = selection.market;

    if (!crop || !state || !district || !market) {
      var msgEl = document.getElementById(IDS.errorMsg);
      if (msgEl) msgEl.textContent = 'Please select Commodity, State, District and Market.';
      _setResultState('error');
      return;
    }

    requestState.epoch += 1;
    _abort('forecastController');
    _abort('comparisonController');
    _abort('intelligenceController');
    var token = requestState.epoch;
    _setCurrentSelection(selection);
    _clearForecastDependentUi('Loading current market forecast...');
    _setResultState('loading');
    var btn = document.getElementById(IDS.fetchBtn);
    if (btn) { btn.disabled = true; btn.textContent = 'Running Chronos...'; }

    requestState.forecastController = new AbortController();
    fetch(API_BASE + '/api/forecast', {
      method:  'POST',
      headers: { 'Content-Type': 'application/json' },
      signal: requestState.forecastController.signal,
      body:    JSON.stringify({ commodity: crop, state: state, district: district, market: market }),
    })
    .then(function (res) {
      return res.json().then(function (d) { return { status: res.status, data: d }; });
    })
    .then(function (result) {
      if (!_isCurrent(token, selection)) return;
      if (result.data.success) {
        _renderResult(result.data);
        // Also trigger market comparison for this district
        _loadMarketCompare(selection, token);
        _loadMarketIntel(selection, token);
      } else {
        var errMsg = result.data.error || 'Forecast failed.';
        if (result.data.available_markets && result.data.available_markets.length > 0) {
          errMsg += '\n\nAvailable markets in this district: ' + result.data.available_markets.join(', ');
        }
        var msgEl = document.getElementById(IDS.errorMsg);
        if (msgEl) msgEl.textContent = errMsg;
        _setResultState('error');
      }
    })
    .catch(function (err) {
      if (!_isCurrent(token, selection) || err.name === 'AbortError') return;
      var msgEl = document.getElementById(IDS.errorMsg);
      if (msgEl) msgEl.textContent = 'Could not connect to forecast API. Start the backend: python backend/app.py\n\nError: ' + err.message;
      _clearForecastDependentUi('Forecast unavailable for the current selection.');
      _setResultState('error');
    })
    .finally(function () {
      if (!_isCurrent(token, selection)) return;
      requestState.forecastController = null;
      if (btn) { btn.disabled = false; btn.textContent = 'Generate Forecast'; }
      _updateFetchButton();
    });
  }

  /* ── Market Comparison loader ──────────────────────────────────────── */
  function _loadMarketCompare(selection, token) {
    var commodity = selection.commodity;
    var state = selection.state;
    var district = selection.district;
    var selectedMarket = selection.market;
    var mcSection = document.getElementById('market-compare-section');
    var mcBody    = document.getElementById('mc-table-body');
    var mcNote    = document.getElementById('mc-api-note');
    var mcOrigin  = document.getElementById('mc-origin-label');
    var mcCrop    = document.getElementById('mc-crop-label');
    if (!mcBody) return;

    if (mcOrigin) mcOrigin.textContent = district + ', ' + state;
    if (mcCrop)   mcCrop.textContent   = commodity;
    if (mcNote)   mcNote.hidden        = false;

    _abort('comparisonController');
    requestState.comparisonController = new AbortController();
    fetch(API_BASE + '/api/market-compare?commodity=' + encodeURIComponent(commodity) +
          '&state=' + encodeURIComponent(state) + '&district=' + encodeURIComponent(district), {
            signal: requestState.comparisonController.signal,
          })
    .then(function (res) {
      if (!res.ok) throw new Error('API error: ' + res.status);
      return res.json();
    })
    .then(function (d) {
      if (!_isCurrent(token, selection)) return;
      if (!d.success || !d.markets || !d.markets.length) {
        mcBody.innerHTML = '<tr><td colspan="6" style="font-size:var(--text-xs);color:var(--color-slate-400);padding:8px;">No market data found for this district.</td></tr>';
        return;
      }
      var rows = d.markets.map(function (m) {
        var isSel = m.market.toLowerCase() === selectedMarket.toLowerCase();
        return '<tr style="' + (isSel ? 'background:rgba(16,185,129,0.07);font-weight:600;' : '') + '">' +
          '<td style="font-size:var(--text-xs);padding:6px 4px;">' + _esc(m.market) + (isSel ? ' ★' : '') + '</td>' +
          '<td style="font-size:var(--text-xs);font-family:monospace;">₹' + Number(m.latest_price || 0).toLocaleString('en-IN') + '</td>' +
          '<td style="font-size:var(--text-xs);">' + _esc(m.latest_date) + '</td>' +
          '<td style="font-size:var(--text-xs);color:' + (m.stale_data ? '#D97706' : 'var(--color-slate-500)') + ';">' +
            (m.days_since_update != null ? m.days_since_update + 'd' : '—') +
            (m.stale_data ? ' (stale)' : '') + '</td>' +
          '<td style="font-size:var(--text-xs);">' + _esc(m.record_count) + '</td>' +
          '<td style="font-size:var(--text-xs);">' + (m.has_enough_data ? 'Enough for forecast' : 'Sparse') + '</td>' +
        '</tr>';
      }).join('');
      mcBody.innerHTML = rows;

      // Remove demo badge
      var demoTag = mcSection && mcSection.querySelector('.badge-demo');
      if (demoTag) demoTag.textContent = 'Real Data';

      // Update note
      if (mcNote) {
        mcNote.innerHTML = '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" style="flex-shrink:0;color:#10B981;"><path d="M9 12l2 2 4-4m6 2a9 9 0 1 1-18 0 9 9 0 0 1 18 0z"/></svg>' +
          '<p style="font-size:var(--text-xs);color:#065F46;">Latest modal prices from the combined historical dataset for ' +
          _esc(commodity) + ' in <strong>' + _esc(district) + ', ' + _esc(state) +
          '</strong>. Dates shown are last observation dates, not live ticks.</p>';
      }
    })
    .catch(function (err) {
      if (!_isCurrent(token, selection) || err.name === 'AbortError') return;
      if (mcBody) mcBody.innerHTML = '<tr><td colspan="6" style="font-size:var(--text-xs);color:var(--color-slate-400);padding:8px;">Market comparison unavailable. ' + err.message + '</td></tr>';
    })
    .finally(function () {
      if (_isCurrent(token, selection)) requestState.comparisonController = null;
    });
  }

  function _loadMarketIntel(selection, token) {
    var params = new URLSearchParams({
      commodity: selection.commodity,
      state: selection.state,
      district: selection.district,
      market: selection.market,
    });
    _abort('intelligenceController');
    requestState.intelligenceController = new AbortController();
    fetch(API_BASE + '/api/market-intel?' + params.toString(), {
      signal: requestState.intelligenceController.signal,
    })
      .then(function (res) {
        if (!res.ok) throw new Error('API error: ' + res.status);
        return res.json();
      })
      .then(function (data) {
        if (!_isCurrent(token, selection) || !data.success) return;
        var miBody = document.getElementById('market-intel-body');
        if (!miBody) return;
        miBody.setAttribute('data-selection-key', _selectionKey(selection));
        var latest = typeof data.latest_price === 'number' ? '₹' + _fmt(data.latest_price) : '—';
        miBody.innerHTML = '<tr style="background:rgba(16,185,129,0.05);">' +
          '<td><div class="font-semibold text-slate-900">' + _esc(data.market) + ' (Selected)</div></td>' +
          '<td class="price-cell">' + latest + '/QTL</td>' +
          '<td>' + _esc(data.latest_date) + (data.stale_data ? ' (stale)' : '') + '</td>' +
          '<td class="font-mono text-xs">' + _esc(data.historical_records) + '</td>' +
          '<td class="text-xs">' + _esc(data.context_length) + ' obs</td>' +
          '<td class="text-xs">' + (data.gap_info ? 'Gap noted' : 'No large gap') +
            (data.n_winsorized ? '; ' + data.n_winsorized + ' outlier(s) clipped' : '') + '</td>' +
          '<td class="text-xs">' + _esc(data.data_confidence || '—') + '</td></tr>';
      })
      .catch(function (err) {
        if (!_isCurrent(token, selection) || err.name === 'AbortError') return;
        var miBody = document.getElementById('market-intel-body');
        if (miBody) miBody.innerHTML = '<tr><td colspan="7">Market intelligence unavailable for the current selection.</td></tr>';
      })
      .finally(function () {
        if (_isCurrent(token, selection)) requestState.intelligenceController = null;
      });
  }

  /* ── Initialization ────────────────────────────────────────────────── */
  function init() {
    var section = document.getElementById(IDS.section);
    if (!section) return;

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

    // Wire MC fetch button too (in case user clicks it independently)
    var mcBtn = document.getElementById('mc-fetch-btn');
    if (mcBtn) {
      mcBtn.addEventListener('click', function () {
        var crop     = document.getElementById(IDS.cropSelect).value;
        var state    = document.getElementById(IDS.stateSelect).value;
        var district = document.getElementById(IDS.districtSelect).value;
        var market   = document.getElementById(IDS.marketSelect).value;
        if (crop && state && district) {
          var selection = { commodity: crop, state: state, district: district, market: market || '' };
          _beginSelectionChange();
          _setCurrentSelection(selection);
          _loadMarketCompare(selection, requestState.epoch);
        } else {
          alert('Please select Commodity, State, and District first using the Price Forecast section above.');
        }
      });
    }

    loadCrops();
    console.info('[KL_PriceForecast] Module initialised (Chronos ML API connected).');
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }

  return {
    loadCrops: loadCrops,
    getCurrentSelection: function () { return _readSelection(); },
  };
})();


window.KL_PriceForecast = KL_PriceForecast;

document.addEventListener('kl:forecastCleared', function () {
  var ids = [
    'ba-crop', 'ba-quality', 'ba-location', 'ba-market-price',
    'ba-forecast', 'ba-demand', 'ba-logistics', 'ba-net-realisation',
  ];
  ids.forEach(function (id) {
    var el = document.getElementById(id);
    if (el) el.textContent = '—';
  });
  var chip = document.getElementById('ba-recommendation-chip');
  if (chip) {
    chip.textContent = 'Generate Forecast First';
    chip.style.background = 'var(--color-slate-200)';
    chip.style.color = 'var(--color-slate-600)';
  }
  var reason = document.getElementById('ba-rec-reason');
  if (reason) reason.textContent = 'Select a market and generate a forecast above — the recommendation will update from real data.';
  var recIdle = document.getElementById('rec-idle-state');
  var recResult = document.getElementById('rec-result-state');
  if (recIdle) recIdle.hidden = false;
  if (recResult) recResult.hidden = true;
  var miBody = document.getElementById('market-intel-body');
  if (miBody) miBody.innerHTML = '<tr><td colspan="7">Select a market and generate a forecast to load current market intelligence.</td></tr>';
  var mcBody = document.getElementById('mc-table-body');
  if (mcBody) mcBody.innerHTML = '<tr><td colspan="6">Select a market and generate a forecast to load market comparison.</td></tr>';
});

/* =========================================================================
   kl:forecastReady listener — wires Best Action + Recommendations sections
   from real forecast API data. No hardcoded values.
   ========================================================================= */
document.addEventListener('kl:forecastReady', function (e) {
  var data = e.detail;
  if (!data) return;

  // Publish the best forecast point so the Best Action breakdown can show a
  // real "sell now vs wait" comparison. Uses the decision engine's own
  // recommended day when it gave one, else the last day of the horizon.
  try {
    var fdays = data.forecast || [];
    if (fdays.length) {
      var pick = null;
      var recDay = data.sale_window && data.sale_window.recommended_day;
      if (recDay != null) {
        pick = fdays.filter(function (f) { return f.day === recDay; })[0] || null;
      }
      if (!pick) pick = fdays[fdays.length - 1];
      var p50 = pick.p50 != null ? pick.p50 : pick.price;
      window.__klLastForecast = {
        p50: Number(p50),
        day: pick.day || fdays.length,
        date: pick.date || '',
        latest_price: Number(data.latest_price),
        market: data.market || '',
        commodity: data.commodity || '',
      };
    } else {
      window.__klLastForecast = null;
    }
  } catch (err) {
    window.__klLastForecast = null;
  }

  var sw = data.sale_window;

  /* ── Best Action section ─────────────────────────────────────────── */
  var baMarketPrice   = document.getElementById('ba-market-price');
  var baForecast      = document.getElementById('ba-forecast');
  var baDemand        = document.getElementById('ba-demand');
  var baNetReal       = document.getElementById('ba-net-realisation');
  var baChip          = document.getElementById('ba-recommendation-chip');
  var baReason        = document.getElementById('ba-rec-reason');
  var baCrop          = document.getElementById('ba-crop');
  var baQuality       = document.getElementById('ba-quality');
  var baLocation      = document.getElementById('ba-location');

  // Update crop/quality/location fields from selected market
  if (baCrop)     baCrop.textContent    = data.commodity || '—';
  if (baQuality)  baQuality.textContent = '—';  // grade not in forecast response; user sets it when creating lot
  if (baLocation) baLocation.textContent = data.market + ', ' + data.district + ', ' + data.state;

  // Update KPI widgets (stat section top of page)
  var statBestNet     = document.getElementById('stat-best-net-realisation');
  var statBestNetSub  = document.getElementById('stat-best-net-subtext');
  if (statBestNet && data.latest_price) {
    statBestNet.textContent    = '₹' + data.latest_price.toLocaleString('en-IN');
    if (statBestNetSub) statBestNetSub.textContent = data.market + ' latest price';
  }


  var latestPrice = data.latest_price;
  var fmt = function(v) {
    return typeof v === 'number'
      ? '₹' + v.toLocaleString('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
      : String(v || '—');
  };

  if (baMarketPrice && latestPrice) {
    baMarketPrice.textContent = fmt(latestPrice) + ' / QTL';
    baMarketPrice.title = 'As of ' + data.date_range.end;
  }

  if (baForecast && data.forecast && data.forecast.length) {
    var lastDay = data.forecast[data.forecast.length - 1];
    var firstDay = data.forecast[0];
    var trend = lastDay.price > latestPrice ? '▲ Rising' : lastDay.price < latestPrice ? '▼ Falling' : '→ Flat';
    baForecast.innerHTML = fmt(firstDay.price) + '–' + fmt(lastDay.price) +
      '<br><small style="color:var(--color-slate-500);">' + trend + ' over 7 days</small>';
  }

  if (baDemand) {
    baDemand.textContent = 'Platform buyers available — click View Matches';
  }

  if (baNetReal && sw) {
    baNetReal.textContent = sw.wait_days === 0
      ? fmt(latestPrice) + ' / QTL (sell now)'
      : fmt(sw.expected_price) + ' / QTL (on Day ' + sw.wait_days + ')';
  }

  if (baChip && sw) {
    var action = sw.action || 'MONITOR';
    var isWait = action.startsWith('WAIT');
    var chipLabel = isWait ? ('Wait ' + sw.wait_days + ' Day' + (sw.wait_days > 1 ? 's' : '')) : 'Sell Now';
    var chipColor = isWait ? '#D97706' : '#10B981';
    baChip.textContent = chipLabel;
    baChip.style.background = chipColor;
    baChip.style.color = '#fff';
    baChip.className = 'ba-rec-chip';
  }

  if (baReason && sw) {
    baReason.textContent = sw.reason || '';
  }

  /* ── Recommendations section ─────────────────────────────────────── */
  var recIdle   = document.getElementById('rec-idle-state');
  var recResult = document.getElementById('rec-result-state');
  var recContent = document.getElementById('rec-content');

  if (recIdle)   recIdle.hidden   = true;
  if (recResult) recResult.hidden = false;

  if (recContent && sw && data.forecast) {
    var recChipColor = (sw.action || '').startsWith('WAIT') ? '#D97706' : '#10B981';
    var recAction = (sw.action || '').startsWith('WAIT')
      ? 'Wait ' + sw.wait_days + ' Day' + (sw.wait_days > 1 ? 's' : '')
      : 'Sell Now';

    var priceRows = data.forecast.slice(0, 4).map(function(f) {
      var vs = f.price - latestPrice;
      var vsStr = vs > 0 ? '<span style="color:#10B981;">+₹' + vs.toFixed(0) + '</span>'
                        : vs < 0 ? '<span style="color:#E11D48;">-₹' + Math.abs(vs).toFixed(0) + '</span>'
                        : '—';
      return '<div style="display:flex;justify-content:space-between;font-size:0.7rem;padding:3px 0;">' +
        '<span style="color:var(--color-slate-500);">Day ' + f.day + ' (' + f.date + ')</span>' +
        '<span>₹' + f.price.toLocaleString('en-IN') + ' ' + vsStr + '</span>' +
      '</div>';
    }).join('');

    recContent.innerHTML =
      '<div class="rec-header" style="margin-bottom:var(--space-3);">' +
        '<div>' +
          '<div class="rec-lot-name">' + data.commodity + ' — ' + data.market + '</div>' +
          '<div class="rec-target-market" style="font-size:0.7rem;color:var(--color-slate-500);">' +
            data.state + ' › ' + data.district + ' | Latest price: ' + fmt(latestPrice) + '/QTL (' + data.date_range.end + ')' +
          '</div>' +
        '</div>' +
        '<div style="display:flex;flex-direction:column;align-items:flex-end;gap:4px;">' +
          '<span style="display:inline-flex;align-items:center;padding:6px 14px;border-radius:999px;background:' + recChipColor + ';color:#fff;font-weight:700;font-size:var(--text-sm);">' + recAction + '</span>' +
          '<span style="font-size:0.65rem;color:var(--color-slate-400);">Uncertainty: ' + (sw.uncertainty || '?') + '</span>' +
        '</div>' +
      '</div>' +

      '<div class="breakdown-table" style="margin-bottom:var(--space-3);">' +
        '<div class="breakdown-row">' +
          '<span class="breakdown-label">Current Market Price</span>' +
          '<span class="breakdown-value">' + fmt(latestPrice) + ' / QTL</span>' +
        '</div>' +
        '<div class="breakdown-row">' +
          '<span class="breakdown-label">7-Day Forecast Range</span>' +
          '<span class="breakdown-value">' +
            fmt(Math.min.apply(null, data.forecast.map(function(f){return f.price_low||f.price;}))) + ' – ' +
            fmt(Math.max.apply(null, data.forecast.map(function(f){return f.price_high||f.price;}))) + ' / QTL' +
          '</span>' +
        '</div>' +
        (sw.wait_days > 0 ? [
          '<div class="breakdown-row"><span class="breakdown-label">Expected Price on Day ' + sw.wait_days + '</span>' +
          '<span class="breakdown-value text-emerald">' + fmt(sw.expected_price) + ' / QTL</span></div>',
          '<div class="breakdown-row"><span class="breakdown-label">Estimated Gain per QTL</span>' +
          '<span class="breakdown-value text-emerald">+' + fmt(sw.expected_gain_per_qtl) + '</span></div>',
        ].join('') : '') +
        '<div class="breakdown-row"><span class="breakdown-label">Historical Records Used</span>' +
          '<span class="breakdown-value">' + data.historical_records + ' records (' + data.date_range.start + ' – ' + data.date_range.end + ')</span></div>' +
      '</div>' +

      '<div style="margin-bottom:var(--space-3);">' +
        '<div style="font-size:0.68rem;font-weight:700;color:var(--color-slate-500);margin-bottom:4px;">Forecast Sample (first 4 days):</div>' +
        priceRows +
      '</div>' +

      '<div style="background:var(--color-primary-50);padding:var(--space-3);border-radius:var(--radius-md);border:1px solid var(--color-primary-200);">' +
        '<h4 style="font-size:var(--text-xs);font-weight:700;color:var(--color-primary-900);margin-bottom:6px;">Why this recommendation?</h4>' +
        '<p style="font-size:0.7rem;color:var(--color-slate-700);">' + (sw.reason || '') + '</p>' +
        (sw.data_quality_note ? '<p style="font-size:0.68rem;color:#D97706;margin-top:6px;">⚠ ' + sw.data_quality_note + '</p>' : '') +
        (data.data_note ? '<p style="font-size:0.68rem;color:var(--color-slate-500);margin-top:4px;">' + data.data_note + '</p>' : '') +
      '</div>';
  }

});
