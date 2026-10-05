"""HTTP 服务 / HTTP service.

**每个功能都是独立 endpoint**，可单独调用（用户明确要求的形态）。

    python -m agentic_separate.server        # http://127.0.0.1:8302/docs
"""

from __future__ import annotations

import shutil
import tempfile
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse

from agentic_separate import __version__
from agentic_separate.core.config import SeparateConfig, load_config
from agentic_separate.core.errors import SeparateError
from agentic_separate.core.types import SeparationMode
from agentic_separate.separate import SeparateModule

_ALLOWED_SUFFIX = {".wav", ".mp3", ".m4a", ".aac", ".flac", ".ogg", ".opus", ".aiff",
                   ".mp4", ".mkv", ".mov", ".webm", ".avi", ".ts"}


def create_app(config: SeparateConfig | None = None) -> FastAPI:
    """构造应用 / build the app（便于测试注入配置）."""
    cfg = config or load_config()
    module = SeparateModule(cfg)

    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        try:
            yield
        finally:
            module.release()

    api = FastAPI(title="Agentic_VoiceSeparate_Module", version=__version__,
                  lifespan=lifespan)

    def _save(upload: UploadFile) -> Path:
        suffix = Path(upload.filename or "").suffix.lower() or ".bin"
        if suffix not in _ALLOWED_SUFFIX:
            raise HTTPException(415, f"不支持的扩展名 / unsupported suffix: {suffix}")
        tmp = Path(tempfile.mkdtemp(prefix="agentic_sep_http_")) / f"input{suffix}"
        with tmp.open("wb") as fh:
            shutil.copyfileobj(upload.file, fh)
        return tmp

    def _guard(fn, *args: Any, **kwargs: Any) -> Any:
        try:
            return fn(*args, **kwargs)
        except SeparateError as exc:
            raise HTTPException(400, str(exc)) from exc

    @api.get("/healthz")
    def healthz() -> dict[str, Any]:
        return {"ok": True, "version": __version__, "engine": cfg.engine.default,
                "mode": cfg.mode}

    @api.get("/engines")
    def engines() -> dict[str, Any]:
        return {"default": cfg.engine.default, "engines": module.engines()}

    @api.get("/doctor")
    def doctor() -> dict[str, Any]:
        return module.doctor()

    @api.get("/config")
    def show_config() -> dict[str, Any]:
        return cfg.model_dump(mode="json")

    async def _separate(file: UploadFile, mode: SeparationMode,
                        lead_index: int | None, engine: str | None) -> dict[str, Any]:
        path = _save(file)
        if lead_index is not None:
            cfg.engine.uvr.lead_stem_index = lead_index
        result = _guard(module.separate, path, mode, cfg.output_dir / "http", engine)
        return result.to_dict()

    @api.post("/vocals")
    async def vocals(file: UploadFile = File(...), engine: str | None = Form(None)
                     ) -> dict[str, Any]:
        """人声提取 / extract every voice."""
        return await _separate(file, SeparationMode.VOCALS, None, engine)

    @api.post("/accompaniment")
    async def accompaniment(file: UploadFile = File(...), engine: str | None = Form(None)
                            ) -> dict[str, Any]:
        """背景音提取 / extract the instrumental bed."""
        return await _separate(file, SeparationMode.ACCOMPANIMENT, None, engine)

    @api.post("/lead-removal")
    async def lead_removal(file: UploadFile = File(...),
                           lead_index: int | None = Form(None),
                           engine: str | None = Form(None)) -> dict[str, Any]:
        """主体人声去除（保留背景人声）/ remove the lead voice only."""
        return await _separate(file, SeparationMode.LEAD_REMOVAL, lead_index, engine)

    @api.post("/separate")
    async def separate_endpoint(file: UploadFile = File(...),
                                mode: str = Form("both"),
                                engine: str | None = Form(None)) -> dict[str, Any]:
        try:
            mode_enum = SeparationMode(mode.lower())
        except ValueError as exc:
            raise HTTPException(422, f"未知模式 / unknown mode: {mode}") from exc
        return await _separate(file, mode_enum, None, engine)

    @api.get("/download")
    def download(path: str) -> FileResponse:
        """下载产物（仅允许 outputs 之内）/ download an artefact inside outputs."""
        target = Path(path).resolve()
        root = cfg.output_dir.resolve()
        if root not in target.parents and target != root:
            raise HTTPException(403, "只允许下载 outputs 目录内的文件 / outside outputs")
        if not target.is_file():
            raise HTTPException(404, "文件不存在 / not found")
        return FileResponse(str(target), filename=target.name)

    return api


app = create_app()


def run(host: str = "127.0.0.1", port: int = 8302, reload: bool = False,
        config: str | None = None) -> None:
    """起服务 / start uvicorn."""
    import uvicorn

    if reload or config:
        uvicorn.run("agentic_separate.server.app:app", host=host, port=port, reload=reload)
    else:
        uvicorn.run(app, host=host, port=port)


__all__ = ["app", "create_app", "run"]
