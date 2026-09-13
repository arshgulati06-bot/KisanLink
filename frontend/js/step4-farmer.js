/**
 * KisanLink — Farmer dashboard wiring (quick actions, profile, language).
 * Market prices, forecasts, and buyer scores come from the API modules.
 * This file must not inject demo mandi prices or hardcoded sale decisions.
 */

var KL_Step4 = (function () {

  function _initQuickActions() {
    // Includes the hero buttons at the top of the dashboard, not just the
    // chip row, so both drive the same actions.
    var chips = document.querySelectorAll('[data-qa-action]');
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
    var warn = document.getElementById('kl-data-banner');
    if (!window.getIngestStatus) return;
    window.getIngestStatus().then(function (d) {
      var latest = d.latest_date_in_dataset || 'unknown';
      var live = d.live_api_connected ? 'Official API configured.' : 'Official live API is not configured.';
      if (el) {
        el.textContent = 'Dataset latest date: ' + latest + ' · ' +
          (d.total_records || 0).toLocaleString('en-IN') + ' records · ' + live;
      }
      var srcNote = document.getElementById('mc-source-note');
      if (srcNote) {
        srcNote.textContent = (d.data_source_label || 'Latest mandi data available to this server.') +
          ' Prices are the latest modal prices in that source, not a live official API quote.';
      }

      // Only the backend can declare the data synthetic; the UI never guesses.
      if (warn) {
        if (d.dev_fixture) {
          warn.innerHTML =
            '<span class="kl-data-banner-icon" aria-hidden="true">⚠️</span>' +
            '<span><strong>Sample data — not real mandi prices.</strong>' +
            'This server is running on the synthetic development fixture because no ' +
            'historical mandi CSVs were found in <code>ml/data/</code> and no ' +
            '<code>DATA_GOV_API_KEY</code> is configured. Every price, market, and ' +
            'net-realisation figure below is generated for demonstration only.</span>';
          warn.hidden = false;
        } else {
          warn.hidden = true;
        }
      }
    }).catch(function () {
      if (el) {
        el.textContent = 'Backend unavailable — start python backend/app.py to load the historical mandi dataset.';
      }
    });
  }

  function init() {
    _initQuickActions();
    _renderProfile();
    _initLanguageSelector();
    _loadIngestBanner();
    _wireSellNow();
    _wireOfferModal();
    _wireBestActionCtas();
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

    // The mandi archive loads in the background, so /api/commodities answers
    // 503 for the first moments after a cold start. Say so, wait for it, and
    // then fill the lists — rather than silently leaving them empty.
    function _note(msg) {
      ['lot-crop', 'mp-commodity'].forEach(function (id) {
        var el = document.getElementById(id);
        if (el && el.options.length <= 1) {
          el.innerHTML = '<option value="">' + msg + '</option>';
        }
      });
    }

    function _load() {
      return fetch(API_BASE + '/api/commodities')
        .then(function (r) {
          if (r.status === 503) return null;          // still warming
          if (!r.ok) throw new Error('HTTP ' + r.status);
          return r.json();
        })
        .then(function (crops) {
          if (crops === null) {
            _note('Loading market data…');
            if (typeof window.waitForMarketData === 'function') {
              return window.waitForMarketData().then(function (ok) {
                if (ok) return _load();
                _note('Market data unavailable');
              });
            }
            return setTimeout(_load, 4000);
          }
          return _fill(crops);
        })
        .catch(function (e) {
          console.warn('[commodities] could not load:', e);
          _note('Could not load crops — refresh');
        });
    }

    function _fill(crops) {
      if (!Array.isArray(crops)) return;
      window.__klCommodities = crops;
      // 'cqa-crop-select' is deliberately NOT filled from the full commodity
      // list: only four crops have a trained model, and offering all 325
      // guaranteed that most choices came back "unsupported crop".
      // crop-quality.js fills it from /api/ml/quality-status instead.
      ['lot-crop', 'mp-commodity'].forEach(function (id) {
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
    }

    _load();
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

  // Location states: idle → locating → found | denied | unavailable | timeout | unsupported
  function _gpsStatus(text, state) {
    var el = document.getElementById('sn-gps-status');
    if (!el) return;
    el.textContent = text || '';
    el.setAttribute('data-gps-state', state || 'idle');
    el.className = 'sn-gps-status sn-gps-status--' + (state || 'idle');
  }

  function _gpsBusy(busy) {
    var btn = document.getElementById('sn-gps-btn');
    if (!btn) return;
    btn.disabled = !!busy;
    btn.setAttribute('aria-busy', busy ? 'true' : 'false');
    if (busy) {
      if (!btn.dataset.idleLabel) btn.dataset.idleLabel = btn.textContent;
      btn.textContent = 'Locating…';
    } else if (btn.dataset.idleLabel) {
      btn.textContent = btn.dataset.idleLabel;
    }
  }

  function _useGps() {
    if (!navigator.geolocation) {
      _gpsStatus(
        'This browser cannot provide GPS. Select state and district in Price Outlook instead.',
        'unsupported'
      );
      return;
    }
    // Permission is only requested here — on an explicit click, never on load.
    _gpsBusy(true);
    _gpsStatus('Requesting location permission…', 'locating');
    navigator.geolocation.getCurrentPosition(function (pos) {
      var lat = pos.coords.latitude;
      var lon = pos.coords.longitude;
      window.__klGps = { lat: lat, lon: lon };
      _gpsStatus('Location found (' + lat.toFixed(4) + ', ' + lon.toFixed(4) + '). Looking up district…', 'locating');
      var runner = window.reverseGeocode || function (a, b) {
        return window.apiClient.get('/location/reverse?lat=' + encodeURIComponent(a) + '&lon=' + encodeURIComponent(b))
          .then(function (r) { return r.data; });
      };
      runner(lat, lon).then(function (data) {
        if (!data || !data.success) {
          _gpsBusy(false);
          _gpsStatus(
            'Location found, but the district lookup is unavailable. Your coordinates ' +
            'will still be used for distance; keep the selected district for prices.',
            'found'
          );
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
        _gpsBusy(false);
        _gpsStatus(
          'Using current location: ' + (data.district || '') +
          (data.state ? ', ' + data.state : '') + '. Coordinates are not stored.',
          'found'
        );
      }).catch(function () {
        _gpsBusy(false);
        _gpsStatus(
          'Location found, but the district lookup is unavailable. Your coordinates ' +
          'will still be used for distance; keep the selected district for prices.',
          'found'
        );
      });
    }, function (err) {
      window.__klGps = null;
      _gpsBusy(false);
      var code = err && err.code;
      if (code === 1) {
        _gpsStatus(
          'Location permission denied. Select your state and district manually in ' +
          'Price Outlook — everything else still works.',
          'denied'
        );
      } else if (code === 3) {
        _gpsStatus(
          'Timed out waiting for a GPS fix. Try again outdoors, or select your ' +
          'district manually.',
          'timeout'
        );
      } else {
        _gpsStatus(
          'Location is unavailable on this device right now. Select your district ' +
          'manually to continue.',
          'unavailable'
        );
      }
    }, { enableHighAccuracy: true, timeout: 15000, maximumAge: 0 });
  }

  function _badge(rec, synthetic) {
    if (synthetic) return '<span class="badge badge-amber">SAMPLE DATA</span>';
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

  function _sellNowBusy(busy) {
    var btn = document.getElementById('sn-run-btn');
    if (!btn) return;
    btn.disabled = !!busy;
    btn.setAttribute('aria-busy', busy ? 'true' : 'false');
    if (busy) {
      if (!btn.dataset.idleLabel) btn.dataset.idleLabel = btn.textContent;
      btn.textContent = 'Comparing markets…';
    } else if (btn.dataset.idleLabel) {
      btn.textContent = btn.dataset.idleLabel;
    }
  }


  // ---------------------------------------------------------------------
  // Best Action: money breakdown + sell-now-vs-wait, straight from the
  // backend's own net-realisation figures. Nothing is recomputed here.
  // ---------------------------------------------------------------------
  function _perQtl(total, qty) {
    var n = Number(total), q = Number(qty);
    if (!isFinite(n) || !isFinite(q) || q <= 0) return null;
    return n / q;
  }

  function _txt(id, value) {
    var el = document.getElementById(id);
    if (el) el.textContent = value;
  }

  function _renderBreakdown(rec, qty, data, sel) {
    var box = document.getElementById('ba-breakdown');
    if (!box || !rec) return;

    var gross = Number(rec.gross_value != null ? rec.gross_value : rec.gross_sale_value);
    var transport = Number(rec.transport_cost);
    var handling = Number(rec.handling_cost);
    var fee = Number(rec.mandi_fee != null ? rec.mandi_fee : rec.mandi_fee_estimate);
    var costs = Number(rec.total_cost);
    var net = Number(rec.net_realisation);

    function pair(idTotal, idPerQtl, total) {
      _txt(idTotal, _fmtInr(total));
      var pq = _perQtl(total, qty);
      _txt(idPerQtl, pq == null ? '—' : _fmtInr(pq) + '/QTL');
    }

    _txt('ba-breakdown-market', (rec.market || '—') + (rec.district ? ', ' + rec.district : ''));
    pair('ba-bd-gross', 'ba-bd-gross-qtl', gross);
    pair('ba-bd-transport', 'ba-bd-transport-qtl', transport);
    pair('ba-bd-handling', 'ba-bd-handling-qtl', handling);
    pair('ba-bd-fee', 'ba-bd-fee-qtl', fee);
    pair('ba-bd-costs', 'ba-bd-costs-qtl', costs);
    pair('ba-bd-net', 'ba-bd-net-qtl', net);

    _txt('ba-bd-distance', rec.distance_km != null ? _distLine(rec) : 'distance unavailable');

    var perQtlNet = _perQtl(net, qty);
    _txt('ba-net-per-qtl', perQtlNet == null
      ? '—'
      : _fmtInr(perQtlNet) + '/QTL net · ' + qty + ' QTL of ' + (data.commodity || sel.commodity || 'crop'));

    box.hidden = false;

    // Remember what a "Sell Now" CTA should prefill.
    window.__klRecommendation = {
      commodity: data.commodity || sel.commodity || '',
      quantity_qtl: qty,
      price_per_qtl: rec.latest_price || rec.modal_price || null,
      market: rec.market || '',
      district: rec.district || sel.district || '',
      state: rec.state || sel.state || '',
      net_realisation: net,
    };

    _renderTiming(rec, qty, net);
  }

  // Sell now vs wait, using the forecast already on the page. Only shown when
  // a real forecast P50 exists — never invented.
  function _renderTiming(rec, qty, netNow) {
    var row = document.getElementById('ba-timing');
    if (!row) return;
    var fc = window.__klLastForecast;
    var spot = Number(rec.modal_price != null ? rec.modal_price : rec.latest_price);
    if (!fc || !isFinite(Number(fc.p50)) || !isFinite(spot) || spot <= 0) {
      row.hidden = true;
      return;
    }
    var p50 = Number(fc.p50);
    // Costs do not change with the sale date, so the difference in net
    // realisation is exactly the difference in gross.
    var netWait = netNow + (p50 - spot) * qty;
    var delta = netWait - netNow;

    _txt('ba-timing-now', _fmtInr(netNow));
    _txt('ba-timing-now-note', 'At ' + _fmtInr(spot) + '/QTL today');
    _txt('ba-timing-wait', _fmtInr(netWait));
    _txt('ba-timing-wait-note', 'At forecast P50 ' + _fmtInr(p50) + '/QTL'
      + (fc.day ? ' (day ' + fc.day + ')' : ''));

    var d = document.getElementById('ba-timing-delta');
    if (d) {
      var better = delta > 0;
      d.className = 'ba-timing-delta ' + (better ? 'gain' : 'loss');
      if (Math.abs(delta) < 1) {
        d.className = 'ba-timing-delta';
        d.textContent = 'Waiting makes almost no difference on this forecast — '
          + 'selling now avoids storage risk.';
      } else {
        d.textContent = (better ? 'Waiting could add ' : 'Waiting could cost ')
          + _fmtInr(Math.abs(delta))
          + ' (' + _fmtInr(Math.abs(delta) / qty) + '/QTL) versus selling now. '
          + 'Forecast, not a guarantee — storage and spoilage are not included.';
      }
    }
    row.hidden = false;
  }


  // =====================================================================
  // Make Offer: farmer offers one of their published lots against an open
  // buyer requirement. Posts to the real /api/offers endpoint.
  // =====================================================================
  function _offerFeedback(msg, kind) {
    var el = document.getElementById('offer-feedback');
    if (!el) return;
    el.textContent = msg || '';
    el.style.color = kind === 'error' ? '#b91c1c'
                   : kind === 'success' ? 'var(--color-accent-green,#16a34a)'
                   : 'var(--color-slate-500,#64748b)';
  }

  function _offerModal(open) {
    var m = document.getElementById('make-offer-modal');
    if (!m) return;
    if (open) m.classList.add('modal-open');
    else m.classList.remove('modal-open');
  }

  function _offerTotal() {
    var q = Number((document.getElementById('offer-quantity') || {}).value);
    var p = Number((document.getElementById('offer-price') || {}).value);
    var el = document.getElementById('offer-total-line');
    if (!el) return;
    if (!isFinite(q) || !isFinite(p) || q <= 0 || p <= 0) { el.textContent = ''; return; }
    el.textContent = 'Offer value: ' + _fmtInr(q * p) + ' (' + q + ' QTL × ' + _fmtInr(p) + '/QTL)';
  }

  window.klOpenOfferModal = function (opts) {
    opts = opts || {};
    var rec = window.__klRecommendation || {};
    var commodity = opts.commodity || rec.commodity || '';
    var qty = opts.quantity_qtl || rec.quantity_qtl || '';
    var price = opts.price_per_qtl || rec.price_per_qtl || '';

    _offerFeedback('');
    var form = document.getElementById('make-offer-form');
    if (form && form.getAttribute('data-sent')) {
      form.removeAttribute('data-sent');
      form.reset();
      var sb = document.getElementById('submit-make-offer');
      if (sb) { sb.disabled = false; sb.textContent = 'Send Offer'; }
      var cb = document.getElementById('cancel-make-offer');
      if (cb) { var cs = cb.querySelector('span'); if (cs) cs.textContent = 'Cancel'; }
    }
    var ctx = document.getElementById('offer-context');
    if (ctx) {
      if (opts.contextNote) {
        ctx.innerHTML = '<span class="lot-reco-title">Context</span>' + opts.contextNote;
        ctx.hidden = false;
      } else {
        ctx.hidden = true;
        ctx.innerHTML = '';
      }
    }

    var qEl = document.getElementById('offer-quantity');
    var pEl = document.getElementById('offer-price');
    if (qEl && qty) qEl.value = Math.round(Number(qty) * 100) / 100;
    if (pEl && price) pEl.value = Math.round(Number(price) * 100) / 100;

    _offerModal(true);
    _offerTotal();
    _loadOfferRequirements(commodity);
    _loadOfferLots(commodity);
  };

  function _loadOfferRequirements(commodity) {
    var sel = document.getElementById('offer-requirement');
    var help = document.getElementById('offer-requirement-help');
    if (!sel) return;
    sel.innerHTML = '<option value="">Loading open requirements…</option>';
    var url = '/buyer-requirements' + (commodity ? '?commodity=' + encodeURIComponent(commodity) : '');
    window.apiClient.get(url).then(function (r) {
      var reqs = (r.data && (r.data.requirements || r.data.demands)) || [];
      if (!reqs.length) {
        sel.innerHTML = '<option value="">No open buyer requirements' +
          (commodity ? ' for ' + commodity : '') + '</option>';
        if (help) {
          help.textContent = commodity
            ? 'No buyer has posted an open requirement for ' + commodity + ' yet. ' +
              'Offers can only be sent to a real registered buyer.'
            : 'No open buyer requirements right now.';
        }
        return;
      }
      sel.innerHTML = reqs.map(function (q) {
        var label = q.commodity + ' · needs ' + (q.quantity_qtl_min || 0) + '+ QTL' +
          (q.price_per_qtl ? ' · offering ' + _fmtInr(q.price_per_qtl) + '/QTL' : '') +
          (q.preferred_district ? ' · ' + q.preferred_district : '');
        return '<option value="' + q.id + '" data-price="' + (q.price_per_qtl || '') +
          '" data-qty="' + (q.quantity_qtl_min || '') + '">' + label + '</option>';
      }).join('');
      if (help) help.textContent = reqs.length + ' open requirement(s) from registered buyers.';
    }).catch(function (err) {
      sel.innerHTML = '<option value="">Could not load requirements</option>';
      if (help) help.textContent = (err && err.message) || 'Requirement lookup failed.';
    });
  }

  function _loadOfferLots(commodity) {
    var sel = document.getElementById('offer-lot');
    var help = document.getElementById('offer-lot-help');
    if (!sel) return;
    sel.innerHTML = '<option value="">Loading your lots…</option>';
    window.apiClient.get('/lots/my').then(function (r) {
      var lots = (r.data && r.data.lots) || [];
      var match = commodity
        ? lots.filter(function (l) {
            return String(l.commodity || '').toLowerCase() === String(commodity).toLowerCase();
          })
        : lots;
      var use = match.length ? match : lots;
      if (!use.length) {
        sel.innerHTML = '<option value="">You have no published lots yet</option>';
        if (help) help.textContent = 'Publish a sale lot first — an offer always references one of your lots.';
        return;
      }
      sel.innerHTML = use.map(function (l) {
        return '<option value="' + l.id + '" data-qty="' + (l.quantity_qtl || '') +
          '" data-price="' + (l.expected_price || '') + '">#' + l.id + ' · ' +
          l.commodity + ' · ' + (l.quantity_qtl || 0) + ' QTL · ' + (l.grade || '') + '</option>';
      }).join('');
      if (help) {
        help.textContent = match.length
          ? use.length + ' matching lot(s) for ' + commodity + '.'
          : 'No lot for ' + commodity + ' — showing all your lots.';
      }
      sel.dispatchEvent(new Event('change'));
    }).catch(function (err) {
      sel.innerHTML = '<option value="">Could not load your lots</option>';
      if (help) help.textContent = (err && err.message) || 'Lot lookup failed.';
    });
  }

  function _wireOfferModal() {
    var form = document.getElementById('make-offer-form');
    if (!form || form.dataset.wired) return;
    form.dataset.wired = '1';

    var closeBtn = document.getElementById('close-make-offer-modal');
    var cancelBtn = document.getElementById('cancel-make-offer');
    var modal = document.getElementById('make-offer-modal');
    if (closeBtn) closeBtn.addEventListener('click', function () { _offerModal(false); });
    if (cancelBtn) cancelBtn.addEventListener('click', function () { _offerModal(false); });
    if (modal) modal.addEventListener('click', function (e) {
      if (e.target === modal) _offerModal(false);
    });

    ['offer-quantity', 'offer-price'].forEach(function (id) {
      var el = document.getElementById(id);
      if (el) el.addEventListener('input', _offerTotal);
    });

    // Picking a lot caps the quantity at what that lot actually holds.
    var lotSel = document.getElementById('offer-lot');
    if (lotSel) lotSel.addEventListener('change', function () {
      var opt = lotSel.options[lotSel.selectedIndex];
      if (!opt) return;
      var lotQty = Number(opt.getAttribute('data-qty'));
      var qEl = document.getElementById('offer-quantity');
      if (qEl && isFinite(lotQty) && lotQty > 0) {
        qEl.max = lotQty;
        if (!qEl.value || Number(qEl.value) > lotQty) qEl.value = lotQty;
      }
      var pEl = document.getElementById('offer-price');
      var lotPrice = Number(opt.getAttribute('data-price'));
      if (pEl && !pEl.value && isFinite(lotPrice) && lotPrice > 0) pEl.value = lotPrice;
      _offerTotal();
    });

    form.addEventListener('submit', function (e) {
      e.preventDefault();
      var btn = document.getElementById('submit-make-offer');
      var reqId = (document.getElementById('offer-requirement') || {}).value;
      var lotId = (document.getElementById('offer-lot') || {}).value;
      var qty = window.KLNumeric ? window.KLNumeric.read('offer-quantity')
                                 : Number((document.getElementById('offer-quantity') || {}).value);
      var price = window.KLNumeric ? window.KLNumeric.read('offer-price')
                                   : Number((document.getElementById('offer-price') || {}).value);
      var message = (document.getElementById('offer-message') || {}).value || '';

      if (!reqId) { _offerFeedback('Choose a buyer requirement to offer against.', 'error'); return; }
      if (!lotId) { _offerFeedback('Choose which of your lots to offer.', 'error'); return; }
      if (!isFinite(qty) || qty <= 0) { _offerFeedback('Enter a quantity greater than zero.', 'error'); return; }
      if (!isFinite(price) || price <= 0) { _offerFeedback('Enter an asking price greater than zero.', 'error'); return; }

      if (btn) { btn.disabled = true; btn.textContent = 'Sending…'; }
      _offerFeedback('Sending your offer…');

      window.apiClient.post('/offers', {
        requirement_id: Number(reqId),
        lot_id: Number(lotId),
        quantity_qtl: qty,
        price_per_qtl: price,
        message: message,
      }).then(function (r) {
        var d = r.data || {};
        // Leave the success state on screen — the user closes it. Auto-closing
        // hid the confirmation before it could be read.
        _offerFeedback('✓ Offer #' + (d.offer_id || '') + ' sent to the buyer for ' +
          qty + ' QTL at ' + _fmtInr(price) + '/QTL (' + _fmtInr(qty * price) + ' total). ' +
          'It is now pending the buyer\'s response.', 'success');
        if (typeof showToast === 'function') showToast('Offer sent to the buyer.', 'success');
        form.setAttribute('data-sent', '1');
        if (btn) { btn.disabled = true; btn.textContent = 'Offer sent'; }
        var cancel = document.getElementById('cancel-make-offer');
        if (cancel) {
          var span = cancel.querySelector('span');
          if (span) span.textContent = 'Close';
        }
      }).catch(function (err) {
        _offerFeedback((err && err.message) || 'Could not send the offer.', 'error');
        if (typeof showToast === 'function') showToast('Offer failed: ' + ((err && err.message) || 'server error'), 'error');
        if (btn) { btn.disabled = false; btn.textContent = 'Send Offer'; }
      });
    });
  }

  function _wireBestActionCtas() {
    var sellBtn = document.getElementById('ba-sell-now-btn');
    if (sellBtn && !sellBtn.dataset.wired) {
      sellBtn.dataset.wired = '1';
      sellBtn.addEventListener('click', function () {
        // Reuse the same prefill path as the Sell Now result card.
        var proceed = document.getElementById('sn-proceed-btn');
        if (proceed) { proceed.click(); return; }
        var modal = document.getElementById('create-lot-modal');
        if (modal) modal.classList.add('modal-open');
      });
    }
    var offerBtn = document.getElementById('ba-make-offer-btn');
    if (offerBtn && !offerBtn.dataset.wired) {
      offerBtn.dataset.wired = '1';
      offerBtn.addEventListener('click', function () {
        var rec = window.__klRecommendation || {};
        window.klOpenOfferModal({
          commodity: rec.commodity,
          quantity_qtl: rec.quantity_qtl,
          price_per_qtl: rec.price_per_qtl,
          contextNote: rec.market
            ? 'Best market <strong>' + rec.market + '</strong> · estimated net realisation ' +
              _fmtInr(rec.net_realisation) + ' for ' + rec.quantity_qtl + ' QTL.'
            : '',
        });
      });
    }
  }

  window.klRunSellNow = function () {
    var sel = _selectedOutlook();
    var qtyEl = document.getElementById('sn-qty');
    var status = document.getElementById('sn-status');
    var box = document.getElementById('sn-result');
    if (!sel.commodity || !sel.state || !sel.district) {
      if (status) status.textContent = 'Choose your crop, state and district above, then run this comparison.';
      return;
    }
    // KLNumeric shows the reason next to the field and focuses it.
    var qty = window.KLNumeric ? window.KLNumeric.read('sn-qty')
                               : (qtyEl ? Number(qtyEl.value) : null);
    if (qty == null || !isFinite(qty) || qty <= 0) {
      if (status) status.textContent = 'Enter how many quintals you want to sell, for example 25.';
      return;
    }
    _sellNowBusy(true);
    if (status) status.textContent = 'Comparing markets, routes, and net realisation…';
    if (box) {
      box.innerHTML = '<div style="padding:20px;text-align:center;">' +
        '<div class="cqa-spinner-ring" style="width:26px;height:26px;border-width:3px;margin:0 auto;"></div>' +
        '<p style="font-size:0.78rem;color:var(--color-slate-500);margin-top:8px;">' +
        'Ranking markets by net realisation…</p></div>';
    }
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
      _sellNowBusy(false);
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
        status.textContent = (data.dev_fixture
            ? 'Sample data — generated rows, not real mandi prices.'
            : (data.live_note || rec.freshness_label || 'Latest available mandi data')) +
          (lastLabel ? ' · Last available: ' + lastLabel : '') +
          ' · ' + (data.data_source || '');
      }
      var synthetic = !!data.dev_fixture;
      function _card(m, featured) {
        var distHint = m.distance_estimated
          ? 'Road routing unavailable. Showing estimated straight-line distance.'
          : '';
        return '<div style="border:1px solid var(--color-slate-200);border-radius:10px;padding:12px;margin-bottom:10px;' +
          (featured ? 'background:var(--color-slate-50,#f8fafc);' : '') + '">' +
          '<div style="display:flex;justify-content:space-between;gap:8px;align-items:center;margin-bottom:6px;">' +
          '<strong>' + (m.market || '—') + '</strong>' + _badge(m, synthetic) + '</div>' +
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
          '<div class="ba-cta-row">' +
          '<button type="button" class="btn btn-primary btn-sm" id="sn-proceed-btn">Sell Now — list this lot</button>' +
          '<button type="button" class="btn btn-outline btn-sm" id="sn-offer-btn">Make Offer to a Buyer</button>' +
          '</div>';
      }
      _renderBreakdown(rec, qty, data, sel);

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
      var offerBtn = document.getElementById('sn-offer-btn');
      if (offerBtn) {
        offerBtn.addEventListener('click', function () {
          window.klOpenOfferModal({
            commodity: data.commodity || sel.commodity,
            quantity_qtl: qty,
            price_per_qtl: rec.latest_price || rec.modal_price,
            contextNote: 'Best market <strong>' + (rec.market || '—') + '</strong> · estimated net realisation ' +
              _fmtInr(rec.net_realisation) + ' for ' + qty + ' QTL.',
          });
        });
      }

      var proceed = document.getElementById('sn-proceed-btn');
      if (proceed) {
        proceed.addEventListener('click', function () {
          function _set(id, value) {
            var el = document.getElementById(id);
            if (el && value != null && value !== '') el.value = value;
            return el;
          }
          // Crop select is populated asynchronously; only set it if the option exists.
          var crop = document.getElementById('lot-crop');
          var cropName = data.commodity || sel.commodity;
          if (crop && cropName) {
            var has = Array.prototype.some.call(crop.options, function (o) { return o.value === cropName; });
            if (!has) {
              var opt = document.createElement('option');
              opt.value = cropName;
              opt.textContent = cropName;
              crop.appendChild(opt);
            }
            crop.value = cropName;
          }
          _set('lot-quantity', qty);
          _set('lot-unit', 'QTL');
          _set('lot-location', (rec.district || sel.district) + ', ' + (rec.state || sel.state));
          var recoPrice = rec.latest_price || rec.modal_price;
          _set('lot-price', recoPrice != null ? Math.round(Number(recoPrice) * 100) / 100 : '');
          _set('lot-market', rec.market || '');
          _set('lot-district', rec.district || sel.district || '');
          _set('lot-state', rec.state || sel.state || '');
          _set('lot-net-realisation', rec.net_realisation != null ? rec.net_realisation : '');
          _set('lot-transport-cost', rec.transport_cost != null ? rec.transport_cost : '');
          _set('lot-distance-km', rec.distance_km != null ? rec.distance_km : '');

          // Carry the photo assessment across. Without this the lot silently
          // published as "Grade A" even when the model had said Grade C, so
          // the buyer saw a grade nobody had assessed.
          var assessed = (window.CQA && window.CQA.state) || {};
          var gradeEl = document.getElementById('lot-grade');
          if (gradeEl && assessed.assessedGrade) {
            var wanted = String(assessed.assessedGrade);
            var match = Array.prototype.filter.call(gradeEl.options, function (o) {
              return o.value === wanted || o.value.indexOf(wanted) === 0;
            })[0];
            if (match) gradeEl.value = match.value;
          }
          var harvest = document.getElementById('lot-harvest');
          if (harvest && !harvest.value) {
            harvest.value = new Date().toISOString().slice(0, 10);
          }

          // Carry the reasoning into the modal so the farmer sees why this
          // market was chosen while filling the lot in.
          var summary = document.getElementById('lot-reco-summary');
          if (summary) {
            summary.innerHTML =
              '<span class="lot-reco-title">Prefilled from your best-market comparison</span>' +
              '<strong>' + (rec.market || '—') + '</strong>' +
              (rec.district ? ', ' + rec.district : '') +
              ' · Modal ' + _fmtInr(rec.modal_price || rec.latest_price) + '/QTL' +
              ' · ' + _distLine(rec) +
              '<br>Estimated transport ' + _fmtInr(rec.transport_cost) +
              ' · Estimated net realisation <strong>' + _fmtInr(rec.net_realisation) + '</strong>' +
              ' for ' + qty + ' QTL. Planning estimate — edit any field before publishing.' +
              (assessed.assessedGrade
                ? '<br>Photo check: <strong>' + assessed.assessedGrade + '</strong>' +
                  (assessed.assessedCondition ? ' · condition ' + assessed.assessedCondition : '') +
                  (assessed.assessedConfidence != null
                    ? ' · ' + Math.round(assessed.assessedConfidence * 100) + '% model confidence'
                    : '') +
                  ' — grade prefilled above, change it if you disagree.'
                : '');
            summary.hidden = false;
          }

          var modal = document.getElementById('create-lot-modal');
          if (modal) {
            modal.classList.add('modal-open');
            var firstField = document.getElementById('lot-quantity');
            if (firstField) setTimeout(function () { firstField.focus(); }, 60);
          }
        });
      }
    }).catch(function (err) {
      _sellNowBusy(false);
      if (status) status.textContent = (err && err.message) || 'Market comparison is temporarily unavailable.';
      if (box) box.innerHTML = '<p style="font-size:0.8rem;color:var(--color-slate-500);">Could not complete the comparison. Try again or select a different district.</p>';
    });
  };

  return { init: init };
})();

window.KL_Step4 = KL_Step4;
