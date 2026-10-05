# 006 · 装上 ruff 后暴露的 20 项既有问题

## 现象

`tools/check.py` 的 ruff 段报 **20 个错误**（ruff 0.16.10）。此前该段一直
`[SKIP] 未安装 ruff` —— 本轮改名重构执行 `pip install -e ".[all]"` 时把 dev extras 里的
ruff 装上，这是它**第一次真正运行**，因此暴露的是既有代码的问题。

本轮改名引入的 10 处 `I001`（import 排序）**已修完**：包名与门面文件名改成
`agentic_audioprocess.audioprocess` 后，字母序排到了 `core.*` 之前；另有
`engines/null.py` 一行超长需要换行。以下 20 项**与改名无关**。

## 判定（分四类）

| 规则 | 数量 | 性质 | 建议 |
|---|---|---|---|
| `B008` | 8 | **误报**：typer / FastAPI 的官方写法就是在参数默认值里调 `typer.Option()` / `File()` | 在 `pyproject.toml` 给 `cli.py` 与 `server/app.py` 加 per-file ignore（或全局忽略 `B008`） |
| `B023` | 4 | **要人看**：`gui/app.py` 循环内定义的闭包捕获了循环变量 `panel` | 逐处确认是否刻意；若否，用默认参数绑定 |
| `UP037` / `UP035` / `F541` | 5 | 纯风格，`--fix` 可自动修；已有 `from __future__ import annotations`，去引号安全 | 一次 `ruff check --fix` |
| `UP042` / `B027` / `UP036` | 3 | 各有行为含义：`class X(str, Enum)` 换 `StrEnum` 会改 `str()` 行为；ABC 空方法缺 `@abstractmethod`；`check.py` 的版本块已过时 | 逐条判断，**不要盲修** |

## 修法

1. 先补 ruff 配置（`B008` 的 per-file ignore），否则闸口长期红。
2. `ruff check --fix` 处理 5 项可自动修的。
3. `B023` / `UP042` / `B027` / `UP036` 逐条人工决定，改完跑闸口。

## 回归用例

`python tools/check.py` —— 三段（环境自检 / ruff / 全量测试）全绿。
若动了 `gui/app.py`，额外跑 `python -m pytest tests/test_gui.py -q`。

## 为什么记在这里

`tools/check.py` 是项目**唯一**的闸口（见 `docs/00_INDEX.md`），闸口长期红等于没有闸口；
但这属于既有问题，不塞进改名重构那一轮提交，避免一个 commit 混两件事。
