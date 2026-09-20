/**
 * KisanLink — buyer procurement flow
 * ===================================
 *
 * The buyer portal could list farmer lots but could not act on them. The lot
 * cards carried no call to action, there was nowhere to see an offer once it
 * had been sent, and the transaction panel was static placeholder markup that
 * never called the API — so a buyer never saw a deal the backend had actually
 * created, and the farmer's side of the same deal looked one-sided.
 *
 * This closes those gaps against endpoints that already exist. No business
 * logic lives here: offers go to POST /api/offers exactly as the farmer side
 * sends them, sent offers come from GET /api/offers/my, and deals come from
 * GET /api/transactions/my. Nothing is computed that the server does not
 * already return, and nothing is shown that it did not send.
 *
 * The lot cards themselves are still rendered by buyer.html; that renderer
 * publishes what it drew on window.__klBuyerLots, so the buttons below open a
 * lot the buyer is actually looking at rather than re-fetching the list.
 */
(function () {
  'use strict';

  function el(id) { return document.getElementById(id); }

  function esc(v) {
    var d = document.createElement('div');
    d.appendChild(document.createTextNode(v == null ? '' : String(v)));
    return d.innerHTML;
  }

  function inr(v) {
    var n = Number(v);
    return isFinite(n) && n > 0
      ? '₹' + n.toLocaleString('en-IN', { maximumFractionDigits: 0 })
      : null;
  }

  function apiBase() {
    return (window.apiClient && window.apiClient.baseUrl) ||
           (window.CONFIG && window.CONFIG.API_BASE_URL) ||
           (typeof window !== 'undefined' && (window.location.hostname === 'localhost' || window.location.hostname === '127.0.0.1' || window.location.port === '5000')
             ? 'http://127.0.0.1:5000/api'
             : 'https://kisanlink-backend-42qd.onrender.com/api');
  }

  function authHeaders(json) {
    var h = { 'Accept': 'application/json' };
    if (json) h['Content-Type'] = 'application/json';
    try {
      var t = localStorage.getItem('kisanlink_auth_token');
      if (t) h['Authorization'] = 'Bearer ' + t;
    } catch (e) {}
    return h;
  }

  function token() {
    try { return localStorage.getItem('kisanlink_auth_token'); } catch (e) { return null; }
  }

  var MONTHS = ['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'];
  function niceDate(iso) {
    if (!iso) return '—';
    var p = String(iso).slice(0, 10).split('-');
    if (p.length !== 3) return String(iso).slice(0, 10);
    return Number(p[2]) + ' ' + (MONTHS[Number(p[1]) - 1] || p[1]) + ' ' + p[0];
  }

  function toast(msg, kind) {
    if (typeof window.showToast === 'function') window.showToast(msg, kind || 'info');
  }

  /** The lot the buyer is looking at, as the page's own renderer drew it. */
  function lotById(id) {
    return (window.__klBuyerLots || {})[String(id)] || null;
  }

  function statusClass(status) {
    var s = String(status || '').toUpperCase();
    if (s === 'ACCEPTED') return 'badge-success';
    if (s === 'REJECTED' || s === 'WITHDRAWN') return 'badge-rose';
    return 'badge-amber';
  }

  /* ======================================================================
     Modal shell — one dialog reused by the offer form and the detail view
     ====================================================================== */

  var modal = null;

  function ensureModal() {
    if (modal && document.body.contains(modal)) return modal;
    modal = document.createElement('div');
    modal.id = 'bp-modal';
    modal.className = 'modal-backdrop bp-modal';
    modal.setAttribute('role', 'dialog');
    modal.setAttribute('aria-modal', 'true');
    modal.setAttribute('aria-labelledby', 'bp-modal-title');
    modal.innerHTML = '<div class="bp-panel"></div>';
    document.body.appendChild(modal);

    modal.addEventListener('click', function (e) { if (e.target === modal) closeModal(); });
    document.addEventListener('keydown', function (e) {
      if (e.key === 'Escape' && modal.classList.contains('modal-open')) closeModal();
    });
    return modal;
  }

  function openModal(html) {
    var m = ensureModal();
    m.querySelector('.bp-panel').innerHTML = html;
    m.classList.add('modal-open');
    document.body.classList.add('bp-modal-open');
  }

  function closeModal() {
    if (!modal) return;
    modal.classList.remove('modal-open');
    document.body.classList.remove('bp-modal-open');
    // Leave the panel empty so a stale form can never be reopened by accident.
    modal.querySelector('.bp-panel').innerHTML = '';
  }

  function lotSummary(lot) {
    var ask = Number(lot.price_per_qtl || lot.expected_price) || null;
    var where = lot.location || [lot.district, lot.state].filter(Boolean).join(', ');
    return '<div class="bp-context">' +
      '<div class="bp-context-crop">' + esc(lot.commodity || lot.crop || 'Lot') +
        (lot.grade ? ' <span class="badge badge-success">' + esc(lot.grade) + '</span>' : '') +
      '</div>' +
      '<div class="bp-context-meta">Lot #' + esc(lot.id) +
        ' · ' + esc(lot.quantity_qtl || lot.quantity || '—') + ' QTL' +
        (where ? ' · ' + esc(where) : '') +
        (ask ? ' · Farmer asking ' + inr(ask) + '/QTL' : ' · Price negotiable') +
      '</div></div>';
  }

  /* ======================================================================
     Offer form — posts to the existing POST /api/offers
     ====================================================================== */

  function openOffer(lotId) {
    var lot = lotById(lotId);
    if (!lot) {
      toast('That lot is no longer on screen. Refresh the list and try again.', 'error');
      return;
    }
    if (!token()) {
      toast('Log in as a buyer to send an offer.', 'error');
      return;
    }

    var ask = Number(lot.price_per_qtl || lot.expected_price) || '';
    openModal(
      '<header class="bp-panel-head">' +
        '<h2 id="bp-modal-title">Send an offer</h2>' +
        '<button type="button" class="bp-close" data-bp-close aria-label="Close">&times;</button>' +
      '</header>' +
      lotSummary(lot) +
      '<form id="bp-offer-form" novalidate>' +
        '<div class="bp-field-row">' +
          '<label class="bp-field" for="bp-offer-qty"><span>Quantity (QTL)</span>' +
            '<input class="form-input" id="bp-offer-qty" type="text" inputmode="decimal" ' +
                   'autocomplete="off" value="' + esc(lot.quantity_qtl || lot.quantity || '') + '"></label>' +
          '<label class="bp-field" for="bp-offer-price"><span>Your price (₹/QTL)</span>' +
            '<input class="form-input" id="bp-offer-price" type="text" inputmode="decimal" ' +
                   'autocomplete="off" value="' + esc(ask) + '"></label>' +
        '</div>' +
        '<label class="bp-field" for="bp-offer-msg"><span>Message to the farmer (optional)</span>' +
          '<textarea class="form-input" id="bp-offer-msg" rows="2" maxlength="500" ' +
                    'placeholder="e.g. Pickup on Friday, payment on delivery."></textarea></label>' +
        '<p id="bp-offer-total" class="bp-total"></p>' +
        '<p id="bp-offer-feedback" class="bp-feedback" role="alert" hidden></p>' +
        '<div class="bp-actions">' +
          '<button type="button" class="btn btn-outline btn-sm" data-bp-close>Cancel</button>' +
          '<button type="submit" class="btn btn-primary btn-sm" id="bp-offer-submit">Send offer</button>' +
        '</div>' +
      '</form>'
    );

    ['bp-offer-qty', 'bp-offer-price'].forEach(function (id) {
      el(id).addEventListener('input', updateTotal);
    });
    el('bp-offer-form').dataset.lotId = lot.id;
    el('bp-offer-form').addEventListener('submit', submitOffer);
    updateTotal();
    setTimeout(function () { var p = el('bp-offer-price'); if (p) p.focus(); }, 50);
  }

  function updateTotal() {
    var t = el('bp-offer-total');
    if (!t) return;
    var q = parseFloat((el('bp-offer-qty') || {}).value);
    var p = parseFloat((el('bp-offer-price') || {}).value);
    t.textContent = (isFinite(q) && isFinite(p) && q > 0 && p > 0)
      ? 'Offer total: ' + inr(q * p) + ' for ' + q + ' QTL'
      : '';
  }

  function feedback(msg, kind) {
    var f = el('bp-offer-feedback');
    if (!f) return;
    f.textContent = msg || '';
    f.hidden = !msg;
    f.className = 'bp-feedback' + (kind ? ' bp-feedback--' + kind : '');
  }

  function submitOffer(e) {
    e.preventDefault();
    var form = el('bp-offer-form');
    var btn = el('bp-offer-submit');
    var qty = parseFloat(el('bp-offer-qty').value);
    var price = parseFloat(el('bp-offer-price').value);

    if (!isFinite(qty) || qty <= 0) { feedback('Enter a quantity greater than 0.', 'error'); return; }
    if (!isFinite(price) || price <= 0) { feedback('Enter a price greater than 0.', 'error'); return; }

    var label = btn.textContent;
    btn.disabled = true;
    btn.textContent = 'Sending…';
    feedback('');

    var body = {
      lot_id: Number(form.dataset.lotId),
      quantity_qtl: qty,
      price_per_qtl: price
    };
    var note = (el('bp-offer-msg').value || '').trim();
    if (note) body.message = note;

    fetch(apiBase() + '/offers', {
      method: 'POST', headers: authHeaders(true), body: JSON.stringify(body)
    }).then(function (r) {
      return r.json().catch(function () { return {}; })
              .then(function (d) { return { ok: r.ok, status: r.status, d: d }; });
    }).then(function (res) {
      if (!res.ok || !res.d || !res.d.success) {
        throw new Error((res.d && res.d.error) ||
          'The server refused the offer (HTTP ' + res.status + ').');
      }
      feedback('Offer #' + res.d.offer_id + ' sent. The farmer sees it under Received Offers.', 'ok');
      toast('Offer sent straight to the farmer.', 'success');
      loadOffers();
      loadTransactions();
      setTimeout(closeModal, 1500);
    }).catch(function (err) {
      feedback((err && err.message) || 'Could not send the offer. Try again.', 'error');
    }).then(function () {
      if (!btn.isConnected) return;   // the modal may already have closed
      btn.disabled = false;
      btn.textContent = label;
    });
  }

  /* ======================================================================
     Lot details
     ====================================================================== */

  function openDetails(lotId) {
    var lot = lotById(lotId);
    if (!lot) {
      toast('That lot is no longer on screen. Refresh the list and try again.', 'error');
      return;
    }
    var rows = [
      ['Crop', lot.commodity || lot.crop],
      ['Variety', lot.variety],
      ['Grade', lot.grade],
      ['Quantity', (lot.quantity_qtl || lot.quantity)
        ? (lot.quantity_qtl || lot.quantity) + ' QTL' : null],
      ['Asking price', (function (a) { return a ? a + '/QTL' : null; })(
        inr(lot.price_per_qtl || lot.expected_price))],
      ['Location', lot.location || [lot.district, lot.state].filter(Boolean).join(', ')],
      ['Preferred mandi', lot.market],
      ['Available from', lot.harvest_date ? niceDate(lot.harvest_date) : null],
      ['Listed on', lot.created_at ? niceDate(lot.created_at) : null],
      ['Status', lot.status],
      ['Lot ID', '#' + lot.id]
    ].filter(function (r) { return r[1]; });

    var origin = apiBase().replace(/\/api\/?$/, '');
    openModal(
      '<header class="bp-panel-head">' +
        '<h2 id="bp-modal-title">' + esc(lot.commodity || lot.crop || 'Lot') +
          ' · Lot #' + esc(lot.id) + '</h2>' +
        '<button type="button" class="bp-close" data-bp-close aria-label="Close">&times;</button>' +
      '</header>' +
      (lot.image_file
        ? '<img class="bp-detail-photo" alt="Crop photo for lot ' + esc(lot.id) + '" ' +
              'src="' + origin + '/api/lots/' + encodeURIComponent(lot.id) + '/image" ' +
              'onerror="this.remove()">'
        : '') +
      '<dl class="bp-detail-list">' + rows.map(function (r) {
        return '<div><dt>' + esc(r[0]) + '</dt><dd>' + esc(r[1]) + '</dd></div>';
      }).join('') + '</dl>' +
      '<p class="bp-detail-note">Listed directly by the farmer. KisanLink adds no ' +
        'commission and no intermediary to this lot.</p>' +
      '<div class="bp-actions">' +
        '<button type="button" class="btn btn-outline btn-sm" data-bp-close>Close</button>' +
        '<button type="button" class="btn btn-primary btn-sm bp-cta-offer" ' +
                'data-lot="' + esc(lot.id) + '">Buy / Send offer</button>' +
      '</div>'
    );
  }

  /* ======================================================================
     Offers the buyer has sent — GET /api/offers/my
     ====================================================================== */

  function loadOffers() {
    var box = el('buyer-offers-container');
    if (!box) return Promise.resolve();
    if (!token()) { box.innerHTML = loginPrompt('offers'); return Promise.resolve(); }

    return fetch(apiBase() + '/offers/my', { headers: authHeaders() })
      .then(function (r) {
        if (!r.ok) throw new Error('HTTP ' + r.status);
        return r.json();
      })
      .then(function (d) {
        var rows = (d && d.offers) || [];
        var badge = el('buyer-offers-badge');
        var stat = el('buyer-stat-offers');
        if (badge) badge.textContent = rows.length;
        if (stat) stat.textContent = rows.length;

        if (!rows.length) {
          box.innerHTML = emptyState('📨', 'No offers sent yet',
            'Pick a lot under Available Farmer Lots and press “Buy / Send offer”. ' +
            'It reaches that farmer directly.');
          return;
        }
        box.innerHTML = rows.map(function (o) {
          var qty = Number(o.quantity_qtl) || 0;
          var rate = Number(o.price_per_qtl) || 0;
          var to = o.seller_name || (o.seller_user_id ? 'Farmer #' + o.seller_user_id : 'Farmer');
          var where = [o.lot_district, o.lot_state].filter(Boolean).join(', ');
          return '<article class="bp-row">' +
            '<div class="bp-row-main">' +
              '<div class="bp-row-head">' +
                '<h3>' + esc(o.commodity || ('Lot #' + (o.lot_id || '—'))) + '</h3>' +
                '<span class="badge ' + statusClass(o.status) + '">' +
                  esc(o.status || 'PENDING') + '</span>' +
              '</div>' +
              '<p class="bp-row-party">Sent to <strong>' + esc(to) + '</strong>' +
                (where ? ' · ' + esc(where) : '') + '</p>' +
              '<p class="bp-row-meta">Offer #' + esc(o.id) +
                ' · Lot #' + esc(o.lot_id) +
                ' · ' + esc(niceDate(o.created_at)) +
                (o.message ? ' · “' + esc(o.message) + '”' : '') + '</p>' +
            '</div>' +
            figures(qty, rate, qty * rate) +
          '</article>';
        }).join('');
      })
      .catch(function () {
        box.innerHTML = emptyState('⚠️', 'Could not load your offers',
          'Check that the KisanLink backend is running, then refresh this page.');
      });
  }

  /* ======================================================================
     Deals — GET /api/transactions/my (the same row the farmer sees)
     ====================================================================== */

  function loadTransactions() {
    var box = el('buyer-transactions-container');
    if (!box) return Promise.resolve();
    if (!token()) { box.innerHTML = loginPrompt('purchases'); return Promise.resolve(); }

    return fetch(apiBase() + '/transactions/my', { headers: authHeaders() })
      .then(function (r) {
        if (!r.ok) throw new Error('HTTP ' + r.status);
        return r.json();
      })
      .then(function (d) {
        var rows = (d && d.transactions) || [];
        if (!rows.length) {
          box.innerHTML = emptyState('📋', 'No purchases yet',
            'When a farmer accepts one of your offers, the deal appears here — and ' +
            'the identical deal appears in that farmer’s dashboard.');
          return;
        }
        box.innerHTML = rows.map(function (t) {
          var qty = Number(t.quantity_qtl) || 0;
          var rate = Number(t.price_per_qtl) || 0;
          var total = t.gross_amount != null ? Number(t.gross_amount) : qty * rate;
          // Counterparty may be missing on a row whose user was removed.
          var from = t.seller_name ||
                     (t.seller_user_id ? 'Farmer #' + t.seller_user_id : 'Farmer');
          return '<article class="bp-row bp-row--deal">' +
            '<div class="bp-row-main">' +
              '<div class="bp-row-head">' +
                '<h3>' + esc(t.commodity || ('Lot #' + (t.lot_id || '—'))) + '</h3>' +
                '<span class="badge ' + statusClass(t.status) + '">' +
                  esc(t.status || '—') + '</span>' +
              '</div>' +
              '<p class="bp-row-party">Bought from <strong>' + esc(from) + '</strong></p>' +
              '<p class="bp-row-meta">' +
                esc(t.transaction_code || ('Deal #' + t.id)) +
                ' · Lot #' + esc(t.lot_id) +
                ' · ' + esc(niceDate(t.created_at)) + '</p>' +
            '</div>' +
            figures(qty, rate, total) +
          '</article>';
        }).join('');
      })
      .catch(function () {
        box.innerHTML = emptyState('⚠️', 'Could not load your purchases',
          'Check that the KisanLink backend is running, then refresh this page.');
      });
  }

  /* ======================================================================
     Small shared pieces
     ====================================================================== */

  function figures(qty, rate, total) {
    return '<div class="bp-figures">' +
      '<div><span>Quantity</span><strong>' + esc(qty) + ' QTL</strong></div>' +
      '<div><span>Rate</span><strong>' + esc(inr(rate) || '—') + '<small>/QTL</small></strong></div>' +
      '<div class="bp-figures-total"><span>Total</span><strong>' +
        esc(inr(total) || '—') + '</strong></div>' +
    '</div>';
  }

  function emptyState(icon, title, body) {
    return '<div class="empty-state">' +
      '<div class="empty-state-icon">' + icon + '</div>' +
      '<h3>' + esc(title) + '</h3><p>' + esc(body) + '</p></div>';
  }

  function loginPrompt(what) {
    return '<div class="empty-state">' +
      '<div class="empty-state-icon">🔒</div><h3>Login required</h3>' +
      '<p>Log in as a buyer to see your ' + esc(what) + '.</p>' +
      '<p><a class="btn btn-primary btn-sm" href="auth.html" style="margin-top:8px;">Log in</a></p>' +
    '</div>';
  }

  /* ======================================================================
     Wiring
     ====================================================================== */

  function refresh() {
    return Promise.all([loadOffers(), loadTransactions()]);
  }

  function init() {
    if (!el('buyer-lots-container')) return;   // not the buyer page

    // Delegated so cards repainted by the page's own renderer keep working.
    document.addEventListener('click', function (e) {
      if (!e.target || !e.target.closest) return;
      if (e.target.closest('[data-bp-close]')) { closeModal(); return; }
      var offer = e.target.closest('.bp-cta-offer');
      if (offer) { openOffer(offer.getAttribute('data-lot')); return; }
      var details = e.target.closest('.bp-cta-details');
      if (details) { openDetails(details.getAttribute('data-lot')); }
    });

    refresh();

    // A farmer may accept an offer while this tab is open; pick that up when
    // the buyer comes back to the tab rather than polling in the background.
    document.addEventListener('visibilitychange', function () {
      if (!document.hidden) refresh();
    });
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    setTimeout(init, 0);
  }

  window.KLBuyerPortal = {
    openOffer: openOffer,
    openDetails: openDetails,
    loadOffers: loadOffers,
    loadTransactions: loadTransactions,
    refresh: refresh
  };
})();
