/**
 * KisanLink — searchable combobox
 * ================================
 *
 * Turns an existing <select> into a type-to-search field without changing the
 * select's contract: the <select> stays in the DOM as the source of truth, so
 * every `.value` read, `select-option` call and `change` listener already in
 * the app keeps working. This is deliberate — the forecast, Sell Now, market
 * price and lot flows all read those selects directly.
 *
 * Why this exists: state, district and market were plain dropdowns and the
 * mandi-price filters were bare text boxes with no suggestions at all, so a
 * farmer had to scroll long lists or guess exact spellings.
 *
 * Behaviour:
 *   - type to filter, matches highlighted
 *   - ArrowUp / ArrowDown / Enter / Escape / Tab
 *   - click a suggestion to pick it
 *   - clearing the box clears the underlying value
 *   - "no matches" is stated, never a silently empty list
 *   - a disabled/empty source select shows why it is waiting
 */
(function () {
  'use strict';

  var OPEN_BOX = null;

  function _closeOpen(except) {
    if (OPEN_BOX && OPEN_BOX !== except) OPEN_BOX.close();
  }

  document.addEventListener('click', function (e) {
    if (OPEN_BOX && !OPEN_BOX.root.contains(e.target)) OPEN_BOX.close();
  });

  function _escape(s) {
    return String(s).replace(/[&<>"']/g, function (c) {
      return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c];
    });
  }

  /** Bold the typed run inside a suggestion so the match is obvious. */
  function _highlight(text, query) {
    var safe = _escape(text);
    if (!query) return safe;
    var i = text.toLowerCase().indexOf(query.toLowerCase());
    if (i < 0) return safe;
    return _escape(text.slice(0, i)) +
      '<mark>' + _escape(text.slice(i, i + query.length)) + '</mark>' +
      _escape(text.slice(i + query.length));
  }

  function Combobox(select, opts) {
    opts = opts || {};
    this.select = select;
    this.placeholder = opts.placeholder || 'Type to search…';
    this.emptyHint = opts.emptyHint || 'Nothing to choose yet.';
    this.label = opts.label || '';
    this.activeIndex = -1;
    this.items = [];
    this._build();
    this.syncFromSelect();
  }

  Combobox.prototype._build = function () {
    var self = this;
    var sel = this.select;

    // The select stays in the DOM (other code reads it) but is taken out of
    // the visual and tab order.
    sel.classList.add('kl-cb-source');
    sel.setAttribute('tabindex', '-1');
    sel.setAttribute('aria-hidden', 'true');

    var root = document.createElement('div');
    root.className = 'kl-cb';

    var input = document.createElement('input');
    input.type = 'text';
    input.className = 'form-input kl-cb-input';
    input.autocomplete = 'off';
    input.spellcheck = false;
    input.placeholder = this.placeholder;
    input.setAttribute('role', 'combobox');
    input.setAttribute('aria-expanded', 'false');
    input.setAttribute('aria-autocomplete', 'list');
    if (sel.id) input.id = sel.id + '-input';
    if (this.label) input.setAttribute('aria-label', this.label);

    var clear = document.createElement('button');
    clear.type = 'button';
    clear.className = 'kl-cb-clear';
    clear.setAttribute('aria-label', 'Clear ' + (this.label || 'selection'));
    clear.textContent = '×';
    clear.hidden = true;

    var list = document.createElement('ul');
    list.className = 'kl-cb-list';
    list.setAttribute('role', 'listbox');
    list.hidden = true;
    if (sel.id) list.id = sel.id + '-list';
    input.setAttribute('aria-controls', list.id || '');

    sel.parentNode.insertBefore(root, sel);
    root.appendChild(input);
    root.appendChild(clear);
    root.appendChild(list);
    root.appendChild(sel);

    this.root = root;
    this.input = input;
    this.list = list;
    this.clearBtn = clear;

    input.addEventListener('focus', function () { self.open(''); });
    input.addEventListener('input', function () {
      self.open(input.value);
      self.clearBtn.hidden = !input.value;
    });
    input.addEventListener('keydown', function (e) { self._onKey(e); });
    clear.addEventListener('click', function () {
      self.setValue('');
      input.focus();
    });

    // The app repopulates these selects asynchronously; mirror that.
    var mo = new MutationObserver(function () { self.syncFromSelect(); });
    mo.observe(sel, { childList: true, attributes: true, attributeFilter: ['disabled'] });
    sel.addEventListener('change', function () { self.syncFromSelect(); });
  };

  Combobox.prototype._options = function () {
    return Array.prototype.slice.call(this.select.options)
      .filter(function (o) { return o.value !== ''; })
      .map(function (o) { return { value: o.value, text: o.textContent.trim() }; });
  };

  /** Reflect the select's current value + option set into the input. */
  Combobox.prototype.syncFromSelect = function () {
    var opts = this._options();
    this.items = opts;
    var sel = this.select;
    var chosen = opts.filter(function (o) { return o.value === sel.value; })[0];
    if (chosen && document.activeElement !== this.input) {
      this.input.value = chosen.text;
      this.clearBtn.hidden = false;
    } else if (!sel.value && document.activeElement !== this.input) {
      this.input.value = '';
      this.clearBtn.hidden = true;
    }
    var waiting = opts.length === 0;
    this.input.disabled = waiting || sel.disabled;
    this.input.placeholder = waiting ? this.emptyHint : this.placeholder;
    if (!this.list.hidden) this.open(this.input.value);
  };

  Combobox.prototype._filtered = function (query) {
    var q = String(query || '').trim().toLowerCase();
    if (!q) return this.items.slice(0, 60);
    var starts = [], contains = [];
    this.items.forEach(function (o) {
      var t = o.text.toLowerCase();
      var i = t.indexOf(q);
      if (i === 0) starts.push(o);
      else if (i > 0) contains.push(o);
    });
    return starts.concat(contains).slice(0, 60);
  };

  Combobox.prototype.open = function (query) {
    _closeOpen(this);
    OPEN_BOX = this;
    var self = this;
    var matches = this._filtered(query);
    this.matches = matches;
    this.activeIndex = -1;

    if (!this.items.length) {
      this.list.innerHTML = '<li class="kl-cb-empty">' + _escape(this.emptyHint) + '</li>';
    } else if (!matches.length) {
      this.list.innerHTML = '<li class="kl-cb-empty">No match for “' +
        _escape(query) + '”. Check the spelling or clear the box.</li>';
    } else {
      this.list.innerHTML = matches.map(function (o, i) {
        return '<li class="kl-cb-opt" role="option" data-i="' + i + '" data-v="' +
          _escape(o.value) + '">' + _highlight(o.text, String(query || '').trim()) + '</li>';
      }).join('');
      Array.prototype.forEach.call(this.list.querySelectorAll('.kl-cb-opt'), function (li) {
        li.addEventListener('mousedown', function (e) {
          e.preventDefault();
          self.setValue(li.getAttribute('data-v'));
          self.close();
        });
      });
    }
    this.list.hidden = false;
    this.input.setAttribute('aria-expanded', 'true');
  };

  Combobox.prototype.close = function () {
    this.list.hidden = true;
    this.input.setAttribute('aria-expanded', 'false');
    if (OPEN_BOX === this) OPEN_BOX = null;
    // Snap the text back to the real selection so a half-typed word never
    // looks like a choice that was made.
    var sel = this.select;
    var chosen = this.items.filter(function (o) { return o.value === sel.value; })[0];
    this.input.value = chosen ? chosen.text : '';
    this.clearBtn.hidden = !this.input.value;
  };

  Combobox.prototype._move = function (delta) {
    if (this.list.hidden) { this.open(this.input.value); return; }
    var n = (this.matches || []).length;
    if (!n) return;
    this.activeIndex = (this.activeIndex + delta + n) % n;
    var lis = this.list.querySelectorAll('.kl-cb-opt');
    Array.prototype.forEach.call(lis, function (li, i) {
      li.classList.toggle('is-active', i === this.activeIndex);
      if (i === this.activeIndex) li.scrollIntoView({ block: 'nearest' });
    }, this);
  };

  Combobox.prototype._onKey = function (e) {
    if (e.key === 'ArrowDown') { e.preventDefault(); this._move(1); return; }
    if (e.key === 'ArrowUp') { e.preventDefault(); this._move(-1); return; }
    if (e.key === 'Escape') { this.close(); return; }
    if (e.key === 'Enter') {
      var m = this.matches || [];
      if (!this.list.hidden && m.length) {
        e.preventDefault();
        // Enter with nothing highlighted takes the single/top match — the
        // behaviour people expect from a search box.
        this.setValue(m[this.activeIndex >= 0 ? this.activeIndex : 0].value);
        this.close();
      }
      return;
    }
    if (e.key === 'Tab' && !this.list.hidden) {
      var mm = this.matches || [];
      if (this.activeIndex >= 0 && mm.length) this.setValue(mm[this.activeIndex].value);
      this.close();
    }
  };

  /** Write through to the select and fire `change` so existing code reacts. */
  Combobox.prototype.setValue = function (value) {
    var sel = this.select;
    if (sel.value === value) {
      this.syncFromSelect();
      return;
    }
    sel.value = value;
    sel.dispatchEvent(new Event('change', { bubbles: true }));
    this.syncFromSelect();
  };

  /**
   * Attach to a select by id. Safe to call more than once.
   * @returns {Combobox|null}
   */
  function attach(selectId, opts) {
    var sel = document.getElementById(selectId);
    if (!sel || sel.tagName !== 'SELECT' || sel.dataset.klCb) return null;
    sel.dataset.klCb = '1';
    var cb = new Combobox(sel, opts);
    sel.__klCombobox = cb;
    return cb;
  }

  window.KLCombobox = { attach: attach };
})();
