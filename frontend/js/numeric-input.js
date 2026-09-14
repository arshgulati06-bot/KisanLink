/**
 * KisanLink — farmer-friendly numeric fields
 * ==========================================
 *
 * `<input type="number">` actively fought manual entry:
 *   - spinner arrows invited mis-clicks and made typing feel optional
 *   - the scroll wheel silently changed the value while scrolling the page
 *   - `step`/`min` produced opaque browser errors ("the two nearest valid
 *     values are 1943 and 1944") that blocked submit with no visible message
 *
 * These fields are now `type="text" inputmode="decimal"`, so typing, pasting,
 * selecting and deleting behave exactly as a farmer expects, and a numeric
 * keypad still appears on phones. Validity is enforced here and again on the
 * server — nothing was loosened, only moved somewhere it can explain itself.
 *
 * Opt in with class `kl-qty`. Optional data attributes:
 *   data-min      minimum allowed (default 0, exclusive unless data-allow-zero)
 *   data-max      maximum allowed
 *   data-decimals maximum decimal places (default 2)
 *   data-label    name used in messages (falls back to the field's <label>)
 */
(function () {
  'use strict';

  var SELECTOR = '.kl-qty';

  function fieldLabel(el) {
    if (el.dataset.label) return el.dataset.label;
    var lab = el.id && document.querySelector('label[for="' + el.id + '"]');
    if (lab) return lab.textContent.replace('*', '').trim();
    return el.getAttribute('aria-label') || 'This value';
  }

  /** Strip anything that cannot belong to a decimal number. */
  function clean(raw, decimals) {
    var v = String(raw == null ? '' : raw).replace(/[^0-9.]/g, '');
    var parts = v.split('.');
    if (parts.length > 2) v = parts[0] + '.' + parts.slice(1).join('');
    if (decimals === 0) v = v.split('.')[0];
    else {
      var bits = v.split('.');
      if (bits[1] != null && bits[1].length > decimals) {
        v = bits[0] + '.' + bits[1].slice(0, decimals);
      }
    }
    return v;
  }

  /** @returns {{ok: boolean, value: number|null, message: string}} */
  function validate(el) {
    var label = fieldLabel(el);
    var raw = String(el.value || '').trim();
    var min = el.dataset.min != null ? Number(el.dataset.min) : 0;
    var max = el.dataset.max != null ? Number(el.dataset.max) : null;
    var allowZero = el.dataset.allowZero === 'true';
    var required = el.hasAttribute('required');

    if (!raw) {
      return required
        ? { ok: false, value: null, message: 'Please enter ' + label.toLowerCase() + '.' }
        : { ok: true, value: null, message: '' };
    }
    var n = Number(raw);
    if (!isFinite(n)) {
      return { ok: false, value: null, message: label + ' must be a number, for example 25.' };
    }
    if (!allowZero && n <= min) {
      return {
        ok: false, value: n,
        message: label + ' must be more than ' + min + '. Enter a number like 25.',
      };
    }
    if (allowZero && n < min) {
      return { ok: false, value: n, message: label + ' cannot be less than ' + min + '.' };
    }
    if (max != null && n > max) {
      return {
        ok: false, value: n,
        message: label + ' cannot be more than ' + max.toLocaleString('en-IN') + '.',
      };
    }
    return { ok: true, value: n, message: '' };
  }

  function errorNode(el) {
    var next = el.parentNode && el.parentNode.querySelector('.kl-qty-error');
    if (next) return next;
    var p = document.createElement('p');
    p.className = 'kl-qty-error';
    p.setAttribute('role', 'alert');
    p.hidden = true;
    if (el.parentNode) el.parentNode.insertBefore(p, el.nextSibling);
    return p;
  }

  function showError(el, message) {
    var p = errorNode(el);
    if (message) {
      p.textContent = message;
      p.hidden = false;
      el.classList.add('is-invalid');
      el.setAttribute('aria-invalid', 'true');
    } else {
      p.hidden = true;
      p.textContent = '';
      el.classList.remove('is-invalid');
      el.removeAttribute('aria-invalid');
    }
  }

  function wire(el) {
    if (el.dataset.klNum) return;
    el.dataset.klNum = '1';
    var decimals = el.dataset.decimals != null ? Number(el.dataset.decimals) : 2;

    el.addEventListener('input', function () {
      var caretAtEnd = el.selectionStart === el.value.length;
      var cleaned = clean(el.value, decimals);
      if (cleaned !== el.value) {
        var pos = el.selectionStart - (el.value.length - cleaned.length);
        el.value = cleaned;
        if (!caretAtEnd) {
          try { el.setSelectionRange(Math.max(0, pos), Math.max(0, pos)); } catch (e) {}
        }
      }
      // Clear a stale error as soon as the value becomes usable.
      if (validate(el).ok) showError(el, '');
    });

    el.addEventListener('blur', function () {
      if (!el.value.trim()) { showError(el, validate(el).message); return; }
      var r = validate(el);
      showError(el, r.message);
      // Tidy "25." / ".5" into something readable without changing the number.
      if (r.ok && r.value != null) el.value = String(r.value);
    });

    // Typing a stray letter should do nothing rather than silently blank out.
    el.addEventListener('keydown', function (e) {
      if (e.ctrlKey || e.metaKey || e.altKey) return;
      if (e.key.length !== 1) return;
      if (!/[0-9.]/.test(e.key)) e.preventDefault();
    });

    el.addEventListener('paste', function (e) {
      var text = (e.clipboardData || window.clipboardData).getData('text');
      if (text && /[^0-9.,\s₹]/.test(text)) {
        e.preventDefault();
        el.value = clean(text.replace(/[,\s₹]/g, ''), decimals);
        el.dispatchEvent(new Event('input', { bubbles: true }));
      }
    });
  }

  function wireAll(root) {
    (root || document).querySelectorAll(SELECTOR).forEach(wire);
  }

  /**
   * Read a validated number, surfacing the message next to the field.
   * @returns {number|null} null when invalid or empty
   */
  function read(idOrEl) {
    var el = typeof idOrEl === 'string' ? document.getElementById(idOrEl) : idOrEl;
    if (!el) return null;
    var r = validate(el);
    showError(el, r.message);
    if (!r.ok) {
      el.focus();
      return null;
    }
    return r.value;
  }

  window.KLNumeric = { wireAll: wireAll, read: read, validate: validate, showError: showError };

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', function () { wireAll(); });
  } else {
    wireAll();
  }
  // Fields inside modals and re-rendered cards appear later.
  setInterval(function () { wireAll(); }, 1500);
})();
