/**
 * KisanLink — Chat & Voice Assistant Module
 * SIH 2026 — PS SIH26132: Market Linkages & Price Discovery
 * Frontend Step 5: Voice-Ready Farmer Experience with Web Speech API
 *
 * Features:
 *  1. Interactive text & voice assistant UI.
 *  2. Web Speech API SpeechRecognition with localized Indian language BCP-47 codes.
 *  3. Microphone button, listening pulse animation, speech transcript, and stop controls.
 *  4. Graceful fallback for unsupported browsers.
 *  5. Web SpeechSynthesis TTS support via speakAssistantResponse(text).
 *  6. Single integration boundary: sendAssistantMessage(message).
 */

var KL_Chat = (function () {

  var _messages   = [];
  var _isOpen     = false;
  var _isLoading  = false;
  var _isListening = false;
  var _recognition = null;
  var _synth       = window.speechSynthesis || null;

  /* ── Suggested Questions ─────────────────────────────────────────────── */
  var SUGGESTED = [
    { id: 'q1', key: 'chat.q1', text: 'Where should I sell?' },
    { id: 'q2', key: 'chat.q2', text: 'What is the current market price?' },
    { id: 'q3', key: 'chat.q3', text: 'Should I sell now or wait?' },
    { id: 'q4', key: 'chat.q4', text: 'Show my buyer opportunities' },
  ];

  /* ── DOM IDs ─────────────────────────────────────────────────────────── */
  var IDS = {
    toggleBtn:       'chat-toggle-btn',
    panel:           'chat-panel',
    closeBtn:        'chat-close-btn',
    messageList:     'chat-message-list',
    emptyState:      'chat-empty-state',
    inputEl:         'chat-input',
    sendBtn:         'chat-send-btn',
    micBtn:          'chat-mic-btn',
    voiceStatusArea: 'chat-voice-status',
    voiceTranscript: 'chat-voice-transcript',
    suggestedWrap:   'chat-suggested',
    badge:           'chat-unread-badge',
    voiceNotice:     'chat-voice-notice'
  };

  /* ── Helpers ─────────────────────────────────────────────────────────── */
  function _escHtml(str) {
    var d = document.createElement('div');
    d.appendChild(document.createTextNode(str));
    return d.innerHTML;
  }

  function _tsNow() {
    return new Date().toLocaleTimeString('en-IN', { hour: '2-digit', minute: '2-digit' });
  }

  function _addMessage(role, text, allowSpeak) {
    var msg = { role: role, text: text, ts: _tsNow() };
    _messages.push(msg);
    _renderMessage(msg, allowSpeak);
    _scrollToBottom();

    var emptyEl = document.getElementById(IDS.emptyState);
    if (emptyEl) emptyEl.hidden = true;
  }

  function _renderMessage(msg, allowSpeak) {
    var listEl = document.getElementById(IDS.messageList);
    if (!listEl) return;

    var isUser = msg.role === 'user';
    var div = document.createElement('div');
    div.className = 'chat-msg ' + (isUser ? 'chat-msg--user' : 'chat-msg--assistant');

    var speakBtnHtml = '';
    if (!isUser && allowSpeak !== false && _synth) {
      speakBtnHtml =
        '<button type="button" class="chat-msg-speak-btn" aria-label="Listen to response" title="Listen to response">' +
          '<svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">' +
            '<polygon points="11 5 6 9 2 9 2 15 6 15 11 19 11 5"/>' +
            '<path d="M19.07 4.93a10 10 0 0 1 0 14.14M15.54 8.46a5 5 0 0 1 0 7.07"/>' +
          '</svg>' +
        '</button>';
    }

    div.innerHTML =
      '<div class="chat-msg-bubble">' + _escHtml(msg.text) + '</div>' +
      '<div class="chat-msg-footer">' +
        '<span class="chat-msg-ts">' + msg.ts + '</span>' +
        speakBtnHtml +
      '</div>';

    var speakBtn = div.querySelector('.chat-msg-speak-btn');
    if (speakBtn) {
      speakBtn.addEventListener('click', function () {
        speakAssistantResponse(msg.text);
      });
    }

    listEl.appendChild(div);
  }

  function _renderLoadingBubble() {
    var listEl = document.getElementById(IDS.messageList);
    if (!listEl) return;
    var div = document.createElement('div');
    div.id = 'chat-loading-bubble';
    div.className = 'chat-msg chat-msg--assistant';
    div.innerHTML = '<div class="chat-msg-bubble chat-loading-dots"><span></span><span></span><span></span></div>';
    listEl.appendChild(div);
    _scrollToBottom();
  }

  function _removeLoadingBubble() {
    var el = document.getElementById('chat-loading-bubble');
    if (el) el.remove();
  }

  function _scrollToBottom() {
    var listEl = document.getElementById(IDS.messageList);
    if (listEl) listEl.scrollTop = listEl.scrollHeight;
  }

  function _renderSuggested() {
    var wrap = document.getElementById(IDS.suggestedWrap);
    if (!wrap) return;

    var t = window.KL_I18n ? window.KL_I18n.t : function (k) { return k; };

    wrap.innerHTML = SUGGESTED.map(function (q) {
      var label = t(q.key) || q.text;
      return '<button type="button" class="chat-suggested-btn" data-key="' + q.key + '" data-question="' +
             _escHtml(label) + '">' + _escHtml(label) + '</button>';
    }).join('');

    wrap.querySelectorAll('.chat-suggested-btn').forEach(function (btn) {
      btn.addEventListener('click', function () {
        _submitMessage(btn.getAttribute('data-question'));
      });
    });
  }

  /* ════════════════════════════════════════════════════════════════════════
     SPEECH RECOGNITION (VOICE INPUT) & SYNTHESIS
     ════════════════════════════════════════════════════════════════════════ */

  function _isSpeechSupported() {
    return !!(window.SpeechRecognition || window.webkitSpeechRecognition);
  }

  function startVoiceInput() {
    if (!_isSpeechSupported()) {
      _showVoiceNotice('Voice input is not supported in this browser. You can use text instead.');
      return;
    }

    if (_isListening) {
      stopVoiceInput();
      return;
    }

    try {
      var SpeechRec = window.SpeechRecognition || window.webkitSpeechRecognition;
      _recognition = new SpeechRec();

      var speechLang = (window.KL_I18n && window.KL_I18n.getSpeechLocale) ? window.KL_I18n.getSpeechLocale() : 'en-IN';
      _recognition.lang = speechLang;
      _recognition.interimResults = true;
      _recognition.maxAlternatives = 1;
      _recognition.continuous = false;

      _setVoiceUIState('listening');

      _recognition.onstart = function () {
        _isListening = true;
        _setVoiceUIState('listening');
      };

      _recognition.onresult = function (event) {
        var transcript = '';
        for (var i = event.resultIndex; i < event.results.length; ++i) {
          transcript += event.results[i][0].transcript;
        }

        var inputEl = document.getElementById(IDS.inputEl);
        if (inputEl) inputEl.value = transcript;

        var transEl = document.getElementById(IDS.voiceTranscript);
        if (transEl) transEl.textContent = transcript || 'Listening...';

        if (event.results[0].isFinal) {
          stopVoiceInput();
          if (transcript.trim().length > 0) {
            setTimeout(function () {
              _submitMessage(transcript);
            }, 300);
          }
        }
      };

      _recognition.onerror = function (event) {
        console.warn('[KL_Chat] Voice recognition error:', event.error);
        _isListening = false;
        _setVoiceUIState('idle');
        if (event.error === 'not-allowed') {
          _showVoiceNotice('Microphone access was denied. Please allow microphone permissions or type instead.');
        } else if (event.error === 'no-speech') {
          _showVoiceNotice('No speech detected. Please tap the mic and try again.');
        } else {
          _showVoiceNotice('Voice input error (' + event.error + '). You can use text instead.');
        }
      };

      _recognition.onend = function () {
        _isListening = false;
        _setVoiceUIState('idle');
      };

      _recognition.start();

    } catch (e) {
      console.warn('[KL_Chat] Failed to start speech recognition:', e);
      _isListening = false;
      _setVoiceUIState('idle');
      _showVoiceNotice('Voice input could not be started. Please use text instead.');
    }
  }

  function stopVoiceInput() {
    if (_recognition) {
      try { _recognition.stop(); } catch (e) {}
      _recognition = null;
    }
    _isListening = false;
    _setVoiceUIState('idle');
  }

  function _setVoiceUIState(state) {
    var micBtn     = document.getElementById(IDS.micBtn);
    var statusArea = document.getElementById(IDS.voiceStatusArea);

    if (state === 'listening') {
      if (micBtn) {
        micBtn.classList.add('chat-mic-btn--active');
        micBtn.setAttribute('aria-pressed', 'true');
        micBtn.title = 'Stop listening';
      }
      if (statusArea) statusArea.hidden = false;
    } else {
      if (micBtn) {
        micBtn.classList.remove('chat-mic-btn--active');
        micBtn.setAttribute('aria-pressed', 'false');
        micBtn.title = 'Start voice input';
      }
      if (statusArea) statusArea.hidden = true;
    }
  }

  function _showVoiceNotice(text) {
    var noticeEl = document.getElementById(IDS.voiceNotice);
    if (noticeEl) {
      noticeEl.textContent = text;
      noticeEl.hidden = false;
      setTimeout(function () { noticeEl.hidden = true; }, 6000);
    }
  }

  function speakAssistantResponse(text) {
    if (!_synth || !text) return;
    try {
      _synth.cancel(); // Stop any currently playing speech
      var cleanText = text.replace(/<[^>]*>/g, '').replace(/[•—]/g, ' ');
      var utterance = new SpeechSynthesisUtterance(cleanText);
      utterance.lang = (window.KL_I18n && window.KL_I18n.getSpeechLocale) ? window.KL_I18n.getSpeechLocale() : 'en-IN';
      utterance.rate = 0.95;
      _synth.speak(utterance);
    } catch (e) {
      console.warn('[KL_Chat] Speech synthesis failed:', e);
    }
  }

  /* ════════════════════════════════════════════════════════════════════════
     INTEGRATION BOUNDARY — sendAssistantMessage(message)
     ════════════════════════════════════════════════════════════════════════ */
  function sendAssistantMessage(message) {
    /* ── INTEGRATION POINT ────────────────────────────────────────────────
       When backend is ready, replace with:
       return window.apiClient.post('/assistant/message', { message: message })
         .then(function (res) { return res.data.reply; });
    ──────────────────────────────────────────────────────────────────────── */
    var locale = (window.KL_I18n && window.KL_I18n.getLocale) ? window.KL_I18n.getLocale() : 'en';

    var responses = {
      en: 'KisanLink Assistant is not yet connected to a live AI model. Your query "' + message + '" has been noted. When the backend service is integrated, real-time advice will appear here.',
      hi: 'KisanLink सहायक अभी लाइव AI मॉडल से कनेक्ट नहीं है। आपका प्रश्न "' + message + '" नोट कर लिया गया है। बैकएंड सेवा जुड़ने पर यहाँ रीयल-टाइम सलाह मिलेगी।',
      mr: 'KisanLink सहाय्यक सध्या लाइव्ह AI मॉडेलशी जोडलेला नाही. आपला प्रश्न "' + message + '" नोंदवला गेला आहे. सेवा सुरू झाल्यावर येथे थेट सल्ला मिळेल।'
    };

    var reply = responses[locale] || responses.en;

    return new Promise(function (resolve) {
      setTimeout(function () {
        resolve(reply);
      }, 900);
    });
  }

  /* ── Submit Handler ──────────────────────────────────────────────────── */
  function _submitMessage(text) {
    text = (text || '').trim();
    if (!text || _isLoading) return;

    _addMessage('user', text);

    var inputEl = document.getElementById(IDS.inputEl);
    if (inputEl) inputEl.value = '';

    var sugWrap = document.getElementById(IDS.suggestedWrap);
    if (sugWrap) sugWrap.style.display = 'none';

    _isLoading = true;
    _renderLoadingBubble();

    var sendBtn = document.getElementById(IDS.sendBtn);
    if (sendBtn) sendBtn.disabled = true;

    sendAssistantMessage(text).then(function (reply) {
      _isLoading = false;
      _removeLoadingBubble();
      _addMessage('assistant', reply, true);
      if (sendBtn) sendBtn.disabled = false;
    }).catch(function (err) {
      _isLoading = false;
      _removeLoadingBubble();
      _addMessage('assistant', 'Sorry, an error occurred: ' + err.message, false);
      if (sendBtn) sendBtn.disabled = false;
    });
  }

  /* ── Panel Open / Close ──────────────────────────────────────────────── */
  function _openPanel() {
    var panel = document.getElementById(IDS.panel);
    if (panel) { panel.hidden = false; panel.setAttribute('aria-hidden', 'false'); }
    _isOpen = true;
    var badge = document.getElementById(IDS.badge);
    if (badge) badge.hidden = true;
    var inputEl = document.getElementById(IDS.inputEl);
    if (inputEl) setTimeout(function () { inputEl.focus(); }, 100);
  }

  function _closePanel() {
    var panel = document.getElementById(IDS.panel);
    if (panel) { panel.hidden = true; panel.setAttribute('aria-hidden', 'true'); }
    _isOpen = false;
    stopVoiceInput();
  }

  /* ── Initialisation ──────────────────────────────────────────────────── */
  function init() {
    var toggleBtn = document.getElementById(IDS.toggleBtn);
    var closeBtn  = document.getElementById(IDS.closeBtn);
    var sendBtn   = document.getElementById(IDS.sendBtn);
    var micBtn    = document.getElementById(IDS.micBtn);
    var inputEl   = document.getElementById(IDS.inputEl);

    if (!toggleBtn) return;

    toggleBtn.addEventListener('click', function () {
      if (_isOpen) _closePanel(); else _openPanel();
    });

    if (closeBtn) closeBtn.addEventListener('click', _closePanel);

    if (sendBtn) sendBtn.addEventListener('click', function () {
      var inputEl2 = document.getElementById(IDS.inputEl);
      _submitMessage(inputEl2 ? inputEl2.value : '');
    });

    if (micBtn) {
      micBtn.addEventListener('click', function () {
        if (_isListening) {
          stopVoiceInput();
        } else {
          startVoiceInput();
        }
      });
    }

    if (inputEl) {
      inputEl.addEventListener('keydown', function (e) {
        if (e.key === 'Enter' && !e.shiftKey) {
          e.preventDefault();
          _submitMessage(inputEl.value);
        }
      });
    }

    _renderSuggested();

    // Re-render suggested when language switches
    document.addEventListener('kl:localeChanged', function () {
      _renderSuggested();
    });

    console.info('[KL_Chat] Voice-ready assistant initialised.');
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }

  return {
    sendAssistantMessage: sendAssistantMessage,
    startVoiceInput: startVoiceInput,
    stopVoiceInput: stopVoiceInput,
    speakAssistantResponse: speakAssistantResponse
  };
})();

window.KL_Chat = KL_Chat;
window.sendAssistantMessage = KL_Chat.sendAssistantMessage;
window.startVoiceInput = KL_Chat.startVoiceInput;
window.stopVoiceInput = KL_Chat.stopVoiceInput;
window.speakAssistantResponse = KL_Chat.speakAssistantResponse;
