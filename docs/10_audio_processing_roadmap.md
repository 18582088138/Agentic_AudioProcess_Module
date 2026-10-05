# 10 · 音频前后处理版图 / Audio processing roadmap

> 本模块的定位是**音频前后处理**，分离只是其中一类能力。
> 本文写「下一步做什么、候选方案是什么、怎么验收」；**未实现的能力不进 README 的功能表**。
> 跨模组的调研只在它自己的仓库或应用层写权威；本文只记录本模组的结论与本轮查到的候选方案。

## 1 · 已实现 / done

| 能力 | 库 | CLI | HTTP | 模型 |
|---|---|---|---|---|
| 人声提取 | `extract_vocals()` | `audio vocals` | `POST /vocals` | `UVR-MDX-NET-Voc_FT.onnx` |
| 背景音提取 | `extract_accompaniment()` | `audio accompaniment` | `POST /accompaniment` | `UVR-MDX-NET-Inst_Main.onnx` |
| 主体人声去除 | `remove_lead_vocal()` | `audio lead-removal` | `POST /lead-removal` | `UVR_MDXNET_KARA.onnx` |

## 2 · 待实现 / planned

| 能力 | 用户可感知的目标 | 候选方案 | 状态 |
|---|---|---|---|
| 降噪 | 空调 / 风扇 / 电流声 / 底噪明显减弱，语音不发闷、不金属化 | **`sherpa_onnx.OfflineSpeechDenoiser`** —— 本机 1.13.8 已带 GTCRN 与 DPDFNet 两种模型配置，权重在官方 `speech-enhancement-models` release；**零新增依赖** | 待调研 |
| 去环境音 | 房间感 / 混响减弱；环境声压下去，而**背景里的人声保留** | 分两步走：① 混响抑制（sherpa-onnx 无现成 dereverb，需先调研）② VAD 门控（只保留有语音的片段） | 待调研 |
| 音质优化 | 响度对齐到统一目标、峰值不削波、采样率与位深统一 | **纯 DSP**（numpy + soundfile）：重采样、峰值限制、响度近似对齐 | 待设计 |
| 统一管线 | 一条命令串起 解码 → 降噪 → 分离 → 落盘，中间结果可复用 | 门面内加 pipeline 层，每一步仍是可单独调用的函数 | 待设计 |

**不预先写死数字**：任何能力的体积 / RTF / 效果数字，都在**实测之后**才写进文档
（现有分离数字见 `PROJECT_MEMORY.md`；同一事实只在一处权威）。

降噪候选方案的出处：<https://github.com/k2-fsa/sherpa-onnx/releases/tag/speech-enhancement-models>
（sherpa-onnx 的 speech enhancement 例子见其 `c-api-examples/speech-enhancement-*.c`）。

## 3 · 硬约束（新增能力必须遵守）

1. **仍然不引入 torch / demucs**：优先 sherpa-onnx 生态；纯 DSP 能做的（响度、重采样、削波）
   绝不引模型。降噪按这条走，正好零新增依赖。
2. **不破坏既有约定**：各轨与输入**等长**；**不做**逐轨峰值归一化（除非新能力显式声明，
   并把声明写进结果与文档）。
3. **四个入口同步**：库 / CLI / HTTP / GUI，和分离三件套一样各自可单独调用。
4. **离线可测**：新能力要有确定性占位实现（对标 `engines/null.py`），
   真实权重用例打 `real` marker，默认不跑。

## 4 · 扩展点（代码上已经预留什么）

- **引擎层**：`engines/` 的 ABC 是「一进多出」（`separate(chunk, mode) -> {轨名: 波形}`）。
  降噪是「一进一出」，语义不同 —— **新增独立 ABC 与注册表**，不要塞进 `SeparationEngine`。
- **配置**：`configs/audioprocess.yaml` 按能力分段（当前是 engine / mode / models / output / server）。
- **文档**：每项能力各自一份 guide；不要把 `04_api_reference.md` 撑成百科。
- **命名**：包已叫 `agentic_audioprocess`、CLI 已叫 `audio`，新增子命令直接挂上去
  （如 `audio denoise`），不需要再动包名。

## 5 · 验收口径

| 类型 | 客观指标 | 主观（人工听） |
|---|---|---|
| 降噪 / 去环境音 | VAD 语音占比变化、rms 与峰值变化、与输入等长 | 语音是否发闷 / 金属化；背景是否被误杀 |
| 音质优化 | 峰值 ≤ 0 dBFS、目标响度偏差、采样率与位深正确 | 有无削波、泵动感 |

单测只跑与本次改动相关的用例（`-k`）；真实权重用例手动跑
`python -m pytest tests -q -m real`；阶段收尾跑 `tools/check.py`。
