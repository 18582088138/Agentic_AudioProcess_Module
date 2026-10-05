"""分离引擎抽象 / Separation engine abstraction.

**一个引擎只需要会做一件事：一段音频 → 若干条轨。**
An engine does exactly one thing: audio in, a dict of stems out.

轨道命名、落盘、等长校验、轨道顺序判定、业务模式（人声 / 背景音 / 去主体人声）
全部在门面 `SeparateModule` 里 —— 与 `Agentic_ASR_Module` 的引擎抽象同样的取舍：
把这些下沉到各引擎，就会出现 N 份互相不一致的实现。

为什么与 ASR 引擎**分成两套平级抽象**：两者能力正交 ——
一个答「这段音频里哪些是人声」，一个答「这段音频说了什么」。
硬合并会让能力表无法表达（云端 ASR 能做转写但做不了分离，分离模型能分轨但不认识字）。
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Any

import numpy as np

from agentic_separate.core.types import AudioChunk, SeparationMode

if TYPE_CHECKING:  # pragma: no cover
    from agentic_separate.core.config import SeparateConfig

# 轨的规范名 / canonical stem names
VOCALS = "vocals"
ACCOMPANIMENT = "accompaniment"
LEAD = "lead"
BACKGROUND = "background"

ALL_STEMS = (VOCALS, ACCOMPANIMENT, LEAD, BACKGROUND)


class SeparationEngine(ABC):
    """一个分离引擎 / one separation engine.

    权重懒加载 —— 构造实例不该花时间（GUI 开机要用它列引擎）。
    """

    name: str = ""
    implemented: bool = True

    def __init__(self, config: "SeparateConfig | None" = None) -> None:
        self.config = config
        self.loaded = False

    # ── 能力 / capabilities ─────────────────────────────────────────────────

    @classmethod
    @abstractmethod
    def declared_modes(cls) -> set[SeparationMode]:
        """支持的业务模式 / business modes this engine can serve.

        **必须不加载权重就能回答**。
        """

    def modes(self) -> set[SeparationMode]:
        return self.declared_modes()

    def supports(self, mode: SeparationMode) -> bool:
        return mode in self.modes()

    def require(self, mode: SeparationMode) -> None:
        """不支持就报错，绝不静默降级 / fail loudly instead of degrading."""
        if not self.supports(mode):
            from agentic_separate.core.errors import SeparateError

            supported = "、".join(sorted(m.value for m in self.modes())) or "（无）"
            raise SeparateError(f"引擎 {self.name!r} 不支持模式 {mode.value}　"
                                f"已支持 / supported: {supported}")

    # ── 分离 / separation ───────────────────────────────────────────────────

    @abstractmethod
    def separate(self, chunk: AudioChunk, mode: SeparationMode,
                 lead_index: int | None = None) -> dict[str, np.ndarray]:
        """分离成若干条轨 / split into stems.

        参数 / Args:
            chunk: 已归一的一段音频（分离模型通常要 44.1 kHz 立体声）。
            mode: 业务模式，决定用哪个模型、输出哪些轨。
            lead_index: 仅 `LEAD_REMOVAL` 用；None 表示由门面按语音占比判定。

        返回 / Returns:
            `{轨名: 波形数组}`，波形形状与 `chunk.samples` **严格一致**。

        抛出 / Raises:
            ModelMissingError: 权重缺失（报错里要带下载方式）。
            EngineError: 加载或推理失败。
        """

    # ── 元信息与生命周期 / metadata & lifecycle ─────────────────────────────

    def info(self) -> dict[str, Any]:
        return {"engine": self.name, "implemented": self.implemented,
                "loaded": self.loaded,
                "modes": sorted(m.value for m in self.modes())}

    def release(self) -> None:
        """卸载权重 / unload weights（默认无事可做）."""

    def __enter__(self) -> "SeparationEngine":
        return self

    def __exit__(self, *exc: object) -> None:
        self.release()


__all__ = ["ACCOMPANIMENT", "ALL_STEMS", "BACKGROUND", "LEAD", "VOCALS",
           "SeparationEngine"]
