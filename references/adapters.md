# 各 agent 的安装与降级用法

skill 的主体是 `SKILL.md` 与两个 Python 脚本，格式是通用的：YAML frontmatter 加 Markdown 正文。只要 agent 支持这套格式，把整个 `devlog/` 目录放进去就能被识别。

装一个就够，不需要为了“以后可能用”把所有 agent 都装一遍。

## 支持 SKILL.md 的 agent

| agent | 用户级 | 项目级 | 说明 |
|---|---|---|---|
| ClawsGO | `~/.clawsgo/skills/devlog/` | `.clawsgo/skills/devlog/` | 已验证 |
| Claude Code | `~/.claude/skills/devlog/` | `.claude/skills/devlog/` | 已验证目录约定 |
| Codex | `~/.codex/skills/devlog/` | — | 已验证 |
| DeepSeek Harness | `~/.agents/skills/devlog/` | `.dsh/skills/devlog/` | 目录约定来自官方文档；`~/.agents/skills` 是跨 agent 通用位置 |
| Qoder | `~/.lingma/skills/devlog/` | — | 目录约定来自 Lingma/Qoder 文档，以本机版本为准 |

```bash
python install.py --list           # 看本机检测到哪些目录
python install.py --target codex   # 装到其中一个
python install.py --target claude --project .   # 或装到当前项目
```

项目级安装会让 skill 只在这个项目里生效，适合不想动全局配置的场景。同一名称时，项目级通常覆盖用户级。

## 不支持 SKILL.md 的 agent

### Cursor

```bash
python install.py --target claude --project . --cursor
```

生成 `.cursor/rules/devlog.mdc`，`globs: devlog/daily/**`，按需触发。

### 豆包（Doubao）等只能上传技能包的客户端

支持上传含 `SKILL.md` 的文件夹或压缩包，但**没有命令执行环境**：

- 可以把本 skill 当流程手册用，日志结构、四段式、硬规则仍然适用
- `collect_evidence.py`、`check_log.py` 跑不了，证据收集与格式校验需在本地用 Python 补
- 上传时要把 `references/`、`assets/` 一并带上，只传一个 `SKILL.md` 会缺模板与骨架

### Gemini CLI / 其他读 GEMINI.md、AGENTS.md 的 agent

在项目根 `GEMINI.md` 或 `AGENTS.md` 里加一行指针：

```markdown
写开发日志、更新状态表、校验日志格式时，遵循 <本 skill 路径>/SKILL.md 的流程与硬规则。
```

### 没有文件系统的环境（网页端对话）

只能人工把当天过程贴给有文件权限的 agent，由后者执行第 1～4 步。硬规则里的“不编造”“四段式”仍然适用。

## 脚本的运行前提

- Python 3.8+，只用标准库
- 在项目根目录运行（脚本会向上查找 `devlog/`）
- 需要 `git` 命令；没有 git 也能跑，只是版本锚点退化为产物 ID

如果 agent 无法执行命令，退回人工核对：`references/template.md` 末尾的检查清单列了脚本会查的项目。
