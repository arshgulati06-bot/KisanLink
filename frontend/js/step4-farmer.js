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
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    setTimeout(init, 0);
  }

  return { init: init };
})();

window.KL_Step4 = KL_Step4;
