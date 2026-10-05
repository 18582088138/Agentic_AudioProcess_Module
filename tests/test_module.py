"""门面与三个核心功能 / facade and the three core functions.

复测 / rerun:
    C:\\Users\\75203\\miniforge3\\envs\\ov_env_py312\\python.exe -m pytest tests/test_module.py -q

覆盖 / covers: 三个功能各自可用、等长校验、轨道判定可解释、模式校验、引擎清单。
不含 / excludes: 真实 UVR 权重（见 `test_real.py`）。
说明文档 / docs: docs/01_design.md §4
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from agentic_audioprocess.core.config import AudioProcessConfig, load_config
from agentic_audioprocess.core.errors import AudioProcessError, ConfigError
from agentic_audioprocess.core.types import AudioChunk, SeparationMode
from agentic_audioprocess.engines import available, resolve
from agentic_audioprocess.engines.base import (
    ACCOMPANIMENT,
    BACKGROUND,
    LEAD,
    VOCALS,
    SeparationEngine,
)

# ── 配置与注册表 / config & registry ─────────────────────────────────────────


def test_default_config_is_runnable() -> None:
    cfg = load_config(None)
    assert cfg.engine.default == "uvr"
    assert cfg.output_dir.exists()


def test_mode_to_model_mapping() -> None:
    """三个模式必须映射到**不同**的权重 —— 这正是本插件存在的理由。"""
    cfg = AudioProcessConfig()
    assert cfg.model_for("lead_removal").startswith("UVR_MDXNET_KARA")
    assert cfg.model_for("vocals") == "UVR-MDX-NET-Voc_FT.onnx"
    assert cfg.model_for("accompaniment") == "UVR-MDX-NET-Inst_Main.onnx"
    assert len({cfg.model_for(m) for m in ("lead_removal", "vocals", "accompaniment")}) == 3


def test_registry_and_capabilities_without_weights() -> None:
    assert "uvr" in available() and "null" in available()
    for name in available():
        modes = resolve(name).declared_modes()
        assert modes and all(isinstance(m, SeparationMode) for m in modes)


def test_unknown_engine_raises() -> None:
    with pytest.raises(ConfigError):
        resolve("nope")


def test_require_rejects_unsupported_mode() -> None:
    from agentic_audioprocess.engines.null import NullEngine

    class Narrow(NullEngine):
        name = "narrow"

        @classmethod
        def declared_modes(cls):
            return {SeparationMode.VOCALS}

    eng = Narrow(AudioProcessConfig())
    eng.require(SeparationMode.VOCALS)
    with pytest.raises(AudioProcessError):
        eng.require(SeparationMode.LEAD_REMOVAL)


# ── 三个核心功能 / the three functions ───────────────────────────────────────


def test_extract_vocals(module, voice_over_music_wav: Path) -> None:
    result = module.extract_vocals(voice_over_music_wav)
    assert result.mode == SeparationMode.VOCALS.value
    assert VOCALS in result.stems
    assert Path(result.stems[VOCALS].path).is_file()


def test_extract_accompaniment(module, voice_over_music_wav: Path) -> None:
    result = module.extract_accompaniment(voice_over_music_wav)
    assert result.mode == SeparationMode.ACCOMPANIMENT.value
    assert ACCOMPANIMENT in result.stems


def test_remove_lead_vocal_produces_background_and_lead(module,
                                                        voice_over_music_wav: Path) -> None:
    """去主体人声要同时给出「去掉之后的结果」与「被去掉的主体」，便于核对。"""
    result = module.remove_lead_vocal(voice_over_music_wav)
    assert result.mode == SeparationMode.LEAD_REMOVAL.value
    assert BACKGROUND in result.stems and LEAD in result.stems
    assert result.lead_stem, "必须说明哪条轨被判定为主体"
    # 判定依据必须是四者之一，且非空 —— 判反了才查得出来
    assert result.stem_order_resolved_by
    assert any(tag in result.stem_order_resolved_by
               for tag in ("model-convention:", "config:", "vad:", "single-stem"))


def test_lead_removal_can_be_forced_by_config(module, voice_over_music_wav: Path) -> None:
    """判定方向错了是很严重的失败模式，所以必须允许用户强制指定。"""
    module.config.engine.uvr.lead_stem_index = 0
    result = module.remove_lead_vocal(voice_over_music_wav)
    assert "config:lead_stem_index=0" in result.stem_order_resolved_by


def test_model_convention_wins_over_vad(module, voice_over_music_wav: Path) -> None:
    """模型约定表必须优先于 VAD。

    回归背景：第一版用 VAD 语音占比当默认判据，结果**背景音乐被当成语音**，
    含音乐的那条轨占比反而更高（0.914 > 0.7624），判定方向整个反了 ——
    「去掉主体人声」变成了「去掉背景人声」。见 `issues/005`。
    """
    from agentic_audioprocess.core.config import DEFAULT_MODE_MODELS

    # 默认配置用的就是 KARA 模型，约定表里 stem0 = 主体
    assert module.config.model_for("lead_removal") == DEFAULT_MODE_MODELS["lead_removal"]
    result = module.remove_lead_vocal(voice_over_music_wav)
    assert result.stem_order_resolved_by.startswith("model-convention:")


def test_vad_is_used_for_unknown_models(module, voice_over_music_wav: Path) -> None:
    """约定表里没有的模型才退回 VAD，且依据串必须说明「未经约定确认」。"""
    module.config.models["lead_removal"] = "some-unknown-model.onnx"
    result = module.remove_lead_vocal(voice_over_music_wav)
    assert "vad:" in result.stem_order_resolved_by
    assert "约定表" in result.stem_order_resolved_by or "music" in result.stem_order_resolved_by


def test_both_mode_returns_two_stems(module, voice_over_music_wav: Path) -> None:
    result = module.separate(voice_over_music_wav, SeparationMode.BOTH)
    assert set(result.stems) == {VOCALS, ACCOMPANIMENT}


# ── 等长与产物 / length and artefacts ────────────────────────────────────────


def test_stems_are_same_length_as_input(module, voice_over_music_wav: Path) -> None:
    """各轨必须与输入严格等长 —— 否则下游时间轴会整体漂移且不报错。"""
    import soundfile as sf

    chunk = module._load(voice_over_music_wav)
    result = module.separate(voice_over_music_wav, SeparationMode.BOTH)
    n_in = len(chunk.samples)
    for stem in result.stems.values():
        data, sr = sf.read(stem.path, always_2d=True)
        assert len(data) == n_in, f"{stem.name} 长度 {len(data)} != 输入 {n_in}"
        assert sr == chunk.sample_rate


def test_output_files_are_named_by_mode(module, voice_over_music_wav: Path) -> None:
    result = module.remove_lead_vocal(voice_over_music_wav)
    for name, stem in result.stems.items():
        assert name in Path(stem.path).stem
        assert "lead_removal" in Path(stem.path).stem


def test_empty_audio_raises(module) -> None:
    chunk = AudioChunk(samples=np.zeros((0, 2), dtype=np.float32), sample_rate=44100)
    with pytest.raises(AudioProcessError):
        module.separate(chunk, SeparationMode.VOCALS)


def test_unknown_mode_raises(module, voice_over_music_wav: Path) -> None:
    with pytest.raises(AudioProcessError):
        module.separate(voice_over_music_wav, "not-a-mode")


# ── 体检 / doctor ────────────────────────────────────────────────────────────


def test_engines_listing(module) -> None:
    items = module.engines()
    names = {i["name"] for i in items}
    assert {"uvr", "null"} <= names
    assert len([i for i in items if i.get("default")]) == 1


def test_doctor_reports_models(module) -> None:
    report = module.doctor()
    assert "models" in report and "checks" in report
    for mode in ("lead_removal", "vocals", "accompaniment"):
        assert mode in report["models"]
        assert "exists" in report["models"][mode]


def test_release_clears_engines(module) -> None:
    module.engine("null")
    module.release()
    assert not module._engines


# ── 引擎契约 / engine contract ───────────────────────────────────────────────


def test_engine_returns_same_shape(voice_over_music_wav: Path) -> None:
    """引擎契约：输出波形必须与输入同形（门面才有得裁剪）。"""
    from agentic_audioprocess.audio.io import decode
    from agentic_audioprocess.engines.null import NullEngine

    eng = NullEngine(AudioProcessConfig())
    chunk = decode(voice_over_music_wav)
    for mode in (SeparationMode.VOCALS, SeparationMode.ACCOMPANIMENT,
                 SeparationMode.BOTH, SeparationMode.LEAD_REMOVAL):
        out = eng.separate(chunk, mode)
        assert out, f"{mode} 未返回任何轨"
        for arr in out.values():
            assert arr.shape == chunk.samples.shape


def test_engine_is_abstract() -> None:
    with pytest.raises(TypeError):
        SeparationEngine()  # type: ignore[abstract]
