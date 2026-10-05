"""`python -m agentic_audioprocess.server` —— 起 HTTP 服务。"""

from __future__ import annotations

from agentic_audioprocess.core.config import load_config
from agentic_audioprocess.server.app import run

if __name__ == "__main__":
    cfg = load_config()
    run(cfg.server.host, cfg.server.port)
