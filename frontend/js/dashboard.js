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
      lots: initial.LOTS ? [...initial.LOTS] : [],
      demands: initial.BUYER_DEMANDS ? [...initial.BUYER_DEMANDS] : [],
      offers: initial.OFFERS ? [...initial.OFFERS] : [],
      transactions: initial.TRANSACTIONS ? [...initial.TRANSACTIONS] : []
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
      location: lotData.location || 'Nashik District',
      harvestDate: lotData.harvestDate || new Date().toISOString().split('T')[0],
      expectedPrice: Number(lotData.expectedPrice) || 3000,
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
      buyerName: this.state.buyerProfile.name || 'Sahyadri Agro Processors',
      buyerType: this.state.buyerProfile.type || 'Food Processor',
      crop: demandData.crop,
      quantity: Number(demandData.quantity),
      unit: demandData.unit || 'QTL',
      grade: demandData.grade || 'Grade A',
      deliveryLocation: demandData.deliveryLocation || 'Pune Hub',
      offeredRate: Number(demandData.offeredRate) || 3100,
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

  acceptOffer(offerId) {
    const offer = this.state.offers.find(o => o.id === offerId);
    if (!offer) return null;

    offer.status = 'ACCEPTED';

    // Create corresponding transaction
    const newTx = {
      id: `TX-2026-${String(this.state.transactions.length + 50).padStart(3, '0')}`,
      lotId: offer.lotId,
      crop: offer.crop,
      quantity: offer.quantity,
      unit: offer.unit,
      buyerName: offer.buyerName,
      agreedRate: offer.offeredRate,
      grossTotal: offer.quantity * offer.offeredRate,
      status: 'TRANSACTION_CREATED',
      currentStep: 2, // 1: Offered, 2: Accepted, 3: Logistics, 4: Delivered, 5: Paid
      date: new Date().toISOString().split('T')[0]
    };

    this.state.transactions.unshift(newTx);

    // Update lot status
    const lot = this.state.lots.find(l => l.id === offer.lotId);
    if (lot) {
      lot.status = 'OFFER_ACCEPTED';
    }

    this.saveState();
    return { offer, transaction: newTx };
  }

  rejectOffer(offerId) {
    const offer = this.state.offers.find(o => o.id === offerId);
    if (offer) {
      offer.status = 'REJECTED';
      this.saveState();
    }
    return offer;
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
 */
function initFarmerDashboard() {
  const lotsContainer = document.getElementById('farmer-lots-container');
  if (!lotsContainer) return; // Not on farmer page

  renderFarmerLots();
  renderFarmerOffers();
  renderFarmerTransactions();
}

function renderFarmerLots() {
  const container = document.getElementById('farmer-lots-container');
  const statCount = document.getElementById('stat-active-lots-count');
  if (!container) return;

  const lots = window.dashboardState.getLots();
  if (statCount) statCount.textContent = lots.length;

  if (lots.length === 0) {
    container.innerHTML = `
      <div class="empty-state" style="grid-column: 1 / -1;">
        <div class="empty-state-icon">🌾</div>
        <h3>No Active Sale Lots</h3>
        <p>Create your first crop lot to discover live market prices and buyer matching opportunities.</p>
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
          <div class="lot-variety">${lot.variety}</div>
        </div>
        <span class="badge ${lot.status === 'OFFER_ACCEPTED' ? 'badge-verified' : lot.status === 'OFFER_RECEIVED' ? 'badge-amber' : 'badge-success'}">
          ${lot.status.replace('_', ' ')}
        </span>
      </div>

      <div class="lot-spec-grid">
        <div class="spec-item">
          <span class="spec-label">Available Volume</span>
          <span class="spec-val">${lot.quantity} ${lot.unit}</span>
        </div>
        <div class="spec-item">
          <span class="spec-label">Quality Grade</span>
          <span class="spec-val">${lot.grade}</span>
        </div>
        <div class="spec-item">
          <span class="spec-label">Farm Location</span>
          <span class="spec-val">${lot.location}</span>
        </div>
        <div class="spec-item">
          <span class="spec-label">Harvest Date</span>
          <span class="spec-val">${lot.harvestDate}</span>
        </div>
      </div>

      <div class="flex items-center justify-between" style="padding-top: var(--space-2); border-top: 1px solid var(--color-slate-100);">
        <div>
          <span class="text-xs text-slate">Expected Base:</span>
          <span class="font-mono font-bold text-slate-900" style="margin-left: 4px;">₹${lot.expectedPrice.toLocaleString('en-IN')}/${lot.unit}</span>
        </div>
        <a href="#recommendations-section" class="btn btn-outline btn-sm">
          <span>View Matches</span>
        </a>
      </div>
    </div>
  `).join('');
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
          <div class="text-xs text-emerald font-semibold">Est. Net Take-Home: ₹${offer.netTakeHome.toLocaleString('en-IN')}/${offer.unit}</div>
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

window.handleAcceptOffer = function(offerId) {
  const res = window.dashboardState.acceptOffer(offerId);
  if (res) {
    renderFarmerOffers();
    renderFarmerLots();
    renderFarmerTransactions();
    if (typeof showToast === 'function') {
      showToast(`Offer ${offerId} accepted! Transaction ${res.transaction.id} created with verified milestones.`, 'success');
    }
  }
};

window.handleRejectOffer = function(offerId) {
  window.dashboardState.rejectOffer(offerId);
  renderFarmerOffers();
  if (typeof showToast === 'function') {
    showToast(`Offer ${offerId} declined.`, 'info');
  }
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

function renderBuyerMatchedSupply() {
  const container = document.getElementById('buyer-matched-lots-container');
  if (!container) return;

  const lots = window.dashboardState.getLots();
  container.innerHTML = lots.map(lot => `
    <div class="buyer-card">
      <div class="buyer-card-header">
        <div>
          <div class="flex items-center gap-2">
            <h3 style="font-size: var(--text-base); font-weight: var(--weight-bold);">${lot.crop}</h3>
            <span class="badge badge-success">${lot.grade}</span>
          </div>
          <p style="font-size: var(--text-xs); color: var(--color-slate-500); margin-top: 2px;">
            Origin: ${lot.location} • Available: <strong>${lot.quantity} ${lot.unit}</strong>
          </p>
        </div>
        <div class="match-score-badge" style="--score: 92;">
          <div class="match-score-inner">92%</div>
        </div>
      </div>

      <div class="buyer-factors-list">
        <div class="factor-row">
          <span class="factor-name">Volume Fit</span>
          <span class="factor-stat text-emerald">100% Compatible</span>
        </div>
        <div class="factor-row">
          <span class="factor-name">Declared Grade</span>
          <span class="factor-stat">${lot.grade}</span>
        </div>
        <div class="factor-row">
          <span class="factor-name">Farmer Base Price</span>
          <span class="factor-stat font-mono">₹${lot.expectedPrice}/${lot.unit}</span>
        </div>
      </div>

      <button type="button" class="btn btn-primary btn-sm" style="width: 100%;" onclick="handleSendDigitalOffer('${lot.id}', '${lot.crop}', ${lot.quantity})">
        <span>Make Digital Offer</span>
      </button>
    </div>
  `).join('');
}

window.handleSendDigitalOffer = function(lotId, crop, quantity) {
  if (typeof showToast === 'function') {
    showToast(`Digital Purchase Offer sent for ${crop} (${quantity} QTL). Farmer notified!`, 'success');
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

  form.addEventListener('submit', (e) => {
    e.preventDefault();
    const formData = new FormData(form);
    const lotData = {
      crop: formData.get('crop'),
      variety: formData.get('variety'),
      quantity: formData.get('quantity'),
      unit: formData.get('unit'),
      grade: formData.get('grade'),
      location: formData.get('location'),
      harvestDate: formData.get('harvestDate'),
      expectedPrice: formData.get('expectedPrice')
    };

    if (!lotData.crop || !lotData.quantity || !lotData.location) {
      if (typeof showToast === 'function') {
        showToast('Please fill in all mandatory fields (Crop, Quantity, Location).', 'warning');
      }
      return;
    }

    const created = window.dashboardState.createLot(lotData);
    modal.classList.remove('modal-open');
    form.reset();

    renderFarmerLots();
    if (typeof showToast === 'function') {
      showToast(`Sale lot ${created.id} for ${created.crop} created successfully!`, 'success');
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

  form.addEventListener('submit', (e) => {
    e.preventDefault();
    const formData = new FormData(form);
    const demandData = {
      crop: formData.get('crop'),
      quantity: formData.get('quantity'),
      unit: formData.get('unit'),
      grade: formData.get('grade'),
      deliveryLocation: formData.get('deliveryLocation'),
      offeredRate: formData.get('offeredRate'),
      requiredDate: formData.get('requiredDate')
    };

    if (!demandData.crop || !demandData.quantity || !demandData.deliveryLocation) {
      if (typeof showToast === 'function') {
        showToast('Please fill in all mandatory fields.', 'warning');
      }
      return;
    }

    const created = window.dashboardState.createDemand(demandData);
    modal.classList.remove('modal-open');
    form.reset();

    renderBuyerDemands();
    if (typeof showToast === 'function') {
      showToast(`Demand requirement ${created.id} posted successfully!`, 'success');
    }
  });
}
