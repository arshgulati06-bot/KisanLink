/**
 * KisanLink — live mandi prices, at the top of the farmer dashboard
 * =================================================================
 *
 * The one number a farmer opens this app for. It used to be buried in a
 * collapsed "Market Prices" page and the dashboard header claimed "Official
 * API configured" merely because an environment variable was set — which read
 * as "live pricing is working" while every figure shown came from the archive.
 *
 * The rule here is absolute: the LIVE badge is driven by the feed's own
 * `is_live`/`status`, never by the presence of a key, never by the age of a
 * row, never inferred in this file. If today's official record does not exist
 * the card says LATEST AVAILABLE and prints the record's real date.
 *
 * Order of attempts:
 *   /market-prices/live    official data.gov.in feed
 *   /market-prices/latest  local archive, clearly labelled as such
 * Neither blocks the rest of the dashboard, and every state — loading, live,
 * fallback, empty, error — has a rendering.
 */
(function () {
  'use strict';

  var MAX_CARDS = 6;
  var REQUEST_TIMEOUT_MS = 25000;
  var seq = 0;                       // guards against a stale response landing

  function el(id) { return document.getElementById(id); }
  function esc(v) {
    var d = document.createElement('div');
    d.appendChild(document.createTextNode(v == null ? '' : String(v)));
    return d.innerHTML;
  }
  function inr(v) {
    var n = Number(v);
    return isFinite(n) ? '₹' + n.toLocaleString('en-IN', { maximumFractionDigits: 0 }) : '—';
  }
  function niceDate(iso) {
    if (!iso) return '—';
    var p = String(iso).slice(0, 10).split('-');
    if (p.length !== 3) return String(iso);
    var months = ['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'];
    return Number(p[2]) + ' ' + (months[Number(p[1]) - 1] || p[1]) + ' ' + p[0];
  }
  function daysOld(iso) {
    if (!iso) return null;
    var then = new Date(String(iso).slice(0, 10) + 'T00:00:00');
    if (isNaN(then.getTime())) return null;
    var now = new Date();
    return Math.round((new Date(now.getFullYear(), now.getMonth(), now.getDate()) - then) / 86400000);
  }

  /** The status pill. `kind` is one of live | latest | error | loading. */
  function setStatus(kind, text) {
    var pill = el('lmp-status');
    var label = el('lmp-status-text');
    if (!pill || !label) return;
    pill.className = 'lmp-pill lmp-pill--' + kind;
    label.textContent = text;
  }

  function setMeta(html) {
    var m = el('lmp-meta');
    if (m) { m.innerHTML = html || ''; m.hidden = !html; }
  }

  function skeleton() {
    var body = el('lmp-body');
    if (!body) return;
    body.innerHTML =
      '<div class="lmp-grid">' +
      '<div class="lmp-card lmp-card--skeleton"><span></span><span></span><span></span></div>'.repeat(3) +
      '</div>';
  }

  function message(icon, title, detail, withRetry) {
    var body = el('lmp-body');
    if (!body) return;
    body.innerHTML =
      '<div class="lmp-msg">' +
        '<div class="lmp-msg-icon" aria-hidden="true">' + icon + '</div>' +
        '<h3>' + esc(title) + '</h3>' +
        '<p>' + esc(detail) + '</p>' +
        (withRetry ? '<button type="button" class="btn btn-outline btn-sm" id="lmp-retry">Try again</button>' : '') +
      '</div>';
    var r = el('lmp-retry');
    if (r) r.addEventListener('click', function () { load(); });
  }

  /**
   * Render the price cards.
   * @param {Array} rows normalised records
   * @param {boolean} isLive the FEED's verdict, never our own guess
   */
  function renderCards(rows, isLive) {
    var body = el('lmp-body');
    if (!body) return;
    body.innerHTML = '<div class="lmp-grid">' + rows.slice(0, MAX_CARDS).map(function (r) {
      var age = daysOld(r.date);
      var tag = isLive
        ? '<span class="lmp-tag lmp-tag--live"><span class="lmp-dot"></span>LIVE · TODAY</span>'
        : '<span class="lmp-tag lmp-tag--latest">LATEST · ' + esc(niceDate(r.date)) +
          (age != null && age > 0 ? ' · ' + age + 'd' : '') + '</span>';

      var sub = [r.variety, r.grade].filter(function (v) {
        return v && String(v).toLowerCase() !== 'nan';
      }).map(esc).join(' · ');

      // Modal is the hero; min and max flank it as quieter context.
      var band =
        '<div class="lmp-band">' +
          '<div class="lmp-band-cell lmp-band-cell--min">' +
            '<span class="lmp-band-label">Min</span>' +
            '<span class="lmp-band-value">' + inr(r.min_price) + '</span></div>' +
          '<div class="lmp-band-cell lmp-band-cell--max">' +
            '<span class="lmp-band-label">Max</span>' +
            '<span class="lmp-band-value">' + inr(r.max_price) + '</span></div>' +
        '</div>';

      return '<article class="lmp-card' + (isLive ? ' lmp-card--live' : '') + '">' +
        '<header class="lmp-card-head">' +
          '<div>' +
            '<h3>' + esc(r.commodity || '—') + '</h3>' +
            (sub ? '<p class="lmp-sub">' + sub + '</p>' : '') +
          '</div>' + tag +
        '</header>' +
        '<div class="lmp-hero">' +
          '<div class="lmp-price">' + inr(r.modal_price) +
            '<span class="lmp-unit">/quintal</span></div>' +
          '<div class="lmp-hero-label">Modal price</div>' +
        '</div>' +
        ((r.min_price != null && r.max_price != null) ? band : '') +
        '<footer class="lmp-where">' +
          '<span class="lmp-market">' + esc(r.market || '—') + '</span>' +
          '<span class="lmp-loc">' +
            esc([r.district, r.state].filter(Boolean).join(', ') || '—') + '</span>' +
          '<span class="lmp-src">' +
            (isLive ? 'Official Data.gov.in' : 'Local mandi archive') + '</span>' +
        '</footer>' +
      '</article>';
    }).join('') + '</div>';
  }

  function selection() {
    return {
      commodity: (el('lmp-crop') || {}).value || '',
      state: (el('lmp-state') || {}).value || '',
      district: (el('lmp-district') || {}).value || '',
      market: (el('lmp-market') || {}).value || ''
    };
  }

  /** Fill a dependent picker from an endpoint, keeping the current choice. */
  function fillDependent(id, url, allLabel) {
    var sel = el(id);
    if (!sel) return Promise.resolve();
    var keep = sel.value;
    sel.disabled = true;
    return fetch(url).then(function (r) { return r.ok ? r.json() : []; })
      .then(function (list) {
        var arr = Array.isArray(list) ? list : [];
        sel.innerHTML = '<option value="">' + allLabel + '</option>' +
          arr.map(function (v) {
            return '<option value="' + esc(v) + '">' + esc(v) + '</option>';
          }).join('');
        if (keep && arr.indexOf(keep) >= 0) sel.value = keep;
        sel.disabled = arr.length === 0;
      }).catch(function () {
        sel.innerHTML = '<option value="">' + allLabel + '</option>';
        sel.disabled = true;
      });
  }

  /** State -> district -> market, each narrowing the next. */
  function refreshDependents(changed) {
    var base = (window.apiClient && window.apiClient.baseUrl) || '/api';
    var sel = selection();
    var chain = Promise.resolve();
    if (changed === 'state' || changed === 'init') {
      var d = el('lmp-district'); if (d && changed === 'state') d.value = '';
      var m0 = el('lmp-market'); if (m0 && changed === 'state') m0.value = '';
      chain = chain.then(function () {
        // /api/districts is scoped by commodity AND state — sending state
        // alone returns a 400 and left the picker permanently disabled.
        return (sel.state && sel.commodity)
          ? fillDependent('lmp-district',
              base + '/districts?commodity=' + encodeURIComponent(sel.commodity) +
              '&state=' + encodeURIComponent(sel.state),
              'All districts')
          : fillDependent('lmp-district', 'data:application/json,[]', 'All districts');
      });
    }
    if (changed === 'state' || changed === 'district' || changed === 'init') {
      chain = chain.then(function () {
        var cur = selection();
        return (cur.state && cur.district && cur.commodity)
          ? fillDependent('lmp-market',
              base + '/markets?commodity=' + encodeURIComponent(cur.commodity) +
              '&state=' + encodeURIComponent(cur.state) +
              '&district=' + encodeURIComponent(cur.district), 'All markets')
          : fillDependent('lmp-market', 'data:application/json,[]', 'All markets');
      });
    }
    return chain;
  }

  function withTimeout(promise) {
    return new Promise(function (resolve, reject) {
      var done = false;
      var t = setTimeout(function () {
        if (!done) { done = true; reject(new Error('timeout')); }
      }, REQUEST_TIMEOUT_MS);
      promise.then(function (v) {
        if (!done) { done = true; clearTimeout(t); resolve(v); }
      }, function (e) {
        if (!done) { done = true; clearTimeout(t); reject(e); }
      });
    });
  }

  function load() {
    var mine = ++seq;
    var sel = selection();
    if (!sel.commodity) {
      setStatus('loading', 'Choose a crop');
      setMeta('');
      message('🌾', 'Pick a crop to see prices',
              'Mandi prices are published per commodity — choose one above.', false);
      return;
    }
    setStatus('loading', 'Checking official feed…');
    setMeta('');
    skeleton();

    var live = (typeof window.getLiveMarketPrices === 'function')
      ? withTimeout(window.getLiveMarketPrices(sel)).catch(function (e) { return { _err: e }; })
      : Promise.resolve({ _err: new Error('client missing') });

    live.then(function (res) {
      if (mine !== seq) return;                 // a newer request already ran

      // LIVE only on the feed's own verdict.
      var feedSaysLive = !!(res && res.success && res.is_live && res.records && res.records.length);
      if (feedSaysLive) {
        setStatus('live', 'LIVE');
        setMeta('Official government feed · <strong>data.gov.in / AGMARKNET</strong> · ' +
                'fetched ' + esc(new Date().toLocaleTimeString('en-IN',
                  { hour: '2-digit', minute: '2-digit' })) + ' · ' +
                res.records.length + ' record(s) dated today');
        renderCards(res.records.map(function (r) {
          return {
            commodity: r.commodity, market: r.market, district: r.district,
            state: r.state, variety: r.variety, grade: r.grade,
            min_price: r.min_price, max_price: r.max_price,
            modal_price: r.modal_price, date: r.arrival_date
          };
        }), true);
        return;
      }

      // Say WHY it is not live, then show the archive — clearly labelled.
      var why = (res && res._err)
        ? (res._err.message === 'timeout'
            ? 'The official feed did not answer in time.'
            : 'Could not reach the official feed.')
        : (res && res.error) ||
          'The official feed returned no record dated today for this selection.';
      fallback(mine, sel, why);
    });
  }

  function fallback(mine, sel, why) {
    if (typeof window.getLatestMarketPrices !== 'function') {
      setStatus('error', 'UNAVAILABLE');
      message('⚠️', 'Prices unavailable', why, true);
      return;
    }
    withTimeout(window.getLatestMarketPrices(sel)).then(function (res) {
      if (mine !== seq) return;
      var rows = (res && res.prices) || [];
      if (!rows.length) {
        setStatus('error', 'NO RECORDS');
        setMeta(esc(why));
        message('📭', 'No records for this selection',
                'Try a different crop, or clear the state filter.', true);
        return;
      }
      var newest = rows[0].date || res.latest_date;
      setStatus('latest', 'LATEST AVAILABLE');
      setMeta(esc(why) + ' Showing the latest verified record from the local ' +
              'mandi archive — <strong>' + esc(niceDate(newest)) + '</strong>. ' +
              'This is <strong>not</strong> a live quote.');
      renderCards(rows.map(function (r) {
        return {
          commodity: r.commodity || sel.commodity, market: r.market,
          district: r.district, state: r.state, variety: r.variety,
          grade: r.grade, min_price: r.min_price, max_price: r.max_price,
          modal_price: r.modal_price, date: r.date
        };
      }), false);
    }).catch(function (e) {
      if (mine !== seq) return;
      var warming = /503/.test(String(e && e.message));
      setStatus('error', warming ? 'LOADING DATA' : 'UNAVAILABLE');
      message(warming ? '⏳' : '⚠️',
              warming ? 'Market data is still loading' : 'Prices unavailable',
              warming
                ? 'The server is still reading the mandi archive. This takes a '
                  + 'moment after a restart.'
                : why + ' The local archive could not be read either.',
              true);
    });
  }

  /** Fill the crop and state pickers from the archive the server has. */
  function fillPickers() {
    var crop = el('lmp-crop');
    var state = el('lmp-state');
    if (!crop) return;
    var base = (window.apiClient && window.apiClient.baseUrl) || '/api';

    // Shared with the other modules that need this list, so one dashboard
    // load fetches it once rather than three times.
    var fetchCrops = (typeof window.getCommoditiesOnce === 'function')
      ? window.getCommoditiesOnce()
      : fetch(base + '/commodities').then(function (r) {
          return r.ok ? r.json() : null;
        });

    fetchCrops.then(function (list) {
      if (!list || !list.length) {
        if (typeof window.waitForMarketData === 'function') {
          crop.innerHTML = '<option value="">Loading market data…</option>';
          return window.waitForMarketData().then(function (ok) {
            if (ok) fillPickers();
          });
        }
        return;
      }
      // Common crops first so the default view is useful immediately.
      var preferred = ['Tomato', 'Onion', 'Potato', 'Wheat', 'Rice', 'Banana'];
      var present = preferred.filter(function (c) { return list.indexOf(c) >= 0; });
      var rest = list.filter(function (c) { return present.indexOf(c) < 0; });
      crop.innerHTML = present.concat(rest).map(function (c) {
        return '<option value="' + esc(c) + '">' + esc(c) + '</option>';
      }).join('');
      if (present.length) crop.value = present[0];
      load();
    }).catch(function () {
      crop.innerHTML = '<option value="">Could not load crops</option>';
      setStatus('error', 'UNAVAILABLE');
      message('⚠️', 'Could not reach the server',
              'Check that the KisanLink backend is running.', true);
    });

    if (state) {
      fetch(base + '/states').then(function (r) { return r.ok ? r.json() : null; })
        .then(function (list) {
          if (!Array.isArray(list)) return;
          state.innerHTML = '<option value="">All states</option>' + list.map(function (v) {
            return '<option value="' + esc(v) + '">' + esc(v) + '</option>';
          }).join('');
        }).catch(function () {});
    }
  }

  function init() {
    if (!el('lmp')) return;
    var t = null;
    function debounced(changed) {
      return function () {
        clearTimeout(t);
        t = setTimeout(function () {
          refreshDependents(changed).then(load);
        }, 150);
      };
    }
    var e1 = el('lmp-crop');   if (e1) e1.addEventListener('change', debounced('state'));
    var e2 = el('lmp-state');  if (e2) e2.addEventListener('change', debounced('state'));
    var e3 = el('lmp-district'); if (e3) e3.addEventListener('change', debounced('district'));
    var e4 = el('lmp-market'); if (e4) e4.addEventListener('change', debounced('market'));
    var r = el('lmp-refresh');
    if (r) r.addEventListener('click', function () { load(); });
    fillPickers();
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    setTimeout(init, 0);
  }

  window.KLLiveMandi = { load: load };
})();
