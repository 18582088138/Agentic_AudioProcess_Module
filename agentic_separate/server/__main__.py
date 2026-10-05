"""`python -m agentic_separate.server` —— 起 HTTP 服务。"""

from __future__ import annotations

from agentic_separate.core.config import load_config
from agentic_separate.server.app import run

if __name__ == "__main__":
    cfg = load_config()
    run(cfg.server.host, cfg.server.port)
