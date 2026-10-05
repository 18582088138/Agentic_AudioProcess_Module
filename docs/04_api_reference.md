# 04 · 接口参考 / API reference

> **库 / HTTP / CLI 三者一一对应**，每个功能都是独立入口，可单独调用，
> 不要求走完整流水线。
> 方案与取舍见 `01_design.md`；部署与权重下载见 `05_deployment.md`。

---

## 1 · 库 / Library

### 1.1 构造 / constructor

```python
from agentic_separate import SeparateModule

sep = SeparateModule(config=None, engine=None)
```

| 参数 | 类型 | 说明 |
|---|---|---|
| `config` | `SeparateConfig \| None` | None 时读 `configs/separate.yaml`（缺失则用内置默认值） |
| `engine` | `str \| SeparationEngine \| None` | 引擎名或引擎实例；None 用 `config.engine.default`（默认 `uvr`） |

**权重是懒加载的**：构造实例不花时间，也不占内存 —— 真正加载发生在第一次分离时。
所以它可以安全地在界面初始化时创建。

支持上下文管理器，退出时自动卸载：

```python
with SeparateModule() as sep:
    result = sep.extract_vocals("demo.mp4")
# 到这里权重已释放
```

### 1.2 三个核心功能 / the three functions

| 方法 | 模式 | 产出的轨 |
|---|---|---|
| `extract_vocals(media, out_dir=None, engine=None)` | `vocals` | `vocals` |
| `extract_accompaniment(media, out_dir=None, engine=None)` | `accompaniment` | `accompaniment` |
| `remove_lead_vocal(media, out_dir=None, engine=None)` | `lead_removal` | `background` + `lead` |

三者都是 `separate()` 的薄封装，参数含义完全一致，统一返回 `SeparationResult`。

**`remove_lead_vocal()` 返回两条轨，这是刻意的**：
`background` 是「去掉主体人声后」的结果（即你要的东西），
`lead` 是被摘出来的主体人声（留作核对 —— 判反方向时看一眼就知道）。

**`media` 参数有三种形态**：

| 形态 | 说明 |
|---|---|
| `str` | 文件路径 |
| `Path` | 同上 |
| `AudioChunk` | 已经解码好的音频；`source` 为空时落盘文件名用 `audio` |

任意容器都可以（wav / mp3 / m4a / mp4 / mkv …）—— 门面会用 ffmpeg 归一成
**44.1 kHz 立体声**（UVR 模型的要求）。

### 1.3 通用入口 / generic entry

```python
def separate(media, mode=None, out_dir=None, engine=None) -> SeparationResult
```

| 参数 | 类型 | 说明 |
|---|---|---|
| `media` | `str \| Path \| AudioChunk` | 见上 |
| `mode` | `SeparationMode \| str \| None` | None 用 `config.mode`；字符串**大小写不敏感**、自动去空格 |
| `out_dir` | `str \| Path \| None` | None 用 `config.output_dir`（默认项目根的 `outputs/`） |
| `engine` | `str \| None` | None 用配置默认 |

未知模式抛 `SeparateError`，错误信息里会列出全部合法取值。

### 1.4 元信息与生命周期 / meta & lifecycle

| 方法 | 返回 | 说明 |
|---|---|---|
| `engines()` | `list[dict]` | 引擎清单，每项含 `name` / `default` / `modes`（失败时是 `error`）。**不加载权重** |
| `doctor()` | `dict` | 体检：引擎、默认引擎、模式、每个模式的权重是否存在、VAD 后端、`checks`、`ok` |
| `engine(name=None)` | `SeparationEngine` | 取（并缓存）引擎实例 |
| `detector()` | `SpeechRatioDetector` | 共享的语音占比检测器（轨道判定的兜底判据用它） |
| `release()` | `None` | 卸载全部引擎并清空缓存 |

`doctor()` 返回结构（实测）：

```json
{
  "engines": [{"name": "uvr", "default": true, "modes": ["accompaniment", "both", "lead_removal", "vocals"]}],
  "default_engine": "uvr",
  "mode": "lead_removal",
  "models": {
    "lead_removal": {"file": "UVR_MDXNET_KARA.onnx", "path": "...", "exists": true},
    "vocals":       {"file": "UVR-MDX-NET-Voc_FT.onnx", "path": "...", "exists": true},
    "accompaniment":{"file": "UVR-MDX-NET-Inst_Main.onnx", "path": "...", "exists": true}
  },
  "vad_backend": "silero",
  "checks": [],
  "ok": true
}
```

### 1.5 数据结构 / data structures

#### `SeparationMode`

| 取值 | 含义 |
|---|---|
| `SeparationMode.VOCALS` = `"vocals"` | 人声提取：要**所有**人声 |
| `SeparationMode.ACCOMPANIMENT` = `"accompaniment"` | 背景音提取：去掉**所有**人声 |
| `SeparationMode.LEAD_REMOVAL` = `"lead_removal"` | 主体人声去除：只去**主体**，背景人声保留 |
| `SeparationMode.BOTH` = `"both"` | 两轨都要 |

> `LEAD_REMOVAL` 与 `ACCOMPANIMENT` **不是同一件事**，这是本插件存在的理由。
> 区别见 `01_design.md §1.1`。

#### `SeparationResult`

| 字段 | 类型 | 说明 |
|---|---|---|
| `mode` | `str` | 本次模式（枚举的值） |
| `engine` | `str` | 实际使用的引擎名 |
| `stems` | `dict[str, Stem]` | 轨名 → `Stem` |
| `duration` | `float` | 音频时长（秒） |
| `sample_rate` | `int` | 采样率（默认 44100） |
| `lead_stem` | `str \| None` | **哪条轨被判定为主体人声**；非 `lead_removal` 模式为 None |
| `stem_order_resolved_by` | `str` | **判定依据**（见下） |
| `warnings` | `list[str]` | 例如「长度不一致已对齐」「某轨写盘失败」 |
| `raw` | `dict \| None` | `loaded_file`（本次加载的权重）+ `speech_ratios`（VAD 判据时的占比） |

`ok` 属性 = `bool(stems) and not warnings`；`to_dict()` 可直接 JSON 序列化。

**`stem_order_resolved_by` 的四种取值**（这是排查「方向判反」的唯一线索）：

| 取值形态 | 含义 |
|---|---|
| `config:lead_stem_index=0` | 用户在配置/CLI 里显式指定 |
| `model-convention:UVR_MDXNET_KARA.onnx->stem0` | 命中**模型约定表**（实测得出，默认路径） |
| `vad:speech_ratio {...}` | 约定表里没有该模型，退回语音占比判定 |
| `vad:ambiguous spread=...` | 两条轨占比几乎一样，判定**不可靠**（偏低 0.02 时） |
| `single-stem` / `not-needed` | 只有一条轨 / 该模式不需要判定 |

#### `Stem`

| 字段 | 类型 | 说明 |
|---|---|---|
| `name` | `str` | `vocals` / `accompaniment` / `lead` / `background` |
| `path` | `str` | 落盘的 wav 路径 |
| `duration` | `float` | 时长（秒），与输入一致 |
| `sample_rate` | `int` | 采样率 |
| `channels` | `int` | 声道数（默认 2） |

#### `AudioChunk`（可以自己造一个传进去）

| 字段 | 类型 | 说明 |
|---|---|---|
| `samples` | `np.ndarray` | `float32`，形状 `(num_samples, channels)` 或 `(num_samples,)` |
| `sample_rate` | `int` | 默认 44100 |
| `source` | `str` | 来源标识，仅用于命名与报错 |

`duration` 与 `channels` 是只读属性。

#### `SeparateConfig` 关键项

| 字段 | 默认 | 说明 |
|---|---|---|
| `engine.default` | `"uvr"` | `uvr` \| `null` |
| `engine.uvr.model_dir` | `models/sherpa-separation` | 权重目录（相对项目根） |
| `engine.uvr.num_threads` | `4` | CPU 线程数 |
| `engine.uvr.provider` | `"cpu"` | onnxruntime provider |
| `engine.uvr.lead_stem_index` | `None` | 显式指定哪条轨是主体；None = 自动判定 |
| `mode` | `"lead_removal"` | `separate()` 不传 mode 时的默认 |
| `models` | 三模式映射 | 见 `configs/separate.yaml` |
| `output_sample_rate` | `44100` | 解码目标采样率 |
| `normalize` | `False` | **不做逐轨峰值归一化**（会破坏轨间相对音量；当前实现未使用此开关，保留为配置位） |
| `output_dir` | 项目根 `outputs/` | 默认产物目录 |
| `server.host` / `server.port` | `127.0.0.1` / `8302` | HTTP 服务 |

配置优先级：**进程环境变量 > `.env` > `configs/separate.yaml` > 内置默认值**。
环境变量名见 `.env.example`（`SEPARATE_ENGINE` / `SEPARATE_MODE` / `SEPARATE_MODELS_DIR` /
`SEPARATE_OUTPUT_DIR` / `SEPARATE_NUM_THREADS` / `SEPARATE_SERVER_HOST` / `SEPARATE_SERVER_PORT`）。

### 1.6 落盘命名 / output naming

```
{素材名}_{模式}_{轨名}.wav
```

`素材名` 取 `Path(chunk.source).stem`；`AudioChunk.source` 为空时用 `audio`。

| 调用 | 产物 |
|---|---|
| `extract_vocals("demo.mp4")` | `demo_vocals_vocals.wav` |
| `extract_accompaniment("demo.mp4")` | `demo_accompaniment_accompaniment.wav` |
| `remove_lead_vocal("demo.mp4")` | `demo_lead_removal_background.wav`、`demo_lead_removal_lead.wav` |
| `separate("demo.mp4", "both")` | `demo_both_vocals.wav`、`demo_both_accompaniment.wav` |

**各轨与输入严格等长**（门面强制校验，不等长会裁剪/补零并把这件事写进 `warnings`）。

### 1.7 完整示例 / a complete example

```python
from pathlib import Path
from agentic_separate import SeparateModule, SeparationMode

with SeparateModule() as sep:
    # ① 人声提取：要所有人声
    v = sep.extract_vocals("demo.mp4", out_dir="outputs/refs")
    print(v.stems["vocals"].path, v.stems["vocals"].duration)

    # ② 背景音提取：去掉所有人声
    b = sep.extract_accompaniment("demo.mp4")

    # ③ 主体人声去除：只去主体，背景人声保留
    n = sep.remove_lead_vocal("demo.mp4")
    print("去掉主体后 / background:", n.stems["background"].path)
    print("被摘出的主体 / lead   :", n.stems["lead"].path)
    print("哪条是主体           :", n.lead_stem)
    print("判定依据             :", n.stem_order_resolved_by)
    # -> model-convention:UVR_MDXNET_KARA.onnx->stem0

    # 强制指定方向（判定不可靠时用）
    sep.config.engine.uvr.lead_stem_index = 1
    forced = sep.remove_lead_vocal("demo.mp4")
    assert forced.stem_order_resolved_by.startswith("config:")

    # 通用入口
    both = sep.separate("demo.mp4", SeparationMode.BOTH)
    print(sorted(both.stems))       # ['accompaniment', 'vocals']
```

---

## 2 · HTTP

```bash
python -m agentic_separate.server          # 或 separate serve
# http://127.0.0.1:8302/docs  （自动生成的交互式文档）
```

### 2.1 端点 / endpoints

| 方法 | 路径 | 用途 |
|---|---|---|
| GET | `/healthz` | 存活 + 版本 + 默认引擎与模式 |
| GET | `/engines` | 引擎清单与支持的模式 |
| GET | `/doctor` | 体检（同库的 `doctor()`） |
| GET | `/config` | 当前生效配置（JSON） |
| GET | `/download?path=` | 下载产物（**仅限 `outputs/` 之内**） |
| POST | `/vocals` | ① 人声提取 |
| POST | `/accompaniment` | ② 背景音提取 |
| POST | `/lead-removal` | ③ 主体人声去除 |
| POST | `/separate` | 通用入口，`mode` 可选四个取值 |

### 2.2 表单字段 / form fields

| 端点 | 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|---|
| `/vocals` | `file` | 文件 | ✅ | 素材 |
| | `engine` | str | | 默认用配置 |
| `/accompaniment` | `file` | 文件 | ✅ | |
| | `engine` | str | | |
| `/lead-removal` | `file` | 文件 | ✅ | |
| | `lead_index` | int | | 强制指定哪条轨是主体（0/1） |
| | `engine` | str | | |
| `/separate` | `file` | 文件 | ✅ | |
| | `mode` | str | | 默认 `both` |
| | `engine` | str | | |

**上传扩展名白名单**：`.wav .mp3 .m4a .aac .flac .ogg .opus .aiff .mp4 .mkv .mov .webm .avi .ts`。
HTTP 端点不接受 `lead_stem_index` 之外的路径输入（没有"传本地路径"的口子）。

产物落在 `{output_dir}/http/`。

### 2.3 curl 示例

```bash
# 人声提取
curl -s -F "file=@demo.mp4" http://127.0.0.1:8302/vocals | jq

# 背景音提取
curl -s -F "file=@demo.mp4" http://127.0.0.1:8302/accompaniment | jq

# 主体人声去除（保留背景人声）
curl -s -F "file=@demo.mp4" http://127.0.0.1:8302/lead-removal | jq
curl -s -F "file=@demo.mp4" -F "lead_index=1" http://127.0.0.1:8302/lead-removal | jq

# 通用入口
curl -s -F "file=@demo.mp4" -F "mode=both" http://127.0.0.1:8302/separate | jq

# 体检 / 引擎表
curl -s http://127.0.0.1:8302/doctor | jq
curl -s http://127.0.0.1:8302/engines | jq

# 下载产物（路径必须是 outputs 之内）
curl -s -o out.wav "http://127.0.0.1:8302/download?path=F:/2026年/Agentic_VoiceSeparate_Module/outputs/http/demo_lead_removal_background.wav"
```

成功响应就是 `SeparationResult.to_dict()`：

```json
{
  "mode": "lead_removal",
  "engine": "uvr",
  "stems": {
    "background": {"name": "background", "path": "...", "duration": 24.0,
                   "sample_rate": 44100, "channels": 2},
    "lead":       {"name": "lead", "path": "...", "duration": 24.0,
                   "sample_rate": 44100, "channels": 2}
  },
  "duration": 24.0,
  "sample_rate": 44100,
  "lead_stem": "vocals",
  "stem_order_resolved_by": "model-convention:UVR_MDXNET_KARA.onnx->stem0",
  "warnings": []
}
```

### 2.4 失败响应 / error responses

| 状态码 | 触发条件 | 响应体 |
|---|---|---|
| **415** | 上传扩展名不在白名单 | `{"detail": "不支持的扩展名 / unsupported suffix: .txt"}` |
| **422** | `/separate` 的 `mode` 非法 | `{"detail": "未知模式 / unknown mode: bogus"}` |
| **400** | 分离失败（`SeparateError`：空音频、未知模式、权重缺失、引擎报错） | `{"detail": "<错误信息>"}` |
| **403** | `/download` 的 `path` 落在 `outputs/` 之外 | `{"detail": "只允许下载 outputs 目录内的文件 / outside outputs"}` |
| **404** | `/download` 的文件不存在 | `{"detail": "文件不存在 / not found"}` |

**状态码已逐条实测**（走真实 ASGI 栈的 `TestClient`，与真实 HTTP 行为一致）：

| 请求 | 状态码 | 响应体 |
|---|---|---|
| `POST /vocals`（上传 `.txt`） | **415** | `{"detail": "不支持的扩展名 / unsupported suffix: .txt"}` |
| `POST /separate`（`mode=bogus`） | **422** | `{"detail": "未知模式 / unknown mode: bogus"}` |
| `GET /download`（越权路径） | **403** | `{"detail": "只允许下载 outputs 目录内的文件 / outside outputs"}` |
| `GET /download`（文件不存在） | **404** | `{"detail": "文件不存在 / not found"}` |
| `POST /vocals`（正常） | **200** | `SeparationResult` 的 JSON |

对应的命令行写法：

```bash
curl -s -o /dev/null -w "%{http_code}\n" -F "file=@note.txt" http://127.0.0.1:8302/vocals          # 415
curl -s -o /dev/null -w "%{http_code}\n" -F "file=@demo.wav" -F "mode=bogus" \
     http://127.0.0.1:8302/separate                                                                 # 422
```

---

## 3 · CLI

```bash
separate --help              # 安装后可用
python -m agentic_separate.cli --help    # 等价写法
```

### 3.1 命令一览

| 命令 | 说明 |
|---|---|
| `version` | 打印版本 |
| `doctor` | 环境与模型体检（不加载权重） |
| `engines` | 列出引擎与支持的模式 |
| `vocals <media>` | ① 人声提取 |
| `accompaniment <media>` | ② 背景音提取 |
| `lead-removal <media>` | ③ 主体人声去除 |
| `run <media> --mode …` | 通用入口 |
| `serve` | 起 HTTP 服务 |
| `gui` | 起图形界面 |

### 3.2 通用参数

| 参数 | 适用于 | 说明 |
|---|---|---|
| `media` | vocals / accompaniment / lead-removal / run | **必填**，素材路径 |
| `--out-dir <path>` | 同上 | 产物目录；默认 `config.output_dir` |
| `--engine <str>` | 同上 | 引擎名；默认 `uvr` |
| `--config <str>` | 全部命令 | 指定配置文件 |
| `--mode <str>` | 仅 `run` | 默认 `both`；取值 `vocals\|accompaniment\|lead_removal\|both` |
| `--lead-index <int>` | 仅 `lead-removal` | 强制指定哪条轨是主体人声（0 或 1） |
| `--host` / `--port` | serve / gui | 默认 `127.0.0.1`；端口默认 8302 / 8402 |

### 3.3 示例

```bash
# 体检
separate doctor

# 引擎与模式
separate engines

# ① 人声提取
separate vocals demo.mp4
separate vocals demo.mp4 --out-dir outputs/refs

# ② 背景音提取
separate accompaniment demo.mp4

# ③ 主体人声去除（会打印 lead_stem 与判定依据）
separate lead-removal demo.mp4
separate lead-removal demo.mp4 --lead-index 1     # 强制方向

# 通用入口
separate run demo.mp4 --mode both
separate run demo.mp4 --mode vocals

# 不加载权重先验证链路（零依赖占位引擎）
separate vocals demo.mp4 --engine null

# 服务与界面
separate serve --host 0.0.0.0 --port 8302
separate gui --port 8402
```

`lead-removal` 的**实际输出**（在 `models/samples/zh.mp3` 上以 `--engine null` 跑出来的原样）：

```
$ python -m agentic_separate.cli lead-removal models\samples\zh.mp3 --engine null
null  mode=lead_removal  duration=5.62s  sr=44100
主体人声轨 / lead stem: lead　判定依据 / evidence: model-convention:UVR_MDXNET_KARA.onnx->stem0
                              轨 / stems
┌────────────┬────────────────────────────────┬──────┬────────┬──────┐
│ 名称       │ 文件                           │ 时长 │ 采样率 │ 声道 │
├────────────┼────────────────────────────────┼──────┼────────┼──────┤
│ lead       │ zh_lead_removal_lead.wav       │ 5.62 │ 44100  │ 2    │
│ background │ zh_lead_removal_background.wav │ 5.62 │ 44100  │ 2    │
└────────────┴────────────────────────────────┴──────┴────────┴──────┘
```

> 上面用的是 `null` 占位引擎，但依据串仍显示 KARA 的模型约定 —— 这不是 bug：
> `_resolve_order()` 查约定表用的是**配置里该模式的权重文件名**
> （`config.model_path(mode)`），与实际加载哪个引擎无关。真实使用 `uvr` 引擎时两者一致。

**退出码**：成功 0；`SeparateError`（未知模式、文件不存在、权重缺失等）→ 1；
`Ctrl-C` → 130。

---

## 4 · 相关文档

| 想知道什么 | 读哪份 |
|---|---|
| 为什么三个模式用三套模型 | `01_design.md §1.1` |
| 轨道顺序判定的四级策略与两次踩坑 | `01_design.md §4.1`、`issues/005` |
| 权重下载与性能实测 | `05_deployment.md` |
| 界面怎么用 | `07_gui_guide.md` |
| 环境与硬约束 | `PROJECT_MEMORY.md` |
