# 论文 Workshop 速览

基于 Claude Code 的 review-workshop skill，给一个学术 workshop 或会议的主页 URL，自动通读全部论文，产出一份**按主线分类的综述报告**。

## 它做什么 / 怎么用它

面对一个 workshop 或会议论文集，逐篇读完再形成判断往往要花几天。这个工具帮你先做一轮**总览**：它会通读全部论文，提炼出该领域当前的**趋势走向**与各篇工作之间的**共性问题**，同时把**每一篇**的核心问题、关键进展和技术思路拆解为结构化速查卡。在此基础上，它还会做一轮**议题×论文对照**——系统性地扫描跨论文的共性问题、建议优先二次深读的中心论文、以及尚未被覆盖的研究空白，帮你快速定位重点、给出核查线索。这些对照结果一律标注"待人核查"：真正的深度 critical thinking 由你读原文完成。先速览、后精读，把时间花在最值得读的论文上。

成品是单文件 HTML，包含六个板块：编者整体判断（卷首）、分类总表、按主线展开的综述、议题×论文对照（共性问题/中心论文/研究空白）、逐篇速查卡（含少量关键架构图与批判核查提示）、未公开论文。一个约 20 篇的会议，大约 10-15 分钟跑完，消耗约 100 万 token。

> 样例成品见 [`examples/`](examples/)，流水线架构图见 [`docs/flowchart.svg`](docs/flowchart.svg)。

## 设计哲学

**用 Claude Code 指挥一条多智能体 workflow。** 主 agent（Claude Code）负责编排整条流水线：扇出多个子agent 并行精读每篇论文，再由主线写手子agent、查漏 critic 子agent 与议题对照子agent 协作完成综述与跨论文对照，最后由编者（主 agent）撰写卷首并组装终稿。你只需给出一个 URL，Claude Code 就会搭建并运行这条多智能体流水线，全程自动调度。

**能用脚本做的不交给模型。** 整条流水线只在 5 处调用 LLM：侦察主页提取论文清单、精读每篇论文、撰写主线综述与查漏、议题对照扫描、编者写卷首判断。其余环节（下载、抽文本、分组、抠图、渲染 HTML）全由确定性脚本完成。这让产出结构每次一致，可横向比较多个会议。

## 流水线概览

```
主页 URL
  │
  ├─ 1. 侦察（LLM）─────────→ manifest.json
  │
  ├─ 2. 采集预处理（纯脚本）──→ pdf/ + txt/ + 体量画像
  │
  ├─ 3. 标定（3 篇试跑）────→ 成本估算 + 质量验证
  │
  ├─ 4. 并行精读（Workflow）──→ digests.json（便宜模型，N 路并发）
  │
  ├─ 5. 主题综述 + 查漏 ────→ sections.json + critic.txt（便宜模型）
  │
  ├─ 6. 议题对照（CrossCut）─→ crosscut.json（便宜模型，待人核查）
  │
  ├─ 7. 配图（少而精）──────→ figures/fig_<id>.png（强模型看图定框）
  │
  └─ 8. 卷首 + 组装 ────────→ report.html（强模型写卷首 + 脚本渲染）
```

各阶段详细输入输出、使用的工具与模型分档，见 [SKILL.md](SKILL.md) 中的阶段总览表。

## 安装与触发

### 安装

把项目放进 Claude Code 的个人技能目录：

```
~/.claude/skills/review-workshop/
```

也可以解压 `.skill` 包到该路径。

### 触发

在 Claude Code 对话中，用自然语言或斜杠命令触发：

```
帮我通读这个 workshop 的所有论文，出一份综述：https://example.com/workshop
```

```
/review-workshop https://example.com/workshop
```

## 人工确认关口

流水线设有 4 个确认点，在侦察完成后合并为一次性确认，拍板后全自动跑到底：

| 关口 | 确认什么 |
|------|----------|
| 选题范围 | 抓到的论文清单、缺失项、是否排除某些条目 |
| 分类方案 | 主线类目名 + 每篇预归类 |
| 配图策略 | 默认"少而精"，确认上限（建议 4-8 张） |
| 终稿格式 | 单文件 HTML（默认）/ 视角侧重 |

说"全自动"或传 `--yes` 可跳过确认，使用默认策略。

## 依赖

- **Claude Code**（运行环境）
- **poppler**（提供 `pdftotext`、`pdftoppm`、`pdfinfo`；macOS: `brew install poppler`）
- **Python + Pillow**（`pip install Pillow`）
- **模型分档**：精读 / 综述 / 查漏 / 议题对照用便宜模型（Sonnet / Haiku），卷首 / 配图用强模型（Opus）

## 目录结构

```
SKILL.md                                  # 给 agent 的完整操作说明书
scripts/
  acquire.py                              # 下载 PDF + pdftotext 抽文本 + 体量画像
  extract_figure.py                       # 关键图定位 / 渲染 / 裁剪（三步循环）
  build_report.py                         # 确定性组装单文件 HTML，不调用模型
schemas/
  digest.schema.json                      # 每篇精读的结构化输出契约
prompts/
  recon.md                                # 侦察：从主页提取论文清单
  reader.md                               # 精读：单篇结构化摘要
  theme_writer.md                         # 写手：一条主线的综述
  critic.md                               # 查漏：审查归类、事实、跨主线视角
  crosscut.md                             # 议题对照：跨论文系统性对照扫描
  preface.md                              # 卷首：编者整体判断
workflow/
  review_workshop.template.js             # 并行精读 + 综合的 Workflow 编排模板
docs/
  flowchart.svg                           # 流水线架构图
examples/
  cvpr2026-video-world-model.html         # 样例成品
```

## 独立部署（脱离 Claude Code）

想把它做成不依赖 Claude Code 的独立程序：

- 把 `workflow/` 的编排替换为 **Claude Agent SDK** 的子agent调用
- `scripts/`、`prompts/`、`schemas/` 原样复用
- 加一个 `cli.py` 入口

skill 版与 SDK 版共享同一套阶段定义、提示词和 schema。

## License

MIT
