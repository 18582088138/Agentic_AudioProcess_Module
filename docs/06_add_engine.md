# 06 · 怎么接一个新的分离引擎 / Adding an engine

> 现有两个引擎：`uvr`（sherpa-onnx 的 UVR MDX 系 onnx，主力）与 `null`（占位）。
> 本文说清接入一个（比如 demucs / RoFormer / 云端分离 API）要动哪些地方、
> 有哪些**不写就会静默出错**的契约。
> 引擎抽象的设计理由见 `01_design.md §2`。

---

## 1 · 四步 / four steps

### ① 建文件 `agentic_separate/engines/mysep.py`

最小骨架（可直接改名起用）：

```python
"""我的分离引擎 / my separation engine.

一句话写清：它做什么、与 uvr 的区别、需要什么权重。
"""

from __future__ import annotations

from typing import Any

import numpy as np

from agentic_separate.core.errors import EngineError, ModelMissingError
from agentic_separate.core.types import AudioChunk, SeparationMode
from agentic_separate.engines.base import (
    ACCOMPANIMENT,
    VOCALS,
    SeparationEngine,
)


class MyEngine(SeparationEngine):
    """一个分离引擎 / one separation engine."""

    name = "myengine"
    implemented = True

    def __init__(self, config: Any = None) -> None:
        super().__init__(config)
        self._backend = None          # 权重句柄，懒加载

    # ── 能力：必须不加载权重就能回答 ────────────────────────────────────
    @classmethod
    def declared_modes(cls) -> set[SeparationMode]:
        # 只声明**真能跑**的模式；声明了却跑不了，用户会在运行时才撞到
        return {SeparationMode.VOCALS, SeparationMode.ACCOMPANIMENT,
                SeparationMode.LEAD_REMOVAL, SeparationMode.BOTH}

    # ── 分离：唯一必实现的方法 ──────────────────────────────────────────
    def separate(self, chunk: AudioChunk, mode: SeparationMode,
                 lead_index: int | None = None) -> dict[str, np.ndarray]:
        self.require(mode)            # 不支持就报错，绝不静默降级
        self._ensure()                # 懒加载权重

        first, second = self._infer(chunk)      # 两条轨，形状必须与输入同形

        if mode == SeparationMode.VOCALS:
            return {VOCALS: first}
        if mode == SeparationMode.ACCOMPANIMENT:
            return {ACCOMPANIMENT: second}
        if mode == SeparationMode.BOTH:
            return {VOCALS: first, ACCOMPANIMENT: second}
        # LEAD_REMOVAL：两条都交回门面，由门面按判定结果映射成 lead / background
        return {VOCALS: first, ACCOMPANIMENT: second}

    # ── 加载与释放 ─────────────────────────────────────────────────────
    def _ensure(self) -> None:
        if self._backend is not None:
            return
        from pathlib import Path

        path = Path("models/my-model.onnx")      # 或从 self.config 取
        if not path.is_file():
            raise ModelMissingError(
                f"权重缺失 / weight missing: {path}\n"
                f"下载 / download: <给出确切地址>")
        try:
            self._backend = _load(path)
        except Exception as exc:  # noqa: BLE001
            raise EngineError(f"加载失败 / failed to load: {exc}") from exc
        self.loaded = True

    def _infer(self, chunk: AudioChunk) -> tuple[np.ndarray, np.ndarray]:
        ...      # 你的推理；返回两条与 chunk.samples 同形的 float32 波形

    def release(self) -> None:
        self._backend = None
        self.loaded = False
        import gc

        gc.collect()
```

### ② 登记到注册表

`agentic_separate/engines/__init__.py`：

```python
ENGINES: dict[str, str] = {
    "uvr": "agentic_separate.engines.uvr:UvrEngine",
    "null": "agentic_separate.engines.null:NullEngine",
    "myengine": "agentic_separate.engines.mysep:MyEngine",   # ← 加这行
}
```

存的是 `"模块:类名"` 字符串 —— **延迟导入**是有意的：列一遍引擎名不该把
sherpa-onnx 拉进来（那要几秒）。所以**不要在 `__init__.py` 顶部 import 你的引擎**。

### ③ 配置里选它

`configs/separate.yaml`：

```yaml
engine:
  default: myengine        # 或临时用 SeparateModule(engine="myengine")
```

如果新引擎需要**按模式加载不同权重**，把它加进 `models` 映射（门面的
`config.model_path(mode)` 会读这张表）：

```yaml
models:
  lead_removal: my-kara.onnx
  vocals: my-vocals.onnx
  accompaniment: my-inst.onnx
```

### ④ 写测试

照抄 `tests/test_module.py::test_engine_returns_same_shape` 的结构：
用**确定性输入**断言形状与轨名，不要断言具体音质。至少覆盖：

| 要测的 | 参考用例 |
|---|---|
| 输出与输入**同形** | `test_engine_returns_same_shape` |
| 不支持的模式**报错** | `test_require_rejects_unsupported_mode` |
| 引擎清单能列出它、且**不加载权重** | `test_registry_and_capabilities_without_weights` |
| 走一遍门面三个功能 | `test_extract_vocals` / `test_extract_accompaniment` / `test_remove_lead_vocal_produces_lead_and_background` |

真实权重用例放 `tests/test_real.py` 并打 `@pytest.mark.real`。

---

## 2 · 五条硬约束 / hard contracts

不遵守会**静默出错**（不报错，但结果没用），逐条都是踩出来的。

### 2.1 输出波形必须与输入**同形**

门面的 `_enforce_same_length()` 依赖这条契约来保证「各轨与输入等长」。
形状对不上（比如少了几个样本、或者声道数不对），门面虽然会裁剪/补零，
但那是安全网而不是常态 —— 补出来的部分是**假数据**。

### 2.2 键名契约：`vocals` / `accompaniment` 是规范名

门面 `_to_output_stems()` 对三种模式是**按键取值**的：

| 模式 | 门面怎么取 | 引擎必须返回的键 |
|---|---|---|
| `vocals` | `raw[VOCALS]` | **必须有 `"vocals"`** |
| `accompaniment` | `raw[ACCOMPANIMENT]` | **必须有 `"accompaniment"`** |
| `both` | 两个都取 | **两个都要有** |
| `lead_removal` | 按判定结果把两条映射成 `lead` / `background` | 键名**不限**，但必须有**两条** |

（`uvr` 引擎在 `lead_removal` 时也返回 `{vocals, accompaniment}` 当占位，
门面不会直接用这两个名字。）

### 2.3 `declared_modes()` 必须不加载权重就能回答

GUI 与 HTTP 在**开机时**就要用它把引擎选择器与提示填出来。
为了查能力先载 50 MB 权重是不可接受的。

### 2.4 不支持的模式必须 `require()` 报错

```python
self.require(mode)      # 一行，别省
```

静默降级（比如 `lead_removal` 不支持就悄悄返回全部人声）会让调用方拿到一份
看起来正常、语义却错的结果 —— 这是最贵的一类 bug。

### 2.5 权重懒加载，换模型先释放

构造引擎实例必须**瞬时**（界面开机要列引擎）。加载放在 `_ensure()` 里。
若一个引擎会按模式换权重，进新权重前先 `self.release()` —— 8 GB 卡上两份权重
同时驻留是自找麻烦（`uvr` 引擎就是这么做的）。

---

## 3 · 若新引擎要支持「主体人声去除」

`LEAD_REMOVAL` 有个额外要求：**得说清哪条轨是主体人声**。

门面的 `_resolve_order()` 是四级判定（配置 → 模型约定表 → VAD → 兜底），
其中**模型约定表**按**权重文件名**查：

```python
# agentic_separate/separate.py
_MODEL_LEAD_INDEX = {
    "UVR_MDXNET_KARA.onnx": 0,      # 实测：stem0 = 主体
    "UVR_MDXNET_KARA_2.onnx": 1,    # 实测：stem1 = 主体，与 KARA 相反
}
```

所以接入新引擎时你**二选一**：

1. **在 `_MODEL_LEAD_INDEX` 里加一条** —— 先在真实素材上实测出哪条是主体，
   再把结论写进去（不要照抄官方示例，`issues/005` 就是照抄踩的坑）；
2. **让用户显式指定** `engine.uvr.lead_stem_index`（或在 CLI 上加 `--lead-index`）。

**不要**指望 VAD 兜底：实测它会把**背景音乐当成语音**，含音乐的轨占比反而更高
（0.914 > 0.7624），方向会整个判反。详见 `issues/005`。

---

## 4 · 能不能接云端分离 API

可以，抽象是通用的（引擎只要吐波形）。但有两点要自己处理：

1. **上传/下载开销**：云端通常有体积与时长上限，切分与拼接得自己写
   （门面目前**不做**分片，它假定引擎能吃下整段）；
2. **`lead_removal` 的语义**：得先确认那家 API 到底是「去主唱留伴唱」
   还是「去掉所有人声」—— 这两者在业务上是不同的功能
   （见 `01_design.md §1.1`），别被名字骗了。

---

## 5 · 相关文档

| 想知道什么 | 读哪份 |
|---|---|
| 引擎抽象为什么这么窄 | `01_design.md §2`、`§3` |
| 轨道判定的四级策略与踩坑 | `01_design.md §4.1`、`issues/005` |
| 权重下载与许可注意事项 | `05_deployment.md`、`01_design.md §8.2` |
| 测试怎么组织 | `03_unit_tests.md` |
