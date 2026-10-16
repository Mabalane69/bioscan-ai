/**
 * app.js - BioScan AI Client Application Controller
 * Handles webcam stream, biometric HUD overlays, Web Audio sound synthesis,
 * REST API communication, SVG avatar generation, and family pedigree rendering.
 */

// Application State
const state = {
  currentTab: 'webcam', // 'webcam' | 'upload' | 'samples'
  webcamStream: null,
  activeImageBase64: null,
  isScanning: false,
  soundEnabled: true,
  currentDossier: null,
  samples: [],
  selectedSampleId: null,
  geminiApiKey: localStorage.getItem('bioscan_gemini_key') || '',
  engineChoice: localStorage.getItem('bioscan_engine') || 'auto',
  activeView: 'cards' // 'cards' | 'tree'
};

// Web Audio API Synthesizer
let audioCtx = null;

function getAudioContext() {
  if (!audioCtx) {
    const AudioContextClass = window.AudioContext || window.webkitAudioContext;
    if (AudioContextClass) {
      audioCtx = new AudioContextClass();
    }
  }
  if (audioCtx && audioCtx.state === 'suspended') {
    audioCtx.resume();
  }
  return audioCtx;
}

const soundFX = {
  beep(freq = 880, duration = 0.08, type = 'sine') {
    if (!state.soundEnabled) return;
    try {
      const ctx = getAudioContext();
      if (!ctx) return;
      const osc = ctx.createOscillator();
      const gain = ctx.createGain();
      osc.type = type;
      osc.frequency.setValueAtTime(freq, ctx.currentTime);
      gain.gain.setValueAtTime(0.06, ctx.currentTime);
      gain.gain.exponentialRampToValueAtTime(0.0001, ctx.currentTime + duration);
      osc.connect(gain);
      gain.connect(ctx.destination);
      osc.start();
      osc.stop(ctx.currentTime + duration);
    } catch (e) {
      console.warn("Audio play error", e);
    }
  },

  scanSweep() {
    if (!state.soundEnabled) return;
    try {
      const ctx = getAudioContext();
      if (!ctx) return;
      const osc = ctx.createOscillator();
      const gain = ctx.createGain();
      osc.type = 'sawtooth';
      osc.frequency.setValueAtTime(220, ctx.currentTime);
      osc.frequency.exponentialRampToValueAtTime(880, ctx.currentTime + 0.35);
      osc.frequency.exponentialRampToValueAtTime(440, ctx.currentTime + 0.7);
      gain.gain.setValueAtTime(0.04, ctx.currentTime);
      gain.gain.exponentialRampToValueAtTime(0.0001, ctx.currentTime + 0.75);
      osc.connect(gain);
      gain.connect(ctx.destination);
      osc.start();
      osc.stop(ctx.currentTime + 0.75);
    } catch (e) {}
  },

  lockTarget() {
    soundFX.beep(1200, 0.06);
    setTimeout(() => soundFX.beep(1800, 0.09), 80);
  },

  chimeSuccess() {
    const notes = [523.25, 659.25, 783.99, 1046.50]; // C5, E5, G5, C6
    notes.forEach((freq, idx) => {
      setTimeout(() => soundFX.beep(freq, 0.18, 'triangle'), idx * 75);
    });
  }
};

// DOM Elements
const elements = {
  video: document.getElementById('webcam-video'),
  canvas: document.getElementById('canvas-overlay'),
  laser: document.getElementById('laser-scanline'),
  hudText: document.getElementById('scanner-hud-text'),
  scanBtn: document.getElementById('btn-scan-trigger'),
  scanBtnLabel: document.getElementById('scan-btn-label'),
  statePill: document.getElementById('scanner-state-pill'),
  engineStatusPill: document.getElementById('engine-status-pill'),
  activeEngineLabel: document.getElementById('active-engine-label'),
  telemetryLog: document.getElementById('telemetry-log'),
  fileInput: document.getElementById('file-input'),
  dropzone: document.getElementById('viewport-upload'),
  sampleGrid: document.getElementById('sample-grid'),
  emptyState: document.getElementById('empty-state'),
  dossierCard: document.getElementById('dossier-card'),
  familySection: document.getElementById('family-section'),
  familyCardsGrid: document.getElementById('family-cards-grid'),
  familyTreeContainer: document.getElementById('family-tree-container'),
  treeCanvasWrapper: document.getElementById('tree-canvas-wrapper'),
  audioToggleBtn: document.getElementById('audio-toggle-btn'),
  audioIconOn: document.getElementById('audio-icon-on'),
  audioIconOff: document.getElementById('audio-icon-off'),
  settingsModal: document.getElementById('settings-modal'),
  settingsOpenBtn: document.getElementById('settings-open-btn'),
  settingsCloseBtn: document.getElementById('settings-close-btn'),
  engineSelect: document.getElementById('engine-select'),
  geminiKeyInput: document.getElementById('gemini-key-input'),
  btnTestKey: document.getElementById('btn-test-key'),
  btnSaveSettings: document.getElementById('btn-save-settings'),
  settingsFeedback: document.getElementById('settings-feedback'),
  viewCardsBtn: document.getElementById('view-cards-btn'),
  viewTreeBtn: document.getElementById('view-tree-btn'),
  btnExportJson: document.getElementById('btn-export-json'),
  btnPrintDossier: document.getElementById('btn-print-dossier')
};

// Logging Utility
function logTelemetry(msg, type = 'normal') {
  const line = document.createElement('div');
  line.className = `log-line ${type}`;
  line.textContent = `> ${msg}`;
  elements.telemetryLog.appendChild(line);
  elements.telemetryLog.scrollTop = elements.telemetryLog.scrollHeight;
}

// Initialize Application
document.addEventListener('DOMContentLoaded', () => {
  setupTabs();
  setupSettings();
  setupAudio();
  setupViewToggle();
  setupExportActions();
  loadSamplePortraits();
  startWebcam();
  initOverlayCanvas();
});

// Tab Navigation
function setupTabs() {
  const tabs = document.querySelectorAll('.tab-btn');
  tabs.forEach(tab => {
    tab.addEventListener('click', () => {
      soundFX.beep(600, 0.04);
      tabs.forEach(t => t.classList.remove('active'));
      tab.classList.add('active');
      const tabId = tab.getAttribute('data-tab');
      state.currentTab = tabId;

      document.getElementById('viewport-webcam').style.display = tabId === 'webcam' ? 'flex' : 'none';
      document.getElementById('viewport-upload').style.display = tabId === 'upload' ? 'flex' : 'none';
      document.getElementById('viewport-samples').style.display = tabId === 'samples' ? 'block' : 'none';

      if (tabId === 'webcam') {
        startWebcam();
        elements.hudText.textContent = "ALIGN FACE WITHIN RETICLE";
      } else if (tabId === 'upload') {
        stopWebcam();
        setupDropzone();
      } else if (tabId === 'samples') {
        stopWebcam();
        if (state.selectedSampleId) {
          elements.scanBtn.disabled = false;
        }
      }
    });
  });
}

// Webcam Stream Management
async function startWebcam() {
  if (state.webcamStream) return;
  try {
    const stream = await navigator.mediaDevices.getUserMedia({
      video: { width: { ideal: 640 }, height: { ideal: 480 }, facingMode: 'user' },
      audio: false
    });
    state.webcamStream = stream;
    elements.video.srcObject = stream;
    elements.video.play();
    logTelemetry("Optic sensor feed online (640x480). Ready for scan.", "success");
    elements.statePill.textContent = "ONLINE";
  } catch (err) {
    console.warn("Webcam access unavailable or denied:", err);
    logTelemetry("Webcam feed unavailable. You can use 'Upload' or 'Sample Faces'.", "error");
    elements.hudText.textContent = "WEBCAM OFFLINE - USE UPLOAD OR SAMPLES";
    elements.statePill.textContent = "STANDBY";
  }
}

function stopWebcam() {
  if (state.webcamStream) {
    state.webcamStream.getTracks().forEach(track => track.stop());
    state.webcamStream = null;
    elements.video.srcObject = null;
  }
}

// Overlay Canvas Animations (HUD Bounding Box, Landmarks)
let animationFrameId = null;
let hudAngle = 0;

function initOverlayCanvas() {
  const canvas = elements.canvas;
  const ctx = canvas.getContext('2d');

  function resizeCanvas() {
    canvas.width = canvas.parentElement.clientWidth;
    canvas.height = canvas.parentElement.clientHeight;
  }
  resizeCanvas();
  window.addEventListener('resize', resizeCanvas);

  function drawHUD() {
    if (state.currentTab === 'webcam' && elements.video.readyState >= 2) {
      ctx.clearRect(0, 0, canvas.width, canvas.height);
      const cx = canvas.width / 2;
      const cy = canvas.height / 2;
      const rx = canvas.width * 0.26;
      const ry = canvas.height * 0.35;

      hudAngle += 0.02;

      // Outer Face Oval Guide
      ctx.save();
      ctx.beginPath();
      ctx.ellipse(cx, cy, rx, ry, 0, 0, Math.PI * 2);
      ctx.strokeStyle = state.isScanning ? 'rgba(0, 242, 254, 0.9)' : 'rgba(0, 242, 254, 0.35)';
      ctx.lineWidth = 1.5;
      ctx.setLineDash([8, 6]);
      ctx.lineDashOffset = -hudAngle * 10;
      ctx.stroke();
      ctx.restore();

      // Eye Anchors
      const eyeOffset = rx * 0.42;
      const eyeY = cy - ry * 0.18;
      drawCrosshair(ctx, cx - eyeOffset, eyeY, 8);
      drawCrosshair(ctx, cx + eyeOffset, eyeY, 8);

      // Mouth Anchor
      drawCrosshair(ctx, cx, cy + ry * 0.45, 10);

      // Facial Mesh Points
      const meshPoints = [
        [cx - rx * 0.8, cy], [cx + rx * 0.8, cy],
        [cx - rx * 0.5, cy - ry * 0.5], [cx + rx * 0.5, cy - ry * 0.5],
        [cx - rx * 0.4, cy + ry * 0.75], [cx + rx * 0.4, cy + ry * 0.75],
        [cx, cy + ry * 0.9]
      ];
      ctx.fillStyle = state.isScanning ? '#00f2fe' : 'rgba(0, 242, 254, 0.4)';
      meshPoints.forEach(([x, y]) => {
        ctx.beginPath();
        ctx.arc(x, y, 2.5, 0, Math.PI * 2);
        ctx.fill();
      });
    }
    animationFrameId = requestAnimationFrame(drawHUD);
  }
  drawHUD();
}

function drawCrosshair(ctx, x, y, size) {
  ctx.save();
  ctx.strokeStyle = 'rgba(0, 242, 254, 0.5)';
  ctx.lineWidth = 1;
  ctx.beginPath();
  ctx.moveTo(x - size, y);
  ctx.lineTo(x + size, y);
  ctx.moveTo(x, y - size);
  ctx.lineTo(x, y + size);
  ctx.stroke();
  ctx.restore();
}

// Dropzone Setup
function setupDropzone() {
  const dropzone = elements.dropzone;
  const fileInput = elements.fileInput;

  dropzone.onclick = () => fileInput.click();

  dropzone.ondragover = (e) => {
    e.preventDefault();
    dropzone.classList.add('drag-over');
  };

  dropzone.ondragleave = () => {
    dropzone.classList.remove('drag-over');
  };

  dropzone.ondrop = (e) => {
    e.preventDefault();
    dropzone.classList.remove('drag-over');
    if (e.dataTransfer.files.length) {
      handleImageFile(e.dataTransfer.files[0]);
    }
  };

  fileInput.onchange = () => {
    if (fileInput.files.length) {
      handleImageFile(fileInput.files[0]);
    }
  };
}

function handleImageFile(file) {
  if (!file.type.startsWith('image/')) {
    logTelemetry("Selected file is not an image.", "error");
    return;
  }
  const reader = new FileReader();
  reader.onload = (e) => {
    state.activeImageBase64 = e.target.result;
    renderUploadedPreview(e.target.result, file.name);
    soundFX.lockTarget();
    logTelemetry(`Imported image: ${file.name} (${Math.round(file.size / 1024)} KB)`, "success");
    elements.scanBtn.disabled = false;
  };
  reader.readAsDataURL(file);
}

function renderUploadedPreview(dataUrl, name) {
  elements.dropzone.innerHTML = `
    <div style="position:relative; width:100%; height:100%; overflow:hidden; border-radius:10px;">
      <img src="${dataUrl}" style="width:100%; height:100%; object-fit:cover;" alt="Uploaded Face Preview">
      <div style="position:absolute; bottom:8px; left:8px; background:rgba(0,0,0,0.7); padding:4px 8px; border-radius:4px; font-size:0.75rem; color:#00f2fe;">
        ✓ ${name} ready
      </div>
    </div>
  `;
}

// Sample Faces Gallery
async function loadSamplePortraits() {
  try {
    const res = await fetch('/api/samples');
    const data = await res.json();
    if (data.status === 'success') {
      state.samples = data.samples;
      renderSampleGrid(data.samples);
    }
  } catch (err) {
    console.warn("Could not load sample portraits", err);
  }
}

function renderSampleGrid(samples) {
  elements.sampleGrid.innerHTML = samples.map(s => `
    <div class="sample-card" data-id="${s.id}" data-url="${s.thumbnail}">
      <img src="${s.thumbnail}" class="sample-thumb" alt="${s.name}">
      <div class="sample-info">
        <h4>${s.name}</h4>
        <span>${s.description}</span>
      </div>
    </div>
  `).join('');

  document.querySelectorAll('.sample-card').forEach(card => {
    card.addEventListener('click', async () => {
      soundFX.beep(750, 0.05);
      document.querySelectorAll('.sample-card').forEach(c => c.classList.remove('active'));
      card.classList.add('active');
      const url = card.getAttribute('data-url');
      state.selectedSampleId = card.getAttribute('data-id');
      
      // Fetch sample image as base64
      try {
        const resp = await fetch(url);
        const blob = await resp.blob();
        const reader = new FileReader();
        reader.onload = (e) => {
          state.activeImageBase64 = e.target.result;
          soundFX.lockTarget();
          logTelemetry(`Selected sample profile: ${card.querySelector('h4').textContent}`, "active");
          elements.scanBtn.disabled = false;
        };
        reader.readAsDataURL(blob);
      } catch (e) {
        logTelemetry("Failed to load sample image data", "error");
      }
    });
  });
}

// Scan Trigger Action
elements.scanBtn.addEventListener('click', () => {
  executeScan();
});

async function executeScan() {
  if (state.isScanning) return;
  state.isScanning = true;

  soundFX.lockTarget();
  elements.laser.classList.add('scanning');
  elements.scanBtn.disabled = true;
  elements.scanBtnLabel.textContent = "ACQUIRING PHENOTYPE...";
  elements.statePill.textContent = "SCANNING";

  let imagePayload = state.activeImageBase64;

  // If in webcam mode, capture snapshot from video feed
  if (state.currentTab === 'webcam') {
    if (!elements.video.videoWidth) {
      logTelemetry("Webcam feed not ready. Please wait or select a sample.", "error");
      finishScan(false);
      return;
    }
    const snapCanvas = document.createElement('canvas');
    snapCanvas.width = elements.video.videoWidth || 640;
    snapCanvas.height = elements.video.videoHeight || 480;
    const sCtx = snapCanvas.getContext('2d');
    sCtx.drawImage(elements.video, 0, 0, snapCanvas.width, snapCanvas.height);
    imagePayload = snapCanvas.toDataURL('image/jpeg', 0.88);
  }

  if (!imagePayload) {
    logTelemetry("No image available to scan. Please choose an image or use webcam.", "error");
    finishScan(false);
    return;
  }

  // Visual & Sound Feedback
  soundFX.scanSweep();
  logTelemetry("Initiating photon landmark analysis...", "active");

  setTimeout(() => logTelemetry("Measuring craniofacial ratios & pigmentation indices...", "normal"), 300);
  setTimeout(() => logTelemetry("Computing 256-bit cryptographic biogenetic hash...", "normal"), 650);
  setTimeout(() => logTelemetry(`Engaging synthesis engine: ${state.engineChoice.toUpperCase()}...`, "active"), 1000);

  try {
    const response = await fetch('/api/scan', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        image: imagePayload,
        api_key: state.geminiApiKey,
        engine: state.engineChoice
      })
    });

    const resData = await response.json();

    if (resData.status === 'success' && resData.data) {
      state.currentDossier = resData.data;
      renderDossier(resData.data, imagePayload);
      renderFamily(resData.data.family, resData.data.profile);
      renderPedigreeTree(resData.data.family, resData.data.profile);

      elements.emptyState.style.display = 'none';
      elements.dossierCard.style.display = 'flex';
      elements.familySection.style.display = 'flex';

      soundFX.chimeSuccess();
      logTelemetry(`Dossier synthesized successfully via ${resData.data.source}`, "success");
      elements.activeEngineLabel.textContent = resData.data.source.includes("Gemini") ? "Google Gemini Vision" : "Biogenetic Synthesizer";
      finishScan(true);
    } else {
      throw new Error(resData.error || "Analysis failed");
    }
  } catch (err) {
    console.error("Scan error:", err);
    logTelemetry(`Scan error: ${err.message}`, "error");
    finishScan(false);
  }
}

function finishScan(success) {
  state.isScanning = false;
  elements.laser.classList.remove('scanning');
  elements.scanBtn.disabled = false;
  elements.scanBtnLabel.textContent = "INITIATE BIOMETRIC SCAN";
  elements.statePill.textContent = success ? "ANALYZED" : "READY";
}

// Render Dossier Card
function renderDossier(data, capturedPhoto) {
  const p = data.profile;
  const m = data.metrics || {};

  document.getElementById('dossier-captured-img').src = capturedPhoto;
  document.getElementById('dossier-dna-hash').textContent = `DNA: ${p.biometric_dna_hash || m.dna_hash || 'BIO-4921-9921'}`;
  document.getElementById('dossier-name').textContent = p.full_name;
  document.getElementById('dossier-job').textContent = p.occupation;
  
  document.getElementById('dossier-archetype-badge').textContent = `${p.personality_archetype} (${p.mbti_code || 'ARCH'})`;
  document.getElementById('dossier-gender-badge').textContent = p.gender;
  document.getElementById('dossier-heritage-badge').textContent = p.origin_heritage || 'Cosmopolitan';

  document.getElementById('dossier-age').textContent = `${p.estimated_age} Years`;
  document.getElementById('dossier-symmetry').textContent = `${p.symmetry_index || m.symmetry_index || 96.2}%`;
  document.getElementById('dossier-eyes').textContent = p.eye_color;
  document.getElementById('dossier-hair').textContent = p.hair_color;
  document.getElementById('dossier-jaw').textContent = p.jawline_type || 'Defined';
  document.getElementById('dossier-expression').textContent = p.expression || 'Composed';

  document.getElementById('dossier-bio-text').textContent = p.bio;

  // Render Attribute Bars
  const attrGrid = document.getElementById('dossier-attributes-grid');
  attrGrid.innerHTML = '';
  const attrs = p.attributes || {
    "Cognitive Analytical": 94,
    "Emotional Resonance": 88,
    "Resilience & Fortitude": 92,
    "Creative Divergence": 85,
    "Kinship Cohesion": 96
  };

  Object.entries(attrs).forEach(([name, val]) => {
    const item = document.createElement('div');
    item.className = 'attr-item';
    item.innerHTML = `
      <div class="attr-info">
        <span class="attr-name">${name}</span>
        <span class="attr-val">${val}%</span>
      </div>
      <div class="progress-track">
        <div class="progress-fill" style="width: 0%;"></div>
      </div>
    `;
    attrGrid.appendChild(item);
    setTimeout(() => {
      item.querySelector('.progress-fill').style.width = `${val}%`;
    }, 100);
  });
}

// Generate Procedural SVG Avatar for Family Members
function generateFamilyAvatarSvg(avatar, id) {
  const gender = avatar.gender || 'neutral';
  const ageTier = avatar.age_tier || 'mature'; // 'youth' | 'young_adult' | 'mature' | 'elder'
  const skin = avatar.skin_tone || '#d19c74';
  const hairColor = avatar.hair_color || '#332211';
  const hasGlasses = avatar.glasses || false;

  // Determine hair styling
  let hairSvg = '';
  if (gender === 'female') {
    if (ageTier === 'elder') {
      hairSvg = `
        <ellipse cx="50" cy="40" rx="36" ry="32" fill="#E2E8F0" />
        <circle cx="50" cy="18" r="14" fill="#E2E8F0" />
      `;
    } else if (ageTier === 'youth') {
      hairSvg = `
        <ellipse cx="50" cy="46" rx="36" ry="34" fill="${hairColor}" />
        <circle cx="22" cy="50" r="12" fill="${hairColor}" />
        <circle cx="78" cy="50" r="12" fill="${hairColor}" />
      `;
    } else {
      hairSvg = `
        <ellipse cx="50" cy="42" rx="35" ry="34" fill="${hairColor}" />
        <path d="M 18 50 Q 14 78 26 88 Q 32 75 32 50 Z" fill="${hairColor}" />
        <path d="M 82 50 Q 86 78 74 88 Q 68 75 68 50 Z" fill="${hairColor}" />
      `;
    }
  } else {
    // Male
    if (ageTier === 'elder') {
      hairSvg = `
        <path d="M 22 45 Q 50 25 78 45 Q 82 60 76 65 Q 68 36 28 45 Z" fill="#CBD5E1" />
      `;
    } else if (ageTier === 'youth') {
      hairSvg = `
        <path d="M 20 45 Q 50 20 80 45 Q 75 25 50 24 Q 25 25 20 45 Z" fill="${hairColor}" />
        <ellipse cx="50" cy="35" rx="30" ry="16" fill="${hairColor}" />
      `;
    } else {
      hairSvg = `
        <path d="M 22 42 Q 50 22 78 42 Q 80 34 50 30 Q 20 34 22 42 Z" fill="${hairColor}" />
        <ellipse cx="50" cy="38" rx="29" ry="15" fill="${hairColor}" />
      `;
    }
  }

  // Age creases
  let wrinklesSvg = '';
  if (ageTier === 'elder') {
    wrinklesSvg = `
      <path d="M 38 35 Q 50 33 62 35" stroke="rgba(0,0,0,0.25)" stroke-width="1" fill="none" />
      <path d="M 36 38 Q 50 36 64 38" stroke="rgba(0,0,0,0.2)" stroke-width="1" fill="none" />
      <path d="M 30 52 L 26 50 M 70 52 L 74 50" stroke="rgba(0,0,0,0.2)" stroke-width="1" />
    `;
  } else if (ageTier === 'mature') {
    wrinklesSvg = `
      <path d="M 40 36 Q 50 35 60 36" stroke="rgba(0,0,0,0.18)" stroke-width="1" fill="none" />
    `;
  }

  // Glasses
  let glassesSvg = '';
  if (hasGlasses) {
    glassesSvg = `
      <circle cx="38" cy="50" r="9" stroke="#00f2fe" stroke-width="2" fill="rgba(0,242,254,0.15)" />
      <circle cx="62" cy="50" r="9" stroke="#00f2fe" stroke-width="2" fill="rgba(0,242,254,0.15)" />
      <line x1="47" y1="50" x2="53" y2="50" stroke="#00f2fe" stroke-width="2" />
    `;
  }

  return `
    <svg viewBox="0 0 100 100" xmlns="http://www.w3.org/2000/svg">
      <!-- Background Circle -->
      <circle cx="50" cy="50" r="48" fill="#0A0E1A" />
      
      <!-- Back Hair -->
      ${hairSvg}

      <!-- Neck & Torso -->
      <path d="M 42 66 L 42 80 L 58 80 L 58 66 Z" fill="${skin}" filter="brightness(0.9)" />
      <path d="M 20 100 C 20 80 80 80 80 100 Z" fill="#1E293B" />
      
      <!-- Head / Face -->
      <ellipse cx="50" cy="52" rx="24" ry="28" fill="${skin}" />

      <!-- Eyes -->
      <ellipse cx="38" cy="50" rx="3.5" ry="3.5" fill="#0F172A" />
      <ellipse cx="62" cy="50" rx="3.5" ry="3.5" fill="#0F172A" />
      <circle cx="39" cy="49" r="1" fill="#FFFFFF" />
      <circle cx="63" cy="49" r="1" fill="#FFFFFF" />

      <!-- Eyebrows -->
      <path d="M 33 44 Q 38 42 43 44" stroke="#1E293B" stroke-width="1.8" fill="none" />
      <path d="M 57 44 Q 62 42 67 44" stroke="#1E293B" stroke-width="1.8" fill="none" />

      <!-- Nose -->
      <path d="M 50 49 L 48 57 L 52 57" stroke="rgba(0,0,0,0.3)" stroke-width="1.2" fill="none" />

      <!-- Mouth -->
      <path d="M 44 65 Q 50 68 56 65" stroke="#991B1B" stroke-width="1.8" fill="none" />

      <!-- Age Wrinkles -->
      ${wrinklesSvg}

      <!-- Glasses -->
      ${glassesSvg}
    </svg>
  `;
}

// Render Family Cards
function renderFamily(familyMembers, personProfile) {
  const container = elements.familyCardsGrid;
  container.innerHTML = '';

  familyMembers.forEach(m => {
    const card = document.createElement('div');
    card.className = 'family-card';
    card.id = `card-${m.id}`;

    const avatarSvg = generateFamilyAvatarSvg(m.avatar || {}, m.id);

    card.innerHTML = `
      <div class="family-card-header">
        <div class="avatar-circle">
          ${avatarSvg}
        </div>
        <div class="family-meta">
          <span class="relation-badge">${m.relation}</span>
          <h4 class="family-name" title="${m.full_name}">${m.full_name}</h4>
          <span class="family-age-job">${m.age} yrs • ${m.occupation}</span>
        </div>
      </div>

      <div class="family-body">
        <div class="shared-genetics-box">
          <strong>Inherited Craniofacial &amp; Genetic Markers</strong>
          ${m.shared_genetics}
        </div>
        <div class="relationship-dynamic-box">
          "${m.relationship_dynamic}"
        </div>
      </div>

      <div class="family-card-footer">
        <span class="kin-degree">${m.degree || '1st Degree Kin'}</span>
        <button class="btn-regen-member" data-id="${m.id}" title="Synthesize alternative relative archetype">
          <svg viewBox="0 0 24 24" width="12" height="12" fill="none" stroke="currentColor" stroke-width="2">
            <polyline points="23 4 23 10 17 10"></polyline>
            <polyline points="1 20 1 14 7 14"></polyline>
            <path d="M3.51 9a9 9 0 0 1 14.85-3.36L23 10M1 14l4.64 4.36A9 9 0 0 0 20.49 15"></path>
          </svg>
          Re-roll
        </button>
      </div>
    `;

    // Re-roll button listener
    card.querySelector('.btn-regen-member').addEventListener('click', async () => {
      soundFX.beep(950, 0.05);
      logTelemetry(`Re-synthesizing kin profile for ${m.relation}...`, "active");
      try {
        const res = await fetch('/api/regenerate-family-member', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            id: m.id,
            profile: personProfile,
            metrics: state.currentDossier.metrics || {}
          })
        });
        const d = await res.json();
        if (d.status === 'success' && d.member) {
          // Replace in local state
          const idx = state.currentDossier.family.findIndex(f => f.id === m.id);
          if (idx !== -1) {
            state.currentDossier.family[idx] = d.member;
          }
          renderFamily(state.currentDossier.family, personProfile);
          renderPedigreeTree(state.currentDossier.family, personProfile);
          soundFX.chimeSuccess();
          logTelemetry(`Kin profile updated: ${d.member.full_name} (${d.member.relation})`, "success");
        }
      } catch (err) {
        logTelemetry("Failed to re-roll family member", "error");
      }
    });

    container.appendChild(card);
  });
}

// Render Interactive Pedigree Tree
function renderPedigreeTree(family, person) {
  const wrapper = elements.treeCanvasWrapper;
  wrapper.innerHTML = '';

  const grandparents = family.filter(f => f.kinship_category === 'grandparent');
  const parents = family.filter(f => f.kinship_category === 'parent');
  const siblings = family.filter(f => f.kinship_category === 'sibling');
  const partner = family.filter(f => f.kinship_category === 'partner');
  const children = family.filter(f => f.kinship_category === 'child');

  // Tier 1: Grandparents
  if (grandparents.length) {
    const tier = document.createElement('div');
    tier.className = 'tree-tier';
    tier.innerHTML = `<span class="tree-tier-label">Generation I</span>` + grandparents.map(g => createTreeNodeHtml(g)).join('');
    wrapper.appendChild(tier);
  }

  // Tier 2: Parents
  if (parents.length) {
    const tier = document.createElement('div');
    tier.className = 'tree-tier';
    tier.innerHTML = `<span class="tree-tier-label">Generation II</span>` + parents.map(p => createTreeNodeHtml(p)).join('');
    wrapper.appendChild(tier);
  }

  // Tier 3: Person + Partner + Siblings
  const tier3 = document.createElement('div');
  tier3.className = 'tree-tier';
  let tier3Html = `<span class="tree-tier-label">Target Generation</span>`;

  // Scanned Person Node
  tier3Html += `
    <div class="tree-node person-node">
      <div class="tree-node-avatar">
        <img src="${document.getElementById('dossier-captured-img').src}" style="width:100%; height:100%; object-fit:cover;" />
      </div>
      <div class="tree-node-info">
        <h5>${person.full_name} (Target)</h5>
        <span>${person.estimated_age} yrs • ${person.personality_archetype}</span>
      </div>
    </div>
  `;

  if (partner.length) {
    tier3Html += partner.map(p => createTreeNodeHtml(p)).join('');
  }
  if (siblings.length) {
    tier3Html += siblings.map(s => createTreeNodeHtml(s)).join('');
  }
  tier3.innerHTML = tier3Html;
  wrapper.appendChild(tier3);

  // Tier 4: Children
  if (children.length) {
    const tier = document.createElement('div');
    tier.className = 'tree-tier';
    tier.innerHTML = `<span class="tree-tier-label">Next Gen</span>` + children.map(c => createTreeNodeHtml(c)).join('');
    wrapper.appendChild(tier);
  }
}

function createTreeNodeHtml(member) {
  const svg = generateFamilyAvatarSvg(member.avatar || {}, member.id);
  return `
    <div class="tree-node" title="${member.relation} • ${member.degree || ''}">
      <div class="tree-node-avatar">
        ${svg}
      </div>
      <div class="tree-node-info">
        <h5>${member.full_name}</h5>
        <span>${member.relation} (${member.age} yrs)</span>
      </div>
    </div>
  `;
}

// View Toggle (Cards vs Pedigree Tree)
function setupViewToggle() {
  elements.viewCardsBtn.addEventListener('click', () => {
    soundFX.beep(650, 0.04);
    elements.viewCardsBtn.classList.add('active');
    elements.viewTreeBtn.classList.remove('active');
    elements.familyCardsGrid.style.display = 'grid';
    elements.familyTreeContainer.classList.remove('active');
    state.activeView = 'cards';
  });

  elements.viewTreeBtn.addEventListener('click', () => {
    soundFX.beep(650, 0.04);
    elements.viewTreeBtn.classList.add('active');
    elements.viewCardsBtn.classList.remove('active');
    elements.familyCardsGrid.style.display = 'none';
    elements.familyTreeContainer.classList.add('active');
    state.activeView = 'tree';
  });
}

// Audio Toggle
function setupAudio() {
  elements.audioToggleBtn.addEventListener('click', () => {
    state.soundEnabled = !state.soundEnabled;
    elements.audioIconOn.style.display = state.soundEnabled ? 'block' : 'none';
    elements.audioIconOff.style.display = state.soundEnabled ? 'none' : 'block';
    if (state.soundEnabled) soundFX.beep(880, 0.08);
  });
}

// Settings Modal & Key Validation
function setupSettings() {
  elements.engineSelect.value = state.engineChoice;
  elements.geminiKeyInput.value = state.geminiApiKey;

  elements.settingsOpenBtn.addEventListener('click', () => {
    soundFX.beep(700, 0.04);
    elements.settingsModal.classList.add('open');
    elements.settingsFeedback.textContent = '';
  });

  elements.settingsCloseBtn.addEventListener('click', () => {
    soundFX.beep(500, 0.04);
    elements.settingsModal.classList.remove('open');
  });

  elements.settingsModal.addEventListener('click', (e) => {
    if (e.target === elements.settingsModal) {
      elements.settingsModal.classList.remove('open');
    }
  });

  elements.btnTestKey.addEventListener('click', async () => {
    const key = elements.geminiKeyInput.value.trim();
    if (!key) {
      elements.settingsFeedback.innerHTML = `<span style="color:#f43f5e;">Please enter an API key first</span>`;
      return;
    }
    elements.settingsFeedback.innerHTML = `<span style="color:#00f2fe;">Validating key with Gemini endpoint...</span>`;
    try {
      const res = await fetch('/api/test-key', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ api_key: key })
      });
      const d = await res.json();
      if (d.valid) {
        soundFX.chimeSuccess();
        elements.settingsFeedback.innerHTML = `<span style="color:#10b981;">✓ ${d.message}</span>`;
      } else {
        elements.settingsFeedback.innerHTML = `<span style="color:#f43f5e;">✕ ${d.message}</span>`;
      }
    } catch (e) {
      elements.settingsFeedback.innerHTML = `<span style="color:#f43f5e;">Network check failed</span>`;
    }
  });

  elements.btnSaveSettings.addEventListener('click', () => {
    soundFX.beep(1000, 0.05);
    state.geminiApiKey = elements.geminiKeyInput.value.trim();
    state.engineChoice = elements.engineSelect.value;
    localStorage.setItem('bioscan_gemini_key', state.geminiApiKey);
    localStorage.setItem('bioscan_engine', state.engineChoice);

    elements.activeEngineLabel.textContent = state.engineChoice === 'gemini' 
      ? "Google Gemini Vision" 
      : (state.engineChoice === 'biogenetic' ? "Biogenetic Neural Synthesizer" : "Auto (Gemini / Biogenetic)");

    elements.settingsModal.classList.remove('open');
    logTelemetry("Configuration updated and saved.", "success");
  });
}

// Export Actions
function setupExportActions() {
  // Export JSON
  elements.btnExportJson.addEventListener('click', () => {
    if (!state.currentDossier) return;
    soundFX.beep(800, 0.05);
    const dataStr = "data:text/json;charset=utf-8," + encodeURIComponent(JSON.stringify(state.currentDossier, null, 2));
    const dlAnchor = document.createElement('a');
    dlAnchor.setAttribute("href", dataStr);
    const safeName = (state.currentDossier.profile.full_name || 'profile').toLowerCase().replace(/\s+/g, '_');
    dlAnchor.setAttribute("download", `bioscan_dossier_${safeName}.json`);
    document.body.appendChild(dlAnchor);
    dlAnchor.click();
    dlAnchor.remove();
    logTelemetry("Dossier JSON exported successfully.", "success");
  });

  // Print / PDF
  elements.btnPrintDossier.addEventListener('click', () => {
    soundFX.beep(800, 0.05);
    window.print();
  });
}
