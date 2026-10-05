"""命令行 / Command line interface.

    separate doctor                        # 体检
    separate engines                       # 引擎与模式
    separate vocals        <media>         # 人声提取
    separate accompaniment <media>         # 背景音提取
    separate lead-removal  <media>         # 主体人声去除
    separate run           <media> --mode both
    separate serve / separate gui
"""

from __future__ import annotations

import json
from pathlib import Path

import typer
from rich.console import Console
from rich.table import Table

from agentic_separate import __version__
from agentic_separate.core.config import load_config
from agentic_separate.core.errors import SeparateError
from agentic_separate.core.types import SeparationMode
from agentic_separate.separate import SeparateModule

app = typer.Typer(add_completion=False, no_args_is_help=True,
                  help="Agentic_VoiceSeparate_Module —— 本地声音分离插件")
console = Console()


def _module(engine: str | None = None, config: str | None = None) -> SeparateModule:
    return SeparateModule(config=load_config(config), engine=engine)


def _fail(exc: Exception) -> None:
    console.print(f"[red]错误 / error:[/red] {exc}")
    raise typer.Exit(code=1)


def _show(result) -> None:
    console.print(f"[bold]{result.engine}[/bold]  mode={result.mode}  "
                  f"duration={result.duration:.2f}s  sr={result.sample_rate}")
    if result.lead_stem:
        console.print(f"主体人声轨 / lead stem: [bold]{result.lead_stem}[/bold]"
                      f"　判定依据 / evidence: {result.stem_order_resolved_by}")
    table = Table(title="轨 / stems")
    for col in ("名称", "文件", "时长", "采样率", "声道"):
        table.add_column(col)
    for name, stem in result.stems.items():
        table.add_row(name, Path(stem.path).name if stem.path else "",
                      f"{stem.duration:.2f}", str(stem.sample_rate), str(stem.channels))
    console.print(table)
    for w in result.warnings:
        console.print(f"[yellow]warn:[/yellow] {w}")


def _run(mode: SeparationMode, media: Path, out_dir: Path | None, engine: str | None,
         config: str | None) -> None:
    try:
        result = _module(engine, config).separate(media, mode, out_dir, engine)
    except SeparateError as exc:
        _fail(exc)
        return
    _show(result)


@app.command()
def version() -> None:
    """打印版本 / print the version."""
    console.print(f"agentic-separate {__version__}")


@app.command()
def doctor(config: str = typer.Option(None, "--config")) -> None:
    """环境与模型体检 / self-check（不加载权重）."""
    console.print_json(json.dumps(_module(config=config).doctor(),
                                  ensure_ascii=False, default=str))


@app.command()
def engines() -> None:
    """列出引擎与支持的模式 / list engines and their modes."""
    table = Table(title="分离引擎 / engines")
    table.add_column("引擎"), table.add_column("默认"), table.add_column("模式")
    for item in _module().engines():
        table.add_row(item["name"], "✓" if item.get("default") else "",
                      ", ".join(item.get("modes") or []) or (item.get("error") or ""))
    console.print(table)


@app.command()
def vocals(media: Path, out_dir: Path = typer.Option(None, "--out-dir"),
           engine: str = typer.Option(None), config: str = typer.Option(None, "--config")) -> None:
    """人声提取：要所有人声 / extract every voice."""
    _run(SeparationMode.VOCALS, media, out_dir, engine, config)


@app.command()
def accompaniment(media: Path, out_dir: Path = typer.Option(None, "--out-dir"),
                  engine: str = typer.Option(None),
                  config: str = typer.Option(None, "--config")) -> None:
    """背景音提取：去掉所有人声 / extract the instrumental bed."""
    _run(SeparationMode.ACCOMPANIMENT, media, out_dir, engine, config)


@app.command("lead-removal")
def lead_removal(media: Path, out_dir: Path = typer.Option(None, "--out-dir"),
                 engine: str = typer.Option(None),
                 lead_index: int = typer.Option(None, "--lead-index",
                                                help="强制指定哪条轨是主体人声"),
                 config: str = typer.Option(None, "--config")) -> None:
    """主体人声去除：只去主体，保留背景人声 / remove the lead voice only."""
    try:
        module = _module(engine, config)
        if lead_index is not None:
            module.config.engine.uvr.lead_stem_index = lead_index
        result = module.separate(media, SeparationMode.LEAD_REMOVAL, out_dir, engine)
    except SeparateError as exc:
        _fail(exc)
        return
    _show(result)


@app.command()
def run(media: Path, mode: str = typer.Option("both", "--mode"),
        out_dir: Path = typer.Option(None, "--out-dir"), engine: str = typer.Option(None),
        config: str = typer.Option(None, "--config")) -> None:
    """通用入口 / generic entry（--mode vocals|accompaniment|lead_removal|both）."""
    try:
        mode_enum = SeparationMode(mode.lower())
    except ValueError:
        _fail(SeparateError(f"未知模式 / unknown mode: {mode}"))
        return
    _run(mode_enum, media, out_dir, engine, config)


@app.command()
def serve(host: str = typer.Option(None), port: int = typer.Option(None),
          config: str = typer.Option(None, "--config")) -> None:
    """起 HTTP 服务 / run the HTTP service."""
    from agentic_separate.server.app import run as serve_run

    cfg = load_config(config)
    serve_run(host or cfg.server.host, port or cfg.server.port, config=config)


@app.command()
def gui(host: str = typer.Option(None), port: int = typer.Option(None),
        config: str = typer.Option(None, "--config")) -> None:
    """起图形界面 / launch the GUI."""
    from agentic_separate.gui.app import run as gui_run

    cfg = load_config(config)
    gui_run(host or cfg.server.host, port or (cfg.server.port + 100), config=config)


def main() -> None:
    try:
        app()
    except KeyboardInterrupt:  # pragma: no cover
        raise SystemExit(130) from None


if __name__ == "__main__":
    main()
