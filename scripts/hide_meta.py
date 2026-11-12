#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""把日志顶部的 --- frontmatter 改成不可见的 HTML 注释块。

不少 Markdown 渲染器会把 --- frontmatter 显示在页面顶部（GitHub 渲染成表格）。
注释块 <!-- ... --> 在所有渲染器里都不可见；脚本与 agent 读原文时不受影响。

幂等：已经是注释块的文件不动。

用法：
    python hide_meta.py                    处理 devlog/ 下全部 .md
    python hide_meta.py a.md b.md          只处理指定文件
    python hide_meta.py --dry-run          只报告，不写文件
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _common import find_root  # noqa: E402

for stream in (sys.stdout, sys.stderr):
    try:
        stream.reconfigure(encoding="utf-8")
    except Exception:
        pass


def convert(text):
    """返回转换后的文本；无需转换或无法转换时返回 None。"""
    if not text.startswith("---"):
        return None
    end = text.find("\n---", 3)
    if end == -1:
        return None
    block = text[3:end].strip("\n")
    if "-->" in block:
        return None
    return "<!--\n" + block + "\n-->" + text[end + 4:]


def targets(args, root):
    if args.files:
        return [Path(f).resolve() for f in args.files]
    base = root / "devlog"
    return sorted(p for p in base.rglob("*.md") if ".evidence" not in p.parts)


def main():
    ap = argparse.ArgumentParser(description="把 --- frontmatter 改成不可见的注释块")
    ap.add_argument("files", nargs="*", help="要处理的文件，默认 devlog/ 下全部 .md")
    ap.add_argument("--root", help="项目根目录，默认自动查找")
    ap.add_argument("--dry-run", action="store_true", help="只报告，不写文件")
    args = ap.parse_args()

    root = Path(args.root).resolve() if args.root else find_root(Path.cwd())
    if not args.files and not (root / "devlog").is_dir():
        print(f"[错误] {root} 下没有 devlog/", file=sys.stderr)
        return 2

    changed = 0
    for path in targets(args, root):
        if not path.exists():
            print(f"[跳过] 找不到 {path}")
            continue
        new = convert(path.read_text(encoding="utf-8"))
        if new is None:
            continue
        changed += 1
        if not args.dry_run:
            path.write_text(new, encoding="utf-8")
        shown = path.relative_to(root) if root in path.parents else path
        print(f"  {shown}")

    verb = "将会转换" if args.dry_run else "已转换"
    print(f"{verb} {changed} 个文件")
    return 0


if __name__ == "__main__":
    sys.exit(main())
