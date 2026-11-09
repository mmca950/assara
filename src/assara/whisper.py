"""faster-whisper wrapper: chunked transcription of one media file into cues.

faster-whisper computes the spectrogram of the whole file at once: a video of nearly two hours can run
out of memory and get the process killed without any message. The audio is therefore decoded once
(16 kHz mono float32, about 4 MB per minute) and transcribed in chunks of 10 minutes, which keeps memory
stable (about 1.2 GB with the "small" model on CPU).

faster-whisper 1.2 does not work with PyAV 19 (`unexpected keyword argument 'metadata_errors'`): the
`audio` extra pins `av==17.1.0`, which ships its own ffmpeg libraries (no system ffmpeg needed).
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from .library import AssaraError, install_hint, raw_output
from .srt import Cue

CHUNK_SECONDS = 600
SAMPLE_RATE = 16_000
INSTALL_HINT = install_hint("audio")

Transcriber = Callable[[Path], list[Cue]]


def compute_type_for(device: str, configured: str, device_overridden: bool) -> str:
    """Compute type to use. When --device overrides the configured device, use that device's usual type."""
    if device_overridden:
        return "float16" if device == "cuda" else "int8"
    return configured


def load_model(model: str, device: str, compute_type: str):
    try:
        from faster_whisper import WhisperModel
    except ImportError as e:
        raise AssaraError(f"Transcription needs faster-whisper ({e}); {INSTALL_HINT}") from e
    with raw_output():  # the first use downloads the model, with a progress bar
        return WhisperModel(model, device=device, compute_type=compute_type)


def has_audio(media: Path) -> bool:
    try:
        import av
    except ImportError as e:
        raise AssaraError(f"Transcription needs PyAV ({e}); {INSTALL_HINT}") from e
    with av.open(str(media)) as container:
        return bool(container.streams.audio)


def transcribe_file(whisper_model, media: Path, language: str | None) -> list[Cue]:
    """Transcribe one media file in chunks. A file without an audio track returns no cue."""
    if not has_audio(media):
        return []
    from faster_whisper.audio import decode_audio

    audio = decode_audio(str(media), sampling_rate=SAMPLE_RATE)
    step = CHUNK_SECONDS * SAMPLE_RATE
    cues: list[Cue] = []
    for begin in range(0, len(audio), step):
        offset = begin / SAMPLE_RATE
        segments, _ = whisper_model.transcribe(
            audio[begin : begin + step], language=language, vad_filter=True
        )
        for s in segments:
            text = s.text.strip()
            if text:
                cues.append(Cue(s.start + offset, s.end + offset, text))
    del audio
    return cues


def make_transcriber(model: str, device: str, compute_type: str, language: str | None) -> Transcriber:
    """Load the model once and return a function media -> cues."""
    whisper_model = load_model(model, device, compute_type)
    return lambda media: transcribe_file(whisper_model, media, language)
