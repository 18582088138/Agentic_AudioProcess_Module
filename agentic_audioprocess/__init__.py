"""Agentic_AudioProcess_Module —— 可插拔的本地音频处理服务插件。

定位是**音频前后处理**：分离（人声 / 背景音 / 主体人声去除）、降噪、去环境音、
音质优化。当前已实现分离三件套，其余见 `docs/10_audio_processing_roadmap.md`。

三个核心功能 / three core functions，每一个都能独立调用：

| 功能 | 入口 | 一句话 |
|---|---|---|
| 人声提取 | `AudioProcessModule.extract_vocals()` | 要**所有**人声 |
| 背景音提取 | `AudioProcessModule.extract_accompaniment()` | 去掉**所有**人声 |
| **主体人声去除** | `AudioProcessModule.remove_lead_vocal()` | 只去**主体**人声，**背景音里的人声保留** |

第四种（两轨都要）用 `separate(..., SeparationMode.BOTH)`。

四种用法共用同一个门面 / four usages over one facade：
Python 库 · CLI(`audio …`) · HTTP(`python -m agentic_audioprocess.server`) ·
GUI(`python -m agentic_audioprocess.gui`)。

快速开始 / quick start::

    from agentic_audioprocess import AudioProcessModule

    sep = AudioProcessModule()
    vocals = sep.extract_vocals("demo.mp4")          # 人声提取
    bed = sep.extract_accompaniment("demo.mp4")      # 背景音提取
    no_lead = sep.remove_lead_vocal("demo.mp4")      # 主体人声去除
    print(no_lead.stems["background"].path)
    sep.release()

依赖上刻意做得极轻：分离全部走 `sherpa-onnx` 自带的 UVR 后端，**CPU 上跑**
（实测 RTF 0.23~0.36，比 demucs 在 GPU 上还快），显存占用为 0。
"""

from agentic_audioprocess.audioprocess import AudioProcessModule
from agentic_audioprocess.core.config import AudioProcessConfig, load_config
from agentic_audioprocess.core.errors import (
    AudioProcessError,
    ConfigError,
    DecodeError,
    EngineError,
    ModelMissingError,
    StemOrderError,
)
from agentic_audioprocess.core.types import (
    AudioChunk,
    SeparationMode,
    SeparationResult,
    Stem,
)

__version__ = "0.1.0"

__all__ = [
    "AudioChunk",
    "ConfigError",
    "DecodeError",
    "EngineError",
    "ModelMissingError",
    "AudioProcessConfig",
    "AudioProcessError",
    "AudioProcessModule",
    "SeparationMode",
    "SeparationResult",
    "Stem",
    "StemOrderError",
    "__version__",
    "load_config",
]
