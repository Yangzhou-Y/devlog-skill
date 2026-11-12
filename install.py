#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""把 devlog skill 安装到本机各 agent 的 skill 目录。

用法：
    python install.py --list                 查看检测到哪些 agent
    python install.py --all                  装到全部已检测到的位置
    python install.py --target codex         只装 Codex
    python install.py --project .            装到当前项目的 .claude/ 与 .clawsgo/
    python install.py --all --force          覆盖已有安装

安装只做复制，不改动 agent 的任何配置。卸载：删除目标目录下的 devlog 目录即可。
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

AGENTS = {
    "clawsgo": HOME / ".clawsgo" / "skills",
    "codex": HOME / ".codex" / "skills",
    "claude": HOME / ".claude" / "skills",
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


def install_project(project_root, force):
    results = []
    for sub in (Path(".claude") / "skills", Path(".clawsgo") / "skills"):
        ok, msg = install_to(project_root / sub, force)
        results.append((ok, msg))
    return results


def install_cursor(project_root, force):
    """Cursor 不读 SKILL.md，转成 .mdc 规则文件。"""
    rules = project_root / ".cursor" / "rules"
    target = rules / "devlog.mdc"
    if target.exists() and not force:
        return False, f"{target} 已存在（加 --force 覆盖）"
    rules.mkdir(parents=True, exist_ok=True)
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
    ap = argparse.ArgumentParser(description="安装 devlog skill")
    ap.add_argument("--list", action="store_true", help="列出检测到的 agent")
    ap.add_argument("--all", action="store_true", help="安装到全部检测到的位置")
    ap.add_argument("--target", action="append", choices=sorted(AGENTS), help="指定 agent，可重复")
    ap.add_argument("--project", help="项目根目录，安装项目级 skill")
    ap.add_argument("--cursor", action="store_true", help="为 Cursor 生成项目规则文件（需配合 --project）")
    ap.add_argument("--force", action="store_true", help="覆盖已有安装")
    args = ap.parse_args()

    found = detected()
    if args.list or (not args.all and not args.target and not args.project):
        print("检测到的 agent：")
        for name in sorted(AGENTS):
            mark = "✓" if name in found else "—"
            print(f"  {mark} {name:<8} {AGENTS[name]}")
        if not found:
            print("  没有检测到任何 agent 目录；可用 --project 装到项目内")
        return 0

    targets = sorted(found) if args.all else (args.target or [])
    failed = 0
    for name in targets:
        ok, msg = install_to(found[name], args.force)
        print(f"{'[安装]' if ok else '[跳过]'} {name}: {msg}")
        failed += 0 if ok else 1

    if args.project:
        project_root = Path(args.project).resolve()
        if not (project_root / "README.md").exists() and not (project_root / "docs").exists():
            print(f"[提示] {project_root} 不像项目根，仍按指定路径安装")
        for ok, msg in install_project(project_root, args.force):
            print(f"{'[安装]' if ok else '[跳过]'} 项目级: {msg}")
            failed += 0 if ok else 1
        if args.cursor:
            ok, msg = install_cursor(project_root, args.force)
            print(f"{'[安装]' if ok else '[跳过]'} cursor: {msg}")
            failed += 0 if ok else 1

    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
