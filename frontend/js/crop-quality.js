/**
 * KisanLink — Crop Quality Assessment Module
 * SIH 2026 — PS SIH26132: Market Linkages & Price Discovery
 * Frontend Step 5: Enhanced Camera/Upload UX, Photo Guidelines & Decision Pipeline Integration
 *
 * This module provides:
 *  1. Camera capture (getUserMedia) with permission detection, preview, capture, retake, stream cleanup.
 *  2. File upload (JPG/PNG) with drag-and-drop, preview, and removal.
 *  3. Farmer-friendly image quality guidelines (Lighting, Centering, Focus, Texture).
 *  4. 4-State Quality Assessment UI:
 *     - Not Assessed (idle)
 *     - Assessing (loading)
 *     - Assessment Available (live ML result)
 *     - Service Unavailable / Pending (clearly marked placeholder)
 *  5. Direct Pipeline Connector: applyQualityToDecisionPipeline(crop, grade)
 *  6. Single integration boundary: assessCropQuality(imageFile, crop) / analyzeCropQuality(imageFile)
 */

'use strict';

var CQA = {
  ids: {
    section:           'crop-quality-section',
    modeCamera:        'cqa-mode-camera',
    modeUpload:        'cqa-mode-upload',
    cameraPanel:       'cqa-camera-panel',
    uploadPanel:       'cqa-upload-panel',
    videoEl:           'cqa-video',
    canvasEl:          'cqa-canvas',
    captureBtn:        'cqa-capture-btn',
    retakeCameraBtn:   'cqa-retake-camera',
    cameraPlaceholder: 'cqa-camera-placeholder',
    cameraPermDenied:  'cqa-camera-perm-denied',
    cameraLiveWrap:    'cqa-camera-live-wrap',
    cameraCapturedWrap:'cqa-camera-captured-wrap',
    capturedImg:       'cqa-captured-img',
    fileInput:         'cqa-file-input',
    uploadTrigger:     'cqa-upload-trigger',
    uploadPreviewWrap: 'cqa-upload-preview-wrap',
    uploadPreviewImg:  'cqa-upload-preview-img',
    uploadCropName:    'cqa-upload-crop-name',
    uploadFileSize:    'cqa-upload-file-size',
    removeUploadBtn:   'cqa-remove-upload',
    cropSelect:        'cqa-crop-select',
    analyzeBtn:        'cqa-analyze-btn',
    resultArea:        'cqa-result-area',
    loadingState:      'cqa-loading-state',
    idleState:         'cqa-idle-state',
    errorState:        'cqa-error-state',
    errorMessage:      'cqa-error-message',
    resultState:       'cqa-result-state',
    resultGrade:       'cqa-result-grade',
    resultConfidence:  'cqa-result-confidence',
    resultIndicators:  'cqa-result-indicators',
    resultModelStatus: 'cqa-result-model-status',
    analyzeAgainBtn:   'cqa-analyze-again-btn',
    applyPipelineBtn:  'cqa-apply-pipeline-btn'
  },

  state: {
    mode:          'upload', // default to upload for immediate usability
    imageFile:     null,
    cameraStream:  null,
    cameraActive:  false,
    imageCaptured: false,
    selectedCrop:  'Onion',
    assessedGrade: null
  },

  ACCEPTED_TYPES: ['image/jpeg', 'image/png'],
  ACCEPTED_EXT:   '.jpg,.jpeg,.png',
  MAX_FILE_BYTES: 10 * 1024 * 1024
};

/* ============================================================
   INITIALISATION
   ============================================================ */
function initCropQualityAssessment() {
  var section = document.getElementById(CQA.ids.section);
  if (!section) return;

  _bindModeToggles();
  _bindCameraControls();
  _bindUploadControls();
  _bindAnalyzeButton();
  _bindAnalyzeAgainButton();
  _bindPipelineConnector();
  _bindCropSelector();

  // Set initial default mode to upload without triggering camera prompt automatically
  _switchMode('upload');

  console.info('[CQA] Crop Quality Assessment module initialised (ML placeholder active).');
}

/* ============================================================
   MODE TOGGLE — Camera vs Upload
   ============================================================ */
function _bindModeToggles() {
  var btnCamera = document.getElementById(CQA.ids.modeCamera);
  var btnUpload = document.getElementById(CQA.ids.modeUpload);
  if (!btnCamera || !btnUpload) return;

  btnCamera.addEventListener('click', function() { _switchMode('camera'); });
  btnUpload.addEventListener('click', function() { _switchMode('upload'); });
}

function _switchMode(mode) {
  if (CQA.state.mode === 'camera' && mode !== 'camera') {
    _stopCameraStream();
    _resetCameraUI();
  }
  if (CQA.state.mode === 'upload' && mode !== 'upload') {
    _resetUploadUI();
  }

  CQA.state.mode = mode;
  CQA.state.imageFile = null;
  _resetResultArea();

  var cameraPanel = document.getElementById(CQA.ids.cameraPanel);
  var uploadPanel = document.getElementById(CQA.ids.uploadPanel);
  var btnCamera   = document.getElementById(CQA.ids.modeCamera);
  var btnUpload   = document.getElementById(CQA.ids.modeUpload);

  if (mode === 'camera') {
    if (cameraPanel) cameraPanel.hidden = false;
    if (uploadPanel) uploadPanel.hidden = true;
    if (btnCamera) { btnCamera.setAttribute('aria-pressed', 'true'); btnCamera.classList.add('cqa-mode-btn--active'); }
    if (btnUpload) { btnUpload.setAttribute('aria-pressed', 'false'); btnUpload.classList.remove('cqa-mode-btn--active'); }
    _startCamera();
  } else {
    if (cameraPanel) cameraPanel.hidden = true;
    if (uploadPanel) uploadPanel.hidden = false;
    if (btnUpload) { btnUpload.setAttribute('aria-pressed', 'true'); btnUpload.classList.add('cqa-mode-btn--active'); }
    if (btnCamera) { btnCamera.setAttribute('aria-pressed', 'false'); btnCamera.classList.remove('cqa-mode-btn--active'); }
  }

  _updateAnalyzeButton();
}

/* ============================================================
   CAMERA CONTROLS
   ============================================================ */
function _bindCameraControls() {
  var captureBtn = document.getElementById(CQA.ids.captureBtn);
  var retakeBtn  = document.getElementById(CQA.ids.retakeCameraBtn);
  if (captureBtn) captureBtn.addEventListener('click', _capturePhoto);
  if (retakeBtn)  retakeBtn.addEventListener('click', _retakePhoto);
}

function _startCamera() {
  var placeholder  = document.getElementById(CQA.ids.cameraPlaceholder);
  var permDenied   = document.getElementById(CQA.ids.cameraPermDenied);
  var liveWrap     = document.getElementById(CQA.ids.cameraLiveWrap);
  var capturedWrap = document.getElementById(CQA.ids.cameraCapturedWrap);
  var video        = document.getElementById(CQA.ids.videoEl);

  _showEl(placeholder);
  _hideEl(permDenied);
  _hideEl(liveWrap);
  _hideEl(capturedWrap);
  CQA.state.imageCaptured = false;

  if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
    _hideEl(placeholder);
    _showEl(permDenied);
    var t1 = document.querySelector('#cqa-camera-perm-denied .cqa-perm-text');
    if (t1) t1.textContent = 'Camera API is not supported in this browser. Please use the "Upload Image" option instead.';
    return;
  }

  navigator.mediaDevices.getUserMedia({
    video: { facingMode: 'environment', width: { ideal: 1280 }, height: { ideal: 720 } },
    audio: false
  }).then(function(stream) {
    CQA.state.cameraStream = stream;
    CQA.state.cameraActive = true;
    if (video) { video.srcObject = stream; video.play(); }
    _hideEl(placeholder);
    _showEl(liveWrap);
  }).catch(function(err) {
    _hideEl(placeholder);
    _showEl(permDenied);
    var permText = document.querySelector('#cqa-camera-perm-denied .cqa-perm-text');
    if (permText) {
      if (err.name === 'NotAllowedError' || err.name === 'PermissionDeniedError') {
        permText.textContent = 'Camera access was denied. Please allow camera permissions in browser settings, or use "Upload Image".';
      } else if (err.name === 'NotFoundError' || err.name === 'DevicesNotFoundError') {
        permText.textContent = 'No camera was detected on this device. Please use the "Upload Image" option instead.';
      } else {
        permText.textContent = 'Camera could not be started. Please use "Upload Image" instead.';
      }
    }
    console.warn('[CQA] Camera error:', err);
  });
}

function _capturePhoto() {
  var video        = document.getElementById(CQA.ids.videoEl);
  var canvas       = document.getElementById(CQA.ids.canvasEl);
  var capturedImg  = document.getElementById(CQA.ids.capturedImg);
  var liveWrap     = document.getElementById(CQA.ids.cameraLiveWrap);
  var capturedWrap = document.getElementById(CQA.ids.cameraCapturedWrap);

  if (!video || !canvas) return;

  canvas.width  = video.videoWidth  || 640;
  canvas.height = video.videoHeight || 480;
  canvas.getContext('2d').drawImage(video, 0, 0, canvas.width, canvas.height);

  canvas.toBlob(function(blob) {
    var file = new File([blob], 'kl_crop_photo_' + Date.now() + '.jpg', { type: 'image/jpeg' });
    CQA.state.imageFile     = file;
    CQA.state.imageCaptured = true;

    if (capturedImg) {
      capturedImg.src = canvas.toDataURL('image/jpeg', 0.92);
      capturedImg.alt = 'Captured crop photo for quality assessment';
    }

    _hideEl(liveWrap);
    _showEl(capturedWrap);
    _stopCameraStream();
    _updateAnalyzeButton();
    _resetResultArea();
  }, 'image/jpeg', 0.92);
}

function _retakePhoto() {
  CQA.state.imageFile     = null;
  CQA.state.imageCaptured = false;
  _resetResultArea();
  _updateAnalyzeButton();
  _hideEl(document.getElementById(CQA.ids.cameraCapturedWrap));
  _startCamera();
}

function _stopCameraStream() {
  if (CQA.state.cameraStream) {
    CQA.state.cameraStream.getTracks().forEach(function(t) { t.stop(); });
    CQA.state.cameraStream = null;
  }
  CQA.state.cameraActive = false;
  var video = document.getElementById(CQA.ids.videoEl);
  if (video) video.srcObject = null;
}

function _resetCameraUI() {
  _stopCameraStream();
  CQA.state.imageCaptured = false;
  _showEl(document.getElementById(CQA.ids.cameraPlaceholder));
  _hideEl(document.getElementById(CQA.ids.cameraPermDenied));
  _hideEl(document.getElementById(CQA.ids.cameraLiveWrap));
  _hideEl(document.getElementById(CQA.ids.cameraCapturedWrap));
}

/* ============================================================
   UPLOAD CONTROLS
   ============================================================ */
function _bindUploadControls() {
  var fileInput  = document.getElementById(CQA.ids.fileInput);
  var triggerBtn = document.getElementById(CQA.ids.uploadTrigger);
  var removeBtn  = document.getElementById(CQA.ids.removeUploadBtn);

  if (fileInput) {
    fileInput.accept = CQA.ACCEPTED_EXT;
    fileInput.addEventListener('change', _onFileSelected);
  }

  if (triggerBtn) {
    triggerBtn.addEventListener('click', function() { if (fileInput) fileInput.click(); });
    triggerBtn.addEventListener('keydown', function(e) {
      if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); if (fileInput) fileInput.click(); }
    });
  }

  if (removeBtn) { removeBtn.addEventListener('click', _removeUploadedImage); }

  var dropZone = document.getElementById('cqa-upload-dropzone');
  if (dropZone) {
    dropZone.addEventListener('dragover', function(e) { e.preventDefault(); dropZone.classList.add('cqa-dropzone--dragover'); });
    dropZone.addEventListener('dragleave', function() { dropZone.classList.remove('cqa-dropzone--dragover'); });
    dropZone.addEventListener('drop', function(e) {
      e.preventDefault();
      dropZone.classList.remove('cqa-dropzone--dragover');
      var file = e.dataTransfer.files && e.dataTransfer.files[0];
      if (file) _processUploadedFile(file);
    });
  }
}

function _onFileSelected(e) {
  var file = e.target.files && e.target.files[0];
  if (file) _processUploadedFile(file);
  e.target.value = '';
}

function _processUploadedFile(file) {
  if (!CQA.ACCEPTED_TYPES.includes(file.type)) {
    _showUploadError('Unsupported file format. Please upload a JPG or PNG image.');
    return;
  }
  if (file.size > CQA.MAX_FILE_BYTES) {
    _showUploadError('Image too large (' + (file.size / 1024 / 1024).toFixed(1) + ' MB). Maximum allowed is 10 MB.');
    return;
  }

  CQA.state.imageFile = file;
  _resetResultArea();

  var reader = new FileReader();
  reader.onload = function(ev) {
    var previewImg  = document.getElementById(CQA.ids.uploadPreviewImg);
    var cropName    = document.getElementById(CQA.ids.uploadCropName);
    var fileSize    = document.getElementById(CQA.ids.uploadFileSize);
    var previewWrap = document.getElementById(CQA.ids.uploadPreviewWrap);
    var dropZone    = document.getElementById('cqa-upload-dropzone');

    if (previewImg)  { previewImg.src = ev.target.result; previewImg.alt = 'Selected crop image: ' + file.name; }
    if (cropName)    cropName.textContent = file.name;
    if (fileSize)    fileSize.textContent = Math.round(file.size / 1024) + ' KB';
    if (previewWrap) _showEl(previewWrap);
    if (dropZone)    dropZone.style.display = 'none';

    _updateAnalyzeButton();
  };
  reader.readAsDataURL(file);
}

function _showUploadError(message) {
  var errEl = document.getElementById('cqa-upload-file-error');
  if (errEl) {
    errEl.textContent = message;
    _showEl(errEl);
    setTimeout(function() { _hideEl(errEl); }, 5000);
  }
}

function _removeUploadedImage() {
  CQA.state.imageFile = null;
  var previewWrap = document.getElementById(CQA.ids.uploadPreviewWrap);
  var dropZone    = document.getElementById('cqa-upload-dropzone');
  var previewImg  = document.getElementById(CQA.ids.uploadPreviewImg);

  if (previewWrap) _hideEl(previewWrap);
  if (dropZone)    dropZone.style.removeProperty('display');
  if (previewImg)  previewImg.src = '';

  _updateAnalyzeButton();
  _resetResultArea();
}

function _resetUploadUI() { _removeUploadedImage(); }

/* ============================================================
   CROP SELECTOR
   ============================================================ */
function _bindCropSelector() {
  var sel = document.getElementById(CQA.ids.cropSelect);
  if (sel) {
    sel.addEventListener('change', function() {
      CQA.state.selectedCrop = sel.value;
    });
  }
}

/* ============================================================
   ANALYZE BUTTON & INTEGRATION BOUNDARY
   ============================================================ */
function _bindAnalyzeButton() {
  var btn = document.getElementById(CQA.ids.analyzeBtn);
  if (btn) btn.addEventListener('click', _onAnalyzeClick);
}

function _updateAnalyzeButton() {
  var btn = document.getElementById(CQA.ids.analyzeBtn);
  if (!btn) return;
  var hasImage = !!CQA.state.imageFile;
  btn.disabled = !hasImage;
  btn.setAttribute('aria-disabled', hasImage ? 'false' : 'true');
}

function _onAnalyzeClick() {
  if (!CQA.state.imageFile) return;
  _showLoadingState();

  var crop = CQA.state.selectedCrop || 'Onion';

  analyzeCropQuality(CQA.state.imageFile, crop).then(function(result) {
    _showResultState(result);
  }).catch(function(err) {
    _showErrorState(err.message || 'An unexpected error occurred during quality analysis.');
    console.error('[CQA] Analysis error:', err);
  });
}

/**
 * Single Integration Boundary: analyzeCropQuality(imageFile, crop)
 */
function analyzeCropQuality(imageFile, crop) {
  /* ── INTEGRATION POINT ──────────────────────────────────────────────
     When ML backend is ready, replace with:
     var formData = new FormData();
     formData.append('image', imageFile);
     formData.append('crop', crop || 'Onion');
     return fetch(`${window.apiClient.baseUrl}/ml/quality-assessment`, {
       method: 'POST',
       body: formData,
       headers: { Authorization: `Bearer ${window.apiClient.getAuthToken() || ''}` }
     }).then(res => res.json());
  ────────────────────────────────────────────────────────────────────── */

  return new Promise(function(resolve) {
    setTimeout(function() {
      resolve({
        _placeholder: true,
        crop:         crop || 'Onion',
        grade:        null,
        confidence:   null,
        indicators:   [],
        model:        { name: 'CropQualityNet-v1', status: 'not_connected' },
        message:      'Quality assessment will appear when the ML service is connected.'
      });
    }, 1500);
  });
}

/* ============================================================
   DECISION PIPELINE CONNECTOR
   ============================================================ */
function _bindPipelineConnector() {
  var btn = document.getElementById(CQA.ids.applyPipelineBtn);
  if (btn) {
    btn.addEventListener('click', function () {
      applyQualityToDecisionPipeline(CQA.state.selectedCrop, CQA.state.assessedGrade || 'Grade A (Demo)');
    });
  }
}

/**
 * Connects Crop Quality directly into the Best Action Decision Engine
 * @param {string} crop
 * @param {string} grade
 */
function applyQualityToDecisionPipeline(crop, grade) {
  var cropEl    = document.getElementById('ba-crop');
  var qualityEl = document.getElementById('ba-quality');

  if (cropEl) cropEl.textContent = crop || 'Onion';
  if (qualityEl) qualityEl.textContent = grade || 'Grade A';

  // Highlight the decision section & smoothly scroll
  var target = document.getElementById('best-action-section');
  if (target) {
    target.scrollIntoView({ behavior: 'smooth', block: 'start' });
    target.classList.add('pulse-highlight');
    setTimeout(function () { target.classList.remove('pulse-highlight'); }, 2000);
  }

  // Also update price forecast selector if matching
  var pfSelect = document.getElementById('pf-crop-select');
  if (pfSelect && crop) {
    pfSelect.value = crop;
  }
}

/* ============================================================
   RESULT AREA STATE MANAGEMENT
   ============================================================ */
function _resetResultArea()            { _setResultState('idle'); }
function _showLoadingState()           { _setResultState('loading'); }

function _showResultState(result) {
  var gradeEl    = document.getElementById(CQA.ids.resultGrade);
  var confEl     = document.getElementById(CQA.ids.resultConfidence);
  var indEl      = document.getElementById(CQA.ids.resultIndicators);
  var statusEl   = document.getElementById(CQA.ids.resultModelStatus);
  var pipelineBtn= document.getElementById(CQA.ids.applyPipelineBtn);

  if (result._placeholder) {
    if (gradeEl)  gradeEl.innerHTML  = '<span class="cqa-placeholder-chip">Awaiting ML Connection</span>';
    if (confEl)   confEl.innerHTML   = '<span class="cqa-placeholder-dash">&mdash;</span>';
    if (indEl)    indEl.innerHTML    = '<li class="cqa-placeholder-item">Quality assessment will appear when the ML service is connected.</li>';
    if (statusEl) statusEl.textContent = 'ML service not yet connected — UI is integration-ready.';
    if (pipelineBtn) pipelineBtn.hidden = false;
    CQA.state.assessedGrade = 'Grade A (Demo)';
    _setResultState('result');
    return;
  }

  // Real ML result rendering
  if (gradeEl && result.grade) {
    var cls = result.grade === 'A' ? 'cqa-grade-a' : result.grade === 'B' ? 'cqa-grade-b' : 'cqa-grade-c';
    gradeEl.innerHTML = '<span class="cqa-grade-badge ' + cls + '">Grade ' + _escapeHtml(result.grade) + '</span>';
    CQA.state.assessedGrade = 'Grade ' + result.grade;
  } else if (gradeEl) {
    gradeEl.innerHTML = '<span class="cqa-placeholder-dash">&mdash;</span>';
  }

  if (confEl && result.confidence !== null && result.confidence !== undefined) {
    var pct = Math.round(result.confidence * 100);
    confEl.innerHTML = '<span class="cqa-confidence-value">' + pct + '%</span>';
  } else if (confEl) {
    confEl.innerHTML = '<span class="cqa-placeholder-dash">&mdash;</span>';
  }

  if (indEl) {
    if (result.indicators && result.indicators.length > 0) {
      indEl.innerHTML = result.indicators.map(function(ind) {
        return '<li class="cqa-indicator-item"><span class="cqa-indicator-dot" aria-hidden="true"></span>' + _escapeHtml(ind) + '</li>';
      }).join('');
    } else {
      indEl.innerHTML = '<li class="cqa-placeholder-item">No quality indicators returned by the model.</li>';
    }
  }

  if (statusEl) {
    var modelName = (result.model && result.model.name) ? result.model.name : 'KisanLink Quality Model';
    statusEl.textContent = 'Analysed by: ' + modelName;
  }

  if (pipelineBtn) pipelineBtn.hidden = false;
  _setResultState('result');
}

function _showErrorState(message) {
  var msgEl = document.getElementById(CQA.ids.errorMessage);
  if (msgEl) msgEl.textContent = message;
  _setResultState('error');
}

function _setResultState(state) {
  var map = {
    idle:    document.getElementById(CQA.ids.idleState),
    loading: document.getElementById(CQA.ids.loadingState),
    result:  document.getElementById(CQA.ids.resultState),
    error:   document.getElementById(CQA.ids.errorState)
  };
  Object.keys(map).forEach(function(k) { if (map[k]) map[k].hidden = (k !== state); });
}

function _bindAnalyzeAgainButton() {
  var btn = document.getElementById(CQA.ids.analyzeAgainBtn);
  if (btn) btn.addEventListener('click', _resetResultArea);
}

/* ============================================================
   UTILITIES
   ============================================================ */
function _showEl(el) { if (el) el.hidden = false; }
function _hideEl(el) { if (el) el.hidden = true; }
function _escapeHtml(str) {
  var d = document.createElement('div');
  d.appendChild(document.createTextNode(str));
  return d.innerHTML;
}

/* ============================================================
   BOOT
   ============================================================ */
if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', initCropQualityAssessment);
} else {
  initCropQualityAssessment();
}

window.CQA = CQA;
window.analyzeCropQuality = analyzeCropQuality;
window.assessCropQuality = analyzeCropQuality;
window.applyQualityToDecisionPipeline = applyQualityToDecisionPipeline;
