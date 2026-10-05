"""门面 / Facade —— `AudioProcessModule` 是唯一必须记住的类。

它负责**所有与引擎无关**的事 / everything engine-independent：

- 解码归一（任意媒体 → 44.1 kHz 立体声，UV R 模型的输入要求）
- **轨道顺序判定** —— 哪条轨是「主体人声」。官方示例写死 `stems[0]=vocals`，
  但实测不同模型的顺序并不一致，判反了就把「去掉主体人声」做成了「去掉背景人声」
- **等长校验** —— 各轨必须与输入样本数一致，否则下游时间轴整体漂移
- 落盘与命名、业务模式路由、加载前的能力检查

引擎只做一件事：一段音频 → 若干条轨。
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from agentic_audioprocess.audio.io import decode, ffmpeg_available, write_wav
from agentic_audioprocess.audio.vad import SpeechRatioDetector
from agentic_audioprocess.core.config import AudioProcessConfig, load_config
from agentic_audioprocess.core.errors import AudioProcessError
from agentic_audioprocess.core.logging import get_logger
from agentic_audioprocess.core.types import AudioChunk, SeparationMode, SeparationResult, Stem
from agentic_audioprocess.engines import available as available_engines
from agentic_audioprocess.engines import resolve
from agentic_audioprocess.engines.base import (
    ACCOMPANIMENT,
    BACKGROUND,
    LEAD,
    VOCALS,
    SeparationEngine,
)

log = get_logger("audioprocess")

# 每个模式对外产出的轨名 / the stems each mode exposes
_MODE_STEMS: dict[str, tuple[str, ...]] = {
    SeparationMode.VOCALS.value: (VOCALS,),
    SeparationMode.ACCOMPANIMENT.value: (ACCOMPANIMENT,),
    SeparationMode.LEAD_REMOVAL.value: (BACKGROUND, LEAD),
    SeparationMode.BOTH.value: (VOCALS, ACCOMPANIMENT),
}

# 哪些模型里哪条轨是**主体人声** —— 基于本机实测，不是照抄官方示例
# （官方示例写 `stems[0]=vocals`，但实测 kara2 与之相反）。
# Which stem is the lead, **measured on this machine**; the official example's
# hard-coded `stems[0]` does not hold for every model.
_MODEL_LEAD_INDEX: dict[str, int] = {
    "UVR_MDXNET_KARA.onnx": 0,      # 实测：stem0 = 中文主体，stem1 = 背景
    "UVR_MDXNET_KARA_2.onnx": 1,    # 实测：stem1 = 主体，与 KARA 相反
}


class AudioProcessModule:
    """分离门面 / the separation facade."""

    def __init__(self, config: AudioProcessConfig | None = None,
                 engine: str | SeparationEngine | None = None) -> None:
        self.config = config or load_config()
        self._engines: dict[str, SeparationEngine] = {}
        self._detector: SpeechRatioDetector | None = None
        self._default_engine = engine if isinstance(engine, str) else self.config.engine.default
        if isinstance(engine, SeparationEngine):
            self._engines[engine.name] = engine
            self._default_engine = engine.name

    # ── 引擎管理 / engine management ────────────────────────────────────────

    def engine(self, name: str | None = None) -> SeparationEngine:
        """取（并缓存）一个引擎 / get (and cache) an engine."""
        target = name or self._default_engine
        if target in self._engines:
            return self._engines[target]
        cls = resolve(target)
        self._engines[target] = cls(self.config)
        return self._engines[target]

    def engines(self) -> list[dict[str, Any]]:
        """引擎清单（**不加载权重**）/ engine catalogue, weight-free."""
        out: list[dict[str, Any]] = []
        for name in available_engines():
            item: dict[str, Any] = {"name": name, "default": name == self._default_engine}
            try:
                cls = resolve(name)
                item["modes"] = sorted(m.value for m in cls.declared_modes())
            except AudioProcessError as exc:
                item["error"] = str(exc)
                item["modes"] = []
            out.append(item)
        return out

    def detector(self) -> SpeechRatioDetector:
        """共享一个语音占比检测器 / one shared speech-ratio detector."""
        if self._detector is None:
            model = self.config.resolve_model_dir().parent / "sherpa-vad" / "silero_vad.onnx"
            self._detector = SpeechRatioDetector(model_path=model)
        return self._detector

    def doctor(self) -> dict[str, Any]:
        """体检 / self-check（不加载权重）."""
        cfg = self.config
        model_dir = cfg.resolve_model_dir()
        models: dict[str, Any] = {}
        for mode, fname in cfg.models.items():
            p = model_dir / fname
            models[mode] = {"file": fname, "path": str(p), "exists": p.is_file()}
        checks: list[str] = []
        if not ffmpeg_available():
            checks.append("ffmpeg 不在 PATH：非 wav 输入将不可用")
        for mode, info in models.items():
            if not info["exists"]:
                checks.append(f"缺少 {mode} 的权重 {info['file']}（下载见 docs/05_deployment.md）")
        vad = self.detector()
        if vad.backend != "silero":
            checks.append("Silero VAD 缺失：轨道判定将回退到能量法（精度略低）")
        return {"engines": self.engines(), "default_engine": self._default_engine,
                "mode": cfg.mode, "models": models,
                "vad_backend": vad.backend, "checks": checks, "ok": not checks}

    def release(self) -> None:
        """卸载全部引擎 / release every loaded engine."""
        for name, eng in list(self._engines.items()):
            try:
                eng.release()
            except Exception as exc:  # noqa: BLE001
                log.warning("卸载引擎 %s 失败 / release failed: %s", name, exc)
        self._engines.clear()
        self._detector = None

    def __enter__(self) -> "AudioProcessModule":
        return self

    def __exit__(self, *exc: object) -> None:
        self.release()

    # ── 三个核心功能 / the three core functions ─────────────────────────────

    def extract_vocals(self, media: str | Path | AudioChunk, out_dir: str | Path | None = None,
                       engine: str | None = None) -> SeparationResult:
        """**人声提取**：要所有人声 / extract every voice."""
        return self.separate(media, SeparationMode.VOCALS, out_dir, engine)

    def extract_accompaniment(self, media: str | Path | AudioChunk,
                              out_dir: str | Path | None = None,
                              engine: str | None = None) -> SeparationResult:
        """**背景音提取**：去掉所有人声 / extract the instrumental bed."""
        return self.separate(media, SeparationMode.ACCOMPANIMENT, out_dir, engine)

    def remove_lead_vocal(self, media: str | Path | AudioChunk,
                          out_dir: str | Path | None = None,
                          engine: str | None = None) -> SeparationResult:
        """**主体人声去除**：只去掉主体人声，**背景音里的人声保留**。

        产出两条轨：`background`（已去掉主体人声，含背景人声与伴奏）与
        `lead`（被移除的主体人声，留作核对）。
        Produces `background` (lead removed, background voices kept) and the
        extracted `lead` for verification.
        """
        return self.separate(media, SeparationMode.LEAD_REMOVAL, out_dir, engine)

    # ── 通用入口 / the generic entry point ──────────────────────────────────

    def separate(self, media: str | Path | AudioChunk,
                 mode: SeparationMode | str | None = None,
                 out_dir: str | Path | None = None,
                 engine: str | None = None) -> SeparationResult:
        """按模式分离 / separate according to a mode.

        参数 / Args:
            media: 媒体路径，或已解码的 `AudioChunk`。
            mode: 业务模式；None 用配置默认。
            out_dir: 输出目录；None 用 `config.output_dir`。
            engine: 引擎名；None 用配置默认。
        """
        mode_enum = _coerce_mode(mode or self.config.mode)
        eng = self.engine(engine)
        eng.require(mode_enum)

        chunk = self._load(media)
        if chunk.duration <= 0:
            raise AudioProcessError("空音频 / empty audio")

        raw = eng.separate(chunk, mode_enum,
                           lead_index=self.config.engine.uvr.lead_stem_index)

        warnings: list[str] = []
        raw = _enforce_same_length(raw, chunk, warnings)
        stem_order, evidence = self._resolve_order(raw, chunk, mode_enum)

        stems_audio = _to_output_stems(raw, stem_order, mode_enum)
        target_dir = Path(out_dir) if out_dir else self.config.output_dir
        stem_name = Path(chunk.source).stem or "audio" if chunk.source else "audio"
        saved = _save_stems(stems_audio, target_dir, stem_name, mode_enum, chunk, warnings)

        result = SeparationResult(
            mode=mode_enum.value, engine=eng.name, stems=saved,
            duration=round(chunk.duration, 3), sample_rate=chunk.sample_rate,
            lead_stem=stem_order.get("lead"), stem_order_resolved_by=evidence,
            warnings=warnings,
            raw={"loaded_file": eng.info().get("loaded_file"),
                 "speech_ratios": stem_order.get("ratios", {})})
        return result

    # ── 内部 / internals ────────────────────────────────────────────────────

    def _load(self, media: str | Path | AudioChunk) -> AudioChunk:
        if isinstance(media, AudioChunk):
            return media
        return decode(media, target_sr=self.config.output_sample_rate, channels=2)

    def _resolve_order(self, raw: dict[str, Any], chunk: AudioChunk,
                       mode: SeparationMode) -> tuple[dict[str, Any], str]:
        """判定哪条轨是主体人声 / decide which stem is the lead.

        四级判定，从可靠到兜底 / four levels, most reliable first:

        1. **配置显式指定**（`engine.uvr.lead_stem_index`）—— 用户说了算；
        2. **模型约定表**（默认）—— 本机实测得出的「该模型哪条轨是主体」；
        3. **VAD 语音占比** —— 仅用于约定表里没有的模型；
        4. **顺序兜底** —— 取第一条。

        ⚠️ **为什么把 VAD 降到第三位**：联调时发现它会把**背景音乐误判成语音**。
        实测素材「中文主体 + 英文背景 + 正弦背景音乐」：

            vad:speech_ratio {'vocals': 0.7624, 'accompaniment': 0.914}

        含音乐的那条轨占比反而更高（0.914），于是判定方向整个反了 ——
        「去掉主体人声」变成了「去掉背景人声」。用语音识别复核确认了这一点：
        本该干净的 background 轨里仍能识别出中文主体。

        ⚠️ 也不许用**能量**：实测「人声 + 背景音乐」素材里音乐轨 rms（0.1533）
        高于人声轨（0.1114）。

        VAD ratio can be fooled by background music, so it is only a fallback.
        """
        keys = list(raw.keys())
        info: dict[str, Any] = {"ratios": {}}
        if len(keys) == 1:
            info["lead"] = keys[0]
            return info, "single-stem"
        if mode != SeparationMode.LEAD_REMOVAL:
            info["lead"] = None
            return info, "not-needed"

        explicit = self.config.engine.uvr.lead_stem_index
        if explicit is not None and 0 <= explicit < len(keys):
            info["lead"] = keys[explicit]
            return info, f"config:lead_stem_index={explicit}"

        model_name = Path(self.config.model_path(mode.value)).name
        known = _MODEL_LEAD_INDEX.get(model_name)
        if known is not None and 0 <= known < len(keys):
            info["lead"] = keys[known]
            return info, f"model-convention:{model_name}->stem{known}"

        detector = self.detector()
        ratios = {k: round(detector.ratio(raw[k], chunk.sample_rate), 4) for k in keys}
        info["ratios"] = ratios
        lead = max(ratios, key=lambda k: ratios[k])
        info["lead"] = lead
        spread = ratios[lead] - min(ratios.values())
        if spread < 0.02:
            order_note = f"vad:ambiguous spread={spread:.4f} {ratios}"
        else:
            order_note = f"vad:speech_ratio {ratios}（未经模型约定表确认，可能有音乐干扰）"
        return info, order_note


# ── 模块级辅助 / module helpers ──────────────────────────────────────────────


def _coerce_mode(mode: SeparationMode | str) -> SeparationMode:
    if isinstance(mode, SeparationMode):
        return mode
    try:
        return SeparationMode(str(mode).lower().strip())
    except ValueError as exc:
        valid = "、".join(m.value for m in SeparationMode)
        raise AudioProcessError(f"未知模式 / unknown mode {mode!r}　可用 / valid: {valid}") from exc


def _enforce_same_length(raw: dict[str, Any], chunk: AudioChunk,
                         warnings: list[str]) -> dict[str, Any]:
    """强制各轨与输入等长 / force every stem to match the input length.

    不等长会让下游（字幕、音轨混合、参考音频）的时间轴**整体漂移**，
    而且不报错。所以这里裁剪或补零，并把动过手脚这件事写进 warnings。
    """
    n = len(chunk.samples)
    out: dict[str, Any] = {}
    for name, data in raw.items():
        arr = data
        if len(arr) != n:
            if len(arr) > n:
                arr = arr[:n]
            else:
                pad = [(0, 0)] * (arr.ndim - 1)
                arr = __import__("numpy").pad(arr, [(0, n - len(arr))] + pad,
                                              mode="constant")
            warnings.append(f"{name} 轨长度与输入不一致，已对齐到 {n} 个样本 / "
                            f"length mismatch, aligned")
        out[name] = arr
    return out


def _to_output_stems(raw: dict[str, Any], order: dict[str, Any],
                     mode: SeparationMode) -> dict[str, Any]:
    """把引擎的原始轨映射成该模式的对外轨 / map engine stems to public names."""
    keys = list(raw.keys())
    if mode == SeparationMode.VOCALS:
        return {VOCALS: raw[VOCALS]}
    if mode == SeparationMode.ACCOMPANIMENT:
        return {ACCOMPANIMENT: raw[ACCOMPANIMENT]}
    if mode == SeparationMode.BOTH:
        return {VOCALS: raw[VOCALS], ACCOMPANIMENT: raw[ACCOMPANIMENT]}

    # LEAD_REMOVAL：引擎返回的两条轨中，被判定为主体的那条是 lead，
    # 另一条就是「去掉主体人声后」的结果（含背景人声）。
    lead_key = order.get("lead") or keys[0]
    other = next((k for k in keys if k != lead_key), keys[-1])
    return {LEAD: raw[lead_key], BACKGROUND: raw[other]}


def _save_stems(stems: dict[str, Any], out_dir: Path, stem_name: str,
                mode: SeparationMode, chunk: AudioChunk,
                warnings: list[str]) -> dict[str, Stem]:
    """落盘并组装描述 / write the stems and build their descriptors."""
    saved: dict[str, Stem] = {}
    for name, data in stems.items():
        path = out_dir / f"{stem_name}_{mode.value}_{name}.wav"
        try:
            write_wav(path, data, chunk.sample_rate)
        except Exception as exc:  # noqa: BLE001
            warnings.append(f"{name} 轨写盘失败 / write failed: {exc}")
            continue
        arr = data
        saved[name] = Stem(name=name, path=str(path),
                           duration=round(len(arr) / chunk.sample_rate, 3),
                           sample_rate=chunk.sample_rate,
                           channels=1 if getattr(arr, "ndim", 1) == 1 else int(arr.shape[1]))
    return saved


__all__ = ["AudioProcessModule"]
