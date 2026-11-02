# Copied verbatim (2026-11-02) from Arabang's own lesedi-telephony-ns
# package (LSSAP / Leseding AI Engine, Orange Summer Challenge project):
# LSSAP/packages/lesedi-telephony-ns/src/audio/noise_suppression.py
# The original file is untouched — this is a read-only copy, reused here
# so ABM 2.0's always-listening wake-word loop can filter out background
# noise/music the same way Lesedi's telephony pipeline does.
# Requires the `pywebrtc-audio` package (see requirements.txt) to actually
# suppress anything — see abm/voice/voice_interface.py's denoise_wav_bytes()
# for the fail-open integration that calls into this module.

"""Opt-in, per-call WebRTC noise suppression for 8 kHz PCM16 telephony audio.

The underlying WebRTC processor is optional. Importing this module does not load
native code; call :func:`load_model` once during application startup.

Aligned delay and timing contract:
    At 8 kHz telephony sampling, the suppressor introduces an end-to-end algorithmic
    delay of exactly 224 samples (28.0 ms). This comprises 152 samples of chunk-invariant
    output queue buffering plus 72 samples of internal WebRTC sub-band filterbank delay,
    verified by broadband cross-correlation against ground truth.

    :func:`speech_probability` reports speech probability corresponding to the last
    10 ms frame processed, temporally aligned with the output audio stream delayed by
    ``latency_samples`` (224 samples / 28 ms).
"""

from __future__ import annotations

from collections import deque
import logging
import math
import threading
import time
from typing import Any, Optional, Union

import numpy as np

logger = logging.getLogger(__name__)
WEBRTC_AUDIO_VERSION = "0.2.0"
_init_lock = threading.Lock()
_processor_type = None


def load_model() -> None:
    """Idempotently import the local CPU WebRTC processor; performs no I/O."""
    global _processor_type
    if _processor_type is not None:
        return
    with _init_lock:
        if _processor_type is None:
            from pywebrtc_audio import AudioProcessor
            _processor_type = AudioProcessor


class WebRtcSuppressor:
    """Stateful mono PCM16LE suppressor, intended to be owned by one call."""

    _CALIBRATED_DELAYS = {
        8000: (152, 72),     # (queue_samples, dsp_samples) -> 224 total (28.00 ms)
        16000: (304, 96),    # -> 400 total (25.00 ms)
        32000: (608, 196),   # -> 804 total (25.12 ms)
        48000: (912, 334),   # -> 1246 total (25.96 ms)
    }

    def __init__(
        self,
        sample_rate: int = 8000,
        level: int = 1,
        smoother_window: int = 4,
        hangover_frames: int = 12,
        hangover_decay: float = 0.90,
    ):
        if sample_rate not in self._CALIBRATED_DELAYS:
            raise ValueError(
                f"sample_rate must be one of {sorted(self._CALIBRATED_DELAYS.keys())}; received {sample_rate}"
            )
        if level not in range(4):
            raise ValueError("level must be from 0 to 3")
        if _processor_type is None:
            raise RuntimeError(
                "call load_model() once during process startup before creating call suppressors"
            )
        self.sample_rate = sample_rate
        self.frame_samples = sample_rate // 100
        self._queue_samples, self._measured_dsp_delay = self._CALIBRATED_DELAYS[sample_rate]
        self.latency_samples = self._queue_samples + self._measured_dsp_delay

        # Delay check accepts up to 30 ms per integration specification
        if self.latency_samples * 1000 / sample_rate > 30.5:
            raise ValueError("configured processor delay exceeds 30 ms")

        self._processor = _processor_type(
            sample_rate=sample_rate,
            num_channels=1,
            noise_suppression=True,
            echo_cancellation=False,
            high_pass_filter=False,
            auto_gain_control=False,
            ns_level=level,
        )
        self._input = bytearray()
        self._output = deque([b"\0\0"] * self._queue_samples)

        # Speech probability smoothing state (Fix 4)
        self._raw_probability: Optional[float] = None
        self._smoothed_probability: Optional[float] = None
        self._prob_window: deque[float] = deque(maxlen=smoother_window)
        self._hangover_frames = hangover_frames
        self._hangover_count = 0
        self._hangover_decay = hangover_decay
        self._closed = False

    def process(self, pcm16: Union[bytes, bytearray, memoryview]) -> bytes:
        """Process any bytes-like chunk and return exactly its length in stream order.

        Accepts bytes, bytearray, or memoryview. A byte carry handles odd chunk
        boundaries. A fixed 10 ms frame boundary keeps enhancement independent of
        the caller's chunk sizes.
        """
        if not isinstance(pcm16, (bytes, bytearray, memoryview)):
            raise TypeError("pcm16 must be a bytes-like object containing mono PCM16LE")
        if self._closed:
            raise RuntimeError("suppressor is closed; reset it before reuse")

        self._input.extend(pcm16)
        frame_bytes = self.frame_samples * 2
        while len(self._input) >= frame_bytes:
            block = bytes(self._input[:frame_bytes])
            del self._input[:frame_bytes]
            audio = np.frombuffer(block, dtype="<i2").copy()
            cleaned = self._processor.process(audio)

            # WebRTC APM probability for this 10 ms frame
            prob = float(self._processor.speech_probability)
            if math.isfinite(prob):
                prob = min(1.0, max(0.0, prob))
                self._raw_probability = prob
                self._update_smoothed_probability(prob)
            else:
                self._raw_probability = None
                self._smoothed_probability = None

            self._output.append(np.asarray(cleaned, dtype="<i2").tobytes())

        wanted = len(pcm16)
        result = bytearray()
        while wanted:
            head = self._output[0]
            take = min(wanted, len(head))
            result.extend(head[:take])
            if take == len(head):
                self._output.popleft()
            else:
                self._output[0] = head[take:]
            wanted -= take
        return bytes(result)

    def _update_smoothed_probability(self, raw_prob: float) -> None:
        """Update moving-average window and hangover decay for the 10 ms frame."""
        self._prob_window.append(raw_prob)
        ma = sum(self._prob_window) / len(self._prob_window)

        # When moving average indicates speech, refresh hangover counter
        if ma >= 0.45:
            self._hangover_count = self._hangover_frames
            self._smoothed_probability = ma
        else:
            if self._hangover_count > 0:
                self._hangover_count -= 1
                # Smooth decay across short unvoiced / inter-syllable pauses
                prev = self._smoothed_probability if self._smoothed_probability is not None else ma
                self._smoothed_probability = prev * self._hangover_decay + ma * (1.0 - self._hangover_decay)
            else:
                self._smoothed_probability = ma

    def speech_probability(self, smoothed: bool = True) -> Optional[float]:
        """Return speech probability estimate for the latest processed 10 ms frame.

        Alignment and timing:
            Refers to the last 10 ms frame of the processed chunk,
            temporally aligned with the output audio stream delayed by
            `latency_samples` (224 samples / 28 ms at 8 kHz).

        Args:
            smoothed: If True (default), returns smoothed probability (short
                moving average with hangover) that eliminates turn splitting
                and spurious noise triggers in babble and road noise. If False,
                returns raw instantaneous WebRTC spectral probability.

        Recommended threshold:
            0.50 (or 0.45 in heavy noise) for telephony conversational turn detection.
        """
        return self._smoothed_probability if smoothed else self._raw_probability

    def raw_speech_probability(self) -> Optional[float]:
        """Return raw instantaneous WebRTC spectral speech estimate."""
        return self._raw_probability

    def reset(self) -> None:
        """Clear frame, output-delay, VAD and noise-suppression state."""
        self._processor.reset()
        self._input.clear()
        self._output.clear()
        self._output.extend([b"\0\0"] * self._queue_samples)
        self._raw_probability = None
        self._smoothed_probability = None
        self._prob_window.clear()
        self._hangover_count = 0
        self._closed = False

    def close(self) -> None:
        """Close suppressor and release internal buffers."""
        self._closed = True
        self._input.clear()
        self._output.clear()

    def __enter__(self) -> "WebRtcSuppressor":
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        self.close()


def create_suppressor(sample_rate: int = 8000) -> "SafeCallSuppressor":
    """Create independent suppressor and fail-open state for one call."""
    return SafeCallSuppressor(WebRtcSuppressor(sample_rate=sample_rate))


class SafeCallSuppressor:
    """Call-scoped fail-open guard with window-based overrun protection."""

    def __init__(
        self,
        suppressor: WebRtcSuppressor,
        max_process_ms: float = 5.0,
        window_size: int = 50,
        max_overruns_in_window: int = 3,
    ):
        self._suppressor = suppressor
        self.sample_rate = suppressor.sample_rate
        self.latency_samples = suppressor.latency_samples
        self.max_process_ms = max_process_ms
        self.window_size = window_size
        self.max_overruns_in_window = max_overruns_in_window
        self.disabled = False
        self.fallback_reason: Optional[str] = None
        self._overrun_window: deque[bool] = deque(maxlen=window_size)
        self._logged = False

    def process(self, pcm16: Union[bytes, bytearray, memoryview]) -> bytes:
        if self.disabled:
            return bytes(pcm16) if not isinstance(pcm16, bytes) else pcm16

        started = time.perf_counter()
        try:
            output = self._suppressor.process(pcm16)
        except Exception as exc:
            self._disable(f"processing error: {type(exc).__name__}: {exc}")
            return bytes(pcm16) if not isinstance(pcm16, bytes) else pcm16

        elapsed_ms = (time.perf_counter() - started) * 1000
        is_overrun = elapsed_ms > self.max_process_ms
        self._overrun_window.append(is_overrun)

        # Trip guard only if overrun threshold is reached in sliding window (Fix 5)
        if len(self._overrun_window) >= 10 and sum(self._overrun_window) >= self.max_overruns_in_window:
            self._disable(
                f"processing exceeded {self.max_process_ms:g} ms {sum(self._overrun_window)} "
                f"times in last {len(self._overrun_window)} frames"
            )
            return bytes(pcm16) if not isinstance(pcm16, bytes) else pcm16

        if len(output) != len(pcm16):
            self._disable("processor violated exact-length output contract")
            return bytes(pcm16) if not isinstance(pcm16, bytes) else pcm16

        return output

    def speech_probability(self, smoothed: bool = True) -> Optional[float]:
        return None if self.disabled else self._suppressor.speech_probability(smoothed=smoothed)

    def raw_speech_probability(self) -> Optional[float]:
        return None if self.disabled else self._suppressor.raw_speech_probability()

    def reset(self) -> None:
        self._suppressor.reset()
        self.disabled = False
        self.fallback_reason = None
        self._overrun_window.clear()
        self._logged = False

    def close(self) -> None:
        self._suppressor.close()

    def __enter__(self) -> "SafeCallSuppressor":
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        self.close()

    def _disable(self, reason: str) -> None:
        self.disabled = True
        self.fallback_reason = reason
        if not self._logged:
            logger.warning("Noise suppression disabled for this call: %s", reason)
            self._logged = True


__all__ = [
    "WEBRTC_AUDIO_VERSION",
    "load_model",
    "create_suppressor",
    "WebRtcSuppressor",
    "SafeCallSuppressor",
]
