# BioScan AI • Facial Biometrics, Profile Dossier & Kinship Synthesizer

An intelligent web application that scans a human face, extracts facial landmarks, geometry, and color metrics, synthesizes a rich psychological and demographic dossier, and AI-generates a coherent close family network with genetic inheritance markers, relationship dynamics, and visual pedigree trees.

---

## 🌟 Key Features

1. **Facial Biometric Scanner**:
   - **Live Webcam Mode**: Real-time biometric HUD with laser scanline animations, face oval reticle, crosshair alignment, and synthesized Web Audio sound FX.
   - **Photo Upload Mode**: Drag-and-drop or browse files (JPG, PNG, WEBP).
   - **Sample Faces Gallery**: 4 diverse test portraits for instant 1-click scanning without requiring a webcam.
   - **AI Telemetry Console**: Live streaming status logs during landmark acquisition and genetic hash generation.

2. **Personal Profile Dossier**:
   - Scanned face snapshot with 256-bit cryptographic **Biometric DNA Hash**.
   - Estimated age, gender presentation, cultural heritage, and bilateral cranial symmetry score.
   - Personality archetype & MBTI code (e.g., *The Architect - INTJ*, *The Luminary - ENFJ*).
   - Core attribute meters: *Cognitive Analytical*, *Emotional Resonance*, *Resilience*, *Creative Divergence*, and *Kinship Cohesion*.
   - Deep narrative biography reflecting facial demeanor, career calling, and ancestral traits.

3. **AI-Generated Close Family & Kinship**:
   - Coherent genealogy engine generating realistic relatives:
     - **Parents**: Mother & Father (plausible age gap, inherited eye/jawline genetics, career status).
     - **Siblings**: Brother, Sister, or Twin (shared craniofacial ratio, mirroring smile mechanics).
     - **Spouse / Life Partner**: Complementary phenotype and narrative of how they met.
     - **Children**: Son / Daughter (inherited features and aspirational pursuits).
     - **Grandparents / Extended Kin**: Lineage keepers and longevity markers.
   - **Procedural SVG Portraits**: Tailored vector avatars for each relative representing age, hairstyles, glasses, and skin pigmentation.
   - **Interactive Pedigree Tree**: Generational hierarchy view (Generations I, II, Target, Next Gen) with kinship degrees.
   - **Re-roll Member**: Instant re-synthesis of individual relatives.

4. **Dual AI Engine Architecture**:
   - **Built-in Biogenetic Neural Synthesizer (Default)**: Instant, zero-configuration offline engine extracting real pixel geometry, color histograms, and deterministic genealogical inheritance.
   - **Google Gemini Multimodal Vision (Optional)**: Connect your Gemini API Key in the UI settings for deep cloud multimodal LLM reasoning.

5. **Export & Sharing**:
   - **JSON Export**: Downloads complete structured dossier data.
   - **Print / PDF Dossier**: Formats an intelligence-grade physical report with `@media print` styling.

---

## 🚀 Quick Start

### 1. Install Dependencies
```bash
python -m pip install -r requirements.txt
```

### 2. Start the Server
```bash
python server.py
```

### 3. Open in Browser
Navigate to:
```
http://localhost:5050
```

---

## 📂 Project Structure

```
AntiGravityTest/
├── server.py              # HTTP server with REST APIs & static file routing
├── ai_engine.py           # Core biometric feature extractor & kinship synthesis engine
├── generate_samples.py    # Script that generates sample portraits
├── test_server.py         # Unit tests for image analysis & profile synthesis
├── test_api.py            # Integration test verifying all HTTP endpoints
├── requirements.txt       # Dependencies (pillow, requests)
├── README.md              # Documentation
└── static/
    ├── index.html         # Cybernetic biometric UI markup
    ├── styles.css         # Modern dark HUD styling & print stylesheet
    ├── app.js             # Client controller, Web Audio FX, webcam HUD, SVG avatar generator
    └── samples/           # Sample face images for instant testing
```

---

## 📡 REST API Endpoints

- `GET /` — Serves the Single Page Application.
- `GET /api/samples` — Returns metadata and thumbnails for sample test portraits.
- `POST /api/scan` — Accepts `{ image: base64, api_key: "...", engine: "auto"|"biogenetic"|"gemini" }` and returns the generated profile dossier and family network.
- `POST /api/regenerate-family-member` — Regenerates an individual family relative.
- `POST /api/test-key` — Verifies a Google Gemini API key.
