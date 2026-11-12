# devlog

**给 AI agent 用的科研工程开发日志 skill。一天一份、可核验、可续接。**

[![test](https://github.com/Yangzhou-Y/devlog-skill/actions/workflows/test.yml/badge.svg)](https://github.com/Yangzhou-Y/devlog-skill/actions/workflows/test.yml)

A portable devlog skill for AI coding agents: one log per day, every claim traceable to evidence, every log resumable the next morning.

---

## 为什么

让 AI 总结"今天干了什么"，得到的往往是一篇读着不错、但没法用的流水账：数字没有出处，结论没有判据，待办是正文的复述，明天开工还是得从头翻聊天记录。

这套 skill 把"写日志"变成有约束的流程：

- **判断变化** 单独成节，记录今天推翻了哪个假设——这是日志里最值钱的一句
- 每条"通过"都要给 **判据 → 结果 → 证据 → 复现命令** 四段
- 每个数字带 **`[实测]` / `[仿真]` / `[模型]`** 口径，依赖未核实假设的再加 `未标定`
- 构建产物用 **`B-0007`** 这样的 ID 指认，登记在 `BUILDS.md`，带 sha256——位流、安装包、数据集不入库也不怕
- 任务用 `T-xxxx` 编号，只记录**状态迁移**和**连续阻塞天数**，避免清单只增不减
- 写完自动校验，格式硬伤直接报错
- 周报是日日志的**派生视图**：按需汇总，不靠后台常驻；缺哪天日志，周报的「缺口」一节自己会说

## 它长什么样

```markdown
# 2026-11-11 · 采集链路到仿真通过，实机卡在链路异常

## 0. 判断变化
- 原以为旧版固件可以当已知良好基准 → 今天它也异常 → 基准失效，排查转向链路侧

## 1. 数据采集链路（阶段：仿真通过）
- **结果** 判据：1,200 点与参考模型逐位一致｜结果：全部一致｜[仿真]
- **证据** B-0001 · timing.rpt（WNS +0.905 ns）
- **复现** `bash tests/run_sim.sh tb_capture`
```

完整样例见 [`examples/2026-11-11.md`](examples/2026-11-11.md)（虚构数据）。

## 安装

```bash
git clone <this-repo> devlog-skill
cd devlog-skill
python install.py --list           # 看看本机有哪些 agent 目录
python install.py --target codex   # 装到你在用的那一个
```

装一个就够。本机装了多个 agent 时，各自独立安装，互不依赖；不装的那个也不会受影响。

| agent | 用户级路径 | 项目级 |
|---|---|---|
| ClawsGO | `~/.clawsgo/skills/devlog/` | `.clawsgo/skills/` |
| Claude Code | `~/.claude/skills/devlog/` | `.claude/skills/` |
| Codex | `~/.codex/skills/devlog/` | — |
| DeepSeek Harness | `~/.agents/skills/devlog/` | `.dsh/skills/` |
| Qoder | `~/.lingma/skills/devlog/` | — |
| Cursor | 不读 SKILL.md，用 `--project . --cursor` 生成 `.cursor/rules/devlog.mdc` | |
| 其他 | 在 `AGENTS.md` / `GEMINI.md` 里加一行指向 `SKILL.md` | |

路径细节与降级用法见 [`references/adapters.md`](references/adapters.md)。

需要脚本执行能力。豆包等只能上传技能包、不能运行本地命令的客户端，可以把 `SKILL.md` 当流程手册用，但证据收集与校验两个脚本跑不了。

脚本只用 Python 标准库，Python 3.8+。

## 在项目里启用

```bash
mkdir -p devlog/daily devlog/weekly devlog/.evidence
cp devlog-skill/assets/*.md devlog-skill/assets/config.yml devlog/
```

然后把 `devlog/STATE.md` 里的工作流、`devlog/config.yml` 里的阶段词表改成项目的真实情况。之后：

```bash
# 收集当天证据（只读，产物在 devlog/.evidence/）
python scripts/collect_evidence.py --date 2026-11-11

# 写完日志自查
python scripts/check_log.py devlog/daily/2026-11-11.md
```

日常只需要对 agent 说"写今天的开发日志"。

### 日志怎么放

skill 生成的东西全部收在一个目录里，`docs/` 留给别的文档：

```
devlog/
├── INDEX.md                   自动生成，按年月列出全部日志
├── daily/2026-11-11.md        一天一个文件，文件名即日期
├── daily/2025/                跨年后把上一年整体移进来
├── weekly/2026-W46.md
├── .evidence/                 证据快照，可删，建议加进项目 .gitignore
├── STATE.md  TASKS.md  RISKS.md  DECISIONS.md  BUILDS.md
├── config.yml                 工作流与阶段词表
└── notes.md                   项目特有的坑
```

```bash
python scripts/relink.py       # 补对链接层级；日志归档搬家后也用它修复
python scripts/index_logs.py   # 刷新索引
```

证据写成 `[DDR3 位流复测日志](.sim/ddr3_shot/previous_slow_console.txt)` 这样的链接：文字说明这是什么，点一下就能打开当时的文件。路径从项目根写起即可，`relink.py` 会补成相对本日志的层级，不用手算 `../`。

索引里会列出“命名异常”的文件——这是发现日志放错地方、命名不合规的唯一入口。当年保持扁平，跨年再分层；脚本递归查找，移动目录不用改名。

### 周报

```bash
python scripts/weekly.py --end 2026-11-11     # 汇总最近 7 天
```

产出 `devlog/weekly/2026-W46.md`，机械汇总判断变化、任务状态、风险、决策、证据，并列出没写日志的日期。一句话结论与下周里程碑留空，由人补。

周报不依赖定时任务：用户问就生成；写日日志时如果发现距离上次周报已过一周，也会顺带提醒。若确实想要无人值守，用系统计划任务跑这条命令，产物落盘，下次 agent 被调用时再补判断性内容。

## 校验器查什么

| 检查 | 级别 |
|---|---|
| 顶部元数据的日期与文件名一致 | ERROR |
| 有「判断变化」「明早第一件事」两节 | ERROR |
| 引用的 `B-` `T-` `R-` `D-` 编号都已登记 | ERROR |
| 相对链接存在、无绝对路径 | ERROR |
| 阶段与任务状态在词表内 | ERROR |
| 日志任务状态与 `TASKS.md` 一致 | WARN |
| 验证类小节有证据与复现 | WARN |
| 「待补」超过 5 条 | WARN |

## 仓库结构

```
SKILL.md              agent 读取的主文件
references/           模板、各 agent 适配说明
scripts/              证据收集、日志校验、周报汇总（纯标准库）
assets/               七份文档骨架，首次启用时复制到项目 devlog/
examples/             虚构样例
tests/                自测与夹具
install.py            装到指定的 agent
```

## 设计取舍

- **格式由脚本守，内容由人守**：脚本能查结构、编号、链接，查不了"这个结论是否成立"，后者靠四段式约束
- **状态属于项目，规则属于 skill**：项目特有的坑写进 `devlog/notes.md`，不塞进 skill
- **只追加**：日志是历史记录，改旧内容用删除线加更正，不静默重写
- **不做提交**：脚本只读，何时提交由人决定

## 许可

MIT，见 [LICENSE](LICENSE)。
