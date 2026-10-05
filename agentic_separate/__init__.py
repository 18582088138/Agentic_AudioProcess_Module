"""Agentic_VoiceSeparate_Module —— 可插拔的本地声音分离服务插件。

三个核心功能 / three core functions，每一个都能独立调用：

| 功能 | 入口 | 一句话 |
|---|---|---|
| 人声提取 | `SeparateModule.extract_vocals()` | 要**所有**人声 |
| 背景音提取 | `SeparateModule.extract_accompaniment()` | 去掉**所有**人声 |
| **主体人声去除** | `SeparateModule.remove_lead_vocal()` | 只去**主体**人声，**背景音里的人声保留** |

第四种（两轨都要）用 `separate(..., SeparationMode.BOTH)`。

四种用法共用同一个门面 / four usages over one facade：
Python 库 · CLI(`separate …`) · HTTP(`python -m agentic_separate.server`) ·
GUI(`python -m agentic_separate.gui`)。

快速开始 / quick start::

    from agentic_separate import SeparateModule

    sep = SeparateModule()
    vocals = sep.extract_vocals("demo.mp4")          # 人声提取
    bed = sep.extract_accompaniment("demo.mp4")      # 背景音提取
    no_lead = sep.remove_lead_vocal("demo.mp4")      # 主体人声去除
    print(no_lead.stems["background"].path)
    sep.release()

依赖上刻意做得极轻：分离全部走 `sherpa-onnx` 自带的 UVR 后端，**CPU 上跑**
（实测 RTF 0.23~0.36，比 demucs 在 GPU 上还快），显存占用为 0。
"""

from agentic_separate.core.config import SeparateConfig, load_config
from agentic_separate.core.errors import (
    ConfigError,
    DecodeError,
    EngineError,
    ModelMissingError,
    SeparateError,
    StemOrderError,
)
from agentic_separate.core.types import (
    AudioChunk,
    SeparationMode,
    SeparationResult,
    Stem,
)
from agentic_separate.separate import SeparateModule

__version__ = "0.1.0"

__all__ = [
    "AudioChunk",
    "ConfigError",
    "DecodeError",
    "EngineError",
    "ModelMissingError",
    "SeparateConfig",
    "SeparateError",
    "SeparateModule",
    "SeparationMode",
    "SeparationResult",
    "Stem",
    "StemOrderError",
    "__version__",
    "load_config",
]
