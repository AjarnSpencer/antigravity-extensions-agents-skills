---
name: multilingual-tts-dsp
description: >-
  Advanced multi-speaker neural text-to-speech synthesis and broadcast digital signal processing (DSP) suite.
  Provides dynamic runtime candidate probing, persistent model caching, 322-voice multilingual resolution across 142 locales,
  telephone bandpass equalization (300Hz-3400Hz), procedural synth jingle generation, and analogue room tone mixing.
---

# Multi-Speaker Multilingual TTS & Broadcast Audio DSP Skill

This skill guides agents and developers through constructing resilient, high-fidelity audio broadcasts with multi-speaker dialogues, real-time fallbacks, and professional radio studio sound design.

---

## 1. Multi-Tiered Neural TTS Architecture

To guarantee zero dropped turns and sub-second generation even when preview endpoints are unavailable or quota-limited:

1. **Tier 1 (Google GenAI Audio Modality):**
   - Probe candidate endpoints: `gemini-2.5-flash-preview-tts`, `gemini-3.1-flash-tts-preview`, `gemini-2.5-pro-preview-tts`, `gemini-2.0-flash-exp`.
   - Validate active audio generation capability via a lightweight test turn.
   - Cache active model names in `~/.gemini/tts_model_cache.json`.
2. **Tier 2 (Zero-API-Key Microsoft Edge-TTS CDN):**
   - Query dynamic voice matrix with 322 voices across 75+ languages and 142 locales.
   - Fallback executes automatically without requiring user credentials.

```python
async def get_universal_edge_voice(lang_code: str, gender: str = "male", preferred_voice: str = None) -> str:
    """Dynamically resolves native neural voice across 75+ language families."""
    clean_lang = lang_code.lower().split("-")[0].split("_")[0] if lang_code else "en"
    # Query Edge-TTS voices list and match by locale and gender
    ...
```

---

## 2. Broadcast Digital Signal Processing (DSP) Pipeline

### A. Caller Telephony Bandpass Filter
Caller audio is equalized to replicate standard POTS / landline / cellular acoustics:
- **High-Pass Cutoff:** 300 Hz (attenuates low-end proximity effect).
- **Low-Pass Cutoff:** 3400 Hz (attenuates high-frequency air).
- **Analog Line Noise:** Subtle white noise layer at `-48 dBFS`.

### B. Procedural Harmonic Intro/Outro Jingles
Generate synthesized musical chords directly in Python without external audio assets:
- **Scale:** E-minor pentatonic (E3: 164.81Hz, G3: 196.00Hz, A3: 220.00Hz, B3: 246.94Hz, E4: 329.63Hz).
- **Harmonics:** Fundamental frequency + 2nd harmonic (0.4 amp) + 3rd harmonic (0.15 amp).
- **Envelope:** Attack (40ms), Decay (100ms), Sustain (0.7), Exponential Release (2500ms).

### C. Analogue Broadcast Room Tone Bed
Eliminate digital silence between dialogue turns:
- Continuous low-amplitude shaped ambient noise (`-50 dBFS`).
- Overlayed across the entire timeline with smooth 1500ms crossfades.

---

## 3. Strict Speaker Sanitization Invariant

Before sending text to any TTS engine, always run regex sanitization to strip speaker tags (e.g., `Ajarn Spencer:`, `[Caller 1]:`, `Host:`) so engines never read metadata out loud:

```python
def strip_speaker_prefix(text: str) -> str:
    text = re.sub(r'^\s*(?:[A-Za-z0-9_\-\.\s]+|\*+[^*]+\*+|\[[^\]]+\])\s*:\s*', '', text)
    text = re.sub(r'^\s*\[(Caller\s*\d+|Host|Co-host|Speaker\s*\d+)\]\s*', '', text, flags=re.IGNORECASE)
    return text.strip()
```
