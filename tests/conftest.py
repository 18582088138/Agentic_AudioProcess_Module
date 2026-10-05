"""测试共用夹具 / Shared pytest fixtures.

默认 `addopts = "-m 'not real'"` 排除真实权重用例，所以素材必须**合成**。

`voice_over_music_wav` 造的是「类语音信号 + 背景音乐」的 44.1 kHz 立体声素材：
分离模型工作在 44.1 kHz 立体声，VAD 也要能从中检出语音，才能检验轨道判定。
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest
import soundfile as sf

SR = 44100


def _voice_like(seconds: float, sr: int = SR, seed: int = 0) -> np.ndarray:
    """类语音：低频载波 + 谐波 + 音节包络，中间留一段静音。"""
    rng = np.random.default_rng(seed)
    n = int(seconds * sr)
    t = np.arange(n) / sr
    carrier = (np.sin(2 * np.pi * 180 * t) + 0.5 * np.sin(2 * np.pi * 360 * t)
               + 0.25 * np.sin(2 * np.pi * 540 * t))
    syllables = 0.5 * (1 + np.sin(2 * np.pi * 4.0 * t))
    signal = carrier * syllables
    signal += 0.01 * rng.standard_normal(n)
    third = n // 3
    signal[third: 2 * third] = 0.0        # 中间静音，给 VAD 一个断点
    return (signal / (np.max(np.abs(signal)) or 1.0) * 0.7).astype(np.float32)


def _music(seconds: float, sr: int = SR) -> np.ndarray:
    n = int(seconds * sr)
    t = np.arange(n) / sr
    return (0.12 * np.sin(2 * np.pi * 110 * t)
            + 0.08 * np.sin(2 * np.pi * 220 * t)).astype(np.float32)


@pytest.fixture(scope="session")
def voice_over_music_wav(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """9 秒「类语音 + 背景音乐」44.1 kHz 立体声 / voice over music."""
    voice = _voice_like(9.0)
    mix = voice + _music(9.0)
    stereo = np.stack([mix, mix], axis=1).astype(np.float32)
    path = tmp_path_factory.mktemp("audio") / "voice_music.wav"
    sf.write(str(path), stereo, SR, subtype="PCM_16")
    return path


@pytest.fixture(scope="session")
def music_only_wav(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """纯音乐（无语音），用于检验「没有语音时不瞎判」/ music only."""
    music = _music(6.0)
    stereo = np.stack([music, music], axis=1).astype(np.float32)
    path = tmp_path_factory.mktemp("audio") / "music_only.wav"
    sf.write(str(path), stereo, SR, subtype="PCM_16")
    return path


@pytest.fixture()
def module(tmp_path: Path):
    """用 null 引擎、输出到临时目录的门面 / facade on the placeholder engine."""
    from agentic_audioprocess.audioprocess import AudioProcessModule
    from agentic_audioprocess.core.config import load_config

    cfg = load_config(None)
    cfg.output_dir = tmp_path / "outputs"
    cfg.output_dir.mkdir(parents=True, exist_ok=True)
    return AudioProcessModule(cfg, engine="null")


@pytest.fixture(scope="session")
def uvr_models_dir() -> Path:
    from agentic_audioprocess.core.config import ROOT

    return ROOT / "models" / "sherpa-separation"
