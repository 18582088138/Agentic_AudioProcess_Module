# 01 · 方案设计 / Design

本文是**开发前的契约**。改动核心决策要先改这里，再改代码。

---

## 1 · 一句话定位

> **输入音频或视频，输出能直接用的处理结果：分离好的音轨、降噪后的语音、修复过的音质。**
> Audio/video in; processed audio out.

本模块的定位是**音频前后处理**：分离（**已实现**）· 降噪 · 去环境音 · 音质优化。
后三者的版图、候选方案与验收口径见 `10_audio_processing_roadmap.md`（**尚未实现**，
不要按已完成来写代码或文档）。

**不做**：转写、字幕、翻译、配音合成 —— 需要这些时由**应用层**组合其它模组。

| 功能 | 入口 | 用什么模型 | 输出 |
|---|---|---|---|
| 人声提取 | `extract_vocals()` | UVR Voc 系 | `vocals` |
| 背景音提取 | `extract_accompaniment()` | UVR Inst 系 | `accompaniment` |
| **主体人声去除** | `remove_lead_vocal()` | **UVR KARA 系** | `background` + `lead` |
| 两轨都要 | `separate(mode=BOTH)` | UVR 通用 | `vocals` + `accompaniment` |

### 1.1 为什么「主体人声去除」必须单独做一个模式

普通分离模型（demucs / UVR Voc 系）按「**人声 vs 非人声**」训练，
会把**前景与背景的人声一起**归到 vocals。实测「中文主体（居中）+ 英文背景（偏侧、−10 dB）」
素材时，demucs 的 `no_vocals` 轨 rms 只有 **0.0052**（近静音）——它把两种人声都带走了。

而 KARA 系按「**主唱 vs 其余（含伴唱）**」训练，实测同一个素材：

| 轨 | rms | ASR 判读 |
|---|---|---|
| `vocals`（KARA stem0） | 0.1083 | **中文（主体）** |
| `no_vocals`（KARA stem1） | 0.0651 | **英文（背景）** |

⇒ 它真的把主体与背景分开了，**而且是在说话而非唱歌的场景**（这一点调研阶段查不到
任何官方依据，第三方模型卡甚至把「完整混音」列为 out of scope，是我们自己实测确认的）。

---

## 2 · 分层

```
┌─ 用法层 ──  cli.py   server/   gui/       三者调用同一个门面，接口一一对应
├─ 门面层 ──  AudioProcessModule (audioprocess.py)
│              · 解码归一（任意容器 → 44.1 kHz 立体声）
│              · 轨道顺序判定（哪条是主体人声）
│              · 等长校验 · 落盘命名 · 模式路由 · 能力检查
├─ 引擎层 ──  engines/  uvr | null
│              唯一必实现：separate(chunk, mode) -> {轨名: 波形}
└─ 基础层 ──  core/   audio/
```

**为什么引擎接口要窄**：解码、轨道判定、等长校验、命名、模式语义**与引擎无关**。
下沉到各引擎就会出现 N 份互相不一致的实现（同一段音频换个引擎得到不同轨名/长度，
调试时看不出是哪一份在起作用）。

**为什么引擎之间是平级的**：能力正交 —— 一个答「这段音频里哪些是人声」，
另一个可能答「这段音频说了什么」。硬合并成一张能力表反而表达不了
（有的模型能做转写做不了分离，有的能分轨但不认识字）。

---

## 3 · 引擎与能力

```python
class SeparationEngine(ABC):
    @classmethod
    def declared_modes(cls) -> set[SeparationMode]: ...   # 不加载权重就能回答
    @abstractmethod
    def separate(self, chunk: AudioChunk, mode: SeparationMode,
                 lead_index: int | None = None) -> dict[str, np.ndarray]: ...
```

| 引擎 | 模式 | 设备 | 实测 RTF | 显存 | 说明 |
|---|---|---|---|---|---|
| `uvr`（默认） | 全部 | **CPU** | **0.232**（KARA） | **0** | sherpa-onnx 的 UVR MDX 系 onnx |
| `null` | 全部 | — | 即时 | 0 | 零依赖占位，确定性输出，供离线测试与界面预览 |

---

## 4 · 三个要点

### 4.1 轨道顺序判定（最容易出错的一步）

官方示例写死 `stems[0]=vocals`，但实测 **KARA 与 KARA_2 的顺序相反**。
判反了就把「去掉主体人声」做成了「去掉背景人声」，而且**不报错**。

**四级判定**，从可靠到兜底：

1. **配置显式指定** `engine.uvr.lead_stem_index`（用户说了算）；
2. **模型约定表**（默认）—— `_MODEL_LEAD_INDEX`，本机实测得出：
   `UVR_MDXNET_KARA.onnx` → stem0 是主体；`UVR_MDXNET_KARA_2.onnx` → stem1 是主体；
3. **VAD 语音占比** —— 仅用于约定表里没有的模型；
4. **顺序兜底** —— 取第一条。

判定依据一律回传到 `SeparationResult.stem_order_resolved_by`
（形如 `model-convention:UVR_MDXNET_KARA.onnx->stem0`）；两条轨占比差 < 0.02 时
标 `vad:ambiguous` —— **宁可说「不确定」**。

**两条判据都被实测否决过**，所以默认只信任模型约定表：

| 判据 | 反例（实测） |
|---|---|
| 能量（rms） | 「人声 + 背景音乐」素材里，**音乐轨 0.1533 > 人声轨 0.1114** |
| VAD 语音占比 | 「人声 + 背景人声 + 音乐」素材里，**含音乐轨 0.914 > 人声轨 0.7624** |

第二条是端到端联调时抓到的：背景音乐被 VAD 当成语音，判定方向整个反了 ——
「去掉主体人声」变成了「去掉背景人声」。详见 `issues/005`。

### 4.2 等长校验

各轨必须与输入**样本数一致**。门面 `_enforce_same_length()` 会裁剪或补零，
并把「动过手脚」写进 `warnings`。不做这一步，下游（字幕、混音、参考音频）
的时间轴会整体漂移且不报错。

实测 sherpa-onnx 的 UVR 输出天然与输入等长（`shape[1]` 完全一致），这道校验是安全网。

### 4.3 不做逐轨峰值归一化

会破坏轨间相对音量，导致两条轨再也混不回原样。要归一化由调用方显式开
（`config.normalize`，默认 false）。

---

## 5 · 目录结构

```
agentic_audioprocess/
  core/       config.py types.py errors.py logging.py
  audio/      io.py（44.1k 立体声归一）  vad.py（语音占比，轨道判定用）
  engines/    base.py uvr.py null.py
  audioprocess.py 门面 AudioProcessModule
  server/ gui/ cli.py
configs/audioprocess.yaml    models/（gitignore）    outputs/（gitignore）
docs/  tests/  tools/check.py
```

---

## 6 · 对外接口（库 = HTTP = CLI = GUI 一一对应）

| 功能 | 库 | CLI | HTTP |
|---|---|---|---|
| 体检 | `module.doctor()` | `audio doctor` | `GET /doctor` |
| 引擎表 | `module.engines()` | `audio engines` | `GET /engines` |
| ① 人声提取 | `extract_vocals()` | `audio vocals <media>` | `POST /vocals` |
| ② 背景音提取 | `extract_accompaniment()` | `audio accompaniment <media>` | `POST /accompaniment` |
| ③ 主体人声去除 | `remove_lead_vocal()` | `audio lead-removal <media>` | `POST /lead-removal` |
| 通用入口 | `separate(mode=…)` | `audio run <media> --mode …` | `POST /separate` |

**每个功能都是独立 endpoint / 独立 GUI 面板**，可单独调用，不要求走完整流水线。

---

## 7 · 验收标准

| # | 验收 | 判定方式 |
|---|---|---|
| V1 | 全链路不加载权重可跑通 | `pytest -q` 离线全绿（`--engine null`） |
| V2 | 三个功能各自可用 | 断言各模式产出的轨名与文件存在 |
| V3 | **各轨与输入严格等长** | 断言样本数一致、可解码、采样率一致 |
| V4 | **轨道判定可解释** | 断言 `stem_order_resolved_by` 非空；`lead_stem_index` 生效 |
| V5 | **主体/背景确实分开了** | `-m real`：断言 KARA 的两条轨**都不是静音**（退化则背景轨接近静音） |
| V6 | 未知模式被拒 | 断言抛 `AudioProcessError` / HTTP 422 |
| V7 | 下载端点不越权 | 断言 outputs 之外的文件拿不到 |

V1–V4、V6、V7 离线可验；V5 需要真实权重（`-m real`，约 30 秒）。

---

## 8 · 明确的取舍

1. **分离走 sherpa-onnx UVR，不用 demucs**：CPU、零新增依赖、不占显存，
   而且能做 demucs 做不到的「主体/背景人声」区分。代价是 KARA 系训练域是音乐，
   影视对白的泛化性目前只做过合成素材验证，**真实素材需要复验**（V5 已固化）。
2. **不用 RoFormer 系**：质量确实更高（人声 SDR 12.9 vs KARA 系约 10），
   但社区权重许可混乱（**GPL-3.0** / `license: other` / 干脆未声明），
   而 demucs/UVR 系是 MIT。这点质量差距换不来许可风险。
3. **「主体人声去除」的预期要写清**：主体与背景**同时说话**的重叠段无法完美分离，
   交付说明里写的是「显著衰减主体人声」而不是「彻底移除」。
4. **不做逐轨归一化**（见 4.3）。
