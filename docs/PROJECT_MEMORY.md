# 项目记忆 / Project memory

> 新会话接手先读这里，再读 `docs/00_INDEX.md`。

## 当前状态（2026-10）

**分离功能开发已完成**，`tools/check.py` 全绿（数字现跑）；
**项目已改名为音频处理模块**（原 VoiceSeparate），标识符映射见本文 §改名重构。

本仓库是**音频处理模组**（分离 + 前后处理）。转写等能力不在本模组 ——
**模组之间不许互相引用、互相指引**（守则 §七）：需要串联多个模组时由**应用层 pipeline**
组合，脚本放在模组之外（`F:\2026年\Agentic_Pipelines\`），不写进任何模组。

剩下的是**人工动作**：

| 待办 | 看哪 |
|---|---|
| **本轮改名的 git 提交** | `docs/11_git_commands_rename.md` |
| 首轮开发的分步指令（已执行完，留档） | `docs/08_git_commands.md` |
| 降噪 / 去环境音 / 音质优化的推进 | `docs/10_audio_processing_roadmap.md` |
| **拿真实影视素材复验泛化性** —— 这是本插件最要紧的未验项 | `docs/09_dev_log.md` 的后续待办 |
| 界面手工验证 | `docs/07_gui_guide.md` 的 9 步清单 |

**本插件最需要被真实素材检验的一点**：KARA 系模型的训练域是**音乐**，
而「主体人声去除」用在**影视对白**上时是否依然可靠，目前只在**合成素材**上验证过
（中文主体 + 英文背景，结论是能分开）。真实素材表现请你复验。

**接手顺序**：本文件 → `docs/00_INDEX.md` → 按需读一份。
**改代码前必读** `.dsh/skills/agentic-audioprocess-dev/SKILL.md`。

## 环境

| 项 | 值 |
|---|---|
| Python | `C:\Users\75203\miniforge3\envs\ov_env_py312\python.exe`（3.12.14） |
| ffmpeg | `C:\Users\75203\Documents\ffmpeg-master\bin`（**已在 PATH**，必需） |
| 依赖 | 只有 `sherpa-onnx`（+2 个包）。**不需要 torch，也不需要 demucs** |
| GPU | 不参与。分离全部在 CPU 上跑，显存占用 0（后续处理能力同样按 CPU 优先选型） |

## 常用命令

```bash
cd F:\2026年\Agentic_AudioProcess_Module
python -m pytest tests -q               # 离线（约 5 秒）
python -m pytest tests -q -m real       # 真实 UVR 权重（约 30 秒）
python tools/check.py                   # 收尾闸口

audio doctor / engines / vocals / accompaniment / lead-removal / run / serve / gui
```

## 实测数字（不要凭印象改）

| 模型 | 体积 | RTF（CPU） | 显存 |
|---|---|---|---|
| `UVR_MDXNET_KARA.onnx` | 28 MB | **0.232** | **0** |
| `UVR_MDXNET_KARA_2.onnx` | 50 MB | 0.363 | 0 |
| （对照）demucs htdemucs | ~300 MB | 0.740（GPU） | +861 MB |

## 三条硬约束

1. **轨道顺序不许硬编码**：官方示例写 `stems[0]=vocals`，实测 KARA 与 KARA_2 相反。
   **四级判定**：配置 → **模型约定表**（默认）→ VAD 语音占比 → 兜底；
   依据回传到 `stem_order_resolved_by`。
   **能量与 VAD 都被实测否决过**：能量 —— 音乐轨 rms 0.1533 > 人声轨 0.1114；
   VAD —— 含音乐的轨占比 0.914 > 人声轨 0.7624（导致方向判反）。`issues/005`
2. **各轨必须与输入等长**：门面强制校验并对齐，不等长会让下游时间轴整体漂移且不报错。
3. **不做逐轨峰值归一化**：会破坏轨间相对音量，两轨再也混不回原样。

## 一条容易踩的环境坑

下载权重**必须用 python `requests`**：`curl.exe` 在 Windows 上会被 schannel 中断
（`server closed abruptly`）。模型要从 sherpa-onnx 官方 release 下，
不要下上游 `TRvlvr/model_repo` 的原件（缺 metadata，读不了）。

## 三个模式对应三套模型（别混）

| 模式 | 模型 | 语义 |
|---|---|---|
| `vocals` | `UVR-MDX-NET-Voc_FT.onnx` | 要**所有**人声 |
| `accompaniment` | `UVR-MDX-NET-Inst_Main.onnx` | 去掉**所有**人声 |
| `lead_removal` | `UVR_MDXNET_KARA.onnx` | 只去**主体**人声，背景人声保留 |

## 改名重构（VoiceSeparate → AudioProcess）

只改**项目级标识符**；语义本来就属于「分离」的符号一律保留，改了反而错。

| 项 | 旧 | 新 |
|---|---|---|
| 仓库 / 目录 | `Agentic_VoiceSeparate_Module` | `Agentic_AudioProcess_Module` |
| 分发名 | `agentic-separate` | `agentic-audioprocess` |
| 包名 | `agentic_separate` | `agentic_audioprocess` |
| 门面文件 | `separate.py` | `audioprocess.py` |
| 门面类 | `SeparateModule` | `AudioProcessModule` |
| 配置类 | `SeparateConfig` | `AudioProcessConfig` |
| 异常基类 | `SeparateError` | `AudioProcessError` |
| 配置文件 | `configs/separate.yaml` | `configs/audioprocess.yaml` |
| CLI | `separate` | `audio` |
| 环境变量前缀 | `SEPARATE_*` | `AUDIOPROCESS_*` |
| 开发 skill | `agentic-separate-dev` | `agentic-audioprocess-dev` |

**保留**：`SeparationMode` / `SeparationResult` / `SeparationEngine` / `StemOrderError` /
`SEPARATION_SR` / 门面方法 `separate()` / HTTP 端点 `/separate`。

改名后必须重装 editable 包（旧 `egg-info` 指向旧包名）：`pip install -e ".[all]"`。
本地 `.env` 若存在，把 `SEPARATE_*` 改成 `AUDIOPROCESS_*`（本机当前**没有** `.env`，
所以无迁移成本）。提交指令见 `docs/11_git_commands_rename.md`。

## 模组独立性（守则 §七，硬约束）

**不许互相引用、互相指引**：不 import 别的模组，不贴别的模组的路径 / API / issue /
设计正文；需要串联多个模组时由**应用层 pipeline** 组合，脚本放在模组之外
（`F:\2026年\Agentic_Pipelines\`）。本仓库只记录本模组的结论。

## 提交纪律

**AI 不执行 `git commit` / `git push`**，指令交人工执行。
commit 类型前缀英文（feat/fix/docs/test/chore/refactor），正文中文。
