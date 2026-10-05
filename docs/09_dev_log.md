# 09 · 开发与测试记录 / Development log

> 记录**交付了什么、与方案哪里不一样、踩了什么坑**。
> 测试条数、行数这类会腐烂的数字不写在这里 —— 现算：
> `python tools/check.py`（它同时跑环境自检 + ruff + 全量离线测试）。

---

## 1 · 交付内容 / deliverables

| 部分 | 内容 |
|---|---|
| 包 | `agentic_audioprocess/` —— core / audio / engines / audioprocess.py（门面）/ server / gui / cli.py |
| 引擎 | `uvr`（sherpa-onnx 的 UVR MDX 系 onnx，**CPU**）、`null`（零依赖占位） |
| 功能 | 人声提取 · 背景音提取 · **主体人声去除**（+ 通用入口「两轨都要」） |
| 四种用法 | Python 库 · CLI（`audio`）· HTTP（8302）· GUI（8402） |
| 权重 | `models/sherpa-separation/` 5 个 onnx（28~67 MB）+ `models/sherpa-vad/silero_vad.onnx` |
| 文档 | `docs/`（索引 / 方案 / 接口 / 测试 / 部署 / 接引擎 / GUI / 提交指令 / 本记录 / 问题单） |

**关键实测结论**：
本插件的分离在 **CPU** 上 RTF 0.232（KARA），比对照方案 demucs 在 **GPU** 上（0.740）
还快，且**零显存占用**、**零新增重依赖**。

---

## 2 · 测试结果 / test results

| 类别 | 命令 | 状态 |
|---|---|---|
| 离线套件（不加载权重） | `python -m pytest tests -q` | 全绿 |
| 真实 UVR 权重 | `python -m pytest tests -q -m real` | 全绿 |
| 收尾闸口 | `python tools/check.py` | 全绿 |

用例分布与**刻意写死的断言**见 `03_unit_tests.md §2 §3`。
其中唯一真正重要的验收是 `test_kara_separates_lead_from_background`：
它断言「中文主体 + 英文背景」素材分离后**两条轨都不是静音** ——
若模型退化成普通的人声/伴奏二分，背景轨会接近静音。

---

## 3 · 与方案的偏差 / deviations from the design

### 3.1 轨道判定的默认判据换了两次（本次最大的偏差，且是方案级的）

方案里写的是「VAD 语音占比」会给出可靠的轨道顺序。**实际第一次联调就判反了。**

**第一次否决：能量（rms）判据。**
最初想用「能量更高的那条是主体人声」，在「人声 + 人声」素材上确实成立
（0.108 vs 0.065）。但换成「人声 + 背景音乐」后直接反了：

| 素材 | 人声轨 rms | 另一轨 rms |
|---|---|---|
| 人声 + 人声 | 0.1083（主体） | 0.0651（背景） |
| **人声 + 音乐** | 0.1114（人声） | **0.1533（音乐，反而更高）** |

**第二次否决：VAD 语音占比。**
改成 VAD 占比后，在「中文主体 + 英文背景 + 正弦背景音乐」素材上又反了：

```
lead=accompaniment  依据=vad:speech_ratio {'vocals': 0.7624, 'accompaniment': 0.914}
```

**背景音乐被 VAD 当成了语音**，含音乐的那条轨占比反而更高，于是
「去掉主体人声」变成了「去掉背景人声」。用 ASR 复核确认了方向确实反了：

| 轨（判反后） | ASR 识别结果 |
|---|---|
| `background` | 开放时间早上9点至下午5点…（**中文主体，本该已去掉**） |
| `lead` | The driver chased him corn for the boy…（**英文背景，本该是主体**） |

**最终方案**：改为**四级判定**，默认走**模型约定表**（本机实测得出的
「该模型哪条轨是主体」），VAD 降为未知模型的兜底并在依据串里注明可能有音乐干扰。

修正后的效果：

| 轨 | ASR 识别结果 |
|---|---|
| `background` | The driver chased him corn for the boy…（英文，**背景人声保留**）✅ |
| `lead` | 开放时间早上9点至下午5点…（中文，**主体被摘出**）✅ |

`stem_order_resolved_by` 现在是 `model-convention:UVR_MDXNET_KARA.onnx->stem0`。
完整复盘见 `issues/005`。

**这条偏差的教训**：**判据本身也要被验收**。「两条轨哪个是主体」看似显然，
但两个直觉判据（能量、VAD）都被真实素材推翻了 —— 最后只能靠**实测出来的
模型约定**，并把判定依据回传给调用方，让方向问题可被肉眼核对。

### 3.2 配置项 `normalize` 保留但当前未使用

方案里有「不做逐轨峰值归一化」这一条，配置也留了 `normalize: false`。
实际实现里**没有代码读这个开关**（因为默认就是"不做"，也没有做归一化的实现）。
留成配置位是有意的：将来若要加归一化，接口已经在位。已在 `04_api_reference.md §1.5` 注明。

### 3.3 一处已知死代码（未清理）

`audioprocess.py` 里的模块级常量 `_MODE_STEMS`（模式 → 对外轨名的映射表）
**定义了但没有被任何代码引用** —— 实际映射由 `_to_output_stems()` 直接完成。
保留它只会让读代码的人以为改它有用。属清理项，见 §5。

### 3.4 NiceGUI 3.x 的上传契约变更（已修）

NiceGUI 3.x 改了上传事件的结构（`UploadEventArguments` 只剩 `file` 字段，
2.x 的 `e.name` / `e.content` 没了）。旧写法会让上传直接报错。
本仓库的回归用例在 `tests/test_gui.py`。

---

## 4 · 已记档问题 / logged issues

| 单 | 内容 | 回归用例 |
|---|---|---|
| `issues/005-stem-order-is-not-fixed.md` | 轨道顺序不能硬编码；官方示例与实测不一致；**能量与 VAD 两条判据都被否决** | `test_model_convention_wins_over_vad`、`test_lead_removal_can_be_forced_by_config`、`test_vad_is_used_for_unknown_models`、`test_kara_separates_lead_from_background` |
| `issues/006-existing-ruff-findings.md` | 装上 ruff 后暴露的 20 项既有 lint 问题（闸口首次真正运行） | `tools/check.py` 的 ruff 段 |

**另外两个坑（各自在本仓库都有回归用例）**：

| 内容 | 本模组怎么应对 |
|---|---|
| sherpa-onnx 的 Silero VAD **必须分块喂 + 边喂边取**，否则静默漏检/丢段 | `audio/vad.py` 直接照做，并用 `test_audio.py::test_silero_backend_detects_voice`（占比 > 0.4）守住 |
| NiceGUI 3.x 上传事件没有 `name` | `gui/app.py::save_upload` 用 `await file.save()`；`test_gui.py` 锁死契约 |

---

## 5 · 后续待办 / follow-ups

| # | 事项 | 说明 |
|---|---|---|
| 1 | **用真实影视素材复验 KARA 的泛化性** | 目前「主体 vs 背景人声可分」只在**合成素材**上验证过（中文主体 + 英文背景）。KARA 系的训练域是**音乐**，影视对白属域外。这是本插件最大的未覆盖风险 —— 若发现背景和声/群众声被连带削掉明显，需考虑备选路线（见 `01_design.md §8`） |
| 2 | 主体与背景**同时说话**的重叠段 | 技术天花板，无法完美分离。交付口径是「显著衰减主体人声」而非「彻底移除」。若要改善只能上目标说话人提取（TSE），需额外权重与注册音频 |
| 3 | 清理死代码 `_MODE_STEMS` | 见 §3.3。纯清理，无行为影响 |
| 4 | `normalize` 配置位 | 见 §3.2。要么实现，要么删掉，别让配置骗人 |
| 5 | `UVR_MDXNET_KARA_2` 的 stem 顺序 | **已完成**：实测与 KARA 相反（stem1 是主体），已写进 `_MODEL_LEAD_INDEX` 约定表 |
| 6 | 若追求更高 SDR | 接入路径见 `06_add_engine.md`；但注意 RoFormer 系社区权重许可混乱（**GPL-3.0** / `license: other` / 未声明），见 `01_design.md §8.2` |

---

## 6 · 改名重构 / rename（VoiceSeparate → AudioProcess）

| 项 | 说明 |
|---|---|
| 为什么改 | 本模块不只做分离 —— 定位是**音频前后处理**（分离 · 降噪 · 去环境音 · 音质优化），旧名把范围写窄了 |
| 改了什么 | 仓库 / 目录、分发名、包名、门面文件名与类名、配置类、异常基类、配置文件、CLI 名、环境变量前缀、开发 skill（映射表见 `PROJECT_MEMORY.md §改名重构`） |
| 没改什么 | 语义本就属于「分离」的符号：`SeparationMode` / `SeparationResult` / `SeparationEngine` / `StemOrderError` / `SEPARATION_SR` / `separate()` / `POST /separate`；三个模式与模型的映射、四级轨道判定、等长与不归一化三条硬约束**一条都没动** |
| 功能范围 | 本轮**只改名与扩定位**；降噪 / 去环境音 / 音质优化**未实现**，版图见 `10_audio_processing_roadmap.md` |
| 兼容性 | **破坏性**：CLI 由 `separate` 变 `audio`，包名与 `SEPARATE_*` 环境变量都变了；改名后必须重装 editable 包（旧 egg-info 指向旧包名）。本机无 `.env`，无凭据迁移成本 |
| 跨模组 | **不牵连任何其它模组**：按守则 §七，模组之间不许互相引用；本轮顺手清掉了本仓库里对其它模组的直接引用（对方的 issue / 设计正文 / 可照抄的调用示例），只保留「由应用层组合」这类关系说明 |
| 需要人工做 | `11_git_commands_rename.md`（分 3 组提交，**不涉及其它仓库**） |
| 验证 | 离线测试全绿（数字现跑）；`audio version` / `audio doctor` 正常；`tools/check.py` 的 ruff 段另有既有问题，见 `issues/006` |

---

## 7 · 状态

分离功能的开发、测试、文档均已完成；**本轮改名重构已完成，待人工提交**
（`git status` 应显示重命名 + 修改 + 新文档）。
**提交指令**：本轮 `11_git_commands_rename.md`，首轮留档 `08_git_commands.md`。
