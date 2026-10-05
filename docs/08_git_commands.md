# 08 · Git 提交指令汇总（人工执行）

> **AI 不执行 `git commit` / `git push`**，本文件交人工执行。
> ⚠️ **本文件是首轮开发的指令，已全部执行完（仓库现有 8 条提交），留档备查。**
> 本轮**改名重构**（VoiceSeparate → AudioProcess）的提交指令见
> `11_git_commands_rename.md`；两者不要混着执行。
>
> 下文出现的 `agentic_separate/`、`separate` 等旧标识符是**当时的历史状态**，
> 已按 `PROJECT_MEMORY.md §改名重构` 全部改名，**不要照着旧路径重新 add**。

**提交前确认**：

```bash
git status --short      # 不应出现 .env / models/ / outputs/ / *.onnx
git status --ignored --short | head -20
```

看到权重或 `.env` 进了暂存区就**先停下来查** `.gitignore`。权重只在
`models/sherpa-separation/`（约 300 MB），一律不入库。

commit 类型前缀英文，正文中文。

---

## 步骤 1/8 · 工程骨架与依赖

```bash
git reset
git add pyproject.toml .gitignore .env.example tools/ .dsh/
git commit -m "chore: 工程骨架与依赖

- pyproject.toml: 只依赖 sherpa-onnx（不需要 torch，也不需要 demucs）
- tools/check.py: 收尾闸口（环境自检 + ruff + 全量测试）
- .dsh/skills/agentic-audioprocess-dev: 三个模式的模型映射与轨道判定纪律"
```

## 步骤 2/8 · 方案、部署与项目记忆

```bash
git reset
git add README.md docs/00_INDEX.md docs/PROJECT_MEMORY.md docs/01_design.md  docs/05_deployment.md docs/issues/
git commit -m "docs: 方案、部署与项目记忆

- 01_design.md: 三个模式与三套模型的映射、四级轨道判定、验收标准 V1-V7
- 05_deployment.md: 权重下载（必须用 python requests，curl 会被 schannel 中断）
- issues/005: 轨道顺序不能硬编码（含两次判据被实测否决的记录）
- PROJECT_MEMORY.md: 最要紧的未验项是真实影视素材上的泛化性"
```

## 步骤 3/8 · 核心层、音频层与配置

```bash
git reset
git add agentic_audioprocess/__init__.py agentic_audioprocess/core/ agentic_audioprocess/audio/ configs/
git commit -m "feat(core): 配置、类型、异常与音频层

- 解码出口固定 44.1kHz 立体声（UVR 模型的输入要求）
- 语音占比检测记下两个 VAD 教训（分块喂 + 边喂边取）
- 模式到模型的映射写在 config：去主体人声必须用 KARA 系"
```

## 步骤 4/8 · 引擎层

```bash
git reset
git add agentic_audioprocess/engines/
git commit -m "feat(engines): UVR 分离引擎与占位引擎

- uvr: sherpa-onnx 的 OfflineSourceSeparation（CPU RTF 0.232、零显存、零新增依赖）
- null: 零依赖占位，输出确定性结果，支撑离线测试与界面预览
- 权重缺失时抛 ModelMissingError 并附下载地址"
```

## 步骤 5/8 · 门面

```bash
git reset
git add agentic_audioprocess/audioprocess.py
git commit -m "feat: 门面 AudioProcessModule 与四级轨道判定

- 人声提取 / 背景音提取 / 主体人声去除，三者各自独立可调用
- _resolve_order: 配置 > **模型约定表** > VAD > 兜底，依据回传到结果里
  · 约定表是实测出来的（KARA 的 stem0 是主体、KARA_2 的 stem1 是主体）
  · 能量与 VAD 两条判据都被背景音乐骗过：音乐轨 rms 0.1533 > 人声轨 0.1114；
    含音乐轨 VAD 占比 0.914 > 人声轨 0.7624，导致方向判反（issues/005）
- _enforce_same_length: 强制各轨与输入等长，动过手脚写进 warnings"
```

## 步骤 6/8 · 三种入口

```bash
git reset
git add agentic_audioprocess/cli.py agentic_audioprocess/__main__.py  agentic_audioprocess/server/ agentic_audioprocess/gui/
git commit -m "feat: CLI / HTTP / GUI

- 三个功能各自独立命令 / 端点 / 面板，均可单独调用
- GUI 上传按 NiceGUI 3.x 的契约实现：事件对象只有 file 字段，
  落盘用 await file.save(path)，文件名只取 basename 防目录穿越"
```

## 步骤 7/8 · 测试

```bash
git reset
git add tests/
git commit -m "test: 离线套件与真实 UVR 权重用例

- 核心断言：KARA 的两条轨都不能是静音（若退化成普通二分，背景轨会接近静音）
- 轨道判定回归：模型约定表必须优先于 VAD
- test_gui.py: 把 NiceGUI 3.x 的上传事件契约钉死"
```

## 步骤 8/8 · 用法与过程文档

```bash
git reset
git add docs/02_dev_plan.md docs/03_unit_tests.md docs/04_api_reference.md  docs/06_add_engine.md docs/07_gui_guide.md docs/08_git_commands.md docs/09_dev_log.md
git commit -m "docs: 用法、测试、扩展与开发记录

- 04_api_reference: 库 / HTTP / CLI 完整接口参考
- 03/07: 用例分布与界面手工验证清单
- 02/09: 回顾式计划与开发中与方案的偏差"
```

---

## 核对

```bash
git status          # 应当干净
git log --oneline   # 8 条提交
```

---

## 与其它模组的关系

本模组**只做音频处理**，不 import 别的模组，也不在文档里指引别的模组的路径与接口
（守则 §七 模组独立性）。需要串联多个模组时由**应用层 pipeline** 组合，
组合脚本放在模组之外。
