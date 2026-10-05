"""音频解码与归一 / decoding.

复测 / rerun:
    C:\\Users\\75203\\miniforge3\\envs\\ov_env_py312\\python.exe -m pytest tests/test_audio.py -q

覆盖 / covers: 44.1 kHz 立体声归一、写盘、语音占比检测（含能量回退）。
说明文档 / docs: docs/01_design.md §4
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest
import soundfile as sf

from agentic_audioprocess.audio.io import SEPARATION_SR, decode, read_wav, write_wav
from agentic_audioprocess.audio.vad import SpeechRatioDetector
from agentic_audioprocess.core.errors import DecodeError


def test_decode_to_44k_stereo(voice_over_music_wav: Path) -> None:
    """分离模型要 44.1 kHz 立体声，形状必须是 (num_samples, channels)。"""
    chunk = decode(voice_over_music_wav)
    assert chunk.sample_rate == SEPARATION_SR
    assert chunk.samples.ndim == 2
    assert chunk.samples.shape[1] == 2
    assert chunk.duration == pytest.approx(9.0, abs=0.05)


def test_decode_mono_input_becomes_stereo(tmp_path: Path) -> None:
    mono = tmp_path / "mono.wav"
    sf.write(str(mono), np.zeros(44100, dtype=np.float32), 44100, subtype="PCM_16")
    chunk = decode(mono)
    assert chunk.samples.shape[1] == 2
    assert chunk.duration == pytest.approx(1.0, abs=0.05)


def test_decode_missing_file_raises() -> None:
    with pytest.raises(DecodeError):
        decode("Z:/definitely/not/here.wav")


def test_write_and_read_roundtrip(tmp_path: Path) -> None:
    data = np.zeros((44100, 2), dtype=np.float32)
    path = write_wav(tmp_path / "a.wav", data, 44100)
    assert path.is_file()
    again = read_wav(path)
    assert again.samples.shape == (44100, 2)


def test_energy_backend_reports_ratio() -> None:
    """没有 Silero 模型时也要能给出占比 / energy fallback must still work."""
    detector = SpeechRatioDetector(model_path=None)
    assert detector.backend == "energy"
    sr = 16000
    t = np.arange(sr * 4) / sr
    spoken = (np.sin(2 * np.pi * 180 * t) * (0.5 + 0.5 * np.sin(2 * np.pi * 4 * t))
              ).astype(np.float32)
    spoken[sr * 2:] = 0.0
    ratio = detector.ratio(spoken, sr)
    assert 0.2 < ratio < 0.9


def test_silero_backend_detects_voice(voice_over_music_wav: Path) -> None:
    """真实 Silero 路径：素材里 2/3 是语音，占比应明显偏高。"""
    from agentic_audioprocess.core.config import ROOT

    model = ROOT / "models" / "sherpa-vad" / "silero_vad.onnx"
    if not model.is_file():
        pytest.skip("本机没有 Silero VAD 模型")
    detector = SpeechRatioDetector(model_path=model)
    assert detector.backend == "silero"
    chunk = decode(voice_over_music_wav)
    ratio = detector.ratio(chunk.samples, chunk.sample_rate)
    # 这条同时回归两个已知坑：整段喂入会漏检、环形缓冲不取会丢段
    assert ratio > 0.4, f"占比异常偏低（{ratio:.3f}），检查分块喂入与边喂边取"
