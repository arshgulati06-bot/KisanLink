/**
 * KisanLink — Farmer dashboard wiring (quick actions, profile, language).
 * Market prices, forecasts, and buyer scores come from the API modules.
 * This file must not inject demo mandi prices or hardcoded sale decisions.
 */

var KL_Step4 = (function () {

  function _initQuickActions() {
    var chips = document.querySelectorAll('.qa-chip');
    chips.forEach(function (chip) {
      chip.addEventListener('click', function () {
        var action = chip.getAttribute('data-qa-action');
        switch (action) {
          case 'sellNow':
            _scrollToSection('best-action-section');
            if (typeof window.klRunSellNow === 'function') window.klRunSellNow();
            break;
          case 'wait':
            _scrollToSection('price-forecast-section');
            break;
          case 'compare':
            _scrollToSection('market-compare-section');
            break;
          case 'checkQuality':
            _scrollToSection('crop-quality-section');
            break;
          case 'findBuyers':
            _scrollToSection('buyer-matches-section');
            break;
        }
      });
    });
  }

  function _scrollToSection(sectionId) {
    var el = document.getElementById(sectionId);
    if (el) {
      el.scrollIntoView({ behavior: 'smooth', block: 'start' });
      el.classList.add('pulse-highlight');
      setTimeout(function () { el.classList.remove('pulse-highlight'); }, 1800);
    }
  }

  function _renderProfile() {
    var state = window.dashboardState;
    var profile = state ? state.state.farmerProfile : null;
    if (!profile) return;
    _setVal('profile-name', profile.name || 'Farmer');
    _setVal('profile-location', profile.location || '');
    _setVal('profile-contact', profile.contact || profile.phone || '');
    _setVal('profile-lang', (window.KL_I18n && window.KL_I18n.getLocale()) ? window.KL_I18n.getLocale().toUpperCase() : 'English');
  }

  function _initLanguageSelector() {
    var selects = document.querySelectorAll('.kl-lang-select, [data-lang-select]');
    selects.forEach(function (sel) {
      sel.addEventListener('change', function () {
        if (window.KL_I18n) window.KL_I18n.setLocale(sel.value);
      });
    });
    var btns = document.querySelectorAll('[data-lang-btn]');
    btns.forEach(function (btn) {
      btn.addEventListener('click', function () {
        var locale = btn.getAttribute('data-lang-btn');
        if (window.KL_I18n) window.KL_I18n.setLocale(locale);
      });
    });
    document.addEventListener('kl:localeChanged', function () {
      _renderProfile();
    });
  }

  function _setVal(id, text) {
    var el = document.getElementById(id);
    if (el) el.textContent = text;
  }

  function _loadIngestBanner() {
    var el = document.getElementById('ingest-status-banner');
    if (!el || !window.getIngestStatus) return;
    window.getIngestStatus().then(function (d) {
      var latest = d.latest_date_in_dataset || 'unknown';
      var live = d.live_api_connected ? 'Official API configured.' : 'Official live API is not configured.';
      el.textContent = 'Dataset latest date: ' + latest + ' · ' + (d.total_records || 0).toLocaleString('en-IN') + ' records · ' + live;
    }).catch(function () {
      el.textContent = 'Backend unavailable — start python backend/app.py to load the historical mandi dataset.';
    });
  }

  function init() {
    _initQuickActions();
    _renderProfile();
    _initLanguageSelector();
    _loadIngestBanner();
    _wireSellNow();
    _fillCommoditySelects();
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    setTimeout(init, 0);
  }

  function _fillCommoditySelects() {
    var API_BASE = (window.CONFIG && window.CONFIG.API_BASE_URL)
      ? window.CONFIG.API_BASE_URL.replace(/\/api\/?$/, '')
      : 'http://localhost:5000';
    fetch(API_BASE + '/api/commodities').then(function (r) { return r.json(); }).then(function (crops) {
      if (!Array.isArray(crops)) return;
      window.__klCommodities = crops;
      ['lot-crop', 'mp-commodity', 'cqa-crop-select'].forEach(function (id) {
        var el = document.getElementById(id);
        if (!el) return;
        var current = el.value;
        el.innerHTML = '<option value="">Select commodity…</option>';
        crops.forEach(function (c) {
          var opt = document.createElement('option');
          opt.value = c;
          opt.textContent = c;
          el.appendChild(opt);
        });
        if (current) el.value = current;
      });
      function wireFilter(searchId, selectId) {
        var search = document.getElementById(searchId);
        var select = document.getElementById(selectId);
        if (!search || !select || search.dataset.wired) return;
        search.dataset.wired = '1';
        search.addEventListener('input', function () {
          var q = search.value.toLowerCase();
          var current = select.value;
          select.innerHTML = '<option value="">Select commodity…</option>';
          crops.filter(function (c) { return !q || String(c).toLowerCase().indexOf(q) >= 0; }).forEach(function (c) {
            var opt = document.createElement('option');
            opt.value = c;
            opt.textContent = c;
            select.appendChild(opt);
          });
          if (current) select.value = current;
        });
      }
      wireFilter('lot-crop-search', 'lot-crop');
      wireFilter('cqa-crop-search', 'cqa-crop-select');
    }).catch(function () {});
  }

  function _fmtInr(v) {
    var n = Number(v);
    if (!isFinite(n)) return '—';
    return '₹' + n.toLocaleString('en-IN', { maximumFractionDigits: 0 });
  }

  function _selectedOutlook() {
    return {
      commodity: (document.getElementById('pf-crop-select') || {}).value || '',
      state: (document.getElementById('pf-state-select') || {}).value || '',
      district: (document.getElementById('pf-district-select') || {}).value || '',
      market: (document.getElementById('pf-market-select') || {}).value || '',
    };
  }

  function _wireSellNow() {
    var btn = document.getElementById('sn-run-btn');
    if (btn) btn.addEventListener('click', function () { window.klRunSellNow(); });
    var gpsBtn = document.getElementById('sn-gps-btn');
    if (gpsBtn) gpsBtn.addEventListener('click', _useGps);
  }

  function _gpsStatus(text) {
    var el = document.getElementById('sn-gps-status');
    if (el) el.textContent = text || '';
  }

  function _useGps() {
    _gpsStatus('Requesting location permission…');
    if (!navigator.geolocation) {
      _gpsStatus('This browser cannot provide GPS. Select state and district in Price Outlook.');
      return;
    }
    navigator.geolocation.getCurrentPosition(function (pos) {
      var lat = pos.coords.latitude;
      var lon = pos.coords.longitude;
      window.__klGps = { lat: lat, lon: lon };
      _gpsStatus('Got GPS (' + lat.toFixed(4) + ', ' + lon.toFixed(4) + '). Looking up district…');
      var runner = window.reverseGeocode || function (a, b) {
        return window.apiClient.get('/location/reverse?lat=' + encodeURIComponent(a) + '&lon=' + encodeURIComponent(b))
          .then(function (r) { return r.data; });
      };
      runner(lat, lon).then(function (data) {
        if (!data || !data.success) {
          _gpsStatus('GPS received. Reverse lookup unavailable — keep using selected district.');
          return;
        }
        window.__klGps.state = data.state || '';
        window.__klGps.district = data.district || '';
        var st = document.getElementById('pf-state-select');
        var dt = document.getElementById('pf-district-select');
        if (st && data.state) {
          st.value = data.state;
          st.dispatchEvent(new Event('change'));
        }
        if (dt && data.district) {
          setTimeout(function () {
            dt.value = data.district;
            dt.dispatchEvent(new Event('change'));
          }, 400);
        }
        _gpsStatus('Using current location: ' + (data.district || '') + (data.state ? ', ' + data.state : '') + '. Coordinates are not stored.');
      }).catch(function () {
        _gpsStatus('GPS received. Reverse lookup unavailable — keep using selected district.');
      });
    }, function (err) {
      window.__klGps = null;
      var denied = err && (err.code === 1 || err.code === err.PERMISSION_DENIED);
      if (denied) {
        _gpsStatus('Location permission denied — using selected district.');
      } else {
        _gpsStatus('GPS permission was denied. Select your district manually.');
      }
    }, { enableHighAccuracy: true, timeout: 15000, maximumAge: 0 });
  }

  function _badge(rec) {
    if (rec.is_live_price) return '<span class="badge badge-success">LIVE</span>';
    return '<span class="badge">LATEST AVAILABLE</span>';
  }

  function _distLine(rec) {
    if (!rec || rec.distance_km == null) return 'Distance unavailable';
    if (rec.distance_estimated) {
      return rec.distance_km + ' km (straight-line estimate)';
    }
    var t = rec.duration_minutes != null ? ' · Travel time: ' + Math.round(rec.duration_minutes) + ' min' : '';
    return rec.distance_km + ' km road' + t;
  }

  window.klRunSellNow = function () {
    var sel = _selectedOutlook();
    var qtyEl = document.getElementById('sn-qty');
    var status = document.getElementById('sn-status');
    var box = document.getElementById('sn-result');
    var qty = qtyEl ? Number(qtyEl.value) : 10;
    if (!sel.commodity || !sel.state || !sel.district) {
      if (status) status.textContent = 'Select commodity, state and district in Price Outlook first, then run this comparison.';
      return;
    }
    if (status) status.textContent = 'Comparing markets, routes, and net realisation…';
    if (box) box.innerHTML = '';
    var runner = window.getSellNowPlan || function (opts) {
      return window.apiClient.post('/sell-now', opts).then(function (r) { return r.data; });
    };
    var payload = {
      commodity: sel.commodity,
      state: sel.state,
      district: sel.district,
      market: sel.market,
      quantity_qtl: qty,
    };
    if (window.__klGps && window.__klGps.lat != null) {
      payload.lat = window.__klGps.lat;
      payload.lon = window.__klGps.lon;
    }
    runner(payload).then(function (data) {
      if (!data || !data.success) {
        if (status) status.textContent = (data && data.error) || 'Could not rank markets.';
        if (box) box.innerHTML = '<p style="font-size:0.8rem;color:var(--color-slate-500);">No nearby market recommendation could be built for this selection.</p>';
        return;
      }
      var rec = data.recommended || {};
      var lastDate = rec.latest_date || '';
      var parts = lastDate.split('-');
      var lastLabel = parts.length === 3 ? (parts[2] + '-' + parts[1] + '-' + parts[0]) : lastDate;
      if (status) {
        status.textContent = (data.live_note || rec.freshness_label || 'Latest available mandi data') +
          (lastLabel ? ' · Last available: ' + lastLabel : '') +
          ' · ' + (data.data_source || '');
      }
      function _card(m, featured) {
        var distHint = m.distance_estimated
          ? 'Road routing unavailable. Showing estimated straight-line distance.'
          : '';
        return '<div style="border:1px solid var(--color-slate-200);border-radius:10px;padding:12px;margin-bottom:10px;' +
          (featured ? 'background:var(--color-slate-50,#f8fafc);' : '') + '">' +
          '<div style="display:flex;justify-content:space-between;gap:8px;align-items:center;margin-bottom:6px;">' +
          '<strong>' + (m.market || '—') + '</strong>' + _badge(m) + '</div>' +
          '<div style="font-size:0.9rem;font-weight:600;">Modal ' + _fmtInr(m.modal_price || m.latest_price) + '/QTL</div>' +
          '<div style="font-size:0.75rem;color:var(--color-slate-500);margin:4px 0;">Arrival: ' + (m.latest_date || '—') +
          ' · ' + (m.freshness_label || '') + '</div>' +
          '<div style="font-size:0.78rem;">Road distance: ' + _distLine(m) + '</div>' +
          (distHint ? '<div style="font-size:0.68rem;color:var(--color-slate-400);">' + distHint + '</div>' : '') +
          '<div style="font-size:0.78rem;">Estimated transport cost: ' + _fmtInr(m.transport_cost) +
          ' · Handling: ' + _fmtInr(m.handling_cost) +
          ' · Mandi fee: ' + _fmtInr(m.mandi_fee || m.mandi_fee_estimate) + '</div>' +
          '<div style="font-size:0.78rem;">Gross value: ' + _fmtInr(m.gross_value || m.gross_sale_value) +
          ' · Estimated total costs: ' + _fmtInr(m.total_cost) + '</div>' +
          '<div style="font-size:0.95rem;font-weight:700;color:var(--color-accent-green);margin-top:6px;">Estimated net realisation: ' +
          _fmtInr(m.net_realisation) +
          (m.net_per_qtl != null ? ' (' + _fmtInr(m.net_per_qtl) + '/QTL)' : '') + '</div>' +
          '<p style="font-size:0.68rem;color:var(--color-slate-400);margin:4px 0 0;">Formula: (modal × quantity) − estimated transport − handling − mandi fee. Planning estimate, not guaranteed earnings.</p></div>';
      }
      var others = (data.markets || []).slice(1, 4).map(function (m) { return _card(m, false); }).join('');
      if (box) {
        box.innerHTML =
          _card(rec, true) +
          '<p style="font-size:0.78rem;color:var(--color-slate-700);margin-bottom:10px;">' + (data.explanation || '') + '</p>' +
          '<p style="font-size:0.68rem;color:var(--color-slate-400);margin-bottom:10px;">' + (data.cost_disclaimer || '') + ' ' + (data.distance_disclaimer || '') + '</p>' +
          others +
          '<button type="button" class="btn btn-primary btn-sm" id="sn-proceed-btn" style="margin-top:12px;">Proceed to Sell</button>';
      }
      var netEl = document.getElementById('ba-net-realisation');
      if (netEl) netEl.textContent = _fmtInr(rec.net_realisation);
      var locEl = document.getElementById('ba-location');
      if (locEl) locEl.textContent = (rec.market || '') + ', ' + (rec.district || '');
      var cropEl = document.getElementById('ba-crop');
      if (cropEl) cropEl.textContent = data.commodity || sel.commodity;
      var qtyLabel = document.getElementById('ba-quantity');
      if (qtyLabel) qtyLabel.textContent = qty + ' QTL';
      var priceEl = document.getElementById('ba-market-price');
      if (priceEl) priceEl.textContent = _fmtInr(rec.latest_price) + '/QTL';
      var logEl = document.getElementById('ba-logistics');
      if (logEl) logEl.textContent = _fmtInr(rec.transport_cost) + ' est.';
      var proceed = document.getElementById('sn-proceed-btn');
      if (proceed) {
        proceed.addEventListener('click', function () {
          var crop = document.getElementById('lot-crop');
          var q = document.getElementById('lot-quantity');
          var loc = document.getElementById('lot-location');
          var price = document.getElementById('lot-price');
          var harvest = document.getElementById('lot-harvest');
          var mkt = document.getElementById('lot-market');
          var dist = document.getElementById('lot-district');
          var st = document.getElementById('lot-state');
          if (crop) crop.value = data.commodity || sel.commodity;
          if (q) q.value = qty;
          if (loc) loc.value = (rec.district || sel.district) + ', ' + (rec.state || sel.state);
          if (price) price.value = rec.latest_price || rec.modal_price || '';
          if (mkt) mkt.value = rec.market || '';
          if (dist) dist.value = rec.district || sel.district || '';
          if (st) st.value = rec.state || sel.state || '';
          if (harvest && !harvest.value) {
            var t = new Date();
            harvest.value = t.toISOString().slice(0, 10);
          }
          var modal = document.getElementById('create-lot-modal');
          if (modal) modal.classList.add('modal-open');
        });
      }
    }).catch(function (err) {
      if (status) status.textContent = (err && err.message) || 'Market comparison is temporarily unavailable.';
      if (box) box.innerHTML = '<p style="font-size:0.8rem;color:var(--color-slate-500);">Could not complete the comparison. Try again or select a different district.</p>';
    });
  };

  return { init: init };
})();

window.KL_Step4 = KL_Step4;
