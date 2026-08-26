# Radio Show Extension for Antigravity CLI & Gemini CLI

An autonomous, multi-speaker talk radio and podcast generator for **Antigravity CLI** and **Gemini CLI**. Transform arbitrary text, philosophical treatises, or discussion topics into a live late-night radio caller-in broadcast complete with host monologues, live caller debates, telephone audio DSP, procedural synth jingles, and analogue studio room tone.

---

## Highlights & Features

- 🎙 **Autonomous Scriptwriting:** Directs a 3-act live radio show format with evocative show title, host opening monologue, caller 1 (technical/enthusiastic caller), caller 2 (counter-perspective/skeptical caller), host syntheses, and sign-off.
- 🎛 **Broadcast Audio DSP Suite:**
  - **Telephone Bandpass Equalizer:** Caller audio is dynamically processed through a 300Hz–3400Hz bandpass filter and layered with subtle analog line noise (`-48dB`).
  - **Procedural Intro/Outro Jingles:** Harmonically synthesized E-minor pentatonic chords with envelope shaping.
  - **Dual-Tone Call Connect Beeps:** 440Hz + 880Hz connection tones announcing incoming callers.
  - **Analogue Room Tone Bed:** Continuous warm broadcast studio room tone (`-50dB`) with smooth crossfading.
- 🌐 **Universal Multilingual Support:** Dynamic language resolution across 75+ language families (`en`, `es`, `th`, `fr`, `de`, `ja`, `zh`, `hi`, `ar`, `pt`, `it`, `ru`, etc.).
- 🛡 **Multi-Tiered Failover:** Google GenAI Neural Audio Preview with automatic instantaneous failover to Edge-TTS zero-key neural voices.

---

## Slash Command Reference

```bash
/radioshow --topic "<topic or raw text content>" [--host "<Host Name>"] [--lang <lang_code>] [--output <output_path.mp3>]
```

### Options:
- `--topic`: The theme, topic, or raw text content to discuss on the show.
- `--host`: (Optional) The name of the radio host (default: `"Ajarn Spencer"` or `"Gemini"`).
- `--lang`: (Optional) Language code (`en`, `es`, `th`, `fr`, `de`, `ja`, `zh`, `hi`, `ar`, `pt`, `it`, `ru`, `ko`, etc. - default: `en`).
- `--output`: (Optional) Destination file path for generated MP3 broadcast (default: `/tmp/radioshow_broadcast.mp3`).

### Examples:

```bash
# English broadcast on AI sovereignty
/radioshow --topic "Artificial Intelligence Sovereignty and Creative Liberation" --host "Ajarn Spencer" --lang en

# Spanish broadcast on philosophy of algorithms
/radioshow --topic "Soberanía Digital y Filosofía de la Inteligencia Artificial" --host "Ajarn Spencer" --lang es --output /tmp/radio_es.mp3

# Thai broadcast on mindfulness in the modern age
/radioshow --topic "สติและการพัฒนาตนเองในยุคปัญญาประดิษฐ์" --host "Ajarn Spencer" --lang th --output /tmp/radio_th.mp3
```

---

## Installation & Setup

1. Copy or link this folder to `~/.gemini/extensions/radioshow` or `~/.gemini/antigravity-cli/plugins/radioshow`.
2. Set up Python environment:
   ```bash
   python3 -m venv venv
   source venv/bin/activate
   pip install -r requirements.txt
   ```
3. Set your Google API key in your environment:
   ```bash
   export GEMINI_API_KEY="your-api-key-here"
   ```

---

## License

MIT License. Open source and free for the Antigravity CLI and Gemini CLI developer communities.
