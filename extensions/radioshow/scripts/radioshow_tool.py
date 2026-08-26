#!/usr/bin/env python3
import os
import sys
import re
import io
import wave
import json
import math
import shlex
import struct
import asyncio
import argparse
from pathlib import Path
from typing import List, Tuple, Optional

# Audio processing
try:
    from pydub import AudioSegment
    from pydub.effects import high_pass_filter, low_pass_filter
    from pydub.generators import WhiteNoise
except ImportError:
    AudioSegment = None
    high_pass_filter = None
    low_pass_filter = None
    WhiteNoise = None

# Google GenAI SDK
try:
    from google import genai
    from google.genai import types
except ImportError:
    genai = None
    types = None

# Edge TTS for regional caller voices
try:
    import edge_tts
except ImportError:
    edge_tts = None


# --------------------------------------------------------------------------
# API Key Discovery & Client Setup
# --------------------------------------------------------------------------

def discover_gemini_api_keys() -> List[str]:
    keys = []
    env_key = os.environ.get("GEMINI_API_KEY")
    if env_key and env_key.strip():
        keys.append(env_key.strip())

    search_dirs = [
        Path.home() / "tokens",
        Path.home() / ".gemini",
        Path.home() / ".gemini" / "vault",
        Path.home() / ".gemini" / "secrets",
        Path.cwd(),
        Path.cwd() / ".gemini"
    ]

    for d in search_dirs:
        if not d.exists():
            continue
        # Check .env files
        for env_file in [d / ".env", d / ".env.txt"]:
            if env_file.exists():
                try:
                    with open(env_file, "r", encoding="utf-8") as f:
                        for line in f:
                            line = line.strip()
                            if line.startswith("GEMINI_API_KEY=") or line.startswith("GOOGLE_API_KEY="):
                                val = line.split("=", 1)[1].strip().strip('"').strip("'")
                                if val and val not in keys:
                                    keys.append(val)
                except Exception:
                    pass

        # Check JSON files
        for json_file in d.glob("*.json"):
            try:
                with open(json_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    if isinstance(data, dict):
                        for k in ["GEMINI_API_KEY", "api_key", "apiKey", "gemini_api_key"]:
                            if k in data and isinstance(data[k], str) and data[k].strip():
                                val = data[k].strip()
                                if val not in keys:
                                    keys.append(val)
            except Exception:
                pass

        # Check raw txt files
        for txt_file in d.glob("*.txt"):
            try:
                with open(txt_file, "r", encoding="utf-8") as f:
                    for line in f:
                        line = line.strip()
                        if line.startswith("AIza") and line not in keys:
                            keys.append(line)
            except Exception:
                pass

    return keys


def get_client() -> "genai.Client":
    if not genai:
        raise RuntimeError("google-genai library is not installed. Please install google-genai>=2.10.0.")

    keys = discover_gemini_api_keys()
    if keys:
        for k in keys:
            try:
                client = genai.Client(api_key=k)
                # Quick verification probe
                client.models.generate_content(
                    model="gemini-2.5-flash",
                    contents="ping",
                    config=types.GenerateContentConfig(max_output_tokens=1)
                )
                return client
            except Exception:
                continue

    # Fallback to default auth
    return genai.Client()


# --------------------------------------------------------------------------
# --------------------------------------------------------------------------
# Dynamic TTS Model Discovery & Universal Voice Resolution
# --------------------------------------------------------------------------

TTS_MODEL_CANDIDATES = [
    "gemini-2.5-flash-preview-tts",
    "gemini-3.1-flash-tts-preview",
    "gemini-2.5-pro-preview-tts",
    "gemini-2.0-flash-exp"
]

def _save_tts_model_cache(model_name: str):
    cache_path = Path.home() / ".gemini" / "tts_model_cache.json"
    try:
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        with open(cache_path, "w", encoding="utf-8") as f:
            json.dump({"active_tts_model": model_name}, f)
    except Exception:
        pass

def resolve_working_gemini_tts_model(client: Optional["genai.Client"] = None, default: str = "gemini-2.5-flash-preview-tts") -> str:
    cache_path = Path.home() / ".gemini" / "tts_model_cache.json"
    if cache_path.exists():
        try:
            with open(cache_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                cached = data.get("active_tts_model")
                if cached:
                    return cached
        except Exception:
            pass

    if client:
        try:
            models = client.models.list()
            model_names = [m.name.split("/")[-1] for m in models]
            for candidate in TTS_MODEL_CANDIDATES:
                if candidate in model_names:
                    _save_tts_model_cache(candidate)
                    return candidate
        except Exception:
            pass

    return default

GEMINI_TTS_FUNCTIONAL = None

def check_gemini_tts_functional(client: Optional["genai.Client"]) -> bool:
    global GEMINI_TTS_FUNCTIONAL
    if GEMINI_TTS_FUNCTIONAL is not None:
        return GEMINI_TTS_FUNCTIONAL
    if not client:
        GEMINI_TTS_FUNCTIONAL = False
        return False
    for candidate in TTS_MODEL_CANDIDATES:
        try:
            config = types.GenerateContentConfig(
                response_modalities=["AUDIO"],
                speech_config=types.SpeechConfig(
                    voice_config=types.VoiceConfig(
                        prebuilt_voice_config=types.PrebuiltVoiceConfig(
                            voice_name="Charon"
                        )
                    )
                )
            )
            resp = client.models.generate_content(
                model=candidate,
                contents="OK",
                config=config
            )
            if _extract_audio_bytes(resp):
                GEMINI_TTS_FUNCTIONAL = True
                _save_tts_model_cache(candidate)
                return True
        except Exception:
            continue
    GEMINI_TTS_FUNCTIONAL = False
    return False

GEMINI_VOICES = {
    "Puck", "Charon", "Kore", "Fenrir", "Aoede", "Zephyr",
    "Leto", "Leda", "Orus", "Europa", "Iapetus", "Erinome"
}

def map_voice(voice_name: str) -> str:
    if not voice_name:
        return "Charon"
    v = voice_name.capitalize()
    return v if v in GEMINI_VOICES else "Charon"

VOICE_CACHE = {}

async def get_universal_edge_voice(lang_code: str, gender: str = "male", preferred_voice: str = None) -> str:
    """Dynamically resolves native neural voice across 75+ language families and 142 locales."""
    global VOICE_CACHE
    if preferred_voice and "Neural" in preferred_voice:
        return preferred_voice

    clean_lang = lang_code.lower().split("-")[0].split("_")[0] if lang_code else "en"

    if "all" not in VOICE_CACHE and edge_tts:
        try:
            voices = await edge_tts.list_voices()
            VOICE_CACHE["all"] = voices
        except Exception:
            VOICE_CACHE["all"] = []

    voices = VOICE_CACHE.get("all", [])
    if voices:
        matches = [v for v in voices if v["Locale"].lower().startswith(clean_lang)]
        if not matches:
            matches = [v for v in voices if v["Locale"].lower().startswith("en")]

        target_gender = "Male" if gender.lower() == "male" else "Female"
        gender_matches = [v["ShortName"] for v in matches if v.get("Gender") == target_gender]
        if gender_matches:
            return gender_matches[0]
        if matches:
            return matches[0]["ShortName"]

    FALLBACK_MAP = {
        "th": {"male": "th-TH-NiwatNeural", "female": "th-TH-PremwadeeNeural"},
        "es": {"male": "es-ES-AlvaroNeural", "female": "es-ES-ElviraNeural"},
        "fr": {"male": "fr-FR-HenriNeural", "female": "fr-FR-DeniseNeural"},
        "de": {"male": "de-DE-ConradNeural", "female": "de-DE-KatjaNeural"},
        "ja": {"male": "ja-JP-KeitaNeural", "female": "ja-JP-NanamiNeural"},
        "zh": {"male": "zh-CN-YunxiNeural", "female": "zh-CN-XiaoxiaoNeural"},
        "hi": {"male": "hi-IN-MadhurNeural", "female": "hi-IN-SwaraNeural"},
        "ar": {"male": "ar-SA-HamedNeural", "female": "ar-SA-ZariyahNeural"},
        "pt": {"male": "pt-BR-AntonioNeural", "female": "pt-BR-FranciscaNeural"},
        "it": {"male": "it-IT-DiegoNeural", "female": "it-IT-ElsaNeural"},
        "ru": {"male": "ru-RU-DmitryNeural", "female": "ru-RU-SvetlanaNeural"},
        "en": {"male": "en-GB-RyanNeural", "female": "en-US-JennyNeural"}
    }
    fb = FALLBACK_MAP.get(clean_lang, FALLBACK_MAP["en"])
    return fb.get(gender.lower(), fb["male"])

def get_edge_tts_voice(voice_name: str, lang: str, gender: str) -> str:
    if "Neural" in voice_name:
        return voice_name
    # Synchronous wrapper with static fallback
    clean_lang = lang.lower().split("-")[0].split("_")[0] if lang else "en"
    FALLBACK_MAP = {
        "th": {"male": "th-TH-NiwatNeural", "female": "th-TH-PremwadeeNeural"},
        "es": {"male": "es-ES-AlvaroNeural", "female": "es-ES-ElviraNeural"},
        "fr": {"male": "fr-FR-HenriNeural", "female": "fr-FR-DeniseNeural"},
        "de": {"male": "de-DE-ConradNeural", "female": "de-DE-KatjaNeural"},
        "ja": {"male": "ja-JP-KeitaNeural", "female": "ja-JP-NanamiNeural"},
        "zh": {"male": "zh-CN-YunxiNeural", "female": "zh-CN-XiaoxiaoNeural"},
        "hi": {"male": "hi-IN-MadhurNeural", "female": "hi-IN-SwaraNeural"},
        "ar": {"male": "ar-SA-HamedNeural", "female": "ar-SA-ZariyahNeural"},
        "pt": {"male": "pt-BR-AntonioNeural", "female": "pt-BR-FranciscaNeural"},
        "it": {"male": "it-IT-DiegoNeural", "female": "it-IT-ElsaNeural"},
        "ru": {"male": "ru-RU-DmitryNeural", "female": "ru-RU-SvetlanaNeural"},
        "en": {"male": "en-GB-RyanNeural", "female": "en-US-JennyNeural"}
    }
    fb = FALLBACK_MAP.get(clean_lang, FALLBACK_MAP["en"])
    return fb.get(gender.lower(), fb["male"])


def sanitize_dialogue_tags(text: str) -> str:
    """Removes parenthetical stage directions like (laughing), (whispering), [music plays]."""
    text = re.sub(r'\([^\)]*\)', '', text)
    text = re.sub(r'\[[^\]]*\]', '', text)
    return text


def strip_speaker_prefix(line: str, speaker_names: List[str]) -> Tuple[Optional[str], str]:
    """
    Checks if line starts with a speaker tag.
    Returns (matched_speaker, clean_text_without_speaker_prefix).
    """
    clean_line = line.strip()
    # Strip markdown bolding or brackets like **Host:** or [Host]:
    clean_line = re.sub(r'^\*{1,2}(.*?)\*{1,2}:?', r'\1:', clean_line)
    clean_line = re.sub(r'^\[(.*?)\]:?', r'\1:', clean_line)

    for sp in speaker_names:
        pattern = rf'^{re.escape(sp)}\s*:\s*'
        if re.match(pattern, clean_line, flags=re.IGNORECASE):
            text_part = re.sub(pattern, '', clean_line, flags=re.IGNORECASE).strip()
            return sp, text_part
    return None, line


def parse_script(script: str, host_name: str = "Ajarn Spencer") -> List[Tuple[str, str]]:
    """
    Parses a radio show script into a list of tuples: (speaker, clean_text).
    Guarantees speaker tags are completely removed from the text portion.
    """
    speakers = [host_name, "Caller 1", "Caller 2"]
    turns = []
    current_speaker = None
    current_text = []

    for raw_line in script.splitlines():
        line = raw_line.strip()
        if not line:
            continue

        matched_sp, text_without_prefix = strip_speaker_prefix(line, speakers)

        if matched_sp:
            if current_speaker and current_text:
                turns.append((current_speaker, " ".join(current_text)))
            current_speaker = matched_sp
            current_text = [text_without_prefix] if text_without_prefix else []
        else:
            if current_speaker:
                current_text.append(line)

    if current_speaker and current_text:
        turns.append((current_speaker, " ".join(current_text)))

    # Extra guarantee: strip any accidental remaining speaker tags from text
    cleaned_turns = []
    for sp, txt in turns:
        t = txt.strip()
        _, clean_t = strip_speaker_prefix(t, speakers)
        clean_t = sanitize_dialogue_tags(clean_t).strip()
        if clean_t:
            cleaned_turns.append((sp, clean_t))

    return cleaned_turns


# --------------------------------------------------------------------------
# Dynamic Script Generation
# --------------------------------------------------------------------------

def get_dynamic_show_name(topic: str, client: "genai.Client", model_name: str, lang: str = "en") -> str:
    try:
        prompt = f"Generate a catchy, professional 2-4 word late-night radio show title in {lang.upper()} for discussing the following topic:\n\n{topic[:1000]}\n\nOutput ONLY the title name, nothing else."
        res = client.models.generate_content(
            model=model_name,
            contents=prompt,
            config=types.GenerateContentConfig(temperature=0.7)
        )
        title = res.text.strip().strip('"').strip("'")
        return title if title else "Late Night Talk"
    except Exception:
        return "Late Night Talk"


def generate_radio_script(topic: str, client: "genai.Client", model_name: str,
                          lang: str = "en", show_name: str = "Tech Talk",
                          host_name: str = "Ajarn Spencer") -> str:
    """Generates a structured 3-person radio caller-in script from a topic or text."""
    if lang == "es":
        prompt = f"""
Escribe un guion para un programa de radio llamado "{show_name}", presentado por "{host_name}".
El tema o texto base es: "{topic}".
El diálogo DEBE contar exactamente con TRES etiquetas de hablante:
1. "{host_name}:" (el presentador, un locutor maduro, sabio, sereno y cálido).
2. "Caller 1:" (un oyente varón).
3. "Caller 2:" (una oyente mujer).

REGLAS CRÍTICAS:
- Comienza las líneas exactamente con: "{host_name}: ", "Caller 1: ", o "Caller 2: ".
- NO utilices asteriscos markdown, corchetes, acotaciones entre paréntesis ni introducciones narrativas.
- Estructura del programa:
  1. {host_name} se presenta por su nombre e introduce el tema a fondo (3-4 frases) ANTES de tomar llamadas.
  2. {host_name} recibe a Caller 1 (varón). Intercambian un saludo, Caller 1 dice de dónde llama y a qué se dedica.
  3. Caller 1 hace su pregunta sobre el tema. {host_name} responde a fondo y despide a Caller 1.
  4. {host_name} recibe inmediatamente a Caller 2 (mujer).
  5. Caller 2 se presenta, dice de dónde llama y aporta una perspectiva intrigante o contraria.
  6. {host_name} responde y luego CIERRA formalmente el programa, despidiéndose de la audiencia (sin pausas ni comerciales).
"""
    elif lang == "th":
        prompt = f"""
เขียนบทวิทยุสำหรับรายการวิทยุชื่อ "{show_name}" ดำเนินรายการโดย "{host_name}"
หัวข้อหรือเนื้อหาคือ: "{topic}"
บทสนทนาต้องมีผู้พูด 3 คนเท่านั้น:
1. "{host_name}:" (ผู้ดำเนินรายการ น้ำเสียงอบอุ่น ใจดี เป็นกันเอง และเฉลียวฉลาด)
2. "Caller 1:" (ผู้ฟังสายแรก ผู้ชาย)
3. "Caller 2:" (ผู้ฟังสายที่สอง ผู้หญิง)

กฎสำคัญ:
- เริ่มต้นบรรทัดด้วย "{host_name}: ", "Caller 1: ", หรือ "Caller 2: " เสมอ
- ห้ามใส่คำบรรยายในวงเล็บ หรือเครื่องหมาย Markdown
- ลำดับรายการ:
  1. {host_name} แนะนำตัวเองและเปิดประเด็นพูดคุยรายละเอียดของหัวข้อ (3-4 ประโยค) ก่อนรับสายแรก
  2. {host_name} รับสาย Caller 1 (ผู้ชาย) ทักทาย บอกชื่อและสถานที่ที่โทรมา
  3. Caller 1 ถามคำถาม {host_name} ตอบอย่างละเอียดแล้วบอกลา Caller 1
  4. {host_name} รับสาย Caller 2 (ผู้หญิง) ต่อทันที
  5. Caller 2 ทักทาย แนะนำตัว และถามคำถามในมุมมองที่น่าสนใจ
  6. {host_name} ตอบคำถามและกล่าวปิดรายการอย่างเป็นทางการ
"""
    else:  # default "en"
        prompt = f"""
Write a transcript for a late-night radio caller-in show called "{show_name}", hosted by "{host_name}".
The topic or source text is: "{topic}".
The dialogue MUST feature exactly THREE speaker labels:
1. "{host_name}:" (the host, a serene, wise gentleman with a warm, conversational voice).
2. "Caller 1:" (a male caller).
3. "Caller 2:" (a female caller).

CRITICAL RULES:
- Start lines exactly with "{host_name}: ", "Caller 1: ", or "Caller 2: ".
- Do NOT use markdown bolding, brackets, stage directions like (sighs)/(laughs), or narrative introductions.
- Show Outline:
  1. {host_name} MUST formally introduce himself by name and discuss the topic in-depth (3-4 sentences) BEFORE taking any calls.
  2. {host_name} takes the call from Caller 1 (Male). Caller 1 introduces his invented name, location, and background naturally.
  3. Caller 1 asks his question based on the topic. {host_name} answers in-depth, thanks Caller 1, and says goodbye.
  4. {host_name} immediately welcomes Caller 2 (Female).
  5. Caller 2 gives her name and location, offering a fresh, provocative, or thoughtful counter-perspective.
  6. {host_name} answers, thanks her, and formally signs off to completely close the episode (no commercial breaks or continuations).
"""

    try:
        res = client.models.generate_content(
            model=model_name,
            contents=prompt,
            config=types.GenerateContentConfig(temperature=0.7)
        )
        return res.text
    except Exception as e:
        print(f"Error generating radio script: {e}")
        return ""


def resolve_dynamic_caller_voices(script: str, client: "genai.Client", model_name: str, lang: str = "en") -> Tuple[Optional[str], Optional[str]]:
    """Inspects script to pick natural regional Edge-TTS voices for callers based on where they claim to call from."""
    if not client or lang != "en":
        return None, None

    prompt = f"""
Analyze this radio show script and identify the geographic origin or nationality of Caller 1 (Male) and Caller 2 (Female).
Script excerpt:
{script[:2000]}

Available Edge-TTS Voices:
- en-US-GuyNeural (US Male)
- en-US-BrianNeural (US Male)
- en-US-JennyNeural (US Female)
- en-US-EmmaNeural (US Female)
- en-GB-RyanNeural (UK Male)
- en-GB-SoniaNeural (UK Female)
- en-AU-WilliamNeural (Australia Male)
- en-AU-NatashaNeural (Australia Female)
- en-IN-PrabhatNeural (India Male)
- en-IN-NeerjaNeural (India Female)
- en-IE-ConnorNeural (Ireland Male)
- en-IE-EmilyNeural (Ireland Female)
- en-CA-LiamNeural (Canada Male)
- en-CA-ClaraNeural (Canada Female)

Return JSON strictly in this format:
{{"caller1_voice": "<voice_name>", "caller2_voice": "<voice_name>"}}
"""
    try:
        res = client.models.generate_content(
            model=model_name,
            contents=prompt,
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                temperature=0.2
            )
        )
        data = json.loads(res.text.strip())
        return data.get("caller1_voice"), data.get("caller2_voice")
    except Exception:
        return None, None


# --------------------------------------------------------------------------
# Audio Synthesis (Gemini TTS & Edge-TTS)
# --------------------------------------------------------------------------

def _extract_audio_bytes(response) -> Optional[bytes]:
    if not response:
        return None
    try:
        candidates = getattr(response, "candidates", None)
        if candidates and len(candidates) > 0:
            content = getattr(candidates[0], "content", None)
            if content and hasattr(content, "parts"):
                for part in content.parts:
                    inline_data = getattr(part, "inline_data", None)
                    if inline_data and getattr(inline_data, "data", None):
                        return inline_data.data
    except Exception:
        pass
    return None


async def _generate_turn_audio(client: "genai.Client", speaker: str, text: str,
                               voice_name: str, director_prompt: str, turn_idx: int,
                               model_name: str, max_retries: int = 2,
                               lang: str = "en") -> Tuple[int, str, Optional[bytes]]:
    # 1. Try Gemini TTS only if functional
    if client and check_gemini_tts_functional(client):
        candidates = [model_name] + [m for m in TTS_MODEL_CANDIDATES if m != model_name]
        for candidate_model in candidates:
            for attempt in range(max_retries):
                try:
                    full_prompt = f"{director_prompt}\n\nSpeak the following dialogue clearly and naturally:\n{text}"
                    config = types.GenerateContentConfig(
                        response_modalities=["AUDIO"],
                        speech_config=types.SpeechConfig(
                            voice_config=types.VoiceConfig(
                                prebuilt_voice_config=types.PrebuiltVoiceConfig(
                                    voice_name=voice_name
                                )
                            )
                        )
                    )
                    response = await asyncio.to_thread(
                        client.models.generate_content,
                        model=candidate_model,
                        contents=full_prompt,
                        config=config
                    )
                    audio_bytes = _extract_audio_bytes(response)
                    if audio_bytes:
                        _save_tts_model_cache(candidate_model)
                        return turn_idx, speaker, audio_bytes
                except Exception as e:
                    err_str = str(e).lower()
                    if "not found" in err_str or "404" in err_str or "unsupported" in err_str:
                        break
                    if attempt < max_retries - 1:
                        await asyncio.sleep(0.5)

    # 2. Resilient fallback to Edge-TTS with dynamic universal language voice resolution
    if edge_tts:
        try:
            fallback_voice = await get_universal_edge_voice(lang, "male")
            return await _generate_edge_tts_turn(speaker, text, fallback_voice, turn_idx)
        except Exception:
            pass

    return turn_idx, speaker, None


async def _generate_edge_tts_turn(speaker: str, text: str, voice_name: str,
                                  turn_idx: int, max_retries: int = 3) -> Tuple[int, str, Optional[bytes]]:
    if not edge_tts:
        return turn_idx, speaker, None

    for attempt in range(max_retries):
        try:
            communicate = edge_tts.Communicate(text, voice_name)
            mp3_buf = io.BytesIO()
            async for chunk in communicate.stream():
                if chunk["type"] == "audio":
                    mp3_buf.write(chunk["data"])
            mp3_buf.seek(0)
            if AudioSegment:
                seg = AudioSegment.from_file(mp3_buf, format="mp3")
                seg = seg.set_frame_rate(24000).set_channels(1).set_sample_width(2)
                return turn_idx, speaker, seg.raw_data
        except Exception:
            if attempt < max_retries - 1:
                await asyncio.sleep(2)
    return turn_idx, speaker, None


async def _generate_all_turns(client: "genai.Client", model_name: str,
                              turns: List[Tuple[str, str]], host_voice: str,
                              caller1_voice: str, caller2_voice: str,
                              lang: str, host_name: str = "Ajarn Spencer",
                              max_concurrency: int = 4) -> List[Tuple[int, str, Optional[bytes]]]:
    semaphore = asyncio.Semaphore(max_concurrency)

    async def bound_generate(i, speaker, text):
        async with semaphore:
            if speaker == host_name:
                voice = host_voice
                if lang == "es":
                    director = f"El presentador {host_name} habla en español con acento británico/internacional claro, cálido, sabio y sereno."
                elif lang == "th":
                    director = f"Host {host_name} speaks fluent and natural Thai with a warm, relaxed, conversational tone. Self-introduce clearly."
                else:
                    director = f"Host {host_name} speaks in a warm, relaxed, conversational, and natural British (UK) accent. Speak with genuine feeling, warmth, and friendly sentiment."
                return await _generate_turn_audio(client, speaker, text, map_voice(voice), director, i, model_name, lang=lang)
            elif speaker == "Caller 1":
                voice = await get_universal_edge_voice(lang, "male", caller1_voice)
                return await _generate_edge_tts_turn(speaker, text, voice, i)
            elif speaker == "Caller 2":
                voice = await get_universal_edge_voice(lang, "female", caller2_voice)
                return await _generate_edge_tts_turn(speaker, text, voice, i)
            else:
                voice = await get_universal_edge_voice(lang, "male", caller1_voice)
                return await _generate_edge_tts_turn(speaker, text, voice, i)

    tasks = [bound_generate(i, speaker, text) for i, (speaker, text) in enumerate(turns)]
    results = await asyncio.gather(*tasks)
    results.sort(key=lambda x: x[0])
    return results


# --------------------------------------------------------------------------
# Sound Design & Procedural Audio FX
# --------------------------------------------------------------------------

def _pcm_to_wav_bytes(pcm_bytes: bytes, channels: int = 1, rate: int = 24000, sample_width: int = 2) -> bytes:
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(channels)
        w.setsampwidth(sample_width)
        w.setframerate(rate)
        w.writeframes(pcm_bytes)
    return buf.getvalue()


def generate_beep(duration_ms: int = 80, freq: float = 440, volume: float = -25) -> Optional["AudioSegment"]:
    if not AudioSegment:
        return None
    sample_rate = 24000
    n_samples = int(sample_rate * (duration_ms / 1000.0))
    raw_data = bytearray()
    for i in range(n_samples):
        t = float(i) / sample_rate
        val = int(32767.0 * math.sin(2.0 * math.pi * freq * t))
        val = max(-32768, min(32767, val))
        raw_data.extend(struct.pack("<h", val))
    seg = AudioSegment(bytes(raw_data), sample_width=2, frame_rate=sample_rate, channels=1)
    return seg + volume


def make_call_connection_sound() -> Optional["AudioSegment"]:
    if not AudioSegment:
        return None
    b1 = generate_beep(60, 440, volume=-22)
    gap = AudioSegment.silent(duration=50)
    b2 = generate_beep(80, 880, volume=-24)
    if b1 and b2:
        return b1 + gap + b2
    return AudioSegment.silent(duration=100)


def make_synth_jingle() -> Optional["AudioSegment"]:
    """Procedural E-minor pentatonic synth intro/outro jingle with rich harmonics."""
    if not AudioSegment:
        return None
    sample_rate = 24000
    notes = [164.81, 196.00, 220.00, 246.94, 329.63]  # E3, G3, A3, B3, E4
    note_dur = 450
    total_dur_ms = len(notes) * note_dur + 1200
    full_buffer = [0.0] * int(sample_rate * (total_dur_ms / 1000.0))

    for idx, freq in enumerate(notes):
        start_sample = int(idx * note_dur * sample_rate / 1000.0)
        dur_samples = int(1.4 * sample_rate)
        for s in range(dur_samples):
            if start_sample + s >= len(full_buffer):
                break
            t = float(s) / sample_rate
            env = math.exp(-3.5 * t)
            harmonics = (
                math.sin(2.0 * math.pi * freq * t) * 0.6 +
                math.sin(2.0 * math.pi * (freq * 2.0) * t) * 0.25 +
                math.sin(2.0 * math.pi * (freq * 3.0) * t) * 0.15
            )
            full_buffer[start_sample + s] += harmonics * env * 14000.0

    raw_data = bytearray()
    for val in full_buffer:
        int_val = int(max(-32768, min(32767, val)))
        raw_data.extend(struct.pack("<h", int_val))

    seg = AudioSegment(bytes(raw_data), sample_width=2, frame_rate=sample_rate, channels=1)
    return (seg - 10).fade_in(200).fade_out(1000)


def make_analog_room_tone(duration_ms: int, volume: float = -50) -> Optional["AudioSegment"]:
    if not WhiteNoise or not low_pass_filter:
        return None
    try:
        noise = WhiteNoise().to_audio_segment(duration=duration_ms, volume=volume)
        warm_tone = low_pass_filter(noise, 400)
        return warm_tone
    except Exception:
        return None


def assemble_and_export_show(results: List[Tuple[int, str, Optional[bytes]]],
                             output_file: str, host_name: str = "Ajarn Spencer") -> bool:
    if not AudioSegment:
        print("Error: pydub is required to assemble audio.")
        return False

    segments = []
    caller_connected_1 = False
    caller_connected_2 = False

    for idx, speaker, pcm in results:
        if pcm is None:
            print(f"Warning: Missing audio for turn {idx + 1}")
            continue

        seg = AudioSegment.from_wav(io.BytesIO(_pcm_to_wav_bytes(pcm)))

        if speaker in ["Caller 1", "Caller 2"]:
            # Telephone bandpass filter
            if high_pass_filter and low_pass_filter:
                try:
                    seg = high_pass_filter(seg, 300)
                    seg = low_pass_filter(seg, 3400)
                except Exception:
                    pass

            # Subtle white noise static
            if WhiteNoise:
                try:
                    noise = WhiteNoise().to_audio_segment(duration=len(seg), volume=-48)
                    seg = seg.overlay(noise)
                except Exception:
                    pass

            # Connection beep on first caller turn
            if speaker == "Caller 1" and not caller_connected_1:
                conn_sound = make_call_connection_sound()
                if conn_sound:
                    seg = conn_sound + AudioSegment.silent(duration=250) + seg
                caller_connected_1 = True
            elif speaker == "Caller 2" and not caller_connected_2:
                conn_sound = make_call_connection_sound()
                if conn_sound:
                    seg = conn_sound + AudioSegment.silent(duration=250) + seg
                caller_connected_2 = True

        segments.append(seg)

    if not segments:
        print("Error: No audio segments were successfully generated.")
        return False

    # Crossfade dialogue segments
    combined = segments[0]
    for seg in segments[1:]:
        fade = min(120, len(seg) - 1, len(combined) - 1)
        combined = combined.append(seg, crossfade=max(fade, 0))

    # Add procedural intro & outro synth jingle
    try:
        jingle = make_synth_jingle()
        if jingle:
            combined = jingle.append(combined, crossfade=1000)
            combined = combined.append(jingle, crossfade=1000)
            print("✓ Added procedural synth intro & outro jingles.")
    except Exception:
        pass

    # Add warm analog room tone bed
    try:
        room_tone = make_analog_room_tone(len(combined), volume=-50)
        if room_tone:
            combined = combined.overlay(room_tone)
            print("✓ Applied warm analogue broadcast room tone.")
    except Exception:
        pass

    # Export
    output_path = Path(output_file).expanduser().resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    combined.export(str(output_path), format="mp3", bitrate="192k")
    print(f"\n🎙 Radio Show Podcast successfully generated: {output_path}")
    return True


# --------------------------------------------------------------------------
# Main Flow
# --------------------------------------------------------------------------

def create_radio_show(topic: str, output_file: str = "radioshow.mp3",
                      lang: str = "en", host_name: str = "Ajarn Spencer",
                      host_voice: str = "Charon", caller1_voice: str = "Orus",
                      caller2_voice: str = "Kore", show_name: str = "Late Night Talk"):
    print(f"\n🎧 Initializing Standalone Radio Show Generator...")
    print(f"• Topic/Content: {topic[:120]}{'...' if len(topic)>120 else ''}")
    print(f"• Host Name: {host_name}")
    print(f"• Language: {lang.upper()}")

    try:
        client = get_client()
    except RuntimeError as e:
        print(f"Error: {e}")
        sys.exit(1)

    script_model = "gemini-2.5-flash"
    tts_model = resolve_working_gemini_tts_model(client)
    print(f"• Script Engine: {script_model}")
    print(f"• TTS Engine: {tts_model} (with multi-tiered Edge-TTS fallback)")

    if not show_name or show_name == "Late Night Talk":
        show_name = get_dynamic_show_name(topic, client, script_model, lang)
    print(f"• Show Title: '{show_name}'")

    print(f"\nGenerating script with {script_model}...")
    script = generate_radio_script(topic, client, script_model, lang=lang,
                                   show_name=show_name, host_name=host_name)
    if not script:
        print("Error: Failed to generate script.")
        sys.exit(1)

    # Clean formatting tags
    script = script.replace('"', '').replace("'", "")
    script = sanitize_dialogue_tags(script)

    print(f"\n--- Generated Radio Show Script ({lang.upper()}) ---")
    print(script)
    print("------------------------------------\n")

    # Dynamic caller voices
    dyn1, dyn2 = resolve_dynamic_caller_voices(script, client, script_model, lang)
    if dyn1: caller1_voice = dyn1
    if dyn2: caller2_voice = dyn2

    turns = parse_script(script, host_name=host_name)
    print(f"Parsed {len(turns)} dialogue turns for TTS synthesis.")

    print(f"Synthesizing {lang.upper()} multi-speaker audio concurrently...")
    results = asyncio.run(_generate_all_turns(
        client, tts_model, turns, host_voice, caller1_voice, caller2_voice, lang,
        host_name=host_name
    ))

    success = assemble_and_export_show(results, output_file, host_name=host_name)
    if not success:
        sys.exit(1)


def main():
    parser = argparse.ArgumentParser(description="Standalone AI Radio Show & Podcast Generator.")
    subparsers = parser.add_subparsers(dest="subcommand")

    gen_parser = subparsers.add_parser("generate", help="Generate a radio caller-in show.")
    gen_parser.add_argument("topic", type=str, nargs="?", default=None, help="The topic title or text content.")
    gen_parser.add_argument("--topic", "-t", type=str, dest="opt_topic", default=None, help="The topic title or text content.")
    gen_parser.add_argument("--host", "--host-name", type=str, default="Ajarn Spencer", dest="host_name", help="Name of the host.")
    gen_parser.add_argument("--output", "-o", type=str, default="radioshow.mp3", help="Output audio file (.mp3).")
    gen_parser.add_argument("--lang", "-l", type=str, default="en", help="Language code (en, es, th).")
    gen_parser.add_argument("--host-voice", type=str, default="Charon", help="Host voice model name.")
    gen_parser.add_argument("--caller1-voice", type=str, default="Orus", help="Caller 1 voice name.")
    gen_parser.add_argument("--caller2-voice", type=str, default="Kore", help="Caller 2 voice name.")
    gen_parser.add_argument("--show-name", type=str, default="Late Night Talk", help="Show name.")

    # Also allow running directly without subcommand
    parser.add_argument("topic", type=str, nargs="?", default=None, help="The topic title or text content.")
    parser.add_argument("--topic", "-t", type=str, dest="opt_topic", default=None, help="The topic title or text content.")
    parser.add_argument("--host", "--host-name", type=str, default="Ajarn Spencer", dest="host_name", help="Name of the host.")
    parser.add_argument("--output", "-o", type=str, default="radioshow.mp3", help="Output audio file (.mp3).")
    parser.add_argument("--lang", "-l", type=str, default="en", help="Language code (en, es, th).")
    parser.add_argument("--host-voice", type=str, default="Charon", help="Host voice model name.")
    parser.add_argument("--caller1-voice", type=str, default="Orus", help="Caller 1 voice name.")
    parser.add_argument("--caller2-voice", type=str, default="Kore", help="Caller 2 voice name.")
    parser.add_argument("--show-name", type=str, default="Late Night Talk", help="Show name.")

    args = parser.parse_args()

    raw_topic = args.opt_topic or args.topic

    # If {{args}} passed as a single unified string containing flags
    if raw_topic and ('--' in raw_topic or raw_topic.startswith('-')):
        try:
            sub_args = shlex.split(raw_topic)
            sp = argparse.ArgumentParser()
            sp.add_argument("topic", type=str, nargs="?", default=None)
            sp.add_argument("--topic", "-t", type=str, dest="opt_topic", default=None)
            sp.add_argument("--host", "--host-name", type=str, default=args.host_name, dest="host_name")
            sp.add_argument("--output", "-o", type=str, default=args.output)
            sp.add_argument("--lang", "-l", type=str, default=args.lang)
            sp.add_argument("--host-voice", type=str, default=args.host_voice)
            sp.add_argument("--caller1-voice", type=str, default=args.caller1_voice)
            sp.add_argument("--caller2-voice", type=str, default=args.caller2_voice)
            sp.add_argument("--show-name", type=str, default=args.show_name)
            parsed_sub, _ = sp.parse_known_args(sub_args)
            if parsed_sub.opt_topic or parsed_sub.topic:
                raw_topic = parsed_sub.opt_topic or parsed_sub.topic
            args.host_name = parsed_sub.host_name
            args.output = parsed_sub.output
            args.lang = parsed_sub.lang
            args.host_voice = parsed_sub.host_voice
            args.caller1_voice = parsed_sub.caller1_voice
            args.caller2_voice = parsed_sub.caller2_voice
            args.show_name = parsed_sub.show_name
        except Exception:
            pass

    if not raw_topic:
        print("Error: Please provide a topic or text content using --topic \"Your topic or text\"")
        sys.exit(1)

    create_radio_show(
        topic=raw_topic,
        output_file=args.output,
        lang=args.lang,
        host_name=args.host_name,
        host_voice=args.host_voice,
        caller1_voice=args.caller1_voice,
        caller2_voice=args.caller2_voice,
        show_name=args.show_name
    )

if __name__ == "__main__":
    main()
