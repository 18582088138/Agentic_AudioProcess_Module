# 02 · 开发计划与验收 / Development plan & acceptance

> **本文是回顾式的**：本插件已开发完成，所以这里写的是
> 「当初的阶段划分」+「实际完成情况」+「验收项达成状态」。
> 需求与方案见 `01_design.md`；当前进度与待办见 `PROJECT_MEMORY.md`。

---

## 0 · 当时的纪律

- 一次做一件事，做完自检一次，过了就往下走；
- 验收手段先行：动手前先说清「哪条命令带什么预期输出」；
- 只写、只跑**本次改动相关**的用例；全量只在阶段收尾跑一次 `tools/check.py`；
- 不新建环境、不加重依赖。

---

## 1 · 阶段划分与完成情况

| 阶段 | 当初计划做什么 | 实际完成 | 完成判据 |
|---|---|---|---|
| **0 · 工程骨架** | `git init`、`pyproject.toml`、`.gitignore`、`.env.example`、`tools/check.py`、`.dsh/skills` | ✅ | `python tools/check.py` 能跑通（环境自检 + ruff 跳过 + 空测试集） |
| **1 · core + audio** | 配置、类型、异常、日志；44.1 kHz 立体声解码；语音占比检测 | ✅ | `separate doctor` 打印模型存在性；`decode()` 出口形状为 `(n, 2)` |
| **2 · engines** | `SeparationEngine` 抽象 + `uvr`（sherpa-onnx）+ `null` 占位 | ✅ | `separate engines` 列出两个引擎与各自模式；`null` 引擎输出确定 |
| **3 · 门面** | 解码归一、**轨道顺序判定**、等长校验、落盘命名、模式路由 | ✅ | 三个功能在 `--engine null` 下产出正确轨名与文件 |
| **4 · 接口层** | CLI（9 个命令）、HTTP（9 个端点）、GUI（3 个页签） | ✅ | 三者调用同一个门面，端点/命令/页签一一对应 |
| **5 · 测试** | 离线套件 + 真实权重用例 + 回归 | ✅ | 全绿；**具体条数现算**：`python tools/check.py`（文档里不钉死条数，免得腐烂） |
| **6 · 文档与收尾** | 各阶段文档落点、`PROJECT_MEMORY.md`、`08_git_commands.md` | ✅ | `docs/00_INDEX.md` 可作为入口 |

**与原计划的偏差只有一处**，且是方案级的：**轨道判定的默认判据换了两次**，
详见 `09_dev_log.md` 与 `issues/005`。

---

## 2 · 验收项达成状态

（验收标准定义在 `01_design.md §7`；下表是**达成情况 + 对应用例**。）

| # | 验收 | 状态 | 对应用例 |
|---|---|---|---|
| **V1** | 全链路不加载权重可跑通 | ✅ | 整个离线套件都跑在 `--engine null` 上 |
| **V2** | 三个功能各自可用 | ✅ | `test_extract_vocals` / `test_extract_accompaniment` / `test_remove_lead_vocal_produces_background_and_lead` |
| **V3** | 各轨与输入严格等长 | ✅ | `test_stems_are_same_length_as_input`（离线）、`test_uvr_stems_match_input_length`（`-m real`） |
| **V4** | 轨道判定可解释 | ✅ | `test_lead_removal_can_be_forced_by_config`、`test_model_convention_wins_over_vad`、`test_vad_is_used_for_unknown_models` |
| **V5** | 主体/背景确实分开了 | ✅ | `test_kara_separates_lead_from_background`（`-m real`，断言两条轨都不是静音） |
| **V6** | 未知模式被拒 | ✅ | `test_unknown_mode_raises`（库）、`test_separate_endpoint_bad_mode`（HTTP 422） |
| **V7** | 下载端点不越权 | ✅ | `test_download_confined_to_outputs`（403/404） |

**另外补了四条原计划里没有、但实际必须有的验收**：

| 补充项 | 为什么加 | 对应用例 |
|---|---|---|
| 落盘命名符合约定 | 用户要按文件名找产物 | `test_output_files_are_named_by_mode` |
| 引擎输出与输入同形 | 门面的等长校验依赖这条契约 | `test_engine_returns_same_shape` |
| CLI 报错要有非零退出码 | 否则脚本里 `&&` 链会静默继续 | `test_cli_reports_missing_file` |
| 上传路径防目录穿越 | 客户端能在文件名里塞 `../` | `test_save_upload_strips_client_path` |

---

## 3 · 测试策略（已执行）

```bash
# 日常：只跑离线，秒级，不加载任何权重
python -m pytest tests -q

# 真实 UVR 权重：手动，约 30 秒
python -m pytest tests -q -m real

# 阶段收尾：唯一闸口
python tools/check.py
```

`pyproject.toml` 里 `addopts = "-m 'not real'"` —— **默认套件永不碰权重**，
所以 CI 或随手一跑不会因为少下 50 MB 模型而失败。

---

## 4 · 风险与预案（当初列的，实际结果）

| 当初判断的风险 | 实际是否发生 | 处置 |
|---|---|---|
| UVR 模型只接受 44.1 kHz 立体声 wav，输入格式五花八门 | 发生（预期内） | 门面统一用 ffmpeg 归一，`test_decode_to_44k_stereo` 守住 |
| **轨道顺序判反会把功能做反** | **发生**（两次，见 `issues/005`） | 最终定为四级判定：配置 → **模型约定表** → VAD → 兜底 |
| 权重下载在 Windows 上失败 | 发生 | GitHub release 用 python `requests`；`curl.exe` 会被 schannel 中断（写进 `05_deployment.md`） |
| 各轨与输入不等长导致时间轴漂移 | 未发生（UVR 输出天然等长） | 仍保留 `_enforce_same_length()` 作安全网 |
| KARA 系在**说话**（非唱歌）场景是否有效，调研阶段查不到依据 | 已实测确认**有效** | `test_kara_separates_lead_from_background` 固化为回归 |
| 分离质量无法用单测衡量 | 发生（符合预期） | 单测只断言"没退化、没静音、方向没错"；质量靠人工试听（`07_gui_guide.md §4`） |

---

## 5 · 一件事没做 / deliberately out of scope

**没有把 demucs 或 RoFormer 接进来做对照或兜底。** 理由是实测已经给出结论：
sherpa-onnx 的 UVR 在 **CPU** 上（RTF 0.232）比 demucs 在 **GPU** 上（0.740）还快、
零显存、零新增依赖，而且能做 demucs **做不到**的「主体/背景人声」区分。
再引一个引擎只会增加依赖面，换不来能力。

将来若要追求更高 SDR，接入路径见 `06_add_engine.md`；但请注意
`01_design.md §8.2` 记的许可问题（RoFormer 系社区权重多为 GPL-3.0 或未声明）。
