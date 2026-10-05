# 005 · 分离轨道顺序不能硬编码（官方示例与实测不一致）

**状态**：已处理（`SeparateModule._resolve_order` 三级判定）
**发现**：开发阶段真实权重实测，2026-10-04

---

## 现象 / Symptom

sherpa-onnx 的官方 Python 示例是这样写的：

```python
vocals = output.stems[0].data
non_vocals = output.stems[1].data
```

照抄之后实测「主体人声去除」的结果**方向反了**：该保留的背景人声被去掉、
该去掉的主体人声被留下。而且**没有任何报错** —— 产出的文件看起来完全正常。

用「中文主体（居中）+ 英文背景（偏侧、−10 dB）」的素材复测，两条轨的实际内容：

| 模型 | `stems[0]` | `stems[1]` |
|---|---|---|
| `UVR_MDXNET_KARA.onnx` | **中文（主体）** | 英文（背景） |
| `UVR_MDXNET_KARA_2.onnx` | **英文（背景）** | 中文（主体） |

⇒ **两个模型的顺序互不相同，其中一个还与官方示例相反。**

## 判定 / Diagnosis

`OfflineSourceSeparation` 返回的是一个**有序列表**，但不同权重导出时的输出通道顺序
并没有统一约定。官方示例只是针对它当时用的那个模型写的，不具备普遍性。

## 一次失败的尝试（记下来免得再走一遍）

我最初想用「**能量更高的那条是主体人声**」作为判据 —— 在「人声 + 人声」素材上
它确实成立（0.108 vs 0.065）。但换成「**人声 + 背景音乐**」素材复测就直接反了：

| 素材 | 人声轨 rms | 另一轨 rms |
|---|---|---|
| 人声 + 人声 | 0.1083（主体） | 0.0651（背景） |
| **人声 + 音乐** | 0.1114（人声） | **0.1533（音乐，反而更高）** |

⇒ **能量判据不可用**，已从代码里删掉。

## 修法 / Fix

`SeparateModule._resolve_order()` 采用**四级**判定，从可靠到兜底：

1. **配置显式指定** —— `engine.uvr.lead_stem_index`，用户说了算；
2. **模型约定表**（默认）—— `_MODEL_LEAD_INDEX`，本机实测得出的
   「该模型哪条轨是主体」：
   ```python
   "UVR_MDXNET_KARA.onnx": 0,     # stem0 = 主体
   "UVR_MDXNET_KARA_2.onnx": 1,   # 与 KARA 相反
   ```
3. **VAD 语音占比** —— 仅用于约定表里没有的模型；
4. **顺序兜底** —— 取第一条。

并且**把判定依据回传**到 `SeparationResult.stem_order_resolved_by`
（形如 `model-convention:UVR_MDXNET_KARA.onnx->stem0`）。
判定不可靠时（两条轨占比差 < 0.02）会额外写进 `warnings`。

## 补记：为什么 VAD 只能当兜底（跨插件联调时又踩了一次）

第一版把 **VAD 语音占比**当默认判据，结果在跨插件端到端验证里**判反了**。

素材：「中文主体（居中）+ 英文背景（偏侧 −10 dB）+ 正弦背景音乐」：

```
lead=accompaniment  依据=vad:speech_ratio {'vocals': 0.7624, 'accompaniment': 0.914}
```

**含音乐的那条轨占比反而更高**（0.914 > 0.7624）—— 背景音乐被 VAD 当成了语音。
于是「去掉主体人声」变成了「去掉背景人声」。用 ASR 复核确认了这一点：

| 轨（判反后） | ASR 识别结果 | 说明 |
|---|---|---|
| `background` | 开放时间早上9点至下午5点…（**中文**） | 本该干净，却仍有主体 |
| `lead` | The driver chased him corn for the boy…（**英文**） | 本该是主体，却是背景 |

改用模型约定表后：

| 轨（修正后） | ASR 识别结果 |
|---|---|
| `background` | The driver chased him corn for the boy…（英文，**背景人声保留**）✅ |
| `lead` | 开放时间早上9点至下午5点…（中文，**主体被摘出**）✅ |

**两条判据都不可靠，必须记下来**：

| 判据 | 反例 |
|---|---|
| 能量（rms） | 「人声 + 背景音乐」素材里音乐轨 0.1533 > 人声轨 0.1114 |
| VAD 语音占比 | 「人声 + 背景人声 + 音乐」素材里含音乐轨 0.914 > 人声轨 0.7624 |

所以**默认信任实测出来的模型约定**，VAD 只做未知模型的兜底并在依据串里注明
「未经模型约定表确认，可能有音乐干扰」。

## 回归用例 / Regression

`tests/test_module.py::test_lead_removal_can_be_forced_by_config`（离线）
—— 断言 `lead_stem_index` 生效，且证据串里带 `config:`。

`tests/test_module.py::test_model_convention_wins_over_vad`（离线）
—— 用一个「VAD 会判反」的假引擎（一条轨是纯音乐、一条是语音）断言
**模型约定表优先**，不会退回 VAD。

`tests/test_real.py::test_kara_separates_lead_from_background`（`-m real`）
—— 用真实的「主体 + 背景」素材断言两条轨**都不是静音**
（若退化成普通的人声/伴奏二分，背景轨会接近静音）。

## 备注

对应 `docs/01_design.md §4.5`、`Agentic_ASR_Module/docs/00_research.md §4.4`。
