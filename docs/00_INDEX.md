# 00 · 文档索引 / Index

**默认只读本文件，再按需读一份。** 不要一次加载整个 `docs/`。

| 何时 | 读哪份 | 里面是什么 |
|---|---|---|
| **接手项目（第一步）** | `PROJECT_MEMORY.md` | 环境、常用命令、硬约束、踩过的坑 |
| 方案 | `01_design.md` | 三个模式与模型映射、分层、四级轨道判定、验收标准 |
| 开发过程 | `02_dev_plan.md` | 阶段划分与实际完成情况（回顾式） |
| 测试 | `03_unit_tests.md` | 用例分布、刻意写死的断言、复测命令 |
| **用法** | `04_api_reference.md` | **库 / HTTP / CLI 完整接口参考**（参数、返回、示例、错误码） |
| 部署 | `05_deployment.md` | 权重下载、性能、服务化、与 ASR 插件的协作方式 |
| 接新引擎 | `06_add_engine.md` | 引擎抽象四步与硬约束 |
| GUI | `07_gui_guide.md` | 三个面板的用法与手工验证清单 |
| 提交 | `08_git_commands.md` | 分步 git 指令（**人工执行**） |
| 开发记录 | `09_dev_log.md` | 交付内容、测试结果、与方案的偏差、后续待办 |
| 问题单 | `issues/005-*.md` | 轨道顺序不能硬编码（含两次判据被实测否决的记录） |

## 调研在哪

分离模型的**选型调研与全部实测数据在 ASR 项目的文档里**，本仓库不复制：

- `Agentic_ASR_Module/docs/00_research.md §4.2 / §4.4` —— UVR vs demucs 实测、
  KARA 系能否区分主体/背景人声、RTF 与显存、stem 顺序陷阱；
- `Agentic_ASR_Module/docs/10_reference_research.md §2` —— 降噪 / 人声分离 / RoFormer 系
  的技术参考（**仅备查**）。

> 这一条是刻意的：**同一事实只在一处写权威**，复制一份迟早会两边不一致。

## 项目一句话

Agentic_VoiceSeparate_Module —— 本地声音分离服务插件，三个功能各自独立可调用：

| 功能 | 入口 |
|---|---|
| 人声提取 | `extract_vocals()` |
| 背景音提取 | `extract_accompaniment()` |
| **主体人声去除**（保留背景人声） | `remove_lead_vocal()` |

库 / CLI(`separate …`) / HTTP(8302) / GUI(8402) 四种用法共用同一个门面。

## 一条不可违反的约束

**分离全部走 `sherpa-onnx` 自带的 UVR 后端，不引入 torch 或 demucs。**
实测 CPU RTF 0.23~0.36（比 demucs 在 GPU 上还快）、显存占用 0、模型 28~67 MB。
