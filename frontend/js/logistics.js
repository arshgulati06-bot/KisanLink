/**
 * KisanLink — Transportation & Logistics Frontend Module
 * SIH 2026 — PS SIH26132: AgriTech Logistics & Market Linkages
 * =========================================================================
 *
 * Implements the logistics UI and consumes the real backend logistics contracts
 * from commit 85f1e18:
 *   - GET  /api/logistics/requests
 *   - POST /api/logistics/requests
 *   - GET  /api/logistics/transporters
 *   - GET  /api/logistics/vehicles
 *   - POST /api/logistics/estimate
 *
 * Real Statuses: REQUESTED, ASSIGNED, IN_TRANSIT, DELIVERED, CANCELLED
 * Real Vehicle Types: TRACTOR_TROLLEY, TEMPO, PICKUP, TRUCK_9T, TRUCK_16T
 * Real Units: QUINTAL, KG, TONNE
 *
 * Designed to be completely isolated and safe:
 *   - Does not touch any existing backend logic or database.
 *   - Works cleanly in both Buyer and Farmer dashboard environments.
 *   - Handles loading, empty, success, and honest API unavailable states.
 */
(function () {
  'use strict';

  // Real backend enums
  var STATUSES = ['REQUESTED', 'ASSIGNED', 'IN_TRANSIT', 'DELIVERED', 'CANCELLED'];
  var VEHICLE_TYPES = [
    { value: 'TEMPO', label: 'Tempo / Small Commercial (up to 2.5T)' },
    { value: 'PICKUP', label: 'Pickup Truck (up to 1.5T)' },
    { value: 'TRACTOR_TROLLEY', label: 'Tractor Trolley (Farm-to-Mandi, up to 4T)' },
    { value: 'TRUCK_9T', label: 'Intermediate Commercial (9 Tonne)' },
    { value: 'TRUCK_16T', label: 'Heavy Commercial Truck (16 Tonne)' }
  ];
  var UNITS = ['QUINTAL', 'KG', 'TONNE'];

  var state = {
    requests: [],
    transporters: [],
    filterStatus: 'ALL',
    loading: false,
    apiAvailable: true,
    apiNotice: null
  };

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
           'http://localhost:5000/api';
  }

  function token() {
    try { return localStorage.getItem('kisanlink_auth_token'); } catch (e) { return null; }
  }

  function authHeaders(json) {
    var h = { 'Accept': 'application/json' };
    if (json) h['Content-Type'] = 'application/json';
    var t = token();
    if (t) h['Authorization'] = 'Bearer ' + t;
    return h;
  }

  function toast(msg, kind) {
    if (typeof window.showToast === 'function') window.showToast(msg, kind || 'info');
  }

  var MONTHS = ['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'];
  function niceDate(iso) {
    if (!iso) return '—';
    var p = String(iso).slice(0, 10).split('-');
    if (p.length !== 3) return String(iso).slice(0, 10);
    return Number(p[2]) + ' ' + (MONTHS[Number(p[1]) - 1] || p[1]) + ' ' + p[0];
  }

  function statusBadge(status) {
    var s = String(status || 'REQUESTED').toUpperCase();
    var label = s.replace(/_/g, ' ');
    if (s === 'REQUESTED') label = 'Pending / Requested';
    var cls = 'badge-' + s.toLowerCase();
    return '<span class="badge ' + cls + '">' + esc(label) + '</span>';
  }

  /* =========================================================================
     API Requests
     ========================================================================= */

  function fetchRequests(statusFilter) {
    state.loading = true;
    render();

    var url = apiBase() + '/logistics/requests';
    if (statusFilter && statusFilter !== 'ALL') {
      url += '?status=' + encodeURIComponent(statusFilter);
    }

    return fetch(url, { headers: authHeaders() })
      .then(function (r) {
        if (r.status === 404) {
          state.apiAvailable = false;
          state.apiNotice = 'Logistics service endpoint (/api/logistics/requests) returned HTTP 404. The backend transportation service is not mounted on this server instance.';
          state.requests = [];
          return [];
        }
        if (!r.ok) {
          throw new Error('HTTP ' + r.status + ': ' + r.statusText);
        }
        state.apiAvailable = true;
        state.apiNotice = null;
        return r.json();
      })
      .then(function (d) {
        if (Array.isArray(d)) {
          state.requests = d;
        } else if (d && Array.isArray(d.items)) {
          state.requests = d.items;
        } else if (d && Array.isArray(d.data)) {
          state.requests = d.data;
        } else {
          state.requests = [];
        }
        updateBadges();
      })
      .catch(function (err) {
        state.apiAvailable = false;
        state.apiNotice = (err && err.message) || 'Unable to connect to the logistics service.';
        state.requests = [];
      })
      .then(function () {
        state.loading = false;
        render();
      });
  }

  function fetchTransporters() {
    var url = apiBase() + '/logistics/transporters';
    return fetch(url, { headers: authHeaders() })
      .then(function (r) {
        if (!r.ok) return [];
        return r.json();
      })
      .then(function (d) {
        state.transporters = (d && d.items) || (Array.isArray(d) ? d : []);
        renderTransporters();
      })
      .catch(function () {
        state.transporters = [];
      });
  }

  /* =========================================================================
     Rendering UI
     ========================================================================= */

  function updateBadges() {
    var count = state.requests.length;
    ['buyer-logistics-badge', 'sidebar-logistics-badge'].forEach(function (id) {
      var badge = el(id);
      if (badge) {
        badge.textContent = count;
        badge.style.display = count > 0 ? 'inline-block' : 'inline-block';
      }
    });

    // Overview counters
    var activeCount = state.requests.filter(function (r) {
      return r.status === 'REQUESTED' || r.status === 'ASSIGNED' || r.status === 'IN_TRANSIT';
    }).length;

    var inTransitCount = state.requests.filter(function (r) {
      return r.status === 'IN_TRANSIT';
    }).length;

    var deliveredCount = state.requests.filter(function (r) {
      return r.status === 'DELIVERED';
    }).length;

    var elTotal = el('logistics-stat-total');
    var elActive = el('logistics-stat-active');
    var elTransit = el('logistics-stat-transit');
    var elDelivered = el('logistics-stat-delivered');

    if (elTotal) elTotal.textContent = count;
    if (elActive) elActive.textContent = activeCount;
    if (elTransit) elTransit.textContent = inTransitCount;
    if (elDelivered) elDelivered.textContent = deliveredCount;
  }

  function render() {
    var container = el('logistics-requests-container');
    if (!container) return;

    if (!token()) {
      container.innerHTML =
        '<div class="empty-state">' +
          '<div class="empty-state-icon">🔒</div>' +
          '<h3>Authentication Required</h3>' +
          '<p>Please sign in to view and manage transportation requests.</p>' +
          '<a class="btn btn-primary btn-sm" href="auth.html" style="margin-top:8px;">Sign In</a>' +
        '</div>';
      return;
    }

    if (state.loading) {
      container.innerHTML =
        '<div class="empty-state">' +
          '<div class="cqa-spinner-ring" style="width:28px;height:28px;border-width:3px;margin:0 auto 8px;"></div>' +
          '<p style="font-size:var(--text-xs);color:var(--color-slate-500);">Loading transport requests&hellip;</p>' +
        '</div>';
      return;
    }

    var html = '';

    // If API notice exists
    if (state.apiNotice) {
      html +=
        '<div class="logistics-notice-card warn">' +
          '<div class="logistics-notice-icon">⚠️</div>' +
          '<div class="logistics-notice-body">' +
            '<h4>Logistics Backend Integration Notice</h4>' +
            '<p>' + esc(state.apiNotice) + '</p>' +
            '<p style="margin-top:4px;font-size:0.7rem;color:var(--color-slate-600);">' +
              'The frontend module is fully mapped to real <code>/api/logistics/*</code> contracts. ' +
              'You can still test raising a transport request below to verify payload validation.' +
            '</p>' +
          '</div>' +
        '</div>';
    }

    var filtered = state.requests;
    if (state.filterStatus && state.filterStatus !== 'ALL') {
      filtered = state.requests.filter(function (r) {
        return String(r.status).toUpperCase() === state.filterStatus;
      });
    }

    if (!filtered.length) {
      html +=
        '<div class="empty-state">' +
          '<div class="empty-state-icon">🚚</div>' +
          '<h3>No Transport Requests</h3>' +
          '<p>' + (state.filterStatus === 'ALL'
            ? 'No transport requests have been raised yet. Book farm-gate pickup for lots or accepted deals.'
            : 'No transport requests matching status "' + esc(state.filterStatus) + '".') +
          '</p>' +
          '<button type="button" class="btn btn-primary btn-sm open-request-transport-modal" style="margin-top:var(--space-3);">' +
            '<span>+ Request Transportation</span>' +
          '</button>' +
        '</div>';
      container.innerHTML = html;
      return;
    }

    html += '<div class="logistics-cards-container">' +
      filtered.map(function (req) {
        return renderCard(req);
      }).join('') +
    '</div>';

    container.innerHTML = html;
  }

  function renderCard(req) {
    var reqId = req.id ? '#TRP-' + req.id : (req.transaction_code ? req.transaction_code : '#TRP');
    var crop = req.crop_name || req.commodity || ('Lot #' + (req.lot_id || '—'));
    var qty = req.quantity ? req.quantity + ' ' + (req.unit || 'QUINTAL') : '—';
    var pickup = [req.pickup_district, req.pickup_address].filter(Boolean).join(', ') || 'Farm Gate';
    var drop = [req.drop_district, req.drop_address].filter(Boolean).join(', ') || 'Destination Mandi/Plant';
    var dist = req.distance_km ? Number(req.distance_km).toFixed(1) + ' km' : null;
    var estCost = req.estimated_cost ? inr(req.estimated_cost) : null;
    var actCost = req.actual_cost ? inr(req.actual_cost) : null;

    // Transporter & Vehicle details
    var transporterName = req.transporter_name || req.provider_name || 'Pending assignment';
    var transporterPhone = req.transporter_phone || req.provider_phone;
    var vehicleType = req.assigned_vehicle_type || req.vehicle_type;
    var vehicleNum = req.assigned_vehicle_number;
    var vehicleCap = req.assigned_vehicle_capacity ? req.assigned_vehicle_capacity + 'T' : null;

    // Progress bar for active transit
    var progress = Number(req.route_progress_percent) || 0;
    var eta = req.eta_minutes ? Math.round(req.eta_minutes) + ' mins' : null;
    var routeStatus = req.route_status || 'NOT_STARTED';

    return (
      '<article class="logistics-card" data-request-id="' + esc(req.id) + '">' +
        '<div class="logistics-card-head">' +
          '<div class="logistics-card-code">' +
            '<span class="logistics-req-id">' + esc(reqId) + '</span>' +
            '<span style="font-weight:var(--weight-bold);font-size:var(--text-sm);">' + esc(crop) + '</span>' +
            '<span style="font-size:var(--text-xs);color:var(--color-slate-500);">(' + esc(qty) + ')</span>' +
          '</div>' +
          '<div class="flex items-center gap-2">' +
            (req.scheduled_date ? '<span class="logistics-card-date">Scheduled: ' + esc(niceDate(req.scheduled_date)) + '</span>' : '') +
            statusBadge(req.status) +
          '</div>' +
        '</div>' +

        '<div class="logistics-card-grid">' +
          // Column 1: Route
          '<div class="logistics-route-col">' +
            '<div class="logistics-point">' +
              '<div class="logistics-point-icon" style="color:var(--color-primary-600);">' +
                '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><circle cx="12" cy="12" r="8"/><circle cx="12" cy="12" r="3"/></svg>' +
              '</div>' +
              '<div>' +
                '<div class="logistics-point-title">Pickup</div>' +
                '<div class="logistics-point-sub">' + esc(pickup) + '</div>' +
              '</div>' +
            '</div>' +

            '<div class="logistics-route-connector"></div>' +

            '<div class="logistics-point">' +
              '<div class="logistics-point-icon" style="color:var(--color-accent-amber);">' +
                '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><path d="M12 2v20M17 5H9.5a3.5 3.5 0 0 0 0 7h5a3.5 3.5 0 0 1 0 7H6"/></svg>' +
              '</div>' +
              '<div>' +
                '<div class="logistics-point-title">Destination</div>' +
                '<div class="logistics-point-sub">' + esc(drop) + '</div>' +
              '</div>' +
            '</div>' +

            (dist ? '<div class="logistics-distance-tag"><span>🛣️</span><span>' + esc(dist) + '</span></div>' : '') +
          '</div>' +

          // Column 2: Assigned Fleet
          '<div class="logistics-fleet-col">' +
            '<div class="logistics-fleet-row">' +
              '<span class="logistics-fleet-label">Transporter:</span>' +
              '<span class="logistics-fleet-val"><strong>' + esc(transporterName) + '</strong></span>' +
            '</div>' +
            (transporterPhone ? (
              '<div class="logistics-fleet-row">' +
                '<span class="logistics-fleet-label">Contact:</span>' +
                '<span class="logistics-fleet-val">' + esc(transporterPhone) + '</span>' +
              '</div>'
            ) : '') +
            (vehicleType ? (
              '<div class="logistics-fleet-row">' +
                '<span class="logistics-fleet-label">Vehicle Type:</span>' +
                '<span class="logistics-fleet-val">' + esc(vehicleType.replace(/_/g, ' ')) + '</span>' +
              '</div>'
            ) : '') +
            (vehicleNum ? (
              '<div class="logistics-fleet-row">' +
                '<span class="logistics-fleet-label">Vehicle No:</span>' +
                '<span class="logistics-fleet-val" style="font-family:var(--font-mono);">' + esc(vehicleNum) + (vehicleCap ? ' (' + esc(vehicleCap) + ')' : '') + '</span>' +
              '</div>'
            ) : '') +
            (req.incident_status && req.incident_status !== 'NONE' ? (
              '<div class="logistics-fleet-row" style="color:var(--color-accent-rose);">' +
                '<span class="logistics-fleet-label" style="color:var(--color-accent-rose);">Incident:</span>' +
                '<span class="logistics-fleet-val">' + esc(req.incident_status) + '</span>' +
              '</div>'
            ) : '') +
          '</div>' +

          // Column 3: Pricing & Notes
          '<div class="logistics-cost-col">' +
            '<div>' +
              '<div class="logistics-cost-label">Est. Transport Cost</div>' +
              '<div class="logistics-cost-amount">' + (estCost || 'Calculating…') + '</div>' +
              (actCost ? '<div style="font-size:0.7rem;color:var(--color-slate-500);margin-top:2px;">Final: ' + esc(actCost) + '</div>' : '') +
            '</div>' +
            (req.notes ? (
              '<div style="font-size:0.7rem;color:var(--color-slate-600);border-top:1px dashed var(--color-primary-200);padding-top:4px;">' +
                'Note: “' + esc(req.notes) + '”' +
              '</div>'
            ) : '') +
          '</div>' +
        '</div>' +

        // Progress bar for active requests
        (req.status === 'IN_TRANSIT' || progress > 0 ? (
          '<div class="logistics-progress-wrap">' +
            '<div class="logistics-progress-meta">' +
              '<span>Route Progress: ' + progress + '% (' + esc(routeStatus) + ')</span>' +
              (eta ? '<span>ETA: <strong>' + esc(eta) + '</strong></span>' : '') +
            '</div>' +
            '<div class="logistics-progress-bar">' +
              '<div class="logistics-progress-fill" style="width:' + Math.min(100, Math.max(0, progress)) + '%;"></div>' +
            '</div>' +
          '</div>'
        ) : '') +
      '</article>'
    );
  }

  function renderTransporters() {
    var container = el('logistics-transporters-container');
    if (!container) return;

    if (!state.transporters.length) {
      container.innerHTML =
        '<p style="font-size:var(--text-xs);color:var(--color-slate-500);margin:var(--space-2) 0;">' +
          'No verified transporters registered in this zone currently.' +
        '</p>';
      return;
    }

    container.innerHTML =
      '<div class="logistics-transporters-grid">' +
        state.transporters.map(function (tr) {
          var rating = tr.rating ? Number(tr.rating).toFixed(1) + ' ★' : 'New';
          var rel = tr.reliability_score ? tr.reliability_score + '% reliable' : null;
          return (
            '<div class="logistics-transporter-card">' +
              '<div class="logistics-transporter-head">' +
                '<span class="logistics-transporter-name">' + esc(tr.business_name || 'Transporter') + '</span>' +
                '<span class="badge badge-sky">' + esc(rating) + '</span>' +
              '</div>' +
              '<div class="logistics-transporter-meta">' +
                '<div>Location: ' + esc([tr.district, tr.state].filter(Boolean).join(', ') || 'Regional') + '</div>' +
                (tr.phone ? '<div>Phone: ' + esc(tr.phone) + '</div>' : '') +
                (rel ? '<div>Reliability Score: ' + esc(rel) + '</div>' : '') +
                (tr.total_trips != null ? '<div>Completed Trips: ' + esc(tr.completed_trips || 0) + ' / ' + esc(tr.total_trips) + '</div>' : '') +
              '</div>' +
            '</div>'
          );
        }).join('') +
      '</div>';
  }

  /* =========================================================================
     Request Transport Modal Form Handler
     ========================================================================= */

  function openRequestModal(prefill) {
    if (!token()) {
      toast('Please sign in to book transportation.', 'error');
      return;
    }

    var modal = el('request-transport-modal');
    if (!modal) return;

    // Reset feedback and values
    var fb = el('request-transport-feedback');
    if (fb) { fb.hidden = true; fb.textContent = ''; }

    var p = prefill || {};
    if (el('req-lot-id')) el('req-lot-id').value = p.lot_id || '';
    if (el('req-tx-id')) el('req-tx-id').value = p.transaction_id || '';
    if (el('req-pickup-addr')) el('req-pickup-addr').value = p.pickup_address || '';
    if (el('req-pickup-dist')) el('req-pickup-dist').value = p.pickup_district || '';
    if (el('req-drop-addr')) el('req-drop-addr').value = p.drop_address || '';
    if (el('req-drop-dist')) el('req-drop-dist').value = p.drop_district || '';
    if (el('req-quantity')) el('req-quantity').value = p.quantity || '';
    if (el('req-unit')) el('req-unit').value = p.unit || 'QUINTAL';
    if (el('req-date')) {
      var tomorrow = new Date();
      tomorrow.setDate(tomorrow.getDate() + 1);
      el('req-date').value = p.scheduled_date || tomorrow.toISOString().slice(0, 10);
    }
    if (el('req-vehicle-type')) el('req-vehicle-type').value = p.vehicle_type || 'TEMPO';
    if (el('req-notes')) el('req-notes').value = p.notes || '';

    modal.classList.add('modal-open');
    modal.setAttribute('aria-hidden', 'false');
  }

  function closeRequestModal() {
    var modal = el('request-transport-modal');
    if (modal) {
      modal.classList.remove('modal-open');
      modal.setAttribute('aria-hidden', 'true');
    }
  }

  function submitRequest(e) {
    e.preventDefault();
    var fb = el('request-transport-feedback');
    var btn = el('request-transport-submit-btn');

    function feedback(msg, kind) {
      if (!fb) return;
      fb.textContent = msg;
      fb.hidden = !msg;
      fb.style.color = kind === 'error' ? 'var(--color-accent-rose)' : 'var(--color-primary-700)';
    }

    var lotId = parseInt((el('req-lot-id') || {}).value, 10) || null;
    var txId = parseInt((el('req-tx-id') || {}).value, 10) || null;
    var pickupAddr = ((el('req-pickup-addr') || {}).value || '').trim();
    var pickupDist = ((el('req-pickup-dist') || {}).value || '').trim();
    var dropAddr = ((el('req-drop-addr') || {}).value || '').trim();
    var dropDist = ((el('req-drop-dist') || {}).value || '').trim();
    var qty = parseFloat((el('req-quantity') || {}).value);
    var unit = ((el('req-unit') || {}).value || 'QUINTAL');
    var date = ((el('req-date') || {}).value || '').trim();
    var vehicleType = ((el('req-vehicle-type') || {}).value || 'TEMPO');
    var notes = ((el('req-notes') || {}).value || '').trim();

    if (!lotId && !txId) {
      feedback('Please provide either a Lot ID or Transaction ID for transport linkage.', 'error');
      return;
    }

    if (!pickupDist && !pickupAddr) {
      feedback('Please specify a pickup location or district.', 'error');
      return;
    }

    if (!dropDist && !dropAddr) {
      feedback('Please specify a destination location or district.', 'error');
      return;
    }

    if (!isFinite(qty) || qty <= 0) {
      feedback('Please enter a valid quantity greater than 0.', 'error');
      return;
    }

    // Build payload matching real backend CREATE_REQUEST_SCHEMA
    var payload = {
      quantity: qty,
      unit: unit,
      vehicle_type: vehicleType
    };

    if (lotId) payload.lot_id = lotId;
    if (txId) payload.transaction_id = txId;
    if (pickupAddr) payload.pickup_address = pickupAddr;
    if (pickupDist) payload.pickup_district = pickupDist;
    if (dropAddr) payload.drop_address = dropAddr;
    if (dropDist) payload.drop_district = dropDist;
    if (date) payload.scheduled_date = date;
    if (notes) payload.notes = notes;

    var originalText = btn ? btn.textContent : '';
    if (btn) {
      btn.disabled = true;
      btn.textContent = 'Raising Request…';
    }
    feedback('');

    fetch(apiBase() + '/logistics/requests', {
      method: 'POST',
      headers: authHeaders(true),
      body: JSON.stringify(payload)
    })
    .then(function (r) {
      return r.json().catch(function () { return {}; })
        .then(function (data) {
          return { ok: r.ok, status: r.status, data: data };
        });
    })
    .then(function (res) {
      if (!res.ok) {
        var errMessage = (res.data && res.data.error) ||
                         (res.data && res.data.message) ||
                         ('Server returned HTTP ' + res.status);
        throw new Error(errMessage);
      }

      feedback('Transport request raised successfully.', 'ok');
      toast('Transport request submitted successfully!', 'success');
      setTimeout(function () {
        closeRequestModal();
        fetchRequests(state.filterStatus);
      }, 1200);
    })
    .catch(function (err) {
      var msg = err.message || 'Could not raise transport request.';
      feedback(msg, 'error');
    })
    .then(function () {
      if (btn) {
        btn.disabled = false;
        btn.textContent = originalText;
      }
    });
  }

  /* =========================================================================
     Initialization & Event Wiring
     ========================================================================= */

  function init() {
    var section = el('logistics-section');
    if (!section) return;

    // Delegated click listeners (works for both static and dynamically rendered elements)
    document.addEventListener('click', function (e) {
      if (!e.target || !e.target.closest) return;

      var openBtn = e.target.closest('.open-request-transport-modal');
      if (openBtn) {
        e.preventDefault();
        openRequestModal();
        return;
      }

      var pill = e.target.closest('.logistics-pill-btn');
      if (pill) {
        e.preventDefault();
        document.querySelectorAll('.logistics-pill-btn').forEach(function (b) { b.classList.remove('active'); });
        pill.classList.add('active');
        state.filterStatus = pill.getAttribute('data-status') || 'ALL';
        fetchRequests(state.filterStatus);
        return;
      }

      if (e.target.closest('#close-request-transport-modal') || e.target.closest('#cancel-request-transport-modal')) {
        e.preventDefault();
        closeRequestModal();
        return;
      }

      var modal = el('request-transport-modal');
      if (e.target === modal) {
        closeRequestModal();
      }
    });

    document.addEventListener('keydown', function (e) {
      if (e.key === 'Escape') {
        var modal = el('request-transport-modal');
        if (modal && modal.classList.contains('modal-open')) {
          closeRequestModal();
        }
      }
    });

    // Modal form submit
    var form = el('request-transport-form');
    if (form) form.addEventListener('submit', submitRequest);

    // Refresh button
    var refreshBtn = el('logistics-refresh-btn');
    if (refreshBtn) {
      refreshBtn.addEventListener('click', function () {
        fetchRequests(state.filterStatus);
        fetchTransporters();
      });
    }

    // Initial load
    fetchRequests('ALL');
    fetchTransporters();
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    setTimeout(init, 0);
  }

  // Export module interface
  window.KLLogistics = {
    fetchRequests: fetchRequests,
    fetchTransporters: fetchTransporters,
    openRequestModal: openRequestModal,
    closeRequestModal: closeRequestModal,
    getState: function () { return state; }
  };
})();
