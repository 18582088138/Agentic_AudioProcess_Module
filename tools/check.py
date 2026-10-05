"""收尾闸口 / the single project gate.

    C:\\Users\\75203\\miniforge3\\envs\\ov_env_py312\\python.exe tools\\check.py

三件事 / three stages: 环境自检 → ruff → 全量测试（默认排除 `real`）。
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PY = sys.executable


def section(title: str) -> None:
    print(f"\n{'=' * 70}\n{title}\n{'=' * 70}")


def run(cmd: list[str]) -> bool:
    print(f"$ {' '.join(cmd)}")
    proc = subprocess.run(cmd, cwd=str(ROOT), check=False)
    if proc.returncode != 0:
        print(f"[FAIL] 退出码 / exit code: {proc.returncode}")
        return False
    return True


def environment() -> bool:
    section("1/3 环境自检 / environment self-check")
    ok = True
    print(f"python      : {sys.version.split()[0]}  ({PY})")
    if sys.version_info < (3, 12):
        print("[FAIL] 需要 Python >= 3.12")
        ok = False
    print(f"ffmpeg      : {shutil.which('ffmpeg') or '[MISSING]'}")
    if shutil.which("ffmpeg") is None:
        print("[WARN] 没有 ffmpeg：非 wav 输入将不可用")

    for name in ("numpy", "soundfile", "yaml", "pydantic", "typer"):
        try:
            mod = __import__(name)
            print(f"{name:<12}: {getattr(mod, '__version__', 'ok')}")
        except ImportError:
            print(f"[FAIL] 缺少依赖 / missing: {name}")
            ok = False
    try:
        import sherpa_onnx

        print(f"{'sherpa_onnx':<12}: {getattr(sherpa_onnx, '__version__', 'ok')}")
    except ImportError:
        print("[FAIL] 缺少 sherpa-onnx：所有分离功能都不可用")
        ok = False

    try:
        from agentic_separate.core.config import load_config

        cfg = load_config(None)
        for mode, fname in cfg.models.items():
            p = cfg.resolve_model_dir() / fname
            print(f"model {mode:<14}: {'OK' if p.is_file() else '[MISSING]'}  {p.name}")
        vad = cfg.resolve_model_dir().parent / "sherpa-vad" / "silero_vad.onnx"
        print(f"vad         : {'OK' if vad.is_file() else '[MISSING]'}  {vad.name}")
    except Exception as exc:  # noqa: BLE001
        print(f"[FAIL] 配置不可加载 / config failed: {exc}")
        ok = False
    return ok


def lint() -> bool:
    section("2/3 ruff 静态检查 / lint")
    proc = subprocess.run([PY, "-m", "ruff", "check", "."], cwd=str(ROOT), check=False,
                          capture_output=True, text=True, encoding="utf-8", errors="replace")
    if "No module named" in (proc.stderr or ""):
        print("[SKIP] 未安装 ruff（pip install -e \".[dev]\"）")
        return True
    print(proc.stdout.strip() or "(无输出 / no output)")
    if proc.returncode != 0:
        print("[FAIL] ruff 发现问题")
        return False
    print("[OK] ruff 通过")
    return True


def tests() -> bool:
    section("3/3 全量测试 / full test suite（默认排除 real）")
    return run([PY, "-m", "pytest", "tests", "-q"])


def main() -> int:
    results = {
        "环境自检 / environment": environment(),
        "ruff": lint(),
        "测试 / tests": tests(),
    }
    section("汇总 / summary")
    for name, passed in results.items():
        print(f"{'[OK]  ' if passed else '[FAIL]'} {name}")
    failed = [n for n, p in results.items() if not p]
    if failed:
        print(f"\n未通过 / failed: {', '.join(failed)}")
        return 1
    print("\n全部通过 / all green")
    return 0


if __name__ == "__main__":
    sys.exit(main())
