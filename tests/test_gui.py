"""GUI 上传路径 / GUI upload handling（分离插件侧）.

复测 / rerun:
    C:\\Users\\75203\\miniforge3\\envs\\ov_env_py312\\python.exe -m pytest tests/test_gui.py -q

覆盖 / covers: NiceGUI 3.x 的上传事件契约与文件名防目录穿越。
说明文档 / docs: issues/005 所在仓库的 `docs/`（上传问题与 ASR 侧同一个根因）
"""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

pytest.importorskip("nicegui")


def _upload(name: str, data: bytes = b"RIFFfakewave"):
    from nicegui.elements.upload_files import SmallFileUpload

    return SmallFileUpload(name=name, content_type="audio/wav", _data=data)


def test_save_upload_writes_file(tmp_path: Path) -> None:
    from agentic_separate.gui.app import save_upload

    dest = asyncio.run(save_upload(_upload("demo.wav"), tmp_path))
    assert dest.is_file() and dest.name == "demo.wav"
    assert dest.read_bytes() == b"RIFFfakewave"


def test_save_upload_strips_client_path(tmp_path: Path) -> None:
    from agentic_separate.gui.app import save_upload

    dest = asyncio.run(save_upload(_upload("../../evil.wav"), tmp_path))
    assert dest.parent == tmp_path and dest.name == "evil.wav"


def test_upload_event_arguments_shape() -> None:
    """框架契约回归：事件对象只有 `file`，**没有** `name` / `content`。

    用户实测报的 `'UploadEventArguments' object has no attribute 'name'`
    就是照 NiceGUI 2.x 的写法写的。
    """
    import dataclasses

    from nicegui import events

    fields = {f.name for f in dataclasses.fields(events.UploadEventArguments)}
    assert "file" in fields, f"上传事件里没有 file 字段：{fields}"
    assert "name" not in fields, f"事件对象重新有了 name 字段（{fields}）"


def test_gui_module_imports() -> None:
    from agentic_separate.gui import app as gui_app

    assert callable(gui_app.build_ui)
    assert callable(gui_app.run)
