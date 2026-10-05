"""音频解码与归一 / Audio decoding and normalisation.

sherpa-onnx 的 UVR 分离模型**只接受 wav、且要求 44.1 kHz 立体声**（官方：
`ffmpeg -i in.mp4 -vn -acodec pcm_s16le -ar 44100 -ac 2 out.wav`）。
所以本模块的解码出口是 44.1 kHz 立体声，而不是语音识别常用的 16 kHz 单声道。

另外实测一条硬约束：**各轨输出与输入严格等长**（`shape[1]` 完全一致）。
本模块仍在门面做样本数校验 —— 时间轴漂移是最难查的一类静默 bug。
"""

from __future__ import annotations

import shutil
import subprocess
import tempfile
from pathlib import Path

import numpy as np
import soundfile as sf

from agentic_audioprocess.core.errors import DecodeError
from agentic_audioprocess.core.logging import get_logger
from agentic_audioprocess.core.types import AudioChunk

log = get_logger("audio.io")

SEPARATION_SR = 44100
SEPARATION_CH = 2
_FFMPEG = shutil.which("ffmpeg")


def ffmpeg_available() -> bool:
    return _FFMPEG is not None


def decode(path: str | Path, target_sr: int = SEPARATION_SR,
           channels: int = SEPARATION_CH) -> AudioChunk:
    """解码为分离模型要的形状 / decode into what the separation models want.

    返回的 `samples` 形状是 `(num_samples, channels)`。

    抛出 / Raises:
        DecodeError: 文件不存在，或 ffmpeg 解码失败。
    """
    p = Path(path)
    if not p.is_file():
        raise DecodeError(f"文件不存在 / no such file: {p}")
    if _FFMPEG is None:
        raise DecodeError("解码需要 ffmpeg / ffmpeg is required on PATH")

    cmd = [_FFMPEG, "-v", "error", "-nostdin", "-i", str(p), "-vn", "-sn", "-dn",
           "-map", "0:a:0", "-ac", str(channels), "-ar", str(target_sr),
           "-f", "f32le", "-"]
    proc = subprocess.run(cmd, capture_output=True, check=False)
    if proc.returncode != 0:
        tail = (proc.stderr or b"").decode("utf-8", "replace").strip().splitlines()[-3:]
        raise DecodeError(f"ffmpeg 解码失败 / decode failed: " + " / ".join(tail))
    flat = np.frombuffer(proc.stdout, dtype=np.float32)
    if flat.size == 0:
        raise DecodeError(f"解码结果为空 / decoded nothing: {p}")
    if channels > 1:
        flat = flat[: (flat.size // channels) * channels].reshape(-1, channels)
    return AudioChunk(samples=np.ascontiguousarray(flat, dtype=np.float32),
                      sample_rate=target_sr, source=str(p))


def read_wav(path: str | Path) -> AudioChunk:
    """直接读 wav（不做重采样）/ read a wav without resampling."""
    p = Path(path)
    if not p.is_file():
        raise DecodeError(f"文件不存在 / no such file: {p}")
    data, sr = sf.read(str(p), dtype="float32", always_2d=True)
    return AudioChunk(samples=np.ascontiguousarray(data, dtype=np.float32),
                      sample_rate=sr, source=str(p))


def write_wav(path: str | Path, samples: np.ndarray, sample_rate: int) -> Path:
    """写 16-bit wav（自动建目录）/ write a 16-bit wav, creating parent dirs."""
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    data = np.asarray(samples, dtype=np.float32)
    sf.write(str(p), data, sample_rate, subtype="PCM_16")
    return p


def to_wav_file(chunk: AudioChunk, dst: str | Path) -> Path:
    """把内存里的音频落成 wav 文件（引擎需要路径）/ persist a chunk to a wav file."""
    return write_wav(dst, chunk.samples, chunk.sample_rate)


def to_ffmpeg_wav(src: str | Path, dst: str | Path, sample_rate: int = SEPARATION_SR,
                  channels: int = SEPARATION_CH) -> Path:
    """转成规范 wav / convert to the canonical separation input."""
    src_p, dst_p = Path(src), Path(dst)
    dst_p.parent.mkdir(parents=True, exist_ok=True)
    if _FFMPEG is None:
        raise DecodeError("转 wav 需要 ffmpeg / ffmpeg is required")
    cmd = [_FFMPEG, "-v", "error", "-nostdin", "-y", "-i", str(src_p), "-vn",
           "-acodec", "pcm_s16le", "-ar", str(sample_rate), "-ac", str(channels),
           str(dst_p)]
    proc = subprocess.run(cmd, capture_output=True, check=False)
    if proc.returncode != 0 or not dst_p.is_file():
        tail = (proc.stderr or b"").decode("utf-8", "replace").strip().splitlines()[-3:]
        raise DecodeError("转 wav 失败 / conversion failed: " + " / ".join(tail))
    return dst_p


def temp_wav_path(suffix: str = ".wav") -> Path:
    """临时 wav 路径 / a temp wav path inside its own directory."""
    return Path(tempfile.mkdtemp(prefix="agentic_sep_")) / f"input{suffix}"


__all__ = [
    "SEPARATION_CH",
    "SEPARATION_SR",
    "decode",
    "ffmpeg_available",
    "read_wav",
    "temp_wav_path",
    "to_ffmpeg_wav",
    "to_wav_file",
    "write_wav",
]
