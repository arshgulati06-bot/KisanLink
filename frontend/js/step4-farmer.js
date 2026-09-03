/**
 * KisanLink — Step 4/5 Farmer Dashboard Controller
 * SIH 2026 — PS SIH26132: Market Linkages & Price Discovery
 * Frontend Step 5: Quick Actions, Multilingual sync, and Decision Flow Integration
 *
 * Wires UI sections:
 *  1. Farmer Quick Action Chips (SELL NOW, WAIT, COMPARE MARKETS, CHECK QUALITY, FIND BUYERS)
 *  2. "Best Action for Your Crop" Decision Engine
 *  3. Market Comparison table (location selector + demo dataset)
 *  4. 13-Language selector sync (delegates to KL_I18n)
 *  5. Profile panel (uses DashboardStateManager farmer profile)
 *  6. Buyer Matches rendering (buyer demands from state)
 */

var KL_Step4 = (function () {

  /* ── Demo Market Comparison data ───────────────────────────────────────── */
  var MARKET_DEMO = {
    crop: 'Onion',
    origin: 'Nashik (Dindori Taluka)',
    markets: [
      { name: 'Nashik APMC',    dist: 28,  price: 3100, freight: 65,  net: 3035, highlight: false },
      { name: 'Pune (Pimpri)',   dist: 215, price: 3400, freight: 310, net: 3090, highlight: true  },
      { name: 'Mumbai (Vashi)',  dist: 302, price: 3500, freight: 430, net: 3070, highlight: false },
      { name: 'Aurangabad APMC',dist: 188, price: 3250, freight: 280, net: 2970, highlight: false },
    ],
  };

  /* ── Demo Buyer Match data ────────────────────────────────────────────── */
  var BUYER_MATCH_DEMO = [
    {
      id: 'BM001',
      buyerName: 'Sahyadri Agro Processors',
      buyerType: 'Food Processor',
      crop: 'Onion',
      quantity: '10 QTL',
      quality: 'Grade A',
      deliveryLocation: 'Pune Hub',
      offeredRate: 3200,
      deadline: '15 Sep 2026',
      matchScore: 94,
      status: 'OPEN',
    },
    {
      id: 'BM002',
      buyerName: 'Reliance Fresh Sourcing',
      buyerType: 'Retail Chain',
      crop: 'Onion',
      quantity: '25 QTL',
      quality: 'Grade A or Premium',
      deliveryLocation: 'Mumbai DC',
      offeredRate: 3350,
      deadline: '20 Sep 2026',
      matchScore: 81,
      status: 'OPEN',
    },
    {
      id: 'BM003',
      buyerName: 'Dehydration Unit - Niphad',
      buyerType: 'Processing Unit',
      crop: 'Onion',
      quantity: '50 QTL',
      quality: 'Grade B or above',
      deliveryLocation: 'Niphad, Nashik',
      offeredRate: 2900,
      deadline: '30 Sep 2026',
      matchScore: 76,
      status: 'OPEN',
    },
  ];

  /* ════════════════════════════════════════════════════════════════════════
     1. FARMER QUICK ACTION CHIPS
     ════════════════════════════════════════════════════════════════════════ */
  function _initQuickActions() {
    var chips = document.querySelectorAll('.qa-chip');
    chips.forEach(function (chip) {
      chip.addEventListener('click', function () {
        var action = chip.getAttribute('data-qa-action');
        switch (action) {
          case 'sellNow':
            _scrollToSection('best-action-section');
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

  /* ════════════════════════════════════════════════════════════════════════
     2. "BEST ACTION" DECISION PANEL
     ════════════════════════════════════════════════════════════════════════ */
  function _renderBestAction() {
    var section = document.getElementById('best-action-section');
    if (!section) return;

    var state    = window.dashboardState;
    var lots     = state ? state.getLots() : [];
    var firstLot = lots[0] || null;

    var crop     = firstLot ? firstLot.crop     : 'Onion';
    var qty      = firstLot ? firstLot.quantity + ' QTL' : '15 QTL';
    var grade    = firstLot ? firstLot.grade    : 'Grade A';
    var location = firstLot ? firstLot.location : 'Nashik District';
    var expPrice = firstLot ? firstLot.expectedPrice : 3200;

    _setVal('ba-crop',     crop);
    _setVal('ba-quality',  grade);
    _setVal('ba-location', location);
    _setVal('ba-quantity', qty);
    _setVal('ba-market-price', '₹' + expPrice.toLocaleString('en-IN') + ' / QTL (APMC demo)');
    _setVal('ba-forecast',  'Gradual upward — API pending');
    _setVal('ba-demand',    'High buyer demand (demo)');
    _setVal('ba-logistics', '~₹310 / QTL estimated (Pune route)');

    var netDemo = expPrice - 310;
    _setVal('ba-net-realisation', '₹' + netDemo.toLocaleString('en-IN') + ' / QTL');

    var chip = document.getElementById('ba-recommendation-chip');
    if (chip) {
      chip.textContent = 'SELL NOW';
      chip.className   = 'ba-rec-chip ba-rec-sell';
    }
    _setVal('ba-rec-reason',
      'Market price is trending upward and buyer demand is high. ' +
      'Best estimated net realisation available this week. ' +
      '(Based on demo data — connect ML API for real analysis.)');
  }

  /* ════════════════════════════════════════════════════════════════════════
     3. MARKET COMPARISON TABLE
     ════════════════════════════════════════════════════════════════════════ */
  function _renderMarketCompare(data) {
    data = data || MARKET_DEMO;
    var tbody = document.getElementById('mc-table-body');
    if (!tbody) return;

    tbody.innerHTML = data.markets.map(function (m) {
      return '<tr class="' + (m.highlight ? 'mc-row--best' : '') + '">' +
        '<td class="mc-market-name">' + m.name + (m.highlight ? ' <span class="badge badge-success">Best</span>' : '') + '</td>' +
        '<td>' + m.dist + ' km</td>' +
        '<td>₹' + m.price.toLocaleString('en-IN') + '</td>' +
        '<td>₹' + m.freight + '</td>' +
        '<td class="mc-net' + (m.highlight ? ' mc-net--best' : '') + '">₹' + m.net.toLocaleString('en-IN') + '</td>' +
        '<td><button type="button" class="btn btn-outline btn-xs" onclick="alert(\'Market details: ' + m.name + ' — API integration pending.\')">Details</button></td>' +
      '</tr>';
    }).join('');

    _setVal('mc-origin-label', data.origin);
    _setVal('mc-crop-label',   data.crop);
  }

  function _initMarketCompare() {
    var section = document.getElementById('market-compare-section');
    if (!section) return;

    _renderMarketCompare();

    var fetchBtn = document.getElementById('mc-fetch-btn');
    if (fetchBtn) {
      fetchBtn.addEventListener('click', function () {
        _renderMarketCompare(MARKET_DEMO);
        var note = document.getElementById('mc-api-note');
        if (note) note.hidden = false;
      });
    }
  }

  /* ════════════════════════════════════════════════════════════════════════
     4. BUYER MATCHES
     ════════════════════════════════════════════════════════════════════════ */
  function _renderBuyerMatches() {
    var container = document.getElementById('buyer-matches-container');
    if (!container) return;

    var state   = window.dashboardState;
    var demands = state ? state.getDemands() : [];
    var data    = demands.length > 0 ? demands : BUYER_MATCH_DEMO;

    if (data.length === 0) {
      container.innerHTML = '<div class="empty-state"><p>No buyer opportunities available yet.</p></div>';
      return;
    }

    container.innerHTML = data.map(function (d) {
      var name       = d.buyerName        || d.buyerName   || '—';
      var type       = d.buyerType        || '—';
      var crop       = d.crop             || '—';
      var qty        = d.quantity + ' ' + (d.unit || 'QTL');
      var quality    = d.grade            || d.quality      || '—';
      var delivery   = d.deliveryLocation || '—';
      var rate       = d.offeredRate      ? '₹' + Number(d.offeredRate).toLocaleString('en-IN') + '/QTL' : 'Negotiable';
      var score      = d.matchScore       || null;
      var deadline   = d.requiredDate     || d.deadline     || '—';

      return '<div class="buyer-match-card">' +
        '<div class="bmc-header">' +
          '<div class="bmc-buyer-info">' +
            '<div class="bmc-buyer-name">' + name + '</div>' +
            '<div class="bmc-buyer-type badge badge-sky">' + type + '</div>' +
          '</div>' +
          (score ? '<div class="bmc-match-score"><span class="bmc-score-num">' + score + '%</span><span class="bmc-score-label">Match</span></div>' : '') +
        '</div>' +
        '<div class="bmc-details-grid">' +
          '<div class="bmc-detail"><span class="bmc-label">Crop</span><span class="bmc-val">' + crop + '</span></div>' +
          '<div class="bmc-detail"><span class="bmc-label">Quantity</span><span class="bmc-val">' + qty + '</span></div>' +
          '<div class="bmc-detail"><span class="bmc-label">Quality</span><span class="bmc-val">' + quality + '</span></div>' +
          '<div class="bmc-detail"><span class="bmc-label">Delivery</span><span class="bmc-val">' + delivery + '</span></div>' +
          '<div class="bmc-detail"><span class="bmc-label">Offered Rate</span><span class="bmc-val bmc-rate">' + rate + '</span></div>' +
          '<div class="bmc-detail"><span class="bmc-label">Deadline</span><span class="bmc-val">' + deadline + '</span></div>' +
        '</div>' +
        '<div class="bmc-actions">' +
          '<button type="button" class="btn btn-outline btn-sm" onclick="alert(\'Buyer detail: ' + name + ' — API integration pending.\')">View Details</button>' +
          '<button type="button" class="btn btn-primary btn-sm" onclick="alert(\'Make/Review Offer to ' + name + ' — API integration pending.\')">Make / Review Offer</button>' +
        '</div>' +
      '</div>';
    }).join('');
  }

  /* ════════════════════════════════════════════════════════════════════════
     5. PROFILE PANEL
     ════════════════════════════════════════════════════════════════════════ */
  function _renderProfile() {
    var state   = window.dashboardState;
    var profile = state ? state.state.farmerProfile : null;
    if (!profile) return;

    _setVal('profile-name',     profile.name     || 'Ramesh Patil');
    _setVal('profile-location', profile.location || 'Nashik District, Maharashtra');
    _setVal('profile-contact',  profile.contact  || '+91 94XXX XXXXX');
    _setVal('profile-lang',     (window.KL_I18n && window.KL_I18n.getLocale()) ? window.KL_I18n.getLocale().toUpperCase() : 'English');
  }

  /* ════════════════════════════════════════════════════════════════════════
     6. LANGUAGE SELECTOR (13 Languages)
     ════════════════════════════════════════════════════════════════════════ */
  function _initLanguageSelector() {
    // Select dropdowns
    var selects = document.querySelectorAll('.kl-lang-select, [data-lang-select]');
    selects.forEach(function (sel) {
      sel.addEventListener('change', function () {
        if (window.KL_I18n) window.KL_I18n.setLocale(sel.value);
      });
    });

    // Buttons / Chips
    var btns = document.querySelectorAll('[data-lang-btn]');
    btns.forEach(function (btn) {
      btn.addEventListener('click', function () {
        var locale = btn.getAttribute('data-lang-btn');
        if (window.KL_I18n) window.KL_I18n.setLocale(locale);
      });
    });

    document.addEventListener('kl:localeChanged', function (e) {
      _renderProfile();
      _renderBestAction();
    });
  }

  /* ── Shared helper ───────────────────────────────────────────────────── */
  function _setVal(id, text) {
    var el = document.getElementById(id);
    if (el) el.textContent = text;
  }

  /* ── Init ────────────────────────────────────────────────────────────── */
  function init() {
    _initQuickActions();
    _renderBestAction();
    _initMarketCompare();
    _renderBuyerMatches();
    _renderProfile();
    _initLanguageSelector();
    console.info('[KL_Step4] Step 4/5 farmer controller initialised.');
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    setTimeout(init, 0);
  }

  return { init: init };
})();

window.KL_Step4 = KL_Step4;
