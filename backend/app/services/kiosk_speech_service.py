"""WAV 검증과 faster-whisper 한국어 변환을 담당합니다."""

from pathlib import Path
from tempfile import NamedTemporaryFile
from threading import Lock
from time import perf_counter

from app.core.config import settings
from app.schemas.kiosk import TranscriptionResponse


MAX_AUDIO_BYTES = 10 * 1024 * 1024
WAV_MIME_TYPES = {"audio/wav", "audio/x-wav", "audio/wave"}
_model = None
_model_lock = Lock()


class InvalidAudioError(ValueError):
    pass


class SpeechModelUnavailableError(RuntimeError):
    pass


def transcribe_wav(audio: bytes, content_type: str | None) -> TranscriptionResponse:
    if not audio:
        raise InvalidAudioError("빈 음성 파일입니다.")
    if len(audio) > MAX_AUDIO_BYTES:
        raise InvalidAudioError("음성 파일은 10MB 이하여야 합니다.")
    if content_type not in WAV_MIME_TYPES:
        raise InvalidAudioError("WAV 형식의 음성 파일만 사용할 수 있습니다.")
    if len(audio) < 12 or audio[:4] != b"RIFF" or audio[8:12] != b"WAVE":
        raise InvalidAudioError("올바른 WAV 데이터가 아닙니다.")
    if settings.kiosk_stt_mode != "faster_whisper":
        raise SpeechModelUnavailableError("지원하지 않는 STT 모드입니다.")

    model = _get_model()
    temporary_path: Path | None = None
    started = perf_counter()
    try:
        with NamedTemporaryFile(suffix=".wav", delete=False) as temporary:
            temporary.write(audio)
            temporary_path = Path(temporary.name)
        segments, _info = model.transcribe(str(temporary_path), language="ko")
        text = " ".join(segment.text.strip() for segment in segments if segment.text.strip()).strip()
        return TranscriptionResponse(
            text=text,
            provider="faster-whisper",
            model=settings.kiosk_stt_model,
            latency_ms=round((perf_counter() - started) * 1000),
        )
    finally:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)


def _get_model():
    global _model
    if _model is not None:
        return _model
    with _model_lock:
        if _model is None:
            try:
                from faster_whisper import WhisperModel

                _model = WhisperModel(settings.kiosk_stt_model, device="cpu", compute_type="int8")
            except Exception as error:
                raise SpeechModelUnavailableError("STT 모델을 준비하지 못했습니다.") from error
    return _model
