# Agentic AudioProcess Module

可插拔的**本地音频处理服务插件**：吃进音频/视频，吐出可直接用的**前后处理**结果 ——
分离、净化、修复，全部在 CPU 上跑，**零显存占用**、不引入 torch。

**已实现：分离三件套**，每个都能在库 / CLI / HTTP / GUI 中**独立调用**：

| 功能 | 说明 | 模型 |
|---|---|---|
| ① 人声提取 | 要**所有**人声 | `UVR-MDX-NET-Voc_FT.onnx` |
| ② 背景音提取 | 去掉**所有**人声 | `UVR-MDX-NET-Inst_Main.onnx` |
| ③ **主体人声去除** | 只去**主体**人声，**背景音里的人声保留** | `UVR_MDXNET_KARA.onnx` |

> ①③ 的区别是本插件存在的理由：**普通分离做不到「保留背景人声」**。
> 实测把人声/背景音二分的模型（如 demucs）在「中文主体 + 英文背景」素材上，
> 会把两种人声一起带走，`no_vocals` 轨只剩近静音。

**规划中：音频前后处理** —— 降噪 · 去环境音 · 音质优化 · 统一处理管线。
版图、优先级与候选模型见 [docs/10_audio_processing_roadmap.md](docs/10_audio_processing_roadmap.md)。

本模组**只做音频处理**：转写、字幕、配音合成不在这里 —— 需要时由**应用层**把本模组
与其它模组组合起来（组合脚本放在模组之外，见 `docs/00_INDEX.md §模组独立性`）。

---

## 快速开始

```bash
conda activate ov_env_py312
cd Agentic_AudioProcess_Module
pip install -e ".[all]"

# 体检：ffmpeg、sherpa-onnx、五个权重、VAD
audio doctor

# 不加载权重先试链路（零依赖占位引擎）
audio vocals demo.mp4 --engine null

# 人声提取
audio vocals demo.mp4

# 背景音提取
audio accompaniment demo.mp4

# 主体人声去除（保留背景人声）
audio lead-removal demo.mp4

# 图形界面 / HTTP 服务
python -m agentic_audioprocess.gui      # http://127.0.0.1:8402
python -m agentic_audioprocess.server   # http://127.0.0.1:8302/docs
```

## 库用法

```python
from agentic_audioprocess import AudioProcessModule

sep = AudioProcessModule()                            # 读 configs/audioprocess.yaml

v = sep.extract_vocals("demo.mp4")                # ① 人声提取
b = sep.extract_accompaniment("demo.mp4")         # ② 背景音提取
n = sep.remove_lead_vocal("demo.mp4")             # ③ 主体人声去除
print(n.stems["background"].path)                 #    -> 去掉主体人声的结果
print(n.lead_stem, n.stem_order_resolved_by)      #    哪条是主体、依据是什么

sep.release()
```

## 性能与依赖（实测，RTX 4060 机器但**全部在 CPU 上跑**）

| 模型 | 体积 | RTF | 显存 |
|---|---|---|---|
| `UVR_MDXNET_KARA.onnx` | 28 MB | **0.232** | **0** |
| `UVR_MDXNET_KARA_2.onnx` | 50 MB | 0.363 | 0 |
| （对照）demucs htdemucs | ~300 MB | 0.740（**需要 GPU**） | +861 MB |

依赖上只加 `sherpa-onnx`（2 个包）—— 不需要 torch，也不需要 demucs。
**CPU 上比 demucs 在 GPU 上还快**，而且完全不占显存，8 GB 卡可以整块留给别的模块。

## 输出与命名

落盘文件名形如 `{素材名}_{模式}_{轨名}.wav`：

```
demo_lead_removal_background.wav   ← 去掉主体人声后（含背景人声与伴奏）
demo_lead_removal_lead.wav         ← 被移除的主体人声（留作核对）
demo_vocals_vocals.wav
demo_accompaniment_accompaniment.wav
```

**各轨与输入严格等长**（门面强制校验，不等长会裁剪/补零并写 warning）——
时间轴漂移是最难查的一类静默 bug。默认**不做**逐轨峰值归一化，否则两轨再也混不回原样。

## 测试

```bash
python -m pytest tests -q              # 离线，秒级
python -m pytest tests -q -m real      # 真实 UVR 权重（约 30 秒）
python tools/check.py                  # 收尾闸口
```

## 环境要求

- Python ≥ 3.12（本机 `C:\Users\75203\miniforge3\envs\ov_env_py312\python.exe`）
- **ffmpeg 必须在 PATH 上**（解码任意容器；UVR 模型只接受 wav）
- 权重放在 `models/sherpa-separation/`，下载方式见 `docs/05_deployment.md`
  - ⚠️ GitHub release 请用 python `requests` 下载，`curl.exe` 会被 Windows schannel 中断
