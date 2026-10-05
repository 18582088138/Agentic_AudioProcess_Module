# 05 · 部署 / Deployment

## 1 · 环境要求

| 项 | 要求 |
|---|---|
| Python | ≥ 3.12（本机 `C:\Users\75203\miniforge3\envs\ov_env_py312\python.exe`） |
| ffmpeg / ffprobe | **必须在 PATH**（解码任意容器；UVR 模型只接受 wav） |
| GPU | **不需要**。分离全部在 CPU 上跑 |
| 依赖 | 只有 `sherpa-onnx`（+2 个包），不需要 torch / demucs |

```bash
conda activate ov_env_py312
cd Agentic_AudioProcess_Module
pip install -e ".[all]"
audio doctor          # 检查 ffmpeg、sherpa-onnx、五个权重、VAD
```

## 2 · 权重下载

五个模型放在 `models/sherpa-separation/`（已在 `.gitignore`）。

| 文件 | 体积 | 用途 |
|---|---|---|
| `UVR_MDXNET_KARA.onnx` | 28 MB | **主体人声去除**（默认） |
| `UVR_MDXNET_KARA_2.onnx` | 50 MB | 备选 |
| `UVR-MDX-NET-Voc_FT.onnx` | 64 MB | 人声提取 |
| `UVR-MDX-NET-Inst_Main.onnx` | 50 MB | 背景音提取 |
| `UVR_MDXNET_Main.onnx` | 64 MB | 通用 |

```python
# ⚠️ 用 python requests 下载 —— curl.exe 在 Windows 上会被 schannel 中断（实测）
import requests, os
base = ("https://github.com/k2-fsa/sherpa-onnx/releases/download/"
        "source-separation-models/")
dst = r"F:\2026年\Agentic_AudioProcess_Module\models\sherpa-separation"
os.makedirs(dst, exist_ok=True)
for name in ["UVR_MDXNET_KARA.onnx", "UVR-MDXNET-Voc_FT.onnx",
             "UVR-MDX-NET-Inst_Main.onnx"]:
    with requests.get(base + name, stream=True, timeout=90) as r:
        r.raise_for_status()
        with open(os.path.join(dst, name), "wb") as f:
            for c in r.iter_content(1 << 20):
                f.write(c)
    print("saved", name)
```

VAD 模型（轨道判定用，0.6 MB）：

```python
requests.get("https://github.com/k2-fsa/sherpa-onnx/releases/download/"
             "asr-models/silero_vad.onnx")
# 存到 models/sherpa-vad/silero_vad.onnx
```

**注意**：UVR 权重必须从上面的 **sherpa-onnx release** 下，
不要从上游 `TRvlvr/model_repo` 下原件 —— 后者缺 metadata，sherpa-onnx 读不了。

## 3 · 性能（本机实测）

| 模型 | 体积 | RTF（CPU） | 显存 |
|---|---|---|---|
| `UVR_MDXNET_KARA.onnx` | 28 MB | **0.232** | **0** |
| `UVR_MDXNET_KARA_2.onnx` | 50 MB | 0.363 | 0 |
| （对照）demucs htdemucs | ~300 MB | 0.740（**需要 GPU**） | +861 MB |

RTF 0.232 ⇒ 30 秒音频约 7 秒；1 小时音频约 14 分钟。线程数由
`engine.uvr.num_threads` 控制（默认 4）。

## 4 · 服务化

```bash
python -m agentic_audioprocess.server          # http://127.0.0.1:8302/docs
audio serve --host 0.0.0.0 --port 8302
```

端点：`/vocals` · `/accompaniment` · `/lead-removal` · `/separate` · `/doctor` ·
`/engines` · `/download`。

```bash
curl -F "file=@demo.mp4" http://127.0.0.1:8302/lead-removal
```

## 5 · GUI

```bash
python -m agentic_audioprocess.gui             # http://127.0.0.1:8402
```

三个面板各对应一个功能，产物直接内嵌播放器，可立刻试听。

## 6 · 与其它模组的关系

本模组**只做音频处理**，不 import 别的模组，也不在文档里指路别的模组的包名与接口
（守则 §七 模组独立性）。要串成流水线（例如「先分离再转写」）由**应用层 pipeline**
组合，组合脚本放在模组之外，不写进本仓库。

⚠️ 一条与下游打交道的经验：**不要把分离出的伴奏轨直接送去语音识别** ——
无语音输入时识别器会编出假字幕。要送就送 `vocals` 轨，或先做语音活动检测。
