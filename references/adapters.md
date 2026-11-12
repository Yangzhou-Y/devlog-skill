# 各 agent 的安装与降级用法

skill 的主体是 `SKILL.md` 与两个 Python 脚本，与具体 agent 无关。区别只在“它从哪里被读到”。

## 支持 skill 目录的 agent

把整个目录复制过去即可，目录名保持 `devlog`：

| agent | 用户级路径 | 项目级路径 |
|---|---|---|
| ClawsGO | `~/.clawsgo/skills/devlog/` | `.clawsgo/skills/devlog/` |
| Claude Code | `~/.claude/skills/devlog/` | `.claude/skills/devlog/` |
| Codex | `~/.codex/skills/devlog/` | — |
| 其他兼容 SKILL.md 的 agent | 见其文档 `skills/` 约定 | 见其文档 |

```bash
python install.py --all          # 装到本机已存在的全部 agent 目录
python install.py --target codex --target clawsgo
python install.py --project .    # 装到当前项目的 .claude/ 与 .clawsgo/
```

装完重启对应 agent，新建会话才会加载。

## 不支持 skill 的 agent

### Cursor

复制 `SKILL.md` 正文（去掉 frontmatter）到 `.cursor/rules/devlog.mdc`，前面加：

```yaml
---
description: 写开发日志时按此流程
globs: devlog/daily/**
alwaysApply: false
---
```

### Gemini CLI / 其他读 GEMINI.md、AGENTS.md 的 agent

在项目根 `GEMINI.md` 或 `AGENTS.md` 里加一行指针：

```markdown
写开发日志、更新状态表、校验日志格式时，遵循 <本 skill 路径>/SKILL.md 的流程与硬规则。
```

### 完全没有文件系统的环境（网页端对话）

只能人工把当天过程贴给有文件权限的 agent，由后者执行第 1～4 步。硬规则里的“不编造”“四段式”仍然适用。

## 脚本的运行前提

- Python 3.8+，只用标准库
- 在项目根目录运行（脚本会向上查找 `devlog/`）
- 需要 `git` 命令；没有 git 也能跑，只是版本锚点退化为产物 ID

如果 agent 无法执行命令，退回人工核对：`references/template.md` 末尾的检查清单列了脚本会查的项目。
