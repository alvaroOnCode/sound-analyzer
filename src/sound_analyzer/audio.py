from __future__ import annotations

import json
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

AUDIO_EXTENSIONS = {
    ".wav",
    ".wave",
    ".aiff",
    ".aif",
    ".flac",
    ".mp3",
    ".ogg",
    ".oga",
    ".m4a",
    ".aac",
    ".wma",
    ".caf",
    ".mp2",
    ".au",
}


class FFmpegError(RuntimeError):
    pass


def require_ffmpeg() -> None:
    if shutil.which("ffmpeg") is None or shutil.which("ffprobe") is None:
        raise FFmpegError(
            "Hace falta ffmpeg y ffprobe en el PATH "
            "(Homebrew, winget/choco o apt/dnf)."
        )


@dataclass(frozen=True)
class Probe:
    duration: float
    sample_rate: int
    channels: int
    codec: str


def probe(path: Path) -> Probe:
    require_ffmpeg()
    cmd = [
        "ffprobe",
        "-v",
        "error",
        "-show_entries",
        "format=duration:stream=codec_type,codec_name,sample_rate,channels",
        "-of",
        "json",
        str(path),
    ]
    try:
        raw = subprocess.check_output(cmd, stderr=subprocess.STDOUT)
    except subprocess.CalledProcessError as exc:
        raise FFmpegError(f"ffprobe falló con {path}: {exc.output[-400:]!r}") from exc
    data = json.loads(raw.decode("utf-8", errors="replace"))
    duration = float(data.get("format", {}).get("duration") or 0.0)
    audio_stream = {}
    for stream in data.get("streams") or []:
        if stream.get("codec_type") == "audio":
            audio_stream = stream
            break
    sample_rate = int(audio_stream.get("sample_rate") or 0)
    channels = int(audio_stream.get("channels") or 0)
    codec = str(audio_stream.get("codec_name") or "")
    return Probe(duration=duration, sample_rate=sample_rate, channels=channels, codec=codec)


def load_audio(
    path: Path,
    *,
    sr: int = 48000,
    start: float | None = None,
    duration: float | None = None,
    mono: bool = True,
) -> tuple:
    """Load audio as float32 numpy array via ffmpeg. Returns (samples, sample_rate)."""
    import numpy as np

    require_ffmpeg()
    cmd = ["ffmpeg", "-v", "error", "-nostdin"]
    if start is not None and start > 0:
        cmd += ["-ss", f"{start:.6f}"]
    cmd += ["-i", str(path)]
    if duration is not None and duration > 0:
        cmd += ["-t", f"{duration:.6f}"]
    if mono:
        cmd += ["-ac", "1"]
    cmd += ["-ar", str(sr), "-f", "f32le", "-"]
    try:
        raw = subprocess.check_output(cmd, stderr=subprocess.STDOUT)
    except subprocess.CalledProcessError as exc:
        raise FFmpegError(f"ffmpeg no pudo leer {path}: {exc.output[-400:]!r}") from exc
    samples = np.frombuffer(raw, dtype=np.float32).copy()
    return samples, sr


def extract_wav(
    src: Path,
    dest: Path,
    *,
    start: float | None = None,
    duration: float | None = None,
) -> None:
    require_ffmpeg()
    dest.parent.mkdir(parents=True, exist_ok=True)
    cmd = ["ffmpeg", "-y", "-v", "error", "-nostdin"]
    if start is not None and start > 0:
        cmd += ["-ss", f"{start:.6f}"]
    cmd += ["-i", str(src)]
    if duration is not None and duration > 0:
        cmd += ["-t", f"{duration:.6f}"]
    cmd += ["-acodec", "pcm_s16le", str(dest)]
    subprocess.check_call(cmd)


def play(path: Path, start: float | None = None, duration: float | None = None) -> None:
    """Preview with ffplay (available on macOS, Windows and Linux with ffmpeg)."""
    require_ffmpeg()
    player = shutil.which("ffplay")
    if player is None:
        raise FFmpegError("ffplay no está en el PATH (suele venir con ffmpeg).")
    cmd = [player, "-autoexit", "-nodisp", "-loglevel", "error"]
    if start is not None and start > 0:
        cmd += ["-ss", f"{start:.6f}"]
    if duration is not None and duration > 0:
        cmd += ["-t", f"{duration:.6f}"]
    cmd.append(str(path))
    subprocess.call(cmd)


def detect_silences(
    path: Path,
    *,
    noise_db: float = -35.0,
    min_silence: float = 0.35,
) -> str:
    """Return ffmpeg stderr with silencedetect lines."""
    require_ffmpeg()
    cmd = [
        "ffmpeg",
        "-hide_banner",
        "-nostdin",
        "-i",
        str(path),
        "-af",
        f"silencedetect=noise={noise_db}dB:d={min_silence}",
        "-f",
        "null",
        "-",
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    return (proc.stderr or "") + (proc.stdout or "")
