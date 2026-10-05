"""异常体系 / Error hierarchy.

与 `Agentic_ASR_Module` 保持同一形状（一个基类 + 若干语义明确的子类），
这样两个插件在调用方眼里是对称的。
Same shape as the ASR plugin, so callers see the two plugins as symmetric.
"""

from __future__ import annotations


class SeparateError(Exception):
    """本插件所有异常的基类 / base class of every error in this plugin."""


class ConfigError(SeparateError):
    """配置缺失或非法 / missing or invalid configuration."""


class DecodeError(SeparateError):
    """音频解码或转码失败 / audio decoding or conversion failed."""


class EngineError(SeparateError):
    """分离引擎加载或推理失败 / engine failed to load or to run."""


class ModelMissingError(EngineError):
    """权重文件缺失 / the weight file is missing.

    单独分类的原因：这是**最常见的首次使用障碍**，报错信息里要能直接给出
    下载地址，而不是一句 FileNotFoundError。
    """


class StemOrderError(SeparateError):
    """无法判定哪条轨是主体人声 / cannot tell which stem is the lead.

    见 `docs/issues/005`：官方示例写死 `stems[0]=vocals`，但实测不同模型的
    顺序并不一致，判错会把「去掉主体人声」做成「去掉背景人声」。
    """


__all__ = [
    "ConfigError",
    "DecodeError",
    "EngineError",
    "ModelMissingError",
    "SeparateError",
    "StemOrderError",
]
