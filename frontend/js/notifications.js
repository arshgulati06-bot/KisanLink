/**
 * KisanLink — Activity & Notifications Module
 * SIH 2026 — PS SIH26132
 * Frontend Step 4
 *
 * Uses frontend state / demo data only. No fake real-time push.
 * Integration note: real-time can be wired via WebSocket or SSE later.
 */

var KL_Notifications = (function () {

  /* ── Demo notification items (sourced from CONFIG demo data) ─────────── */
  var DEMO_ITEMS = [
    {
      id: 'n1',
      type: 'offer',
      title: 'New Buyer Offer Received',
      body: 'Sahyadri Agro Processors offered ₹3,200/QTL for 10 QTL Onion (LOT-2026-084).',
      ts: '2026-09-02 • 14:30',
      read: false,
    },
    {
      id: 'n2',
      type: 'quality',
      title: 'Quality Assessment Complete',
      body: 'Crop Quality Check for LOT-2026-084 returned Grade A (ML service pending).',
      ts: '2026-09-02 • 11:15',
      read: false,
    },
    {
      id: 'n3',
      type: 'logistics',
      title: 'Logistics Scheduled',
      body: 'Transport for LOT-2026-083 confirmed — pickup at Dindori on 03 Sep 2026.',
      ts: '2026-09-01 • 18:02',
      read: true,
    },
    {
      id: 'n4',
      type: 'payment',
      title: 'Payment Status Update',
      body: 'Advance payment ₹8,000 received for Transaction TXN-2026-083.',
      ts: '2026-09-01 • 09:44',
      read: true,
    },
  ];

  var _items = DEMO_ITEMS.slice();

  var TYPE_ICONS = {
    offer:     '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/></svg>',
    quality:   '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M9 12l2 2 4-4"/><rect x="3" y="3" width="18" height="18" rx="3"/></svg>',
    logistics: '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="1" y="3" width="15" height="13" rx="1"/><polygon points="16 8 20 8 23 11 23 16 16 16 16 8"/><circle cx="5.5" cy="18.5" r="2.5"/><circle cx="18.5" cy="18.5" r="2.5"/></svg>',
    payment:   '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="1" y="4" width="22" height="16" rx="2" ry="2"/><line x1="1" y1="10" x2="23" y2="10"/></svg>',
  };

  var TYPE_COLORS = {
    offer:     'notif-offer',
    quality:   'notif-quality',
    logistics: 'notif-logistics',
    payment:   'notif-payment',
  };

  function _unreadCount() {
    return _items.filter(function (n) { return !n.read; }).length;
  }

  function _updateBadge() {
    var badge = document.getElementById('notif-badge');
    if (!badge) return;
    var count = _unreadCount();
    badge.textContent = count;
    badge.hidden = count === 0;
  }

  function _markRead(id) {
    _items.forEach(function (n) { if (n.id === id) n.read = true; });
    _updateBadge();
  }

  function _renderList() {
    var container = document.getElementById('kl-notifications-list');
    if (!container) return;

    if (_items.length === 0) {
      container.innerHTML = '<div class="notif-empty">No activity yet.</div>';
      return;
    }

    container.innerHTML = _items.map(function (n) {
      return '<div class="notif-item ' + (n.read ? '' : 'notif-item--unread') + '" data-id="' + n.id + '">' +
        '<div class="notif-icon-wrap ' + (TYPE_COLORS[n.type] || '') + '">' +
          (TYPE_ICONS[n.type] || '') +
        '</div>' +
        '<div class="notif-content">' +
          '<div class="notif-title">' + n.title + (n.read ? '' : ' <span class="notif-dot"></span>') + '</div>' +
          '<div class="notif-body">' + n.body + '</div>' +
          '<div class="notif-ts">' + n.ts + '</div>' +
        '</div>' +
      '</div>';
    }).join('');

    container.querySelectorAll('.notif-item').forEach(function (el) {
      el.addEventListener('click', function () {
        var id = el.getAttribute('data-id');
        el.classList.remove('notif-item--unread');
        el.querySelector('.notif-dot') && el.querySelector('.notif-dot').remove();
        _markRead(id);
      });
    });
  }

  function _togglePanel() {
    var panel = document.getElementById('kl-notifications');
    if (!panel) return;
    var isHidden = panel.hidden;
    panel.hidden = !isHidden;
    if (!isHidden) return;
    _renderList();
  }

  function init() {
    var btn = document.getElementById('notif-toggle-btn');
    if (!btn) return;
    btn.addEventListener('click', _togglePanel);
    _updateBadge();
    console.info('[KL_Notifications] Notification module initialised (demo data).');
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }

  return {
    getUnreadCount: _unreadCount,
    refresh: _renderList,
  };
})();

window.KL_Notifications = KL_Notifications;
