"""跨层数据类型 / Cross-layer data types.

引擎只负责「一段音频 → 若干条轨」，其余（格式归一、等长校验、轨道顺序判定、
落盘与命名）全部由门面 `SeparateModule` 负责。
Engines only turn audio into stems; everything else lives in the facade.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any

import numpy as np


class SeparationMode(str, Enum):
    """三种业务模式 / the three business modes.

    注意 `LEAD_REMOVAL` 与 `ACCOMPANIMENT` **不是同一件事**，这也是本插件
    存在的理由 —— 前者用 KARA 系模型「只去掉主体人声、保留背景里的人声」，
    后者用通用模型「去掉所有人声」。
    LEAD_REMOVAL keeps background voices; ACCOMPANIMENT removes every voice.
    """

    VOCALS = "vocals"                  # 人声提取：要所有人声
    ACCOMPANIMENT = "accompaniment"    # 背景音提取：去掉所有人声
    LEAD_REMOVAL = "lead_removal"      # 主体人声去除：只去主体，保留背景人声
    BOTH = "both"                      # 两轨都要


@dataclass
class Stem:
    """一条分离出来的音轨 / one separated stem."""

    name: str                 # vocals / accompaniment / lead / background
    path: str = ""
    duration: float = 0.0
    sample_rate: int = 44100
    channels: int = 2

    def to_dict(self) -> dict[str, Any]:
        return {"name": self.name, "path": self.path, "duration": self.duration,
                "sample_rate": self.sample_rate, "channels": self.channels}


@dataclass
class SeparationResult:
    """一次分离的完整结果 / the full result of one separation."""

    mode: str
    engine: str
    stems: dict[str, Stem] = field(default_factory=dict)
    duration: float = 0.0
    sample_rate: int = 44100
    # 哪条轨是主体人声，以及**依据什么判定**的 —— 判错方向是最坏的失败模式，
    # 所以判定依据必须回传，便于事后追查。
    # Which stem is the lead, and on what evidence; the evidence travels with
    # the result because getting this backwards is the worst failure mode.
    lead_stem: str | None = None
    stem_order_resolved_by: str = ""
    warnings: list[str] = field(default_factory=list)
    raw: dict[str, Any] | None = None

    @property
    def ok(self) -> bool:
        return bool(self.stems) and not self.warnings

    def to_dict(self) -> dict[str, Any]:
        return {
            "mode": self.mode, "engine": self.engine,
            "stems": {k: v.to_dict() for k, v in self.stems.items()},
            "duration": self.duration, "sample_rate": self.sample_rate,
            "lead_stem": self.lead_stem,
            "stem_order_resolved_by": self.stem_order_resolved_by,
            "warnings": self.warnings,
        }


@dataclass
class AudioChunk:
    """已归一的一段音频 / a normalised piece of audio.

    分离模型要求 **44.1 kHz 立体声**，所以这里的默认值与 ASR 侧（16 kHz 单声道）不同。
    Separation models want 44.1 kHz stereo, unlike the ASR side.
    """

    samples: np.ndarray            # float32, 形状 (num_samples,) 或 (num_samples, ch)
    sample_rate: int = 44100
    source: str = ""

    @property
    def duration(self) -> float:
        return len(self.samples) / float(self.sample_rate or 1)

    @property
    def channels(self) -> int:
        return 1 if self.samples.ndim == 1 else int(self.samples.shape[1])


__all__ = ["AudioChunk", "SeparationMode", "SeparationResult", "Stem"]
