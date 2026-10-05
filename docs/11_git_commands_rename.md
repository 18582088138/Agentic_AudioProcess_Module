# 11 · 改名重构的 Git 提交指令（人工执行）

> **AI 不执行 `git commit` / `git push`**，本文件交人工执行。
> 本轮把项目从 `Agentic_VoiceSeparate_Module` / `agentic_separate` 改名为
> `Agentic_AudioProcess_Module` / `agentic_audioprocess`，定位从「声音分离」
> 扩展为「音频处理」。完整标识符映射表见 `PROJECT_MEMORY.md §改名重构`。

## 为什么只分三组

包名、模块路径、配置文件路径、import、测试是**一个原子改名** ——
任何一个中间 commit 单独存在都跑不起来（`import agentic_separate` 直接失败）。
所以「代码 + 配置」合成一组，文档与新增文档各一组。

## 提交前确认

```bash
cd F:\2026年\Agentic_AudioProcess_Module        # 目录已改名（见步骤 0）
git status --short
git status --ignored --short | head -20         # 不应出现 .env / models/ / outputs/ / *.onnx
```

预期看到：重命名（`R`）+ 修改（`M`）+ 两个新文件（`docs/10_*`、`docs/11_*`）。

重装 editable 包并确认新入口可用（**旧 egg-info 指向旧包名，必须重装**）：

```bash
C:\Users\75203\miniforge3\envs\ov_env_py312\python.exe -m pip install -e ".[all]"
audio version        # 应打印 agentic-audioprocess 0.1.0
audio doctor         # 体检：ffmpeg / sherpa-onnx / 权重 / VAD
```

---

## 步骤 0/4 · 本地目录改名（**必须手动，AI 做不了**）

⚠️ **为什么必须手动**：仓库目录当前被 VS Code 与本开发会话占用，`Rename-Item`
会报「另一个进程正在使用此文件，因此该进程无法访问此文件」（已在会话内复现两次）。

顺序：

1. 在 VS Code 里**关闭** `Agentic_VoiceSeparate_Module` 这个文件夹
   （File → Close Folder），并结束占用它的终端；
2. 在资源管理器里改名，或在**本会话关闭之后**执行：

```powershell
Rename-Item -LiteralPath 'F:\2026年\Agentic_VoiceSeparate_Module' -NewName 'Agentic_AudioProcess_Module'
```

3. 改名后**先重装 editable 包**：旧的 `__editable__*.pth` 指向旧路径，
   不重装会 `import agentic_audioprocess` 失败 —— 命令见下面的「提交前确认」。

远端仓库已在 GitHub 上改名为 `Agentic_AudioProcess_Module`。若 `git remote -v`
仍是旧地址：

```bash
git remote set-url origin https://github.com/18582088138/Agentic_AudioProcess_Module.git
```

## 步骤 1/4 · 代码与配置的原子改名

```bash
git reset
git add -A
git restore --staged README.md docs/ .dsh/
git commit -m "refactor!: 项目改名为音频处理模块（VoiceSeparate → AudioProcess）

- 包 agentic_separate → agentic_audioprocess，门面 separate.py → audioprocess.py
- 分发名 agentic-separate → agentic-audioprocess，CLI separate → audio
- 门面类 SeparateModule → AudioProcessModule，配置类 / 异常基类同步改名
- 配置文件 configs/separate.yaml → configs/audioprocess.yaml
- 环境变量前缀 SEPARATE_* → AUDIOPROCESS_*（本机无 .env，无迁移成本）
- 保留语义本就属于分离的符号：SeparationMode / SeparationResult /
  SeparationEngine / StemOrderError / SEPARATION_SR / separate() / POST /separate"
```

> `!` 表示破坏性变更：CLI 名、包名、环境变量都变了，外部调用方必须跟着改。

## 步骤 2/4 · 文档与 skill 的定位更新

```bash
git add -A README.md docs/ .dsh/
git restore --staged docs/10_audio_processing_roadmap.md docs/11_git_commands_rename.md
git commit -m "docs: 定位从声音分离扩展为音频处理

- README / 00_INDEX / 01_design / 包 docstring：写清模块定位与「已实现 vs 规划中」
- PROJECT_MEMORY：新增改名映射表与重装 editable 的提醒
- .dsh/skills/agentic-audioprocess-dev：skill 目录与内容同步改名
- 08_git_commands.md：标注首轮指令已执行完，指向本轮指令
- issues/006：记录装上 ruff 后暴露的 20 项既有 lint 问题（与改名无关，
  是 check.py 的 ruff 段第一次真正运行的结果）"
```

## 步骤 3/4 · 新增功能版图与提交指令

```bash
git add docs/10_audio_processing_roadmap.md docs/11_git_commands_rename.md
git commit -m "docs: 音频前后处理版图与改名提交指令

- 10_audio_processing_roadmap: 降噪 / 去环境音 / 音质优化 / 统一管线的版图、
  候选方案（降噪走 sherpa-onnx OfflineSpeechDenoiser，GTCRN 与 DPDFNet）、
  扩展点与验收口径；未实测的数字一律不写
- 11_git_commands_rename: 本轮改名的分步指令"
```

## 步骤 4/4 · 打标签并推送

```bash
git tag -a v0.2.0-rename -m "改名重构：VoiceSeparate → AudioProcess"   # 可选
git push origin main
git push origin --tags                                                 # 可选
```

## 核对

```bash
git status              # 应当干净
git log --oneline -3
audio version
python -m pytest tests -q
```

---

## 不涉及其它模组

本模组的改名**不牵连任何其它模组**：模组之间不许互相引用、互相指引（守则 §七），
所以没有"同步另一个仓库"这一步。若在别处看到指向本模组旧名的引用，那是历史遗留，
按 §七 处理 —— 删掉直接引用（代码 import、可照抄的调用、对方的 issue/设计正文），
只保留「需要 X 时由应用层组合」这种关系说明。
