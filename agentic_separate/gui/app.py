"""图形界面 / GUI（NiceGUI）.

**三个功能各占一个面板**，都能独立调用；每个面板都会把分离出的轨直接做播放器，
方便立刻试听效果。耗时操作走 `run.io_bound`，界面不会被卡住。
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

from agentic_separate import __version__
from agentic_separate.core.config import SeparateConfig, load_config
from agentic_separate.core.errors import SeparateError
from agentic_separate.core.types import SeparationMode
from agentic_separate.separate import SeparateModule

_MODE_LABEL = {
    SeparationMode.VOCALS: "① 人声提取（要所有人声）",
    SeparationMode.ACCOMPANIMENT: "② 背景音提取（去掉所有人声）",
    SeparationMode.LEAD_REMOVAL: "③ 主体人声去除（保留背景人声）",
}


async def save_upload(file: Any, dest_dir: str | Path) -> Path:
    """把 NiceGUI 的上传对象存到目标目录 / persist a NiceGUI upload.

    **NiceGUI 3.x 的 API 与 2.x 不同**：`UploadEventArguments` 只有一个字段
    `file`（`FileUpload`，带 `name` / `content_type` / **`await save(path)`**）。
    2.x 的 `e.name` / `e.content` 已经不存在。文件名只取 basename 防目录穿越。
    """
    name = Path(str(getattr(file, "name", "") or "upload.bin")).name or "upload.bin"
    dest = Path(dest_dir) / name
    dest.parent.mkdir(parents=True, exist_ok=True)
    await file.save(str(dest))
    return dest


def build_ui(config: SeparateConfig | None = None) -> SeparateModule:
    """搭出界面并返回门面 / build the page and return the facade."""
    from nicegui import events, run as nice_run, ui

    cfg = config or load_config()
    module = SeparateModule(cfg)
    state: dict[str, Any] = {"path": ""}

    async def call(fn: Callable[..., Any], *args: Any, **kwargs: Any):
        try:
            return True, await nice_run.io_bound(fn, *args, **kwargs)
        except SeparateError as exc:
            return False, str(exc)
        except Exception as exc:  # noqa: BLE001
            return False, f"{type(exc).__name__}: {exc}"

    with ui.header().classes("items-center justify-between q-px-md"):
        ui.label(f"Agentic VoiceSeparate  {__version__}").classes("text-h6")
        engine_select = ui.select({e["name"]: e["name"] for e in module.engines()},
                                  value=cfg.engine.default,
                                  label="引擎 / engine").props("dense outlined").classes("w-40")
        status = ui.label("就绪 / ready").classes("text-caption")

    def set_status(text: str, ok: bool = True) -> None:
        status.text = text
        status.classes(replace="text-caption " + ("text-positive" if ok else "text-negative"))

    with ui.card().classes("w-full"):
        ui.label("素材 / media").classes("text-subtitle2")
        with ui.row().classes("items-center w-full"):
            path_input = ui.input("本地路径 / local path",
                                  placeholder=r"F:\path\to\audio.mp4").classes("grow")

            async def on_upload(e: events.UploadEventArguments) -> None:
                try:
                    dest = await save_upload(e.file, cfg.output_dir / "uploads")
                except Exception as exc:  # noqa: BLE001 - 上传失败不该让界面挂掉
                    set_status(f"上传失败 / upload failed: {exc}", ok=False)
                    return
                path_input.value = str(dest)
                set_status(f"已上传 / uploaded: {dest.name}")
                ui.notify(f"已上传 / uploaded: {dest.name}")

            ui.upload(on_upload=on_upload, auto_upload=True,
                      max_files=1).props('flat dense accept="audio/*,video/*"')

    def current_path() -> str | None:
        raw = (path_input.value or "").strip().strip('"')
        if not raw:
            set_status("请先指定素材 / pick a media file first", ok=False)
            return None
        if not Path(raw).exists():
            set_status(f"文件不存在 / not found: {raw}", ok=False)
            return None
        state["path"] = raw
        return raw

    def render_result(result) -> None:
        """把结果渲染成可试听的播放器 / render the stems as playable audio."""
        if result.lead_stem:
            ui.label(f"主体人声轨 / lead stem: {result.lead_stem}"
                     f"　判定依据 / evidence: {result.stem_order_resolved_by}").classes(
                "text-caption")
        for name, stem in result.stems.items():
            ui.label(f"{name} → {Path(stem.path).name}　{stem.duration:.2f}s").classes(
                "text-subtitle2 q-mt-sm")
            if stem.path and Path(stem.path).is_file():
                ui.audio(Path(stem.path).as_posix()).classes("w-full")
        for w in result.warnings:
            ui.label(f"⚠ {w}").classes("text-warning")

    with ui.tabs().classes("w-full") as tabs:
        tab_objects = {mode: ui.tab(label) for mode, label in _MODE_LABEL.items()}

    with ui.tab_panels(tabs, value=tab_objects[SeparationMode.LEAD_REMOVAL]).classes("w-full"):
        for mode, tab in tab_objects.items():
            with ui.tab_panel(tab):
                panel = ui.column().classes("w-full")

                async def do(mode: SeparationMode = mode) -> None:
                    if not (p := current_path()):
                        return
                    panel.clear()
                    with panel:
                        ui.label("处理中 / working…（首次加载模型需要几秒）")
                    set_status("处理中 / working…")
                    ok, result = await call(module.separate, p, mode,
                                            cfg.output_dir / "gui", engine_select.value)
                    panel.clear()
                    with panel:
                        if ok:
                            render_result(result)
                            set_status(f"完成 / done ({len(result.stems)} 轨)")
                        else:
                            ui.label(f"失败 / failed: {result}").classes("text-negative")
                            set_status("失败 / failed", ok=False)

                label = {SeparationMode.VOCALS: "提取人声 / extract vocals",
                         SeparationMode.ACCOMPANIMENT: "提取背景音 / extract accompaniment",
                         SeparationMode.LEAD_REMOVAL: "去除主体人声 / remove lead vocal"}[mode]
                ui.button(label, on_click=do).props("unelevated")

    ui.label("产物目录 / outputs: " + str(cfg.output_dir)).classes("text-caption q-pa-md")
    return module


def run(host: str = "127.0.0.1", port: int = 8402, config: str | None = None) -> None:
    """起界面 / launch the GUI."""
    from nicegui import ui

    build_ui(load_config(config))
    ui.run(host=host, port=port, title="Agentic VoiceSeparate", reload=False, show=True)


__all__ = ["build_ui", "run"]
