---
name: agentic-audioprocess-dev
description: Agentic_AudioProcess_Module 开发约定 —— 三个模式与模型的映射、轨道顺序判定、等长校验、测试与提交纪律。改这个项目的代码前先读。
---

# Agentic_AudioProcess_Module 开发 skill

## 三个模式，三套模型（这是本插件存在的理由）

| 模式 | 模型 | 语义 |
|---|---|---|
| `vocals` | `UVR-MDX-NET-Voc_FT.onnx` | 要**所有**人声 |
| `accompaniment` | `UVR-MDX-NET-Inst_Main.onnx` | 去掉**所有**人声 |
| `lead_removal` | `UVR_MDXNET_KARA.onnx` | 只去**主体**人声，**背景人声保留** |
| `both` | 同 vocals | 两轨都要 |

**不许把 `lead_removal` 和 `accompaniment` 混为一谈** —— 前者用 KARA 系（按
「主唱 vs 伴唱」训练），后者用通用模型（按「人声 vs 非人声」训练）。
实测通用模型做不到「保留背景人声」。

## 分层边界

```
用法层  cli.py / server/ / gui/     三者调用同一个门面
门面层  AudioProcessModule (audioprocess.py)  解码归一 · 轨道顺序判定 · 等长校验 · 落盘命名
引擎层  engines/*                    唯一必实现：separate(chunk, mode) -> {轨名: 波形}
```

新增引擎两步：实现 `separate()` + 声明 `declared_modes()`，且必须不加载权重可答。

## 三个硬约束

1. **等长**：各轨必须与输入样本数一致。门面 `_enforce_same_length()` 会裁剪/补零
   并写 warning —— 不等长会让下游时间轴整体漂移且不报错。
2. **轨道顺序不许硬编码**：官方示例写 `stems[0]=vocals`，但实测 KARA 与 KARA_2
   **顺序相反**。用 `_resolve_order()` 的**四级判定**
   （配置 → **模型约定表** → VAD 语音占比 → 兜底），
   并把依据回传到 `stem_order_resolved_by`。`issues/005`
   ⚠️ **能量与 VAD 都被实测否决过，默认只信模型约定表**：
   - 能量：音乐轨 rms 0.1533 > 人声轨 0.1114；
   - VAD：含音乐的轨占比 0.914 > 人声轨 0.7624（**方向判反**，
     跨插件联调时抓到的 ——「去掉主体人声」变成了「去掉背景人声」）。
3. **不做逐轨峰值归一化**：会破坏轨间相对音量，两轨再也混不回原样。

## 输入要求

UVR 模型**只接受 44.1 kHz 立体声 wav**（官方口径）。门面负责从任意容器归一，
`audio/io.py::decode()` 出口固定是 `(num_samples, 2)`。

## 依赖纪律

**只依赖 `sherpa-onnx`**（+2 个包）。不要引入 torch 或 demucs：
- 实测 CPU RTF 0.23~0.36，比 demucs 在 GPU 上还快（0.74）；
- 显存占用为 0，8 GB 卡可以整块留给 ASR 模块；
- 模型只有 28~67 MB。

## 测试与提交

- 默认排除 `real`；真实权重用例在 `tests/test_real.py`。
- 核心断言在 `test_kara_separates_lead_from_background`：两条轨都必须**不是静音**
  （若退化成普通二分，背景轨会接近静音）。
- **AI 不执行 `git commit` / `git push`**；commit 类型前缀英文、正文中文。
