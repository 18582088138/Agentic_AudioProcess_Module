"""引擎层 / Engine layer.

具体引擎通过 `resolve()` **延迟导入**，所以列出引擎名不会把 sherpa-onnx 拉进来。
"""

from __future__ import annotations

import importlib
from typing import TYPE_CHECKING

from agentic_audioprocess.core.errors import ConfigError
from agentic_audioprocess.engines.base import SeparationEngine

if TYPE_CHECKING:  # pragma: no cover
    pass

ENGINES: dict[str, str] = {
    "uvr": "agentic_audioprocess.engines.uvr:UvrEngine",
    "null": "agentic_audioprocess.engines.null:NullEngine",
}

LIGHTWEIGHT = ("null",)


def available() -> list[str]:
    """已登记的引擎名 / all registered engine names."""
    return sorted(ENGINES)


def resolve(name: str) -> type[SeparationEngine]:
    """按名字取引擎类 / resolve an engine class by name.

    抛出 / Raises:
        ConfigError: 名字未登记，或依赖缺失。
    """
    target = ENGINES.get(name)
    if target is None:
        raise ConfigError(f"未知引擎 / unknown engine {name!r}　"
                          f"可用 / available: {', '.join(available())}")
    module_name, _, class_name = target.partition(":")
    try:
        module = importlib.import_module(module_name)
    except ImportError as exc:
        raise ConfigError(f"引擎 {name!r} 的依赖未安装 / missing dependency: {exc}　"
                          f"提示 / hint: pip install -e \".[all]\"") from exc
    return getattr(module, class_name)


__all__ = ["ENGINES", "LIGHTWEIGHT", "SeparationEngine", "available", "resolve"]
