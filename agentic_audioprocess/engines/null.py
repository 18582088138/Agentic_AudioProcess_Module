"""占位引擎 / Placeholder engine.

**零重依赖、零权重**：把输入原样当作「人声」轨、静音当作「背景」轨。
它存在的意义是让库 / CLI / HTTP / GUI / 单测在不加载任何模型的情况下跑通整条链路
（验收项 V1），并且输出是**确定性**的，可以直接当断言基准。
Not a toy: it is what makes the offline test suite possible.
"""

from __future__ import annotations

from typing import Any

import numpy as np

from agentic_audioprocess.core.types import AudioChunk, SeparationMode
from agentic_audioprocess.engines.base import (
    ACCOMPANIMENT,
    BACKGROUND,
    LEAD,
    VOCALS,
    SeparationEngine,
)


class NullEngine(SeparationEngine):
    """直通占位 / pass-through placeholder."""

    name = "null"
    implemented = True

    def __init__(self, config: Any = None) -> None:
        super().__init__(config)
        self.loaded = True

    @classmethod
    def declared_modes(cls) -> set[SeparationMode]:
        return {SeparationMode.VOCALS, SeparationMode.ACCOMPANIMENT,
                SeparationMode.LEAD_REMOVAL, SeparationMode.BOTH}

    def separate(self, chunk: AudioChunk, mode: SeparationMode,
                 lead_index: int | None = None) -> dict[str, np.ndarray]:
        self.require(mode)
        data = np.asarray(chunk.samples, dtype=np.float32)
        silence = np.zeros_like(data)
        if mode == SeparationMode.VOCALS:
            return {VOCALS: data}
        if mode == SeparationMode.ACCOMPANIMENT:
            return {ACCOMPANIMENT: silence}
        if mode == SeparationMode.BOTH:
            return {VOCALS: data, ACCOMPANIMENT: silence}
        # LEAD_REMOVAL：把输入当主体人声，另一条给静音 —— 这样
        # 「去掉主体」的结果就是静音，断言起来一目了然。
        return {LEAD: data, BACKGROUND: silence}

    def info(self) -> dict[str, Any]:
        d = super().info()
        d["note"] = "占位引擎：不加载权重，输出确定性结果 / deterministic placeholder"
        return d

    def release(self) -> None:
        self.loaded = True


__all__ = ["NullEngine"]
