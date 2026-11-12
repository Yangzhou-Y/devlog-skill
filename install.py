#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""把 devlog skill 安装到你选定的一个 agent。

用法：
    python install.py --list                     查看本机已有哪些 agent 目录
    python install.py --target codex             装到某一个 agent（用户级）
    python install.py --target claude --project .  装到当前项目
    python install.py --target claude --project . --cursor  另生成 Cursor 规则

安装只做复制，不改动 agent 的任何配置。卸载：删除目标目录下的 devlog 目录。
"""

import argparse
import shutil
import sys
from pathlib import Path

for stream in (sys.stdout, sys.stderr):
    try:
        stream.reconfigure(encoding="utf-8")
    except Exception:
        pass

HERE = Path(__file__).resolve().parent
HOME = Path.home()

# 只复制运行所需的内容，测试与 CI 配置不随安装分发
PAYLOAD = ["SKILL.md", "README.md", "scripts", "references", "assets", "examples"]

# 用户级安装位置
AGENTS = {
    "clawsgo": HOME / ".clawsgo" / "skills",
    "codex": HOME / ".codex" / "skills",
    "claude": HOME / ".claude" / "skills",
    "deepseek": HOME / ".agents" / "skills",
    "qoder": HOME / ".lingma" / "skills",
}

# 项目级安装位置（相对于项目根）
PROJECT_PATHS = {
    "clawsgo": Path(".clawsgo") / "skills",
    "claude": Path(".claude") / "skills",
    "deepseek": Path(".dsh") / "skills",
}


def detected():
    return {name: path for name, path in AGENTS.items() if path.parent.exists()}


def install_to(dest_root, force):
    dest = dest_root / "devlog"
    if dest.exists() and not force:
        return False, f"{dest} 已存在（加 --force 覆盖）"
    dest.mkdir(parents=True, exist_ok=True)
    for item in PAYLOAD:
        src = HERE / item
        if not src.exists():
            continue
        target = dest / item
        if src.is_dir():
            shutil.copytree(src, target, dirs_exist_ok=True)
        else:
            shutil.copy2(src, target)
    return True, str(dest)


def install_cursor(project_root, force):
    """Cursor 不读 SKILL.md，转成 .mdc 规则文件。"""
    target = project_root / ".cursor" / "rules" / "devlog.mdc"
    if target.exists() and not force:
        return False, f"{target} 已存在（加 --force 覆盖）"
    target.parent.mkdir(parents=True, exist_ok=True)
    text = (HERE / "SKILL.md").read_text(encoding="utf-8")
    body = text.split("---", 2)[-1].lstrip() if text.startswith("---") else text
    head = ("---\n"
            "description: 写开发日志、更新状态表、校验日志格式时按此流程\n"
            "globs: devlog/daily/**\n"
            "alwaysApply: false\n"
            "---\n\n"
            "<!-- 由 devlog skill 生成；脚本见已安装的 devlog/scripts/ -->\n\n")
    target.write_text(head + body, encoding="utf-8")
    return True, str(target)


def main():
    ap = argparse.ArgumentParser(description="安装 devlog skill 到指定 agent")
    ap.add_argument("--list", action="store_true", help="列出本机检测到的 agent 目录")
    ap.add_argument("--target", choices=sorted(AGENTS), help="安装到哪一个 agent")
    ap.add_argument("--project", help="项目根目录，安装为项目级 skill")
    ap.add_argument("--cursor", action="store_true", help="另生成 Cursor 规则（需配合 --project）")
    ap.add_argument("--force", action="store_true", help="覆盖已有安装")
    args = ap.parse_args()

    if args.list or not (args.target or args.project):
        print("本机检测到的 agent 目录：")
        found = detected()
        for name in sorted(AGENTS):
            mark = "✓" if name in found else "—"
            print(f"  {mark} {name:<9} {AGENTS[name]}")
        print("\n选用其中一个：python install.py --target <名称>")
        return 0

    if not args.target:
        ap.error("请用 --target 指定一个 agent")
    if args.cursor and not args.project:
        ap.error("--cursor 需要配合 --project")

    if args.project:
        project_root = Path(args.project).resolve()
        if not (project_root / "README.md").exists() and not (project_root / "devlog").exists():
            print(f"[提示] {project_root} 不像项目根，仍按指定路径安装")
        if args.target not in PROJECT_PATHS:
            ap.error(f"{args.target} 没有约定的项目级目录，请只做用户级安装")
        ok, msg = install_to(project_root / PROJECT_PATHS[args.target], args.force)
        print(f"{'[安装]' if ok else '[跳过]'} 项目级 {args.target}: {msg}")
        if not ok:
            return 1
        if args.cursor:
            ok, msg = install_cursor(project_root, args.force)
            print(f"{'[安装]' if ok else '[跳过]'} cursor: {msg}")
            if not ok:
                return 1
        return 0

    if args.target not in detected():
        print(f"[提示] 未检测到 {AGENTS[args.target]} 的父目录，仍按该路径创建")
    ok, msg = install_to(AGENTS[args.target], args.force)
    print(f"{'[安装]' if ok else '[跳过]'} {args.target}: {msg}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
