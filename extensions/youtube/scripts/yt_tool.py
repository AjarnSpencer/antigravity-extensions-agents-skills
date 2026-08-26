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
import hashlib
import argparse
import urllib.parse
from pathlib import Path
from typing import List, Tuple, Optional

# Third-party imports
try:
    import requests
    from bs4 import BeautifulSoup
except ImportError:
    requests = None
    BeautifulSoup = None

try:
    from youtube_transcript_api import YouTubeTranscriptApi
except ImportError:
    YouTubeTranscriptApi = None

try:
    from pydub import AudioSegment
    from pydub.effects import high_pass_filter, low_pass_filter
    from pydub.generators import WhiteNoise
except ImportError:
    AudioSegment = None
    high_pass_filter = None
    low_pass_filter = None
    WhiteNoise = None

try:
    from google import genai
    from google.genai import types
except ImportError:
    genai = None
    types = None

try:
    import edge_tts
except ImportError:
    edge_tts = None


# --------------------------------------------------------------------------
# YouTube Core Tools (Search, Transcript)
# --------------------------------------------------------------------------

def search_youtube(query: str):
    """Searches YouTube and outputs video results in tabular format."""
    encoded_query = urllib.parse.quote(query)
    url = f"https://www.youtube.com/results?search_query={encoded_query}"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
    }
    
    try:
        response = requests.get(url, headers=headers)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, "html.parser")
        scripts = soup.find_all("script")
        
        initial_data = None
        for script in scripts:
            if script.string and "var ytInitialData =" in script.string:
                json_str = script.string.split("var ytInitialData =")[1].strip().rstrip(";")
                initial_data = json.loads(json_str)
                break
                
        if not initial_data:
            print("Could not extract search results.")
            return

        contents = initial_data["contents"]["twoColumnSearchResultsRenderer"]["primaryContents"]["sectionListRenderer"]["contents"][0]["itemSectionRenderer"]["contents"]
        
        results = []
        for item in contents:
            if "videoRenderer" in item:
                video = item["videoRenderer"]
                title = video.get("title", {}).get("runs", [{}])[0].get("text", "N/A")
                video_id = video.get("videoId", "")
                link = f"https://www.youtube.com/watch?v={video_id}"
                channel = video.get("ownerText", {}).get("runs", [{}])[0].get("text", "N/A")
                views = video.get("viewCountText", {}).get("simpleText", "N/A")
                duration = video.get("lengthText", {}).get("simpleText", "N/A")
                results.append({"Title": title, "Channel": channel, "Duration": duration, "Views": views, "Link": link})
                if len(results) >= 10:
                    break
                    
        if not results:
            print("No video results found.")
            return
            
        try:
            from tabulate import tabulate
            print(tabulate(results, headers="keys", tablefmt="pipe"))
        except ImportError:
            for r in results:
                print(f"• {r['Title']} | {r['Channel']} ({r['Duration']})\n  {r['Link']}\n")
    except Exception as e:
        print(f"Error during YouTube search: {e}")


def get_transcript(video_url: str, return_text: bool = False) -> Optional[str]:
    """Fetches the transcript for a given YouTube video URL."""
    if not YouTubeTranscriptApi:
        msg = "Error: youtube-transcript-api is not installed."
        if return_text: return None
        print(msg)
        return None

    video_id = None
    if "youtu.be/" in video_url:
        video_id = video_url.split("youtu.be/")[-1].split("?")[0]
    else:
        video_id_match = re.search(r"v=([^&]+)", video_url)
        if video_id_match:
            video_id = video_id_match.group(1)

    if not video_id:
        # Fallback: maybe video_url is the direct ID
        if len(video_url) == 11 and not re.search(r'[^a-zA-Z0-9_-]', video_url):
            video_id = video_url
        else:
            msg = "Error: Could not extract valid video ID from URL."
            if return_text: return None
            print(msg)
            return None

    try:
        # Try fetching default
        transcript = YouTubeTranscriptApi().fetch(video_id)
        full_transcript = " ".join([snippet.text for snippet in transcript])
        if return_text: return full_transcript
        print(full_transcript)
        return full_transcript
    except Exception:
        pass

    try:
        transcript_list = YouTubeTranscriptApi().list(video_id)
        try:
            transcript = transcript_list.find_transcript(['en', 'es', 'th'])
        except Exception:
            try:
                transcript = next(iter(transcript_list._manually_created_transcripts.values()))
            except Exception:
                transcript = next(iter(transcript_list._generated_transcripts.values()))
        data = transcript.fetch()
        full_transcript = " ".join([snippet.text for snippet in data])
        if return_text: return full_transcript
        print(full_transcript)
        return full_transcript
    except Exception as e:
        msg = f"Error fetching transcript: {e}"
        if return_text: return None
        print(msg)
        return None


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
    text = re.sub(r'\([^\)]*\)', '', text)
    text = re.sub(r'\[[^\]]*\]', '', text)
    return text


def strip_speaker_prefix(line: str, speaker_names: List[str]) -> Tuple[Optional[str], str]:
    clean_line = line.strip()
    clean_line = re.sub(r'^\*{1,2}(.*?)\*{1,2}:?', r'\1:', clean_line)
    clean_line = re.sub(r'^\[(.*?)\]:?', r'\1:', clean_line)

    for sp in speaker_names:
        pattern = rf'^{re.escape(sp)}\s*:\s*'
        if re.match(pattern, clean_line, flags=re.IGNORECASE):
            text_part = re.sub(pattern, '', clean_line, flags=re.IGNORECASE).strip()
            return sp, text_part
    return None, line


def parse_script(script: str, host_name: str = "Ajarn Spencer") -> List[Tuple[str, str]]:
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

    cleaned_turns = []
    for sp, txt in turns:
        t = txt.strip()
        _, clean_t = strip_speaker_prefix(t, speakers)
        clean_t = sanitize_dialogue_tags(clean_t).strip()
        if clean_t:
            cleaned_turns.append((sp, clean_t))

    return cleaned_turns


# --------------------------------------------------------------------------
# YouTube-Based Radio Show Script Generation
# --------------------------------------------------------------------------

def get_dynamic_show_name_from_transcript(transcript: str, client: "genai.Client", model_name: str, lang: str = "en") -> str:
    try:
        prompt = f"Generate a catchy, professional 2-4 word late-night radio show title in {lang.upper()} for discussing the themes of this broadcast/interview:\n\n{transcript[:1500]}\n\nOutput ONLY the show name, nothing else."
        res = client.models.generate_content(
            model=model_name,
            contents=prompt,
            config=types.GenerateContentConfig(temperature=0.7)
        )
        title = res.text.strip().strip('"').strip("'")
        return title if title else "Midnight Broadcast"
    except Exception:
        return "Midnight Broadcast"


def generate_radio_script_from_transcript(transcript: str, client: "genai.Client",
                                          model_name: str, lang: str = "en",
                                          show_name: str = "Tech Talk",
                                          host_name: str = "Ajarn Spencer") -> str:
    """Generates a structured 3-person callers-in radio script analyzing YouTube video content."""
    if lang == "es":
        prompt = f"""
Escribe un guion para un programa de radio llamado "{show_name}", presentado por "{host_name}".
El programa analiza a fondo el siguiente contenido:
{transcript[:5000]}

El diálogo DEBE contar exactamente con TRES etiquetas de hablante:
1. "{host_name}:" (el presentador, un locutor maduro, sabio, sereno y cálido).
2. "Caller 1:" (un oyente varón).
3. "Caller 2:" (una oyente mujer).

REGLAS CRÍTICAS:
- Comienza las líneas exactamente con: "{host_name}: ", "Caller 1: ", o "Caller 2: ".
- NUNCA uses las palabras "video", "transcripción", "YouTube" o "canal". Habla de los temas como realidades e ideas de actualidad.
- INVENTA nombres, ubicaciones globales y profesiones variadas para los oyentes.
- NO uses formato markdown (como **negrita**), corchetes ni acotaciones teatrales.
- Estructura:
  1. {host_name} se presenta por su nombre e introduce las ideas principales del tema a fondo (3-4 frases) ANTES de tomar llamadas.
  2. {host_name} recibe a Caller 1 (varón). Caller 1 saluda, dice de dónde llama y su ocupación, y hace una pregunta reflexiva sobre el tema.
  3. {host_name} responde en profundidad, agradece a Caller 1 y se despide.
  4. {host_name} recibe inmediatamente a Caller 2 (mujer).
  5. Caller 2 se presenta, da su ubicación y plantea un contraargumento intrigante o una duda profunda.
  6. {host_name} responde, sintetiza la lección y CIERRA formalmente el episodio.
"""
    elif lang == "th":
        prompt = f"""
เขียนบทวิทยุสำหรับรายการวิทยุชื่อ "{show_name}" ดำเนินรายการโดย "{host_name}"
โดยสนทนาและวิเคราะห์จากเนื้อหาต่อไปนี้:
{transcript[:5000]}

บทสนทนาต้องมีผู้พูด 3 คนเท่านั้น:
1. "{host_name}:" (ผู้ดำเนินรายการ น้ำเสียงอบอุ่น ใจดี เป็นกันเอง และเฉลียวฉลาด)
2. "Caller 1:" (ผู้ฟังสายแรก ผู้ชาย)
3. "Caller 2:" (ผู้ฟังสายที่สอง ผู้หญิง)

กฎสำคัญ:
- เริ่มต้นบรรทัดด้วย "{host_name}: ", "Caller 1: ", หรือ "Caller 2: " เสมอ
- ห้ามพูดคำว่า "วิดีโอ" "คลิป" "YouTube" หรือ "การถอดเสียง" ให้พูดถึงเนื้อหาเป็นประเด็นความรู้ในโลกจริง
- ห้ามใส่คำบรรยายในวงเล็บ หรือเครื่องหมาย Markdown
- ลำดับรายการ:
  1. {host_name} แนะนำตัวเองและวิเคราะห์ประเด็นสำคัญของหัวข้อ (3-4 ประโยค) ก่อนรับสายแรก
  2. {host_name} รับสาย Caller 1 (ผู้ชาย) ทักทาย บอกชื่อและสถานที่ที่โทรมา แล้วถามคำถาม
  3. {host_name} ตอบอย่างละเอียดแล้วบอกลา Caller 1
  4. {host_name} รับสาย Caller 2 (ผู้หญิง) ต่อทันที
  5. Caller 2 ทักทาย แนะนำตัว และถามคำถามในมุมมองที่น่าสนใจ
  6. {host_name} ตอบคำถามและกล่าวปิดรายการอย่างเป็นทางการ
"""
    else:  # default "en"
        prompt = f"""
Write a transcript for a late-night radio callers-in show called "{show_name}", hosted by "{host_name}".
The discussion analyzes the themes and ideas from this source content:
{transcript[:5000]}

The dialogue MUST feature exactly THREE speaker labels:
1. "{host_name}:" (the host, a serene, wise gentleman with a warm, conversational voice).
2. "Caller 1:" (a male caller).
3. "Caller 2:" (a female caller).

CRITICAL RULES:
- Start lines exactly with "{host_name}: ", "Caller 1: ", or "Caller 2: ".
- NEVER mention "video", "transcript", "YouTube", or "watching". Treat the subject matter as real-world issues, philosophies, or news.
- INVENT creative names, diverse global locations (e.g. London, Dublin, Sydney, Toronto, Mumbai, Austin), and real occupations for the callers.
- Do NOT use markdown bolding, brackets, or stage directions.
- Show Outline:
  1. {host_name} MUST formally introduce himself by name and discuss the core subject matter in-depth (3-4 sentences) BEFORE taking any calls.
  2. {host_name} takes the call from Caller 1 (Male). Caller 1 introduces his name, location, and background naturally, then asks a question based on the topic.
  3. {host_name} answers in-depth, thanks Caller 1, and says goodbye.
  4. {host_name} immediately welcomes Caller 2 (Female).
  5. Caller 2 introduces her name and location, offering a fresh, provocative counter-perspective.
  6. {host_name} synthesizes the discussion, answers thoughtfully, and formally signs off to close the episode.
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
# Audio Synthesis & Procedural Sound Design
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
    if not AudioSegment:
        return None
    sample_rate = 24000
    notes = [164.81, 196.00, 220.00, 246.94, 329.63]
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
        return low_pass_filter(noise, 400)
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
            if high_pass_filter and low_pass_filter:
                try:
                    seg = high_pass_filter(seg, 300)
                    seg = low_pass_filter(seg, 3400)
                except Exception:
                    pass

            if WhiteNoise:
                try:
                    noise = WhiteNoise().to_audio_segment(duration=len(seg), volume=-48)
                    seg = seg.overlay(noise)
                except Exception:
                    pass

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

    combined = segments[0]
    for seg in segments[1:]:
        fade = min(120, len(seg) - 1, len(combined) - 1)
        combined = combined.append(seg, crossfade=max(fade, 0))

    try:
        jingle = make_synth_jingle()
        if jingle:
            combined = jingle.append(combined, crossfade=1000)
            combined = combined.append(jingle, crossfade=1000)
            print("✓ Added procedural synth intro & outro jingles.")
    except Exception:
        pass

    try:
        room_tone = make_analog_room_tone(len(combined), volume=-50)
        if room_tone:
            combined = combined.overlay(room_tone)
            print("✓ Applied warm analogue broadcast room tone.")
    except Exception:
        pass

    output_path = Path(output_file).expanduser().resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    combined.export(str(output_path), format="mp3", bitrate="192k")
    print(f"\n🎙 YouTube Radio Show Podcast successfully generated: {output_path}")
    return True


# --------------------------------------------------------------------------
# YouTube Podcast (Single Narrator from Video Transcript)
# --------------------------------------------------------------------------

def create_podcast(video_url: str, voice: Optional[str] = None, rate: Optional[str] = None,
                   pitch: Optional[str] = None, output_file: str = "podcast.mp3", lang: str = "en"):
    print(f"Fetching transcript from YouTube URL: {video_url}...")
    transcript = get_transcript(video_url, return_text=True)
    if not transcript:
        print("Error: Could not retrieve transcript from the provided YouTube URL.")
        sys.exit(1)

    async def _resolve_and_speak():
        voice_to_use = voice
        if not voice_to_use:
            voice_to_use = await get_universal_edge_voice(lang, "male")
        rate_to_use = rate if rate else "+0%"
        pitch_to_use = pitch if pitch else "+0Hz"

        print(f"Synthesizing solo podcast narration in {lang.upper()} using {voice_to_use} (Rate: {rate_to_use}, Pitch: {pitch_to_use})...")
        communicate = edge_tts.Communicate(transcript, voice_to_use, rate=rate_to_use, pitch=pitch_to_use)
        await communicate.save(output_file)

    try:
        asyncio.run(_resolve_and_speak())
        print(f"✓ Podcast successfully generated: {output_file}")
    except Exception as e:
        print(f"Error generating podcast: {e}")
        sys.exit(1)


# --------------------------------------------------------------------------
# YouTube Radio Show (Callers-In Podcast from Video Context)
# --------------------------------------------------------------------------

def create_youtube_radio_show(video_url: str, output_file: str = "radioshow.mp3",
                              lang: str = "en", host_name: str = "Ajarn Spencer",
                              host_voice: str = "Charon", caller1_voice: str = "Orus",
                              caller2_voice: str = "Kore", show_name: str = "Late Night Broadcast"):
    print(f"\n📺 Analyzing YouTube Video for Radio Show Generation...")
    print(f"• URL: {video_url}")
    print(f"• Host Name: {host_name}")
    print(f"• Language: {lang.upper()}")

    print("Fetching YouTube video transcript...")
    transcript = get_transcript(video_url, return_text=True)
    if not transcript:
        print("Error: Failed to fetch captions/transcript for this YouTube video.")
        print("Please verify the URL is valid and has captions enabled.")
        sys.exit(1)

    print(f"✓ Retrieved transcript ({len(transcript.split())} words).")

    try:
        client = get_client()
    except RuntimeError as e:
        print(f"Error: {e}")
        sys.exit(1)

    script_model = "gemini-2.5-flash"
    tts_model = resolve_working_gemini_tts_model(client)
    print(f"• Script Engine: {script_model}")
    print(f"• TTS Engine: {tts_model} (with multi-tiered Edge-TTS fallback)")

    if not show_name or show_name == "Late Night Broadcast":
        show_name = get_dynamic_show_name_from_transcript(transcript, client, script_model, lang)
    print(f"• Show Title: '{show_name}'")

    print(f"\nGenerating multi-speaker radio callers-in script with {script_model}...")
    script = generate_radio_script_from_transcript(transcript, client, script_model, lang=lang,
                                                   show_name=show_name, host_name=host_name)
    if not script:
        print("Error: Failed to generate script from transcript.")
        sys.exit(1)

    script = script.replace('"', '').replace("'", "")
    script = sanitize_dialogue_tags(script)

    print(f"\n--- Generated YouTube Radio Show Script ({lang.upper()}) ---")
    print(script)
    print("----------------------------------------------------------\n")

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


# --------------------------------------------------------------------------
# Main Entry Point
# --------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="YouTube AI Tool for Search, Transcript, Podcast & Radio Show.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    # Search
    search_p = subparsers.add_parser("search", help="Search YouTube for videos.")
    search_p.add_argument("query", type=str, help="Search query.")

    # Transcript
    trans_p = subparsers.add_parser("transcript", help="Get transcript for YouTube video.")
    trans_p.add_argument("url", type=str, help="YouTube video URL.")

    # Podcast (Solo narration)
    pod_p = subparsers.add_parser("podcast", help="Create a solo podcast from video transcript.")
    pod_p.add_argument("url", type=str, help="YouTube video URL.")
    pod_p.add_argument("--voice", type=str, default=None, help="TTS voice.")
    pod_p.add_argument("--rate", type=str, default=None, help="Speech rate.")
    pod_p.add_argument("--pitch", type=str, default=None, help="Speech pitch.")
    pod_p.add_argument("--output", "-o", type=str, default="podcast.mp3", help="Output filename.")

    # Radioshow (Callers-in show based on video transcript)
    radio_p = subparsers.add_parser("radioshow", help="Generate a multi-speaker radio show podcast from a YouTube video URL.")
    radio_p.add_argument("url", type=str, nargs="?", default=None, help="YouTube video URL.")
    radio_p.add_argument("--url", "-u", type=str, dest="opt_url", default=None, help="YouTube video URL.")
    radio_p.add_argument("--host", "--host-name", type=str, default="Ajarn Spencer", dest="host_name", help="Name of the host.")
    radio_p.add_argument("--output", "-o", type=str, default="radioshow.mp3", help="Output audio file (.mp3).")
    radio_p.add_argument("--lang", "-l", type=str, default="en", help="Language code (en, es, th).")
    radio_p.add_argument("--host-voice", type=str, default="Charon", help="Host voice model.")
    radio_p.add_argument("--caller1-voice", type=str, default="Orus", help="Caller 1 voice model.")
    radio_p.add_argument("--caller2-voice", type=str, default="Kore", help="Caller 2 voice model.")
    radio_p.add_argument("--show-name", type=str, default="Late Night Broadcast", help="Show title.")

    args = parser.parse_args()

    if args.command == "search":
        search_youtube(args.query)

    elif args.command == "transcript":
        get_transcript(args.url)

    elif args.command == "podcast":
        raw_url = args.url
        voice = args.voice
        rate = args.rate
        pitch = args.pitch
        output_file = args.output

        if ' ' in raw_url:
            try:
                sub_args = shlex.split(raw_url)
                sp = argparse.ArgumentParser()
                sp.add_argument("url", type=str)
                sp.add_argument("--voice", type=str, default=None)
                sp.add_argument("--rate", type=str, default=None)
                sp.add_argument("--pitch", type=str, default=None)
                sp.add_argument("--output", "-o", type=str, default="podcast.mp3")
                parsed_sub, _ = sp.parse_known_args(sub_args)
                raw_url = parsed_sub.url
                if parsed_sub.voice: voice = parsed_sub.voice
                if parsed_sub.rate: rate = parsed_sub.rate
                if parsed_sub.pitch: pitch = parsed_sub.pitch
                if parsed_sub.output: output_file = parsed_sub.output
            except Exception:
                pass

        create_podcast(raw_url, voice=voice, rate=rate, pitch=pitch, output_file=output_file)

    elif args.command == "radioshow":
        raw_url = args.opt_url or args.url

        if raw_url and ('--' in raw_url or raw_url.startswith('-')):
            try:
                sub_args = shlex.split(raw_url)
                sp = argparse.ArgumentParser()
                sp.add_argument("url", type=str, nargs="?", default=None)
                sp.add_argument("--url", "-u", type=str, dest="opt_url", default=None)
                sp.add_argument("--host", "--host-name", type=str, default=args.host_name, dest="host_name")
                sp.add_argument("--output", "-o", type=str, default=args.output)
                sp.add_argument("--lang", "-l", type=str, default=args.lang)
                sp.add_argument("--host-voice", type=str, default=args.host_voice)
                sp.add_argument("--caller1-voice", type=str, default=args.caller1_voice)
                sp.add_argument("--caller2-voice", type=str, default=args.caller2_voice)
                sp.add_argument("--show-name", type=str, default=args.show_name)
                parsed_sub, _ = sp.parse_known_args(sub_args)
                if parsed_sub.opt_url or parsed_sub.url:
                    raw_url = parsed_sub.opt_url or parsed_sub.url
                args.host_name = parsed_sub.host_name
                args.output = parsed_sub.output
                args.lang = parsed_sub.lang
                args.host_voice = parsed_sub.host_voice
                args.caller1_voice = parsed_sub.caller1_voice
                args.caller2_voice = parsed_sub.caller2_voice
                args.show_name = parsed_sub.show_name
            except Exception:
                pass

        if not raw_url:
            print("Error: Please provide a valid YouTube URL (e.g. /youtube:radioshow https://www.youtube.com/watch?v=VIDEO_ID [--host \"Host Name\"])")
            sys.exit(1)

        create_youtube_radio_show(
            video_url=raw_url,
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
