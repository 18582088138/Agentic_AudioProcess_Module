# 03 · 单元测试说明 / Unit tests

> 测试策略、成本纪律与复测入口。**用例分布与刻意写死的断言**在这里；
> 每个 issue 的详细背景在 `issues/`。

---

## 1 · 复测命令 / commands

解释器一律用项目环境（绝对路径，可直接粘贴）：

```bash
# 全量离线（秒级，不加载任何权重）
C:\Users\75203\miniforge3\envs\ov_env_py312\python.exe -m pytest tests -q

# 真实 UVR 权重（手动，约 30 秒）
C:\Users\75203\miniforge3\envs\ov_env_py312\python.exe -m pytest tests -q -m real

# 单个文件 / 单个用例
C:\Users\75203\miniforge3\envs\ov_env_py312\python.exe -m pytest tests/test_module.py -q
C:\Users\75203\miniforge3\envs\ov_env_py312\python.exe -m pytest tests/test_module.py::test_model_convention_wins_over_vad -q

# 收尾闸口（环境自检 + ruff + 全量离线测试）
C:\Users\75203\miniforge3\envs\ov_env_py312\python.exe tools\check.py
```

**marker**：`pyproject.toml` 里 `addopts = "-m 'not real'"`，
所以**默认套件永远不碰真实权重**；`-m real` 才会跑 `tests/test_real.py` 的 5 条。
不要为跑一次测试去下一份 50 MB 权重。

---

## 2 · 用例分布 / distribution

| 文件 | 覆盖 | 需要权重 |
|---|---|---|
| `conftest.py` | 共用夹具（见下），本身无用例 | — |
| `test_audio.py` | 44.1 kHz 立体声归一、写读回环、语音占比（能量回退 + Silero） | Silero 那条要 VAD 模型 |
| `test_module.py` | 配置与注册表、三个核心功能、等长校验、**轨道判定四级策略**、落盘命名、引擎契约 | 离线（`null` 引擎） |
| `test_server_cli.py` | CLI 子命令、HTTP 九个端点、失败响应（415/422/403）、下载越权防护 | 离线 |
| `test_gui.py` | NiceGUI 3.x 上传契约、文件名防目录穿越、模块可导入 | 离线 |
| `test_real.py` | **真实 UVR 权重**：三模式跑通、等长、KARA 主/背景可分、纯音乐不崩 | **要 3 个权重** |

### 夹具 / fixtures（`conftest.py`）

| 夹具 | 内容 |
|---|---|
| `voice_over_music_wav` | 9 秒「类语音 + 背景音乐」44.1 kHz 立体声（中间留静音给 VAD 一个断点） |
| `music_only_wav` | 6 秒纯音乐（无语音），用于检验"没有语音时不瞎判" |
| `module` | 用 `null` 引擎、输出到临时目录的 `AudioProcessModule` |
| `uvr_models_dir` | 权重目录路径 |

素材全部是**合成**的 —— 默认套件不能依赖仓库里的大文件。

---

## 3 · 刻意写死的断言 / deliberately pinned assertions

下面几条的阈值是**故意钉死**的：谁把对应的行为改回去，它会立刻变红，
而不是等到线上才发现。改它们之前先读对应的 issue。

| 用例 | 钉住什么 | 为什么 |
|---|---|---|
| `test_module.py::test_model_convention_wins_over_vad` | 断言 `stem_order_resolved_by.startswith("model-convention:")` | 第一版用 VAD 语音占比当默认判据，**背景音乐被当成语音**导致方向判反。这条保证模型约定表始终优先（`issues/005`） |
| `test_module.py::test_lead_removal_can_be_forced_by_config` | 断言依据串带 `config:lead_stem_index=0` | 判反时的逃生舱必须真的生效 |
| `test_module.py::test_vad_is_used_for_unknown_models` | 断言未知模型退回 `vad:` 且提示里带「约定表 / music」 | 兜底路径不能静默变成"确定" |
| `test_module.py::test_stems_are_same_length_as_input` | 断言各轨样本数 **等于**输入 | 不等长会让下游时间轴整体漂移且不报错 |
| `test_audio.py::test_silero_backend_detects_voice` | 断言语音占比 **> 0.4** | 回归两个 VAD 陷阱：整段喂入会漏检、环形缓冲不取会丢段 |
| `test_gui.py::test_upload_event_arguments_shape` | 断言事件字段里有 `file`、而 **`name` / `content` 不在** | NiceGUI 3.x 改了上传 API；老写法会让上传直接报错 |
| `test_real.py::test_kara_separates_lead_from_background` | 断言两条轨 rms **都 > 1e-4**（都不是静音） | 若退化成普通的人声/伴奏二分，背景轨会接近静音 —— 那是本插件核心能力的失效信号 |

最后一条是**这个插件唯一真正重要的验收**：它用的素材是
「中文主体（居中）+ 英文背景（偏侧 −10 dB）」，单一说话人的素材根本无法暴露这个能力。

---

## 4 · 真实用例的前置 / prerequisites for `-m real`

需要 `models/` 下这四个文件（下载方式见 `05_deployment.md`）：

| 文件 | 体积 | 用例 |
|---|---|---|
| `sherpa-separation/UVR_MDXNET_KARA.onnx` | 28 MB | 全部（`uvr_module` 夹具的 skip 条件） |
| `sherpa-separation/UVR-MDX-NET-Voc_FT.onnx` | 64 MB | `test_all_three_modes_run` |
| `sherpa-separation/UVR-MDX-NET-Inst_Main.onnx` | 50 MB | `test_all_three_modes_run` |
| `sherpa-vad/silero_vad.onnx` | 0.6 MB | 轨道判定的兜底路径 |

另外还需要 `models/samples/{zh,en}.mp3`（构造"主体 + 背景"素材用）。
缺任何一个，对应用例会 `pytest.skip` 并打印缺什么，不会静默通过。

---

## 5 · 不做什么 / what these tests do not cover

- **不做浏览器端交互测试**：NiceGUI 的界面行为靠 `07_gui_guide.md §4` 的手工清单。
  单测只锁上传路径的契约与文件名安全。
- **不做全仓库回归**：日常只跑与本改动相关的用例；全量只在阶段收尾跑 `tools/check.py`。
- **不评估分离质量**（SDR / 主观听感）：那需要带标注的数据集，超出单元测试范畴。
  `test_real.py` 只断言"没退化、没静音、方向没错"。
