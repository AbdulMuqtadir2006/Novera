"""Text-to-speech synthesis for the WhatsApp voice-note tool (2026-08-23).

Uses gTTS (a thin wrapper around Google Translate's public TTS endpoint) —
no API key, no ffmpeg/audio-encoder dependency, output is directly valid
MP3 bytes. Chosen over a paid TTS API (OpenAI/ElevenLabs) specifically to
avoid adding a new required secret for what's currently a single low-volume
feature; revisit if voice notes get heavy real-world use, since this is an
unofficial endpoint with no uptime/rate-limit guarantee.
"""
from __future__ import annotations

import io

from gtts import gTTS, gTTSError

# gTTS's language codes match this app's own lang strings ("en"/"ar")
# directly — no translation table needed.
_SUPPORTED_LANGS = {"en", "ar"}


class TTSError(Exception):
    pass


def synthesize(text: str, lang: str = "en") -> bytes:
    """Returns MP3 bytes for `text` spoken in `lang`. Raises TTSError on
    any failure (network, rate limit, empty text) — callers should degrade
    to sending the script as a written message rather than propagate."""
    text = (text or "").strip()
    if not text:
        raise TTSError("empty text")
    gtts_lang = lang if lang in _SUPPORTED_LANGS else "en"
    try:
        buf = io.BytesIO()
        gTTS(text=text, lang=gtts_lang).write_to_fp(buf)
        return buf.getvalue()
    except gTTSError as exc:
        raise TTSError(str(exc)) from exc
