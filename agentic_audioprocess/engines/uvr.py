"""UVR 分离引擎（sherpa-onnx）/ the UVR engine on top of sherpa-onnx.

**这是本插件的主力，也是选型的结论**：`sherpa-onnx` 自带 `OfflineSourceSeparation`，
官方支持 UVR MDX 系 ONNX。实测（RTX 4060 机器，**全部在 CPU 上跑**）：

| 模型 | 体积 | RTF | 显存 |
|---|---|---|---|
| `UVR_MDXNET_KARA.onnx` | 28 MB | **0.232** | **0** |
| `UVR_MDXNET_KARA_2.onnx` | 50 MB | 0.363 | 0 |
| （对照）demucs htdemucs | ~300 MB | 0.740（**GPU**） | +861 MB |

⇒ CPU 上比 demucs 在 GPU 上还快，且完全不占显存。

**为什么不用 demucs**：它只能做人声/伴奏二分。实测「中文主体 + 英文背景」素材时，
它把两种人声全塞进 `vocals`，`no_vocals` 只剩 rms 0.0052 的近静音 ——
**做不到「只去掉主体人声、保留背景人声」**，而那正是本插件的核心功能。

**KARA 系为什么能行**：它的训练目标是「拿掉 lead vocal、留下其余（含 backing
vocals）」。调研阶段查不到它在**说话**（非唱歌）场景的依据，第三方模型卡甚至把
「完整混音」列为 out of scope —— 我们自己实测后才确认可用。
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np

from agentic_audioprocess.core.errors import EngineError, ModelMissingError
from agentic_audioprocess.core.logging import get_logger
from agentic_audioprocess.core.types import AudioChunk, SeparationMode
from agentic_audioprocess.engines.base import ACCOMPANIMENT, VOCALS, SeparationEngine

log = get_logger("engines.uvr")

# 权重下载前缀（官方 release；**不要**从 TRvlvr 原件下，缺 metadata）
DOWNLOAD_BASE = ("https://github.com/k2-fsa/sherpa-onnx/releases/download/"
                 "source-separation-models/")


class UvrEngine(SeparationEngine):
    """UVR MDX 系模型 / UVR MDX family models."""

    name = "uvr"
    implemented = True

    def __init__(self, config: Any = None) -> None:
        super().__init__(config)
        self._backend = None
        self._loaded_file = ""
        self._modes_available = {
            SeparationMode.VOCALS, SeparationMode.ACCOMPANIMENT,
            SeparationMode.LEAD_REMOVAL, SeparationMode.BOTH}

    # ── 能力 / capabilities ─────────────────────────────────────────────────

    @classmethod
    def declared_modes(cls) -> set[SeparationMode]:
        return {SeparationMode.VOCALS, SeparationMode.ACCOMPANIMENT,
                SeparationMode.LEAD_REMOVAL, SeparationMode.BOTH}

    # ── 加载 / loading ──────────────────────────────────────────────────────

    def model_path(self, mode: SeparationMode) -> Path:
        assert self.config is not None
        return self.config.model_path(mode.value)

    def _ensure(self, mode: SeparationMode) -> None:
        """按模式加载对应权重（换模型时先卸）/ load the weight for a mode."""
        path = self.model_path(mode)
        if not path.is_file():
            raise ModelMissingError(
                f"分离模型缺失 / weight missing: {path}\n"
                f"下载 / download:\n  {DOWNLOAD_BASE}{path.name}\n"
                f"（Windows 上请用 python requests 下载；curl 会被 schannel 中断）")
        if self._backend is not None and self._loaded_file == str(path):
            return
        self.release()

        cfg = self.config.engine.uvr
        try:
            import sherpa_onnx

            config = sherpa_onnx.OfflineSourceSeparationConfig(
                model=sherpa_onnx.OfflineSourceSeparationModelConfig(
                    uvr=sherpa_onnx.OfflineSourceSeparationUvrModelConfig(
                        model=str(path)),
                    num_threads=int(cfg.num_threads),
                    debug=False,
                    provider=cfg.provider or "cpu"))
            if not config.validate():
                raise EngineError("OfflineSourceSeparationConfig.validate() 返回 False")
            self._backend = sherpa_onnx.OfflineSourceSeparation(config)
        except EngineError:
            raise
        except Exception as exc:  # noqa: BLE001
            raise EngineError(f"加载 UVR 模型失败 / failed to load {path.name}: {exc}") from exc
        self._loaded_file = str(path)
        self.loaded = True
        log.info("UVR 已加载 / loaded: %s (%s, %d threads)",
                 path.name, cfg.provider, cfg.num_threads)

    # ── 推理 / inference ────────────────────────────────────────────────────

    def separate(self, chunk: AudioChunk, mode: SeparationMode,
                 lead_index: int | None = None) -> dict[str, np.ndarray]:
        self.require(mode)
        self._ensure(mode)

        # sherpa-onnx 要 (num_channels, num_samples) 的 contiguous float32
        data = np.asarray(chunk.samples, dtype=np.float32)
        if data.ndim == 1:
            data = np.stack([data, data], axis=1)
        if data.shape[1] == 1:
            data = np.repeat(data, 2, axis=1)
        if data.shape[1] > 2:
            data = data[:, :2]
        planar = np.ascontiguousarray(data.T)

        try:
            out = self._backend.process(sample_rate=chunk.sample_rate, samples=planar)
        except Exception as exc:  # noqa: BLE001
            raise EngineError(f"分离推理失败 / separation failed: {exc}") from exc

        stems = [np.asarray(s.data, dtype=np.float32) for s in out.stems]
        if len(stems) < 2:
            raise EngineError(f"期望 2 条轨，实际得到 {len(stems)} 条 / expected 2 stems")
        first, second = stems[0], stems[1]

        # 归一到 (num_samples, channels)，与原输入同形
        first = _to_interleaved(first, data.shape[1])
        second = _to_interleaved(second, data.shape[1])

        if mode in (SeparationMode.VOCALS,):
            return {VOCALS: first}
        if mode == SeparationMode.ACCOMPANIMENT:
            return {ACCOMPANIMENT: second}
        if mode == SeparationMode.BOTH:
            return {VOCALS: first, ACCOMPANIMENT: second}

        # LEAD_REMOVAL：KARA 系的约定是「一条是主体人声、一条是其余（含背景人声）」，
        # 而**哪一条是主体因模型而异**（实测 kara2 与官方示例相反），
        # 所以这里不做假设，两条都交回门面，由门面按语音占比 + 配置判定。
        return {VOCALS: first, ACCOMPANIMENT: second}

    # ── 生命周期 / lifecycle ────────────────────────────────────────────────

    def info(self) -> dict[str, Any]:
        d = super().info()
        d.update({"loaded_file": self._loaded_file or None,
                  "provider": self.config.engine.uvr.provider if self.config else None,
                  "num_threads": self.config.engine.uvr.num_threads if self.config else None})
        return d

    def release(self) -> None:
        if self._backend is not None:
            log.info("卸载 UVR / releasing %s", self._loaded_file)
        self._backend = None
        self._loaded_file = ""
        self.loaded = False
        import gc

        gc.collect()


def _to_interleaved(stem: np.ndarray, channels: int) -> np.ndarray:
    """把 (channels, n) 转成 (n, channels)，保持与原输入同形。"""
    arr = np.asarray(stem, dtype=np.float32)
    if arr.ndim == 1:
        return arr if channels == 1 else np.stack([arr] * channels, axis=1)
    if arr.shape[0] == channels:
        return np.ascontiguousarray(arr.T)
    if arr.shape[1] == channels:
        return np.ascontiguousarray(arr)
    # 形状异常时按最长维当时间轴处理，避免静默给出错位结果
    if arr.shape[0] > arr.shape[1]:
        return np.ascontiguousarray(arr[:, :channels])
    return np.ascontiguousarray(arr[:channels, :].T)


__all__ = ["DOWNLOAD_BASE", "UvrEngine"]
