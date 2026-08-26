# Multi-Speaker TTS & Broadcast DSP Engineering

A technical reference for building broadcast-quality multi-speaker audio applications with dynamic candidate probing and digital signal processing.

---

## 1. Dynamic Model Probe & Cache

Preview models (e.g., `gemini-2.5-flash-preview-tts`) may change endpoints, become deprecated, or require specific billing tiers. To prevent runtime timeouts:

1. **Pre-flight Probing:** Perform a 1-character audio generation probe during initialization.
2. **Persistent Caching:** Store verified working model names in `~/.gemini/tts_model_cache.json`.
3. **Graceful Failover:** If probing fails or returns 404/400/429, immediately switch the host to Edge-TTS without retrying failing endpoints.

---

## 2. Universal Multilingual Voice Resolution

Microsoft Edge-TTS provides 322 neural voices across 75+ language families and 142 locales without API keys. The dynamic resolver queries available voices at runtime and maps distinct voices for the Host, Caller 1, and Caller 2:

```python
async def get_universal_edge_voice(lang_code: str, gender: str = "male", preferred_voice: str = None) -> str:
    clean_lang = lang_code.lower().split("-")[0].split("_")[0] if lang_code else "en"
    # Find matching voice in catalog
    for v in voices:
        if v["Locale"].lower().startswith(clean_lang) and v["Gender"].lower() == gender.lower():
            return v["ShortName"]
    return "en-GB-RyanNeural" if gender == "male" else "en-US-EmmaNeural"
```

---

## 3. Acoustic Engineering & DSP Suite

### Telephone Equalization Filter
To simulate remote callers on landlines or mobile phones:
```python
def apply_telephone_filter(segment: AudioSegment) -> AudioSegment:
    # 300Hz high-pass filter + 3400Hz low-pass filter
    filtered = segment.high_pass_filter(300).low_pass_filter(3400)
    # Generate -48dB line noise
    noise = generate_line_noise(len(filtered), gain_db=-48)
    return filtered.overlay(noise)
```

### Procedural Synthesizer (Jingles)
Procedurally generate harmonic intro and outro chimes using pure mathematical sine waves:
$$s(t) = \left( \sin(2\pi f t) + 0.4 \sin(4\pi f t) + 0.15 \sin(6\pi f t) \right) \cdot e^{-\alpha t}$$

---

## 4. Speaker Tag Stripping Invariant
Always sanitize incoming dialogue strings with regular expressions before TTS ingestion:
```python
clean_text = re.sub(r'^\s*(?:[A-Za-z0-9_\-\.\s]+|\*+[^*]+\*+|\[[^\]]+\])\s*:\s*', '', raw_turn)
```
