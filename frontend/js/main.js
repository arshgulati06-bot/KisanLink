/**
 * KisanLink - Landing Page Interactive Logic
 * SIH 2026 — PS SIH26132: Market Linkages & Price Discovery
 * Micro-interactions, animations, demo table switching, accordions, and modals
 */

document.addEventListener('DOMContentLoaded', () => {
  initNavbarScroll();
  initMobileNavigation();
  initScrollAnimations();
  initMarketIntelligenceTabs();
  initExplainableAccordion();
  initRoleDemoModal();
  initSmoothScroll();
});

/**
 * 1. Navbar Scroll Observer
 */
function initNavbarScroll() {
  const navbar = document.querySelector('.navbar-header');
  if (!navbar) return;

  const handleScroll = () => {
    if (window.scrollY > 20) {
      navbar.classList.add('scrolled');
    } else {
      navbar.classList.remove('scrolled');
    }
  };

  window.addEventListener('scroll', handleScroll, { passive: true });
  handleScroll();
}

/**
 * 2. Mobile Navigation Drawer
 */
function initMobileNavigation() {
  const toggleBtn = document.querySelector('.nav-toggle-btn');
  const navLinks = document.querySelector('.nav-links');
  if (!toggleBtn || !navLinks) return;

  toggleBtn.addEventListener('click', () => {
    const isOpen = navLinks.classList.contains('nav-open');
    if (isOpen) {
      navLinks.classList.remove('nav-open');
      toggleBtn.setAttribute('aria-expanded', 'false');
    } else {
      navLinks.classList.add('nav-open');
      toggleBtn.setAttribute('aria-expanded', 'true');
    }
  });

  // Close menu when clicking any nav link
  document.querySelectorAll('.nav-link').forEach(link => {
    link.addEventListener('click', () => {
      navLinks.classList.remove('nav-open');
      toggleBtn.setAttribute('aria-expanded', 'false');
    });
  });
}

/**
 * 3. Scroll Reveal Animations with IntersectionObserver
 */
function initScrollAnimations() {
  const revealElements = document.querySelectorAll('.reveal-init');
  if (!revealElements.length) return;

  if ('IntersectionObserver' in window) {
    const observer = new IntersectionObserver((entries, obs) => {
      entries.forEach(entry => {
        if (entry.isIntersecting) {
          entry.target.classList.add('reveal-visible');
          obs.unobserve(entry.target);
        }
      });
    }, {
      threshold: 0.12,
      rootMargin: '0px 0px -40px 0px'
    });

    revealElements.forEach(el => observer.observe(el));
  } else {
    // Fallback for older browsers
    revealElements.forEach(el => el.classList.add('reveal-visible'));
  }
}

/**
 * 4. Market Intelligence Commodity Tab Switcher
 */
function initMarketIntelligenceTabs() {
  const tabButtons = document.querySelectorAll('.tab-btn');
  const tableBody = document.getElementById('market-table-body');
  const activeCropBadge = document.getElementById('current-commodity-badge');
  if (!tabButtons.length || !tableBody) return;

  tabButtons.forEach(btn => {
    btn.addEventListener('click', () => {
      tabButtons.forEach(b => b.classList.remove('active'));
      btn.classList.add('active');

      const commodityKey = btn.getAttribute('data-crop');
      renderMarketTable(commodityKey, tableBody, activeCropBadge);
    });
  });
  const first = document.querySelector('.tab-btn.active') || tabButtons[0];
  renderMarketTable(first ? first.getAttribute('data-crop') : '', tableBody, activeCropBadge);
}

function renderMarketTable(cropKey, tableBody, activeCropBadge) {
  if (activeCropBadge) {
    activeCropBadge.textContent = cropKey
      ? `${cropKey} — open Farmer Dashboard for live mandi forecasts`
      : 'Open Farmer Dashboard for live mandi data';
  }
  if (!tableBody) return;
  tableBody.style.opacity = '1';
  tableBody.innerHTML = `
    <tr>
      <td colspan="8" style="padding: 16px; font-size: 0.85rem; color: var(--color-slate-600);">
        This landing page no longer shows fabricated APMC prices.
        Use the <a href="pages/farmer.html">Farmer Dashboard</a> Price Outlook section to load
        real historical mandi records and Chronos forecasts for a chosen commodity, state, district and market.
      </td>
    </tr>`;
}

/**
 * 5. Expandable "Why this recommendation?" Accordion
 */
function initExplainableAccordion() {
  const trigger = document.querySelector('.explainable-trigger');
  const content = document.querySelector('.explainable-content');
  if (!trigger || !content) return;

  trigger.addEventListener('click', () => {
    const isExpanded = content.classList.contains('expanded');
    if (isExpanded) {
      content.classList.remove('expanded');
      trigger.setAttribute('aria-expanded', 'false');
      trigger.querySelector('.accordion-chevron').style.transform = 'rotate(0deg)';
    } else {
      content.classList.add('expanded');
      trigger.setAttribute('aria-expanded', 'true');
      trigger.querySelector('.accordion-chevron').style.transform = 'rotate(180deg)';
    }
  });
}

/**
 * 6. Role Selection Demo Modal
 */
function initRoleDemoModal() {
  const modal = document.getElementById('role-demo-modal');
  const closeBtn = document.getElementById('modal-close-btn');
  const triggers = document.querySelectorAll('.open-role-modal-btn');
  const roleCards = document.querySelectorAll('.role-select-card');
  const launchBtn = document.getElementById('launch-role-demo-btn');
  if (!modal) return;

  let selectedRole = 'farmer';

  triggers.forEach(btn => {
    btn.addEventListener('click', (e) => {
      e.preventDefault();
      const defaultRole = btn.getAttribute('data-default-role') || 'farmer';
      selectedRole = defaultRole;
      updateRoleSelection(selectedRole, roleCards);
      modal.classList.add('modal-open');
      modal.setAttribute('aria-hidden', 'false');
    });
  });

  if (closeBtn) {
    closeBtn.addEventListener('click', () => {
      modal.classList.remove('modal-open');
      modal.setAttribute('aria-hidden', 'true');
    });
  }

  // Close on clicking backdrop outside dialog
  modal.addEventListener('click', (e) => {
    if (e.target === modal) {
      modal.classList.remove('modal-open');
      modal.setAttribute('aria-hidden', 'true');
    }
  });

  // Role card selection inside modal
  roleCards.forEach(card => {
    card.addEventListener('click', () => {
      selectedRole = card.getAttribute('data-role');
      updateRoleSelection(selectedRole, roleCards);
    });
  });

  if (launchBtn) {
    launchBtn.addEventListener('click', () => {
      modal.classList.remove('modal-open');
      modal.setAttribute('aria-hidden', 'true');
      const targetUrl = selectedRole === 'farmer' ? 'pages/farmer.html' : 'pages/buyer.html';
      window.location.href = targetUrl;
    });
  }
}

function updateRoleSelection(role, roleCards) {
  roleCards.forEach(card => {
    if (card.getAttribute('data-role') === role) {
      card.classList.add('active');
    } else {
      card.classList.remove('active');
    }
  });
}

/**
 * 7. Toast Notification Utility
 */
function showToast(message, type = 'info', duration = 3500) {
  let container = document.querySelector('.toast-container');
  if (!container) {
    container = document.createElement('div');
    container.className = 'toast-container';
    document.body.appendChild(container);
  }

  const toast = document.createElement('div');
  toast.className = `toast toast-${type}`;
  toast.innerHTML = `
    <div style="flex: 1;">${message}</div>
    <button style="color: #94A3B8; font-size: 1.1rem; line-height: 1;" onclick="this.parentElement.remove()">&times;</button>
  `;

  container.appendChild(toast);

  // Trigger entrance transition
  requestAnimationFrame(() => {
    toast.classList.add('toast-show');
  });

  // Auto dismiss
  setTimeout(() => {
    toast.classList.remove('toast-show');
    setTimeout(() => toast.remove(), 300);
  }, duration);
}
window.showToast = showToast;

/**
 * 8. Smooth Scroll Helper
 */
function initSmoothScroll() {
  document.querySelectorAll('a[href^="#"]').forEach(anchor => {
    anchor.addEventListener('click', function(e) {
      const targetId = this.getAttribute('href');
      if (targetId === '#' || targetId === '') return;
      const targetEl = document.querySelector(targetId);
      if (targetEl) {
        e.preventDefault();
        targetEl.scrollIntoView({
          behavior: 'smooth',
          block: 'start'
        });
      }
    });
  });
}
