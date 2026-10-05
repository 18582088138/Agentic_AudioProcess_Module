"""CLI 与 HTTP 服务 / CLI and HTTP service.

复测 / rerun:
    C:\\Users\\75203\\miniforge3\\envs\\ov_env_py312\\python.exe -m pytest tests/test_server_cli.py -q

覆盖 / covers: CLI 子命令、HTTP 三个功能端点与下载端点越权防护（默认 null 引擎）。
说明文档 / docs: docs/01_design.md §7
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

from agentic_audioprocess.core.config import load_config


def _run_cli(*args: str, timeout: int = 300) -> subprocess.CompletedProcess[str]:
    return subprocess.run([sys.executable, "-m", "agentic_audioprocess.cli", *args],
                          capture_output=True, text=True, encoding="utf-8",
                          errors="replace", timeout=timeout)


def test_cli_version() -> None:
    proc = _run_cli("version")
    assert proc.returncode == 0
    assert "agentic-audioprocess" in proc.stdout


def test_cli_engines() -> None:
    proc = _run_cli("engines")
    assert proc.returncode == 0
    assert "null" in proc.stdout and "uvr" in proc.stdout


def test_cli_doctor() -> None:
    proc = _run_cli("doctor")
    assert proc.returncode == 0
    assert "models" in proc.stdout


def test_cli_vocals_with_null_engine(voice_over_music_wav: Path, tmp_path: Path) -> None:
    proc = _run_cli("vocals", str(voice_over_music_wav), "--engine", "null",
                    "--out-dir", str(tmp_path / "out"))
    assert proc.returncode == 0, proc.stderr
    assert "vocals" in proc.stdout


def test_cli_lead_removal_with_null_engine(voice_over_music_wav: Path,
                                           tmp_path: Path) -> None:
    proc = _run_cli("lead-removal", str(voice_over_music_wav), "--engine", "null",
                    "--out-dir", str(tmp_path / "out"))
    assert proc.returncode == 0, proc.stderr
    assert "background" in proc.stdout
    # 判定依据必须打印出来，否则判反了没法从 CLI 看出来
    assert "evidence" in proc.stdout or "判定依据" in proc.stdout


def test_cli_reports_missing_file() -> None:
    proc = _run_cli("vocals", "Z:/nope/missing.wav", "--engine", "null")
    assert proc.returncode != 0


@pytest.fixture()
def client(tmp_path: Path):
    pytest.importorskip("fastapi")
    from fastapi.testclient import TestClient

    from agentic_audioprocess.server.app import create_app

    cfg = load_config(None)
    cfg.engine.default = "null"
    cfg.output_dir = tmp_path / "outputs"
    cfg.output_dir.mkdir(parents=True, exist_ok=True)
    with TestClient(create_app(cfg)) as c:
        yield c


def test_healthz(client) -> None:
    body = client.get("/healthz").json()
    assert body["ok"] is True


def test_engines_endpoint(client) -> None:
    body = client.get("/engines").json()
    assert any(e["name"] == "null" for e in body["engines"])


def test_doctor_endpoint(client) -> None:
    assert "checks" in client.get("/doctor").json()


def test_vocals_endpoint(client, voice_over_music_wav: Path) -> None:
    with voice_over_music_wav.open("rb") as fh:
        resp = client.post("/vocals", files={"file": ("a.wav", fh, "audio/wav")})
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert "vocals" in body["stems"]


def test_accompaniment_endpoint(client, voice_over_music_wav: Path) -> None:
    with voice_over_music_wav.open("rb") as fh:
        resp = client.post("/accompaniment", files={"file": ("a.wav", fh, "audio/wav")})
    assert resp.status_code == 200, resp.text
    assert "accompaniment" in resp.json()["stems"]


def test_lead_removal_endpoint(client, voice_over_music_wav: Path) -> None:
    with voice_over_music_wav.open("rb") as fh:
        resp = client.post("/lead-removal", files={"file": ("a.wav", fh, "audio/wav")})
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert "background" in body["stems"]
    assert body["stem_order_resolved_by"]


def test_separate_endpoint_bad_mode(client, voice_over_music_wav: Path) -> None:
    with voice_over_music_wav.open("rb") as fh:
        resp = client.post("/separate", files={"file": ("a.wav", fh, "audio/wav")},
                           data={"mode": "bogus"})
    assert resp.status_code == 422


def test_unsupported_suffix_rejected(client, tmp_path: Path) -> None:
    bad = tmp_path / "note.txt"
    bad.write_text("not audio", encoding="utf-8")
    with bad.open("rb") as fh:
        resp = client.post("/vocals", files={"file": ("note.txt", fh, "text/plain")})
    assert resp.status_code == 415


def test_download_confined_to_outputs(client) -> None:
    resp = client.get("/download", params={"path": str(Path.home() / ".dsh" / "AGENTS.md")})
    assert resp.status_code in (403, 404)
