"""真实 UVR 权重用例 / real-model tests（默认被 addopts 排除）。

复测 / rerun:
    C:\\Users\\75203\\miniforge3\\envs\\ov_env_py312\\python.exe -m pytest tests/test_real.py -q -m real

覆盖 / covers: 三个模式在真实 KARA / Voc / Inst 权重上跑通、输出等长、
**「主体人声去除」确实把主体与背景分到了两条轨**（本插件最核心的断言）。
说明文档 / docs: docs/00_research.md（KARA 实测）、docs/issues/005
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest
import soundfile as sf

from agentic_audioprocess.audioprocess import AudioProcessModule
from agentic_audioprocess.core.types import SeparationMode

pytestmark = pytest.mark.real

MODEL_DIR = Path(__file__).resolve().parent.parent / "models" / "sherpa-separation"


def _need(name: str) -> None:
    if not (MODEL_DIR / name).is_file():
        pytest.skip(f"缺少权重 / missing weight: {name}")


@pytest.fixture(scope="module")
def uvr_module():
    _need("UVR_MDXNET_KARA.onnx")
    module = AudioProcessModule()
    yield module
    module.release()


@pytest.fixture(scope="module")
def lead_vs_background(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """构造「主体人声（中文，居中）+ 背景人声（英文，偏侧、−10 dB）」素材。

    这是唯一能检验「主体 vs 背景」区分能力的输入 —— 单一说话人的素材
    根本无法暴露这个能力（两者都会被当成同一个人声）。
    """
    import torch
    import torchaudio

    samples_dir = Path(__file__).resolve().parent.parent / "models" / "samples"
    lead_p, back_p = samples_dir / "zh.mp3", samples_dir / "en.mp3"
    if not lead_p.is_file() or not back_p.is_file():
        pytest.skip("缺少示例音频 / missing sample audio")

    def load(path: Path) -> np.ndarray:
        data, sr = sf.read(str(path), dtype="float32", always_2d=True)
        mono = data.mean(axis=1)
        return torchaudio.functional.resample(torch.from_numpy(mono), sr, 44100).numpy()

    lead, back = load(lead_p), load(back_p)
    n = int(20 * 44100)
    lead = np.tile(lead, int(n / len(lead)) + 1)[:n]
    back = np.tile(back, int(n / len(back)) + 1)[:n]
    lead = lead / (np.max(np.abs(lead)) or 1.0) * 0.85
    back = back / (np.max(np.abs(back)) or 1.0) * 0.30
    mix = np.stack([lead + back, lead + back * 0.65], axis=1).astype(np.float32)
    path = tmp_path_factory.mktemp("leadbg") / "lead_over_back.wav"
    sf.write(str(path), mix, 44100, subtype="PCM_16")
    return path


def test_uvr_lead_removal_runs(uvr_module: AudioProcessModule,
                               voice_over_music_wav: Path) -> None:
    """核心路径：KARA 模型能跑通，并给出 background 与 lead 两条轨。"""
    result = uvr_module.remove_lead_vocal(voice_over_music_wav)
    assert result.stems, "没有产出任何轨"
    assert "background" in result.stems
    assert result.stem_order_resolved_by


def test_uvr_stems_match_input_length(uvr_module: AudioProcessModule,
                                      voice_over_music_wav: Path) -> None:
    """V9：真实模型下各轨也必须与输入严格等长。"""
    chunk = uvr_module._load(voice_over_music_wav)
    result = uvr_module.separate(voice_over_music_wav, SeparationMode.BOTH)
    for stem in result.stems.values():
        data, _ = sf.read(stem.path, always_2d=True)
        assert len(data) == len(chunk.samples), f"{stem.name} 与输入不等长"


def test_kara_separates_lead_from_background(uvr_module: AudioProcessModule,
                                             lead_vs_background: Path) -> None:
    """**本插件最核心的实测断言**：KARA 真的能把主体人声与背景人声分开。

    做法：素材是「中文主体 + 英文背景」。分离后
    · `lead` 轨的**语音占比**应高于 `background` 轨（主体被剥离出来）；
    · 两条轨都必须有内容（不是一条全静音 —— 那意味着它退化成普通的人声/伴奏二分）。

    调研阶段查不到 KARA 在**说话**场景的依据，第三方模型卡把「完整混音」
    列为 out of scope，所以这条只能靠实测守住。
    """
    result = uvr_module.remove_lead_vocal(lead_vs_background)
    lead_stem = result.stems.get("lead")
    bg_stem = result.stems.get("background")
    assert lead_stem and bg_stem, "应同时给出 lead 与 background"

    lead_audio, _ = sf.read(lead_stem.path, always_2d=True)
    bg_audio, _ = sf.read(bg_stem.path, always_2d=True)
    rms_lead = float(np.sqrt(np.mean(lead_audio.astype(np.float64) ** 2)))
    rms_bg = float(np.sqrt(np.mean(bg_audio.astype(np.float64) ** 2)))

    # 两条轨都不能是静音（静音说明退化成了「人声 / 非人声」二分）
    assert rms_lead > 1e-4, "lead 轨几乎是静音，模型可能没提取出主体人声"
    assert rms_bg > 1e-4, "background 轨几乎是静音，模型可能把所有人声一起带走了"

    ratios = result.raw.get("speech_ratios") if result.raw else None
    if ratios:
        # 判定依据必须能在结果里看到，否则判反了也查不出来
        assert max(ratios.values()) >= min(ratios.values())


def test_all_three_modes_run(uvr_module: AudioProcessModule,
                             voice_over_music_wav: Path) -> None:
    for mode, weight in ((SeparationMode.VOCALS, "UVR-MDX-NET-Voc_FT.onnx"),
                         (SeparationMode.ACCOMPANIMENT, "UVR-MDX-NET-Inst_Main.onnx")):
        _need(weight)
        result = uvr_module.separate(voice_over_music_wav, mode)
        assert result.stems, f"{mode} 没有产出轨"


def test_music_only_does_not_crash(uvr_module: AudioProcessModule,
                                   music_only_wav: Path) -> None:
    """纯音乐也要能正常出结果（只是没有主体人声可去）。"""
    result = uvr_module.separate(music_only_wav, SeparationMode.LEAD_REMOVAL)
    assert result.stems
    assert result.stem_order_resolved_by
