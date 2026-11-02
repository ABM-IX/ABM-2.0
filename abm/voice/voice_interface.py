"""
abm/voice/voice_interface.py
=============================
ABM 2.0 — Voice Interface, Phase F Step 1: push-to-talk (NOT always-listening)

Honest scope note: this is push-to-talk, not the "always listening, say
'ABM 2.0 launch' and it wakes up" wake-word experience. Wake-word detection
needs a background audio service plus a keyword-spotting model tuned against
a real microphone and a real voice — that cannot be built or verified
without a live mic, so it is deliberately left for a separate step once this
foundation is confirmed working. Trying to claim both in one shot is exactly
the "reported done, wasn't" pattern this project has already been burned by.

Design contract (same discipline as abm/tray_app.py):
  - Pure I/O wrapper. Adds ZERO new reasoning or memory logic. Every question
    goes through the exact same /api/ask endpoint the web UI and phone client
    already use — same orchestrator, same quad-stream memory, same
    sensitivity classifier, same Groq gateway, same session/history handling.
  - STT: Groq Whisper (whisper-large-v3-turbo) — reuses the same GROQ_API_KEY
    env var as abm/orchestrator/groq_gateway.py. No new account, no new key.
    On failure: raise, do not silently return an empty transcript.
  - TTS: pyttsx3, fully local/offline (SAPI5 on Windows). Zero cloud cost,
    zero new cloud dependency, negligible CPU/RAM — will not compete with a
    game for resources.
  - sounddevice and pyttsx3 are optional at import time — missing them gives
    a clear VoiceDependencyError, not a cryptic ImportError (same pattern as
    abm/tray_app.py's _check_tray_deps).
  - Requires the ABM web API already running (python -m abm.launcher, or via
    the tray app) — this module never boots the registry/orchestrator itself.

Usage:
    python -m abm.voice.voice_interface
    # Press Enter to start a 6-second recording, speak your question, ABM
    # answers out loud. Ctrl+C to quit. Conversation carries a session_id
    # across turns, same rolling-history behavior as the web UI.
"""

from __future__ import annotations

import logging
import os
import sys
import tempfile
import wave
from pathlib import Path
from typing import Optional

import requests

logger = logging.getLogger(__name__)

GROQ_API_KEY_ENV = "GROQ_API_KEY"
GROQ_TRANSCRIPTION_URL = "https://api.groq.com/openai/v1/audio/transcriptions"
# Full whisper-large-v3, not the -turbo variant: turbo trades accuracy for
# speed, and Arabang reported real spelling/word errors in transcripts —
# accuracy matters more than the latency difference here.
GROQ_WHISPER_MODEL = "whisper-large-v3"
# Added 2026-11-02: Arabang reported real latency on every always-listening
# cycle, including the short wait just to hear "I'm listening" back — most
# of that is Whisper round-trip time, and the full model is markedly slower
# than turbo. A wake-word-only cycle just needs to roughly catch "ABM 2.0",
# not transcribe it with full accuracy, so it uses turbo; the moment an
# actual command is being transcribed (accuracy matters — "Spotify" vs
# nonsense), it switches back to the full model. See denoise_wav_bytes's
# caller (abm/clients/web/main.py) and ChatInterface.jsx for which calls
# request which mode.
GROQ_WHISPER_MODEL_FAST = "whisper-large-v3-turbo"

# Vocabulary hint passed as Whisper's "prompt" param — biases transcription
# toward these proper nouns/terms instead of guessing a phonetically similar
# common word. Keep this list short; Whisper only uses it as a light nudge.
GROQ_WHISPER_VOCAB_HINT = (
    "ABM, ABM 2.0, First Minds, Groq, SmartTransit, CleanNova, Mokgosi, "
    "Leseding, Orange Summer Challenge, Gaborone, Botswana, ChromaDB, "
    # App-launching vocabulary (2026-11-02): Arabang reported "Spotify"
    # getting mis-transcribed entirely (came back as "45") — the prompt
    # hint only had project names, nothing from his actual app-launching
    # vocabulary, so Whisper had nothing to bias toward for these.
    "Spotify, WhatsApp, Steam, FC 26, EA Sports FC, open, close, launch, "
    "start, quit."
)

DEFAULT_ABM_BASE_URL = "http://localhost:8080"
DEFAULT_RECORD_SECONDS = 6.0
DEFAULT_SAMPLE_RATE = 16000


class VoiceDependencyError(RuntimeError):
    """Raised when sounddevice or pyttsx3 are not installed."""
    pass


class VoiceInterfaceError(RuntimeError):
    """Raised on a real failure (STT, ask, or ABM API) — never swallowed."""
    pass


def _check_voice_deps() -> tuple:
    """Return (sounddevice module, pyttsx3 module) or raise VoiceDependencyError."""
    try:
        import sounddevice as sd
        import pyttsx3
        return sd, pyttsx3
    except ImportError as exc:
        raise VoiceDependencyError(
            "ABM voice interface requires 'sounddevice' and 'pyttsx3'. "
            "Install them with: pip install sounddevice pyttsx3\n"
            f"Original error: {exc}"
        ) from exc


# ---------------------------------------------------------------------------
# Recording
# ---------------------------------------------------------------------------


def record_audio(
    duration_s: float = DEFAULT_RECORD_SECONDS,
    samplerate: int = DEFAULT_SAMPLE_RATE,
) -> Path:
    """
    Record `duration_s` seconds of mono audio from the default microphone
    and write it to a temp 16-bit PCM WAV file.

    Returns the Path to the temp file. Caller is responsible for deleting it
    (or rely on process exit / OS temp cleanup).
    """
    sd, _ = _check_voice_deps()
    import numpy as np  # sounddevice already depends on numpy — no new requirement

    logger.info("record_audio: recording %.1fs at %d Hz...", duration_s, samplerate)
    frames = sd.rec(int(duration_s * samplerate), samplerate=samplerate, channels=1, dtype="int16")
    sd.wait()

    tmp = tempfile.NamedTemporaryFile(prefix="abm_voice_", suffix=".wav", delete=False)
    tmp_path = Path(tmp.name)
    tmp.close()

    with wave.open(str(tmp_path), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)  # int16 = 2 bytes
        wf.setframerate(samplerate)
        wf.writeframes(frames.tobytes())

    logger.info("record_audio: wrote %s", tmp_path)
    return tmp_path


# ---------------------------------------------------------------------------
# Noise suppression (Arabang's WebRTC suppressor, reused from the Leseding /
# Orange Summer Challenge telephony project — abm/voice/noise_suppression.py
# is a verbatim copy of LSSAP/packages/lesedi-telephony-ns's module).
#
# Added 2026-11-02: background music/noise was confusing wake-word detection
# in the web UI's always-listening loop. This runs the same suppressor his
# telephony pipeline uses, right before transcription, for BOTH the web
# mic path (abm/clients/web/main.py) and this CLI's push-to-talk path.
#
# Fails open by design: if `pywebrtc-audio` isn't installed, or anything
# about a given recording confuses it, this just returns the original audio
# unchanged. Noise suppression is a nice-to-have on top of voice input, and
# must never become the reason voice input stops working.
# ---------------------------------------------------------------------------

_NOISE_SUPPRESSOR_STATE = {"tried": False, "module": None}

# The suppressor only runs at these native WebRTC rates — anything else gets
# linearly resampled to the closest one below before processing.
_SUPPRESSOR_SAMPLE_RATES = (8000, 16000, 32000, 48000)


def _load_noise_suppressor():
    """
    Import and initialize abm.voice.noise_suppression exactly once per
    process. Returns the module on success, or None if it's not installed
    or failed to load — callers must treat None as "skip suppression",
    never as an error.
    """
    if _NOISE_SUPPRESSOR_STATE["tried"]:
        return _NOISE_SUPPRESSOR_STATE["module"]
    _NOISE_SUPPRESSOR_STATE["tried"] = True
    try:
        from abm.voice import noise_suppression as ns
        ns.load_model()
        _NOISE_SUPPRESSOR_STATE["module"] = ns
        logger.info("Noise suppression ready (pywebrtc-audio loaded).")
        return ns
    except Exception as exc:
        logger.warning(
            "Noise suppression unavailable (%s) — voice input still works, "
            "just without background-noise cleanup. Install with: "
            "pip install pywebrtc-audio==0.2.0 numpy",
            exc,
        )
        return None


def _resample_linear_int16(samples, src_rate: int, dst_rate: int):
    """Minimal dependency-light resampler (linear interpolation) for int16
    PCM. Not hi-fi, but perfectly adequate for feeding a short spoken
    command into a noise suppressor — this project avoids pulling in scipy
    just for this, same as the Lesedi toolkit avoids ffmpeg."""
    import numpy as np

    if src_rate == dst_rate or len(samples) == 0:
        return samples
    duration_s = len(samples) / float(src_rate)
    dst_len = max(1, int(round(duration_s * dst_rate)))
    src_x = np.linspace(0, len(samples) - 1, num=dst_len)
    resampled = np.interp(src_x, np.arange(len(samples)), samples.astype(np.float64))
    return resampled.astype(np.int16)


def denoise_wav_bytes(wav_bytes: bytes) -> bytes:
    """
    Run the WebRTC noise suppressor over a WAV recording's audio and return
    a cleaned WAV. Fails open on any problem — suppressor not installed,
    an odd/corrupt WAV, a processing error — by returning the ORIGINAL
    bytes unchanged, logged but not raised.
    """
    ns = _load_noise_suppressor()
    if ns is None:
        return wav_bytes

    import io
    import wave as _wave

    import numpy as np

    try:
        with _wave.open(io.BytesIO(wav_bytes), "rb") as wf:
            n_channels = wf.getnchannels()
            sample_rate = wf.getframerate()
            sample_width = wf.getsampwidth()
            raw = wf.readframes(wf.getnframes())

        if sample_width != 2:
            logger.debug("denoise_wav_bytes: skipping — only 16-bit PCM WAV is handled.")
            return wav_bytes

        samples = np.frombuffer(raw, dtype="<i2")
        if n_channels > 1:
            samples = samples.reshape(-1, n_channels).mean(axis=1).astype("<i2")

        target_rate = sample_rate if sample_rate in _SUPPRESSOR_SAMPLE_RATES else 16000
        if target_rate != sample_rate:
            samples = _resample_linear_int16(samples, sample_rate, target_rate)

        suppressor = ns.create_suppressor(sample_rate=target_rate)
        try:
            # The suppressor has a fixed, documented input->output delay
            # (queue buffering + the native WebRTC filterbank's own internal
            # delay, exposed as .latency_samples) — feeding it one whole
            # utterance in a single call means the LAST latency_samples of
            # real processed audio would otherwise stay stuck in its
            # internal queue, never handed back. Padding the tail with that
            # many silent samples flushes it all out in this one call, and
            # slicing the same offset back off the front undoes the delay —
            # the result lines back up sample-for-sample with the input.
            latency = suppressor.latency_samples
            padded = np.concatenate([samples, np.zeros(latency, dtype="<i2")])
            cleaned_padded = np.frombuffer(suppressor.process(padded.tobytes()), dtype="<i2")
            cleaned_pcm = cleaned_padded[latency:latency + len(samples)].tobytes()
        finally:
            suppressor.close()

        out = io.BytesIO()
        with _wave.open(out, "wb") as wf_out:
            wf_out.setnchannels(1)
            wf_out.setsampwidth(2)
            wf_out.setframerate(target_rate)
            wf_out.writeframes(cleaned_pcm)
        return out.getvalue()
    except Exception as exc:
        logger.warning("denoise_wav_bytes: suppression failed, using original audio — %s", exc)
        return wav_bytes


# ---------------------------------------------------------------------------
# Speech-to-text (Groq Whisper)
# ---------------------------------------------------------------------------


def transcribe_with_groq(wav_path: Path, api_key: Optional[str] = None, model: Optional[str] = None) -> str:
    """
    Transcribe a WAV file via Groq's Whisper endpoint.

    Raises VoiceInterfaceError on any failure — never returns a silent
    empty/placeholder transcript, matching the project's no-silent-fallback
    rule for cloud calls (same as groq_gateway.py).
    """
    key = api_key or os.environ.get(GROQ_API_KEY_ENV)
    if not key:
        raise VoiceInterfaceError(
            f"{GROQ_API_KEY_ENV} is not set — cannot transcribe. "
            "Voice input requires the same Groq key the text pipeline uses."
        )

    try:
        with open(wav_path, "rb") as f:
            response = requests.post(
                GROQ_TRANSCRIPTION_URL,
                headers={"Authorization": f"Bearer {key}"},
                files={"file": (wav_path.name, f, "audio/wav")},
                data={
                    "model": model or GROQ_WHISPER_MODEL,
                    "language": "en",
                    "prompt": GROQ_WHISPER_VOCAB_HINT,
                },
                timeout=30,
            )
        response.raise_for_status()
    except requests.exceptions.ConnectionError as exc:
        raise VoiceInterfaceError(f"Could not reach Groq for transcription: {exc}") from exc
    except requests.exceptions.Timeout as exc:
        raise VoiceInterfaceError(f"Groq transcription timed out: {exc}") from exc
    except requests.exceptions.HTTPError as exc:
        raise VoiceInterfaceError(f"Groq transcription failed ({response.status_code}): {response.text}") from exc

    text = response.json().get("text", "").strip()
    if not text:
        raise VoiceInterfaceError(
            "Groq returned an empty transcript — likely silence or an "
            "unreadable recording. Try again, closer to the mic."
        )
    return text


# ---------------------------------------------------------------------------
# Text-to-speech (local, offline)
# ---------------------------------------------------------------------------


def speak(text: str) -> None:
    """Speak `text` out loud via the local, offline TTS engine. Blocks until done."""
    _, pyttsx3 = _check_voice_deps()
    engine = pyttsx3.init()
    engine.say(text)
    engine.runAndWait()


# ---------------------------------------------------------------------------
# Talking to ABM's existing pipeline (same endpoint the web UI uses)
# ---------------------------------------------------------------------------


def ask_abm(
    question: str,
    base_url: str = DEFAULT_ABM_BASE_URL,
    session_id: Optional[str] = None,
) -> dict:
    """
    POST to ABM's existing /api/ask endpoint — the exact same one the web UI
    and phone client use. No new reasoning/memory path is introduced here.

    Returns the parsed JSON response (contains "synthesis", "session_id", etc).
    """
    payload = {"question": question}
    if session_id:
        payload["session_id"] = session_id

    try:
        response = requests.post(f"{base_url}/api/ask", json=payload, timeout=120)
        response.raise_for_status()
    except requests.exceptions.ConnectionError as exc:
        raise VoiceInterfaceError(
            f"Could not reach ABM at {base_url} — is it running? "
            "(launch via the tray app, or `python -m abm.launcher`)"
        ) from exc
    except requests.exceptions.HTTPError as exc:
        raise VoiceInterfaceError(f"ABM API returned an error: {response.status_code} {response.text}") from exc

    return response.json()


# ---------------------------------------------------------------------------
# One full voice turn
# ---------------------------------------------------------------------------


def run_voice_turn(
    base_url: str = DEFAULT_ABM_BASE_URL,
    session_id: Optional[str] = None,
    record_seconds: float = DEFAULT_RECORD_SECONDS,
) -> Optional[str]:
    """
    Record -> transcribe -> ask ABM -> speak the reply.

    Returns the session_id to reuse on the next turn (keeps the rolling
    conversation, same as the web UI), or None if the turn failed.
    """
    wav_path = record_audio(duration_s=record_seconds)
    try:
        wav_path.write_bytes(denoise_wav_bytes(wav_path.read_bytes()))
        question = transcribe_with_groq(wav_path)
    finally:
        try:
            wav_path.unlink(missing_ok=True)
        except Exception:
            pass

    print(f"You said: {question}")

    result = ask_abm(question, base_url=base_url, session_id=session_id)
    answer = result.get("synthesis", "")
    print(f"ABM: {answer}")

    if answer:
        speak(answer)

    return result.get("session_id", session_id)


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------


def main() -> None:
    try:
        from dotenv import load_dotenv
        load_dotenv()
    except ImportError:
        pass

    logging.basicConfig(level=logging.INFO)

    try:
        _check_voice_deps()
    except VoiceDependencyError as exc:
        print(f"\n[ABM Voice] {exc}", file=sys.stderr)
        sys.exit(1)

    print("ABM 2.0 — Voice Interface (push-to-talk)")
    print("Press Enter to record 6 seconds, Ctrl+C to quit.\n")

    session_id: Optional[str] = None
    while True:
        try:
            input("[Enter to talk] ")
        except KeyboardInterrupt:
            print("\nBye.")
            return

        try:
            session_id = run_voice_turn(session_id=session_id)
        except VoiceInterfaceError as exc:
            print(f"[ABM Voice] {exc}", file=sys.stderr)


if __name__ == "__main__":
    main()
