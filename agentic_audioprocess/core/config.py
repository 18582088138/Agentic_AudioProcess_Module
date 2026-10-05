"""配置 / Configuration.

单一 YAML（`configs/audioprocess.yaml`）+ 环境变量覆盖，优先级：
**进程环境变量 > `.env` > YAML > 内置默认值**。
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings, SettingsConfigDict

from agentic_audioprocess.core.errors import ConfigError

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CONFIG = ROOT / "configs" / "audioprocess.yaml"

# 业务模式 -> 用哪个模型 / mode -> which weight file to load
# 这三行是本插件的核心知识：**去主体人声必须用 KARA 系**，
# 通用模型做不到「保留背景人声」（实测：demucs 会把所有人声一起带走）。
DEFAULT_MODE_MODELS: dict[str, str] = {
    "lead_removal": "UVR_MDXNET_KARA.onnx",
    "vocals": "UVR-MDX-NET-Voc_FT.onnx",
    "accompaniment": "UVR-MDX-NET-Inst_Main.onnx",
}


class Secrets(BaseSettings):
    """环境变量 / `.env` 覆盖 / env-var overrides."""

    model_config = SettingsConfigDict(
        env_file=str(ROOT / ".env"), env_file_encoding="utf-8", extra="ignore")

    audioprocess_engine: str = ""
    audioprocess_mode: str = ""
    audioprocess_models_dir: str = ""
    audioprocess_output_dir: str = ""
    audioprocess_num_threads: int = 0
    audioprocess_server_host: str = ""
    audioprocess_server_port: int = 0


class UvrConfig(BaseModel):
    """sherpa-onnx 的 UVR 分离后端 / the UVR backend of sherpa-onnx."""

    model_dir: str = "models/sherpa-separation"
    num_threads: int = 4
    provider: str = "cpu"
    # None = 运行时按语音占比自动判定哪条轨是主体人声；显式给 0/1 可强制
    lead_stem_index: int | None = None


class EngineConfig(BaseModel):
    default: str = "uvr"            # uvr | null
    uvr: UvrConfig = Field(default_factory=UvrConfig)


class ServerConfig(BaseModel):
    host: str = "127.0.0.1"
    port: int = 8302


class AudioProcessConfig(BaseModel):
    """顶层配置 / top-level configuration."""

    engine: EngineConfig = Field(default_factory=EngineConfig)
    mode: str = "lead_removal"
    models: dict[str, str] = Field(default_factory=lambda: dict(DEFAULT_MODE_MODELS))
    output_sample_rate: int = 44100
    # 不做逐轨峰值归一化：会破坏轨间相对音量，让两条轨再也混不回原样
    normalize: bool = False
    output_dir: Path = ROOT / "outputs"
    server: ServerConfig = Field(default_factory=ServerConfig)

    def resolve_model_dir(self) -> Path:
        p = Path(self.engine.uvr.model_dir)
        return p if p.is_absolute() else (ROOT / p)

    def model_for(self, mode: str | None = None) -> str:
        """该模式对应的模型文件名 / the weight file for a mode."""
        key = (mode or self.mode or "lead_removal").lower()
        return self.models.get(key) or DEFAULT_MODE_MODELS["lead_removal"]

    def model_path(self, mode: str | None = None) -> Path:
        return self.resolve_model_dir() / self.model_for(mode)


def _deep_merge(base: dict[str, Any], over: dict[str, Any]) -> dict[str, Any]:
    out = dict(base)
    for k, v in over.items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _deep_merge(out[k], v)
        else:
            out[k] = v
    return out


def load_config(path: str | Path | None = None, **overrides: Any) -> AudioProcessConfig:
    """加载配置 / load configuration.

    抛出 / Raises:
        ConfigError: YAML 非法或字段类型不对。
    """
    data: dict[str, Any] = {}
    cfg_path = Path(path) if path else DEFAULT_CONFIG
    if cfg_path.is_file():
        try:
            loaded = yaml.safe_load(cfg_path.read_text(encoding="utf-8")) or {}
        except yaml.YAMLError as exc:
            raise ConfigError(f"YAML 解析失败 / cannot parse {cfg_path}: {exc}") from exc
        if not isinstance(loaded, dict):
            raise ConfigError(f"配置根节点必须是映射 / root must be a mapping: {cfg_path}")
        data = loaded

    secrets = Secrets()
    if secrets.audioprocess_engine:
        data = _deep_merge(data, {"engine": {"default": secrets.audioprocess_engine}})
    if secrets.audioprocess_mode:
        data = _deep_merge(data, {"mode": secrets.audioprocess_mode})
    if secrets.audioprocess_models_dir:
        data = _deep_merge(data, {"engine": {"uvr": {"model_dir": secrets.audioprocess_models_dir}}})
    if secrets.audioprocess_output_dir:
        data = _deep_merge(data, {"output_dir": secrets.audioprocess_output_dir})
    if secrets.audioprocess_num_threads:
        data = _deep_merge(data, {"engine": {"uvr": {"num_threads": secrets.audioprocess_num_threads}}})
    if secrets.audioprocess_server_host:
        data = _deep_merge(data, {"server": {"host": secrets.audioprocess_server_host}})
    if secrets.audioprocess_server_port:
        data = _deep_merge(data, {"server": {"port": int(secrets.audioprocess_server_port)}})
    if overrides:
        data = _deep_merge(data, overrides)

    try:
        cfg = AudioProcessConfig(**data)
    except Exception as exc:
        raise ConfigError(f"配置字段非法 / invalid config: {exc}") from exc
    cfg.output_dir.mkdir(parents=True, exist_ok=True)
    return cfg


__all__ = ["DEFAULT_MODE_MODELS", "ROOT", "AudioProcessConfig", "Secrets", "load_config"]
