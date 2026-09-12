/**
 * KisanLink - Dashboard Controller & Client State Manager
 * SIH 2026 — PS SIH26132: Market Linkages & Price Discovery
 * Unified state, lot creation, offer workflow, and transaction lifecycle tracker
 */

class DashboardStateManager {
  constructor() {
    this.storageKey = 'kisanlink_prototype_state_v1';
    this.state = this.loadState();
  }

  loadState() {
    try {
      const saved = localStorage.getItem(this.storageKey);
      if (saved) {
        return JSON.parse(saved);
      }
    } catch (e) {
      console.warn('[DashboardState] LocalStorage unavailable, using in-memory state:', e);
    }

    // Default initialization from CONFIG
    const initial = window.CONFIG?.INITIAL_DATA || {};
    return {
      farmerProfile: initial.FARMER_PROFILE || {},
      buyerProfile: initial.BUYER_PROFILE || {},
      lots: [],
      demands: [],
      offers: [],
      transactions: []
    };
  }

  saveState() {
    try {
      localStorage.setItem(this.storageKey, JSON.stringify(this.state));
    } catch (e) {
      console.warn('[DashboardState] Failed to persist state:', e);
    }
  }

  // --- Farmer Operations ---
  getLots() {
    return this.state.lots;
  }

  createLot(lotData) {
    const newLot = {
      id: `LOT-2026-${String(this.state.lots.length + 85).padStart(3, '0')}`,
      crop: lotData.crop,
      variety: lotData.variety || 'Standard Commercial',
      quantity: Number(lotData.quantity),
      unit: lotData.unit || 'QTL',
      grade: lotData.grade || 'Grade A',
      location: lotData.location || '',
      harvestDate: lotData.harvestDate || new Date().toISOString().split('T')[0],
      expectedPrice: Number(lotData.expectedPrice) || 0,
      status: 'ACTIVE_MARKET',
      createdDate: new Date().toISOString().split('T')[0]
    };

    this.state.lots.unshift(newLot);
    this.saveState();
    return newLot;
  }

  // --- Buyer Operations ---
  getDemands() {
    return this.state.demands;
  }

  createDemand(demandData) {
    const newDemand = {
      id: `DEMAND-2026-${String(this.state.demands.length + 105).padStart(3, '0')}`,
      buyerName: this.state.buyerProfile.name || 'Buyer',
      buyerType: this.state.buyerProfile.type || '',
      crop: demandData.crop,
      quantity: Number(demandData.quantity),
      unit: demandData.unit || 'QTL',
      grade: demandData.grade || 'Grade A',
      deliveryLocation: demandData.deliveryLocation || '',
      offeredRate: Number(demandData.offeredRate) || 0,
      requiredDate: demandData.requiredDate || new Date().toISOString().split('T')[0],
      status: 'ACTIVE'
    };

    this.state.demands.unshift(newDemand);
    this.saveState();
    return newDemand;
  }

  // --- Offers & Transactions ---
  getOffers() {
    return this.state.offers;
  }

  /**
   * Respond to a real offer on the server.
   *
   * This used to mutate localStorage only and mint a client-side transaction
   * id, so the buyer never learned the offer was accepted and the
   * "transaction" existed nowhere but this browser. It now posts to
   * /api/offers/<id>/respond, which is what creates the real transaction row.
   *
   * @returns {Promise<Object>} resolves with the server's response
   */
  respondToOffer(offerId, status) {
    if (!window.apiClient) {
      return Promise.reject(new Error('API client is not loaded on this page.'));
    }
    return window.apiClient
      .post('/offers/' + encodeURIComponent(offerId) + '/respond', { status: status })
      .then((res) => {
        const data = res.data || {};
        if (!data.success) throw new Error(data.error || 'The server rejected that response.');
        return data;
      });
  }

  acceptOffer(offerId) { return this.respondToOffer(offerId, 'ACCEPTED'); }

  rejectOffer(offerId) { return this.respondToOffer(offerId, 'REJECTED'); }

  /** Load the signed-in user's real offers and transactions from the API. */
  refreshOffersAndTransactions() {
    if (!window.apiClient || !window.apiClient.getAuthToken()) {
      return Promise.resolve({ offers: [], transactions: [] });
    }
    return Promise.all([
      window.apiClient.get('/offers/my').catch(() => ({ data: {} })),
      window.apiClient.get('/transactions/my').catch(() => ({ data: {} })),
    ]).then(([o, t]) => {
      this.state.offers = ((o.data || {}).offers || []).map(_normaliseOffer);
      this.state.transactions = ((t.data || {}).transactions || []).map(_normaliseTx);
      this.saveState();
      return { offers: this.state.offers, transactions: this.state.transactions };
    });
  }

  getTransactions() {
    return this.state.transactions;
  }
}

// Global State Instance
window.dashboardState = new DashboardStateManager();

/* --------------------------------------------------------------------------
   UI Binders & Interactive Handlers
   -------------------------------------------------------------------------- */
document.addEventListener('DOMContentLoaded', () => {
  initDashboardSidebar();
  initFarmerDashboard();
  initBuyerDashboard();
  initCreateLotModal();
  initCreateDemandModal();
});

/**
 * Mobile Sidebar Toggle
 */
function initDashboardSidebar() {
  const toggleBtn = document.querySelector('.sidebar-toggle-btn');
  const sidebar = document.querySelector('.dashboard-sidebar');
  if (!toggleBtn || !sidebar) return;

  toggleBtn.addEventListener('click', () => {
    sidebar.classList.toggle('sidebar-open');
  });

  // Close sidebar on link click on mobile
  document.querySelectorAll('.sidebar-link').forEach(link => {
    link.addEventListener('click', () => {
      sidebar.classList.remove('sidebar-open');
    });
  });
}

/**
 * Farmer Dashboard UI Controller
 * Loads lots from the backend API on page init.
 */
function initFarmerDashboard() {
  const lotsContainer = document.getElementById('farmer-lots-container');
  if (!lotsContainer) return; // Not on farmer page

  loadLotsFromBackend();
  // Render immediately from whatever is cached, then replace with the real
  // server state. Without this fetch the Received Offers panel showed the
  // empty state forever, because offers only ever lived in localStorage —
  // a buyer's offer could never reach the farmer's screen.
  renderFarmerOffers();
  renderFarmerTransactions();
  window.dashboardState.refreshOffersAndTransactions().then(function () {
    renderFarmerOffers();
    renderFarmerTransactions();
  }).catch(function (e) {
    console.warn('[offers] could not load offers from the server:', e);
  });
}

/**
 * Load farmer lots from backend, fall back to localStorage state if backend fails.
 */
async function loadLotsFromBackend() {
  const container = document.getElementById('farmer-lots-container');
  const statCount = document.getElementById('stat-active-lots-count');
  const sidebarBadge = document.getElementById('sidebar-lot-badge');
  if (!container) return;

  // Show loading spinner
  container.innerHTML = '<div class="empty-state" style="grid-column:1/-1;"><div class="cqa-spinner-ring" style="width:28px;height:28px;border-width:3px;margin:0 auto 8px;"></div><p style="font-size:var(--text-xs);color:var(--color-slate-500);">Loading your lots…</p></div>';

  try {
    const token = localStorage.getItem('kisanlink_auth_token');
    if (!token) {
      // Not logged in — show empty state
      renderLotsUI([]);
      return;
    }
    const result = await window.getMyLots();
    const lots = (result && result.lots) ? result.lots : [];
    // Sync backend lots into dashboardState for compatibility with match/offer handlers
    window.dashboardState.state.lots = lots.map(l => ({
      id: l.id || l.lot_id,
      crop: l.commodity || l.crop,
      variety: l.variety || 'Standard',
      quantity: l.quantity_qtl || l.quantity || 0,
      unit: 'QTL',
      grade: l.grade || 'Grade A',
      location: l.location || (l.district && l.state ? `${l.district}, ${l.state}` : ''),
      harvestDate: l.harvest_date || l.harvestDate || '',
      expectedPrice: l.expected_price || l.price_per_qtl || l.expectedPrice || 0,
      status: l.status || 'ACTIVE',
      createdDate: l.created_at ? l.created_at.split('T')[0] : '',
    }));
    window.dashboardState.saveState();
    renderLotsUI(window.dashboardState.state.lots);
  } catch (err) {
    // Backend unavailable — show local lots if any exist
    const localLots = window.dashboardState.getLots();
    if (localLots.length > 0) {
      renderLotsUI(localLots);
      if (typeof showToast === 'function') showToast('Could not sync with backend — showing cached lots.', 'warning');
    } else {
      renderLotsUI([]);
    }
  }
}

function renderLotsUI(lots) {
  const container = document.getElementById('farmer-lots-container');
  const statCount = document.getElementById('stat-active-lots-count');
  const sidebarBadge = document.getElementById('sidebar-lot-badge');
  if (!container) return;
  if (statCount) statCount.textContent = lots.length;
  if (sidebarBadge) sidebarBadge.textContent = lots.length;
  renderFarmerLots(lots);
}

function renderFarmerLots(lots) {
  const container = document.getElementById('farmer-lots-container');
  if (!container) return;

  // Accept lots as parameter (from backend) or fall back to dashboardState
  if (!lots) lots = window.dashboardState.getLots();

  if (lots.length === 0) {
    container.innerHTML = `
      <div class="empty-state" style="grid-column: 1 / -1;">
        <div class="empty-state-icon">🌾</div>
        <h3>No Active Sale Lots</h3>
        <p>Create your first crop lot to discover market prices and buyer matching opportunities.</p>
        <button type="button" class="btn btn-primary btn-sm open-create-lot-modal">
          <span>+ Create Sale Lot</span>
        </button>
      </div>
    `;
    return;
  }

  container.innerHTML = lots.map(lot => `
    <div class="lot-card">
      <div class="lot-card-header">
        <div>
          <h3 class="lot-title">${lot.crop}</h3>
          <div class="lot-variety">${lot.variety || 'Standard'}</div>
        </div>
        <span class="badge ${lot.status === 'OFFER_ACCEPTED' ? 'badge-verified' : lot.status === 'OFFER_RECEIVED' ? 'badge-amber' : 'badge-success'}">
          ${(lot.status || 'ACTIVE').replace(/_/g, ' ')}
        </span>
      </div>

      <div class="lot-spec-grid">
        <div class="spec-item">
          <span class="spec-label">Volume</span>
          <span class="spec-val">${lot.quantity} ${lot.unit || 'QTL'}</span>
        </div>
        <div class="spec-item">
          <span class="spec-label">Grade</span>
          <span class="spec-val">${lot.grade || '—'}</span>
        </div>
        <div class="spec-item">
          <span class="spec-label">Location</span>
          <span class="spec-val">${lot.location || '—'}</span>
        </div>
        <div class="spec-item">
          <span class="spec-label">${lot.harvestDate ? 'Harvest Date' : 'Created'}</span>
          <span class="spec-val">${lot.harvestDate || lot.createdDate || '—'}</span>
        </div>
      </div>

      <div class="flex items-center justify-between" style="padding-top: var(--space-2); border-top: 1px solid var(--color-slate-100);">
        <div>
          <span class="text-xs text-slate">Lot ID:</span>
          <span class="font-mono text-xs text-slate-600" style="margin-left: 4px;">#${lot.id}</span>
          ${lot.expectedPrice ? `<span class="font-mono font-bold text-slate-900" style="margin-left: 8px;">₹${Number(lot.expectedPrice).toLocaleString('en-IN')}/${lot.unit || 'QTL'}</span>` : ''}
        </div>
        <button type="button" class="btn btn-outline btn-sm"
          onclick="handleViewMatches('${lot.id}', '${lot.crop}', ${lot.quantity || 0}, '${lot.unit || 'QTL'}', '${lot.grade || ''}', '${lot.location || ''}', ${lot.expectedPrice || 0})"
          aria-label="View matched buyers for ${lot.crop} lot">
          <span>View Matches</span>
        </button>
      </div>
    </div>
  `).join('');
}


/** Map an /api/offers/my row onto the shape the offer card renders. */
function _normaliseOffer(row) {
  const qty = Number(row.quantity_qtl) || 0;
  const rate = Number(row.price_per_qtl) || 0;
  return {
    id: row.id,
    status: row.status || 'PENDING',
    buyerName: row.buyer_name || ('Buyer #' + (row.buyer_user_id || '?')),
    buyerLocation: row.buyer_location || row.buyer_district || 'Not stated',
    crop: row.commodity || row.crop || 'Lot #' + (row.lot_id || '?'),
    lotId: row.lot_id,
    quantity: qty,
    unit: 'QTL',
    offeredRate: rate,
    // Net take-home is only shown when the server actually computed it —
    // no client-side guess at freight or mandi fees.
    netTakeHome: row.net_per_qtl != null ? Number(row.net_per_qtl) : null,
    terms: row.message || 'No additional terms stated.',
  };
}

/** Map an /api/transactions/my row onto the transaction tracker's shape. */
function _normaliseTx(row) {
  const qty = Number(row.quantity_qtl) || 0;
  const rate = Number(row.price_per_qtl) || 0;
  return {
    id: row.id,
    lotId: row.lot_id,
    crop: row.commodity || row.crop || 'Lot #' + (row.lot_id || '?'),
    quantity: qty,
    unit: 'QTL',
    buyerName: row.buyer_name || ('Buyer #' + (row.buyer_user_id || '?')),
    agreedRate: rate,
    grossTotal: row.total_value != null ? Number(row.total_value) : qty * rate,
    status: row.status || 'ACCEPTED',
    currentStep: 2,
    date: (row.created_at || '').slice(0, 10),
  };
}

function renderFarmerOffers() {
  const container = document.getElementById('farmer-offers-container');
  const statOffers = document.getElementById('stat-pending-offers-count');
  if (!container) return;

  const offers = window.dashboardState.getOffers();
  const pendingCount = offers.filter(o => o.status === 'PENDING').length;
  if (statOffers) statOffers.textContent = pendingCount;

  if (offers.length === 0) {
    container.innerHTML = `
      <div class="empty-state">
        <div class="empty-state-icon">📬</div>
        <h3>No Offers Received Yet</h3>
        <p>Once verified buyers review your active lots, their formal purchase offers will appear here.</p>
      </div>
    `;
    return;
  }

  container.innerHTML = offers.map(offer => `
    <div class="offer-card ${offer.status === 'ACCEPTED' ? 'offer-accepted' : ''}" id="offer-card-${offer.id}">
      <div class="offer-main-info">
        <div class="offer-buyer-avatar">🏢</div>
        <div>
          <div class="flex items-center gap-2">
            <h3 style="font-size: var(--text-base); font-weight: var(--weight-bold);">${offer.buyerName}</h3>
            <span class="badge ${offer.status === 'ACCEPTED' ? 'badge-verified' : 'badge-amber'}">${offer.status}</span>
          </div>
          <p style="font-size: var(--text-xs); color: var(--color-slate-500); margin-top: 2px;">
            Lot: <strong>${offer.crop}</strong> (${offer.quantity} ${offer.unit}) • Distance: ${offer.buyerLocation}
          </p>
          <p style="font-size: 0.75rem; color: var(--color-slate-600); margin-top: 4px; max-width: 480px;">
            Terms: ${offer.terms}
          </p>
        </div>
      </div>

      <div class="flex flex-col items-end gap-3">
        <div class="text-right">
          <div class="text-xs text-slate">Offered Gross Rate:</div>
          <div class="offer-price-highlight">₹${offer.offeredRate.toLocaleString('en-IN')}<span style="font-size: 0.8rem; font-weight: normal; color: var(--color-slate-500);"> /${offer.unit}</span></div>
          ${offer.netTakeHome != null ? `<div class="text-xs text-emerald font-semibold">Est. Net Take-Home: ₹${offer.netTakeHome.toLocaleString('en-IN')}/${offer.unit}</div>` : `<div class="text-xs text-slate">Use <strong>Sell Now</strong> for net realisation after freight and mandi fees.</div>`}
        </div>

        ${offer.status === 'PENDING' ? `
          <div class="flex items-center gap-2">
            <button type="button" class="btn btn-primary btn-sm" onclick="handleAcceptOffer('${offer.id}')">
              <span>Accept Offer</span>
            </button>
            <button type="button" class="btn btn-outline btn-sm" onclick="handleRejectOffer('${offer.id}')">
              <span>Decline</span>
            </button>
          </div>
        ` : `
          <span class="badge badge-verified" style="padding: 0.4rem 0.8rem;">
            ✔ Agreement Confirmed
          </span>
        `}
      </div>
    </div>
  `).join('');
}

function renderFarmerTransactions() {
  const container = document.getElementById('farmer-transactions-container');
  if (!container) return;

  const transactions = window.dashboardState.getTransactions();
  if (transactions.length === 0) {
    container.innerHTML = `
      <div class="empty-state">
        <div class="empty-state-icon">📋</div>
        <h3>No Transactions in Progress</h3>
        <p>Accepted offers will automatically initiate an end-to-end transparent transaction milestone tracker.</p>
      </div>
    `;
    return;
  }

  container.innerHTML = transactions.map(tx => `
    <div class="transaction-card" style="margin-bottom: var(--space-4);">
      <div class="tx-header">
        <div>
          <div class="flex items-center gap-2">
            <span class="font-bold text-slate-900">${tx.id}</span>
            <span class="badge badge-sky">${tx.crop} (${tx.quantity} ${tx.unit})</span>
          </div>
          <div class="text-xs text-slate" style="margin-top: 2px;">
            Buyer: <strong>${tx.buyerName}</strong> • Agreed Total: <span class="font-mono font-bold text-slate-900">₹${tx.grossTotal.toLocaleString('en-IN')}</span>
          </div>
        </div>
        <span class="badge badge-verified">${tx.status.replace('_', ' ')}</span>
      </div>

      <!-- Stepper Lifecycle -->
      <div class="stepper-track">
        <div class="step-node ${tx.currentStep >= 1 ? 'completed' : 'active'}">
          <div class="step-node-icon">1</div>
          <span class="step-node-label">Offer Accepted</span>
        </div>
        <div class="step-node ${tx.currentStep >= 2 ? (tx.currentStep > 2 ? 'completed' : 'active') : ''}">
          <div class="step-node-icon">2</div>
          <span class="step-node-label">Transaction Created</span>
        </div>
        <div class="step-node ${tx.currentStep >= 3 ? (tx.currentStep > 3 ? 'completed' : 'active') : ''}">
          <div class="step-node-icon">3</div>
          <span class="step-node-label">Logistics Pending</span>
        </div>
        <div class="step-node ${tx.currentStep >= 4 ? (tx.currentStep > 4 ? 'completed' : 'active') : ''}">
          <div class="step-node-icon">4</div>
          <span class="step-node-label">Delivered & Inspected</span>
        </div>
        <div class="step-node ${tx.currentStep >= 5 ? 'completed' : ''}">
          <div class="step-node-icon">5</div>
          <span class="step-node-label">Payment Settled</span>
        </div>
      </div>
    </div>
  `).join('');
}

function _afterOfferResponse(message, kind) {
  return window.dashboardState.refreshOffersAndTransactions().then(function () {
    renderFarmerOffers();
    renderFarmerLots();
    renderFarmerTransactions();
    if (typeof showToast === 'function') showToast(message, kind);
  });
}

function _offerError(err) {
  var msg = (err && err.message) || 'That could not be saved. Please try again.';
  if (typeof showToast === 'function') showToast(msg, 'error');
  console.error('[offers]', err);
}

window.handleAcceptOffer = function(offerId) {
  window.dashboardState.acceptOffer(offerId).then(function (data) {
    var tx = data.transaction || {};
    _afterOfferResponse(
      tx.id ? ('Offer accepted. Transaction #' + tx.id + ' created.')
            : 'Offer accepted.', 'success');
  }).catch(_offerError);
};

window.handleRejectOffer = function(offerId) {
  window.dashboardState.rejectOffer(offerId).then(function () {
    _afterOfferResponse('Offer declined.', 'info');
  }).catch(_offerError);
};

/**
 * Buyer Dashboard UI Controller
 */
function initBuyerDashboard() {
  const demandsContainer = document.getElementById('buyer-demands-container');
  if (!demandsContainer) return; // Not on buyer page

  renderBuyerDemands();
  renderBuyerMatchedSupply();
}

function renderBuyerDemands() {
  const container = document.getElementById('buyer-demands-container');
  if (!container) return;

  const demands = window.dashboardState.getDemands();
  if (demands.length === 0) {
    container.innerHTML = `
      <div class="empty-state" style="grid-column: 1 / -1;">
        <div class="empty-state-icon">📋</div>
        <h3>No Sourcing Demands Posted</h3>
        <p>Post your crop requirements to get matched with farmer lots across Maharashtra.</p>
        <button type="button" class="btn btn-primary btn-sm open-create-demand-modal">
          <span>+ Create Requirement</span>
        </button>
      </div>
    `;
    return;
  }

  container.innerHTML = demands.map(demand => `
    <div class="lot-card">
      <div class="lot-card-header">
        <div>
          <h3 class="lot-title">${demand.crop}</h3>
          <div class="lot-variety">Target: ${demand.grade} Specification</div>
        </div>
        <span class="badge badge-success">ACTIVE DEMAND</span>
      </div>

      <div class="lot-spec-grid">
        <div class="spec-item">
          <span class="spec-label">Required Volume</span>
          <span class="spec-val">${demand.quantity} ${demand.unit}</span>
        </div>
        <div class="spec-item">
          <span class="spec-label">Delivery Location</span>
          <span class="spec-val">${demand.deliveryLocation}</span>
        </div>
        <div class="spec-item">
          <span class="spec-label">Target Rate</span>
          <span class="spec-val font-mono">₹${demand.offeredRate.toLocaleString('en-IN')}/${demand.unit}</span>
        </div>
        <div class="spec-item">
          <span class="spec-label">Deadline</span>
          <span class="spec-val">${demand.requiredDate}</span>
        </div>
      </div>
    </div>
  `).join('');
}

function renderBuyerMatchedSupply(commodity, lotQty, grade, state, expectedPrice) {
  const container = document.getElementById('buyer-matches-container');
  if (!container) return;

  var selection = window.KL_PriceForecast && window.KL_PriceForecast.getCurrentSelection
    ? window.KL_PriceForecast.getCurrentSelection()
    : {};
  commodity    = selection.commodity || commodity || '';
  lotQty       = lotQty       || 10;
  grade        = grade        || 'Grade A';
  state        = selection.state || state || '';
  expectedPrice = expectedPrice || 0;
  var matchRequestId = (window.__kisanlinkBuyerMatchRequestId || 0) + 1;
  window.__kisanlinkBuyerMatchRequestId = matchRequestId;

  // Show loading
  container.innerHTML = '<div class="empty-state" style="grid-column:1/-1;"><div class="cqa-spinner-ring" style="width:28px;height:28px;border-width:3px;"></div><p style="font-size:var(--text-xs);color:var(--color-slate-500);margin-top:8px;">Finding matched buyers…</p></div>';

  const API_BASE = (window.CONFIG && window.CONFIG.API_BASE_URL)
    ? window.CONFIG.API_BASE_URL.replace(/\/api\/?$/, '')
    : 'http://localhost:5000';

  fetch(API_BASE + '/api/buyer-match', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      commodity:      commodity,
      state:          state,
      quantity_qtl:   lotQty,
      grade:          grade,
      expected_price: expectedPrice,
      district:       selection.district || '',
      market:         selection.market || '',
    })
  })
  .then(function(res) { return res.json(); })
  .then(function(data) {
    if (matchRequestId !== window.__kisanlinkBuyerMatchRequestId) return;
    if (!data.success || !data.matches || data.matches.length === 0) {
      container.innerHTML = '<div class="empty-state" style="grid-column:1/-1;"><div class="empty-state-icon">🤝</div><h3>No Buyer Matches Found</h3><p>No registered buyers currently match this commodity. Try creating a sale lot to attract buyer attention.</p></div>';
      return;
    }

    const html = data.matches.map(function(m) {
      const scoreColor = m.match_score >= 75 ? 'var(--color-accent-green)' : m.match_score >= 50 ? '#D97706' : '#E11D48';
      const factorsHtml = (m.matched_criteria || []).map(function(c) {
        const barW = Math.round(c.score);
        return '<div class="factor-row"><span class="factor-name">' + c.name + '</span><span class="factor-stat" style="font-size:0.7rem;">' + c.score + '/100</span></div>';
      }).join('');

      const unmatchedHtml = m.unmatched_criteria && m.unmatched_criteria.length
        ? '<div style="font-size:0.65rem;color:#E11D48;margin-top:4px;">Note: ' + m.unmatched_criteria.join('; ') + '</div>'
        : '';

      return '<div class="buyer-card">' +
        '<div class="buyer-card-header">' +
          '<div>' +
            '<div class="flex items-center gap-2">' +
              '<h3 style="font-size:var(--text-base);font-weight:var(--weight-bold);">' + m.buyer_name + '</h3>' +
              '<span class="badge badge-success">' + m.required_grade + '</span>' +
            '</div>' +
            '<p style="font-size:var(--text-xs);color:var(--color-slate-500);margin-top:2px;">' +
              m.delivery_location + ' • Needs <strong>' + m.required_qty + ' QTL</strong>' +
            '</p>' +
            '<p style="font-size:0.68rem;color:var(--color-slate-400);margin-top:2px;">' + m.buyer_type + '</p>' +
          '</div>' +
          '<div class="match-score-badge" style="--score:' + m.match_score + ';">' +
            '<div class="match-score-inner" style="color:' + scoreColor + ';">' + m.match_score + '%</div>' +
          '</div>' +
        '</div>' +
        '<div class="buyer-factors-list">' + factorsHtml + '</div>' +
        unmatchedHtml +
        '<div style="display:flex;justify-content:space-between;align-items:center;margin-top:var(--space-3);padding-top:var(--space-3);border-top:1px solid var(--color-slate-100);">' +
          '<span style="font-size:var(--text-sm);font-weight:var(--weight-bold);">₹' + (m.offered_rate||0).toLocaleString('en-IN') + '/QTL</span>' +
          '<span style="font-size:0.65rem;color:var(--color-slate-400);">Needed by: ' + (m.required_date || '—') + '</span>' +
        '</div>' +
        '<button type="button" class="btn btn-primary btn-sm" style="width:100%;margin-top:var(--space-2);" ' +
          'onclick="handleSendDigitalOffer(\'' + m.buyer_id + '\', \'' + (commodity||'') + '\', ' + lotQty + ', ' + (m.offered_rate||0) + ')">' +
          '<span>Make Offer</span>' +
        '</button>' +
      '</div>';
    }).join('');

    container.innerHTML = html;

    // Remove demo badge from buyer matches section
    var bmsSection = document.getElementById('buyer-matches-section');
    if (bmsSection) {
      var demoBadge = bmsSection.querySelector('.badge-demo');
      if (demoBadge) { demoBadge.textContent = 'API Matched'; demoBadge.className = 'badge badge-success'; }
    }
  })
  .catch(function(err) {
    if (matchRequestId !== window.__kisanlinkBuyerMatchRequestId) return;
    container.innerHTML = '<div class="empty-state" style="grid-column:1/-1;"><div class="empty-state-icon">⚠️</div><h3>Buyer Match Unavailable</h3><p>Could not load buyer data: ' + err.message + '</p></div>';
  });
}

/**
 * handleViewMatches — called by View Matches button on each lot card.
 * Passes lot data to buyer matching engine and scrolls to results.
 */
window.handleViewMatches = function(lotId, crop, qty, unit, grade, location, expectedPrice) {
  // Scroll to buyer matches section
  var target = document.getElementById('buyer-matches-section');
  if (target) {
    target.scrollIntoView({ behavior: 'smooth', block: 'start' });
  }

  var currentSelection = window.KL_PriceForecast && window.KL_PriceForecast.getCurrentSelection
    ? window.KL_PriceForecast.getCurrentSelection()
    : {};
  var selectedCommodity = currentSelection.commodity || crop;
  var lotState = currentSelection.state || '';

  // Update section heading to show which lot
  var heading = document.getElementById('bm-heading');
  if (heading) heading.textContent = 'Buyer Opportunities for ' + selectedCommodity;

  // Load real matches
  renderBuyerMatchedSupply(selectedCommodity, qty, grade, lotState, expectedPrice);

  if (typeof showToast === 'function') {
    showToast('Finding verified buyers for ' + crop + '…', 'info');
  }
};

document.addEventListener('kl:forecastCleared', function () {
  window.__kisanlinkBuyerMatchRequestId = (window.__kisanlinkBuyerMatchRequestId || 0) + 1;
  var container = document.getElementById('buyer-matches-container');
  if (container) {
    container.innerHTML = '<div class="empty-state" style="grid-column:1/-1;"><div class="empty-state-icon">🤝</div><h3>Click "View Matches" on a Lot Card</h3><p>Select a current market and view matches for its commodity.</p></div>';
  }
});

/**
 * Send Digital Offer — opens the real offer modal.
 *
 * `buyerId` here is the id of the matched row. Seed sample buyers use a
 * "DEMAND-SEED-..." id and are not registered users, so an offer cannot be
 * delivered to them; the modal then lists the open requirements from real
 * buyers instead of pretending the sample row can receive an offer.
 */
window.handleSendDigitalOffer = function (buyerId, crop, quantity, offeredRate) {
  const isSampleBuyer = !/^\d+$/.test(String(buyerId || ''));
  const note = isSampleBuyer
    ? 'That matched row is a <strong>sample buyer</strong> bundled for the ' +
      'matching demo, so it cannot receive an offer. Pick a real buyer ' +
      'requirement below.'
    : '';
  if (typeof window.klOpenOfferModal === 'function') {
    window.klOpenOfferModal({
      commodity: crop,
      quantity_qtl: quantity,
      price_per_qtl: offeredRate,
      contextNote: note,
    });
    return;
  }
  if (typeof showToast === 'function') {
    showToast('Offer dialog is still loading — try again in a moment.', 'warning');
  }
};

/**
 * Create Lot Modal Form Handler
 */
function initCreateLotModal() {
  const modal = document.getElementById('create-lot-modal');
  const form = document.getElementById('create-lot-form');
  const openButtons = document.querySelectorAll('.open-create-lot-modal');
  const closeBtn = document.getElementById('close-create-lot-modal');
  if (!modal || !form) return;

  // Dynamically attach open buttons (including those added after init)
  document.addEventListener('click', (e) => {
    if (e.target.closest('.open-create-lot-modal')) {
      e.preventDefault();
      modal.classList.add('modal-open');
    }
  });

  if (closeBtn) {
    closeBtn.addEventListener('click', () => modal.classList.remove('modal-open'));
  }

  modal.addEventListener('click', (e) => {
    if (e.target === modal) modal.classList.remove('modal-open');
  });

  // A browser-blocked submit is invisible if the offending field is scrolled
  // out of the modal, which reads to the user as a dead button. Surface it.
  form.addEventListener('invalid', (e) => {
    const field = e.target;
    if (typeof showToast === 'function') {
      const label = form.querySelector(`label[for="${field.id}"]`);
      const name = (label ? label.textContent : field.name || 'A field')
        .replace('*', '').trim();
      showToast(`${name}: ${field.validationMessage}`, 'warning');
    }
    field.scrollIntoView({ block: 'center', behavior: 'smooth' });
    field.focus({ preventScroll: true });
  }, true);

  // Crop photo: preview + validation. Held as a data URL and posted with the
  // lot, so no separate upload step and no partially-created lot.
  let lotImageDataUrl = null;
  const imgInput = document.getElementById('lot-image');
  const imgPrev = document.getElementById('lot-image-preview');
  const imgPrevImg = document.getElementById('lot-image-preview-img');
  const imgErr = document.getElementById('lot-image-error');
  const imgRemove = document.getElementById('lot-image-remove');

  function lotImageError(msg) {
    if (!imgErr) return;
    imgErr.textContent = msg || '';
    imgErr.hidden = !msg;
  }

  function clearLotImage() {
    lotImageDataUrl = null;
    if (imgInput) imgInput.value = '';
    if (imgPrev) imgPrev.hidden = true;
    if (imgPrevImg) imgPrevImg.removeAttribute('src');
    lotImageError('');
  }

  if (imgRemove) imgRemove.addEventListener('click', clearLotImage);

  if (imgInput) {
    imgInput.addEventListener('change', () => {
      const file = imgInput.files && imgInput.files[0];
      if (!file) { clearLotImage(); return; }
      const allowed = ['image/jpeg', 'image/png', 'image/webp'];
      if (allowed.indexOf(file.type) < 0) {
        clearLotImage();
        lotImageError('Please choose a JPG, PNG or WebP image.');
        return;
      }
      if (file.size > 5 * 1024 * 1024) {
        clearLotImage();
        lotImageError('That photo is larger than 5 MB. Please choose a smaller one.');
        return;
      }
      const reader = new FileReader();
      reader.onload = () => {
        lotImageDataUrl = reader.result;
        if (imgPrevImg) imgPrevImg.src = lotImageDataUrl;
        if (imgPrev) imgPrev.hidden = false;
        lotImageError('');
      };
      reader.onerror = () => {
        clearLotImage();
        lotImageError('That photo could not be read. Please choose it again.');
      };
      reader.readAsDataURL(file);
    });
  }

  form.addEventListener('submit', async (e) => {
    e.preventDefault();
    const submitBtn = form.querySelector('[type="submit"]');
    const formData = new FormData(form);

    const commodity = formData.get('crop');
    const location  = formData.get('location');

    if (!commodity || !location) {
      if (typeof showToast === 'function') {
        showToast('Please choose a crop and enter your farm / pickup location.', 'warning');
      }
      return;
    }
    // Quantity and price are typed text fields; validate with plain messages.
    const quantity = window.KLNumeric ? window.KLNumeric.read('lot-quantity')
                                      : Number(formData.get('quantity'));
    if (quantity == null || !isFinite(quantity) || quantity <= 0) {
      if (typeof showToast === 'function') {
        showToast('Please enter how many quintals you have, for example 25.', 'warning');
      }
      return;
    }
    const expectedPrice = window.KLNumeric ? window.KLNumeric.read('lot-price')
                                           : Number(formData.get('expectedPrice'));

    // Recommendation context carried over from "Proceed to Sell", if any.
    const recoMarket = formData.get('market') || '';
    const recoNet    = formData.get('net_realisation') || '';
    const recoFreight= formData.get('transport_cost') || '';
    const recoKm     = formData.get('distance_km') || '';
    const recoNotes  = recoMarket
      ? [
          `Recommended market: ${recoMarket}`,
          recoKm      ? `distance ~${recoKm} km` : '',
          recoFreight ? `estimated transport ₹${recoFreight}` : '',
          recoNet     ? `estimated net realisation ₹${recoNet}` : '',
        ].filter(Boolean).join(' · ') + ' (planning estimate at time of listing)'
      : '';

    const lotPayload = {
      commodity,
      variety:       formData.get('variety') || '',
      quantity_qtl:  Number(quantity),
      unit:          formData.get('unit') || 'QTL',
      grade:         formData.get('grade') || 'Grade A',
      location,
      district:      formData.get('district') || '',
      state:         formData.get('state') || '',
      market:        recoMarket,
      harvest_date:  formData.get('harvestDate') || '',
      price_per_qtl: Number(expectedPrice) || 0,
    };
    if (recoNotes) lotPayload.notes = recoNotes;
    // Optional — a missing photo must never block publishing.
    if (lotImageDataUrl) lotPayload.image_data_url = lotImageDataUrl;

    // Disable submit to prevent double submission
    if (submitBtn) { submitBtn.disabled = true; submitBtn.querySelector('span').textContent = 'Creating…'; }

    try {
      const token = localStorage.getItem('kisanlink_auth_token');
      if (token) {
        // Authenticated: persist to backend
        const result = await window.createLot(lotPayload);
        modal.classList.remove('modal-open');
        form.reset();
        const recoBox = document.getElementById('lot-reco-summary');
        if (recoBox) { recoBox.hidden = true; recoBox.innerHTML = ''; }
        clearLotImage();
        if (typeof showToast === 'function') {
          showToast(`Lot #${result.lot && result.lot.id ? result.lot.id : '—'} for ${commodity} created!`, 'success');
        }
        // Reload from backend to show real ID
        loadLotsFromBackend();
      } else {
        // A sale lot is real business data: it is only ever created against an
        // authenticated account. No browser-only copy is kept, so nothing can
        // look saved while the server knows nothing about it.
        if (typeof showToast === 'function') {
          showToast('Your session has ended. Please sign in again to publish this lot.', 'error');
        }
        setTimeout(function () {
          window.location.href = 'auth.html?expired=1&next=farmer.html';
        }, 1500);
      }
    } catch (err) {
      if (typeof showToast === 'function') {
        showToast(`Could not create lot: ${err.message || 'Server error'}`, 'error');
      }
    } finally {
      if (submitBtn) { submitBtn.disabled = false; submitBtn.querySelector('span').textContent = 'Publish Sale Lot'; }
    }
  });
}


/**
 * Create Sourcing Requirement Modal Handler
 */
function initCreateDemandModal() {
  const modal = document.getElementById('create-demand-modal');
  const form = document.getElementById('create-demand-form');
  const openButtons = document.querySelectorAll('.open-create-demand-modal');
  const closeBtn = document.getElementById('close-create-demand-modal');
  if (!modal || !form) return;

  openButtons.forEach(btn => {
    btn.addEventListener('click', (e) => {
      e.preventDefault();
      modal.classList.add('modal-open');
    });
  });

  if (closeBtn) {
    closeBtn.addEventListener('click', () => modal.classList.remove('modal-open'));
  }

  modal.addEventListener('click', (e) => {
    if (e.target === modal) modal.classList.remove('modal-open');
  });

  form.addEventListener('submit', async (e) => {
    e.preventDefault();
    const formData = new FormData(form);
    const demandData = {
      commodity: formData.get('crop'),
      crop: formData.get('crop'),
      quantity_qtl_min: Number(formData.get('quantity')),
      quantity: formData.get('quantity'),
      unit: formData.get('unit'),
      grade: formData.get('grade'),
      deliveryLocation: formData.get('deliveryLocation'),
      offeredRate: formData.get('offeredRate'),
      price_per_qtl: Number(formData.get('offeredRate')) || 0,
      requiredDate: formData.get('requiredDate'),
      valid_until: formData.get('requiredDate'),
    };

    if (!demandData.crop || !demandData.quantity || !demandData.deliveryLocation) {
      if (typeof showToast === 'function') {
        showToast('Please fill in all mandatory fields.', 'warning');
      }
      return;
    }

    try {
      const token = localStorage.getItem('kisanlink_auth_token');
      if (token && window.createBuyerRequirement) {
        await window.createBuyerRequirement(demandData);
        modal.classList.remove('modal-open');
        form.reset();
        if (typeof showToast === 'function') {
          showToast('Requirement posted to your buyer account.', 'success');
        }
        if (window.loadBuyerRequirementsFromBackend) {
          window.loadBuyerRequirementsFromBackend();
        } else {
          renderBuyerDemands();
        }
        return;
      }
    } catch (err) {
      if (typeof showToast === 'function') {
        showToast(err.message || 'Could not post requirement.', 'error');
      }
      return;
    }

    // Same rule as sale lots: a sourcing requirement is real business data and
    // is only ever created against an authenticated buyer account.
    if (typeof showToast === 'function') {
      showToast('Your session has ended. Please sign in again to post this requirement.', 'error');
    }
    setTimeout(function () {
      window.location.href = 'auth.html?expired=1&next=buyer.html';
    }, 1500);
  });
}
