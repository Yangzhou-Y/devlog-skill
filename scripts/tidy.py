#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""整理日志外观，两件事都幂等：

  1. 元数据移出正文：日志顶部的 --- frontmatter 或 <!-- --> 注释块，
     迁到 devlog/.meta/<日期>.yml。很多预览器会把这两种写法显示出来，
     只有让元数据完全离开日志文件才不可见；脚本读取不受影响。
  2. 标题加粗：# 与 ## 标题的文字两端加上 **，渲染出来更醒目。

用法：
    python tidy.py                    处理 devlog/daily 与 devlog/weekly 下全部 .md
    python tidy.py a.md b.md          只处理指定文件
    python tidy.py --dry-run          只报告，不写文件
    python tidy.py --no-bold          只移元数据，不动标题
"""

import argparse
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _common import find_root, meta_path_for, split_inline_meta  # noqa: E402

for stream in (sys.stdout, sys.stderr):
    try:
        stream.reconfigure(encoding="utf-8")
    except Exception:
        pass

HEADING_RE = re.compile(r"^(#{1,2})[ \t]+(.+?)[ \t]*$")
FENCE_RE = re.compile(r"^\s*(```|~~~)")


def bold_headings(text):
    """# 与 ## 标题加粗，代码围栏内的行不动；返回 (新文本, 改了几处)。"""
    out, count, in_fence = [], 0, False
    for line in text.split("\n"):
        if FENCE_RE.match(line):
            in_fence = not in_fence
        elif not in_fence:
            m = HEADING_RE.match(line)
            if m and not (m.group(2).startswith("**") and m.group(2).endswith("**")):
                line = f"{m.group(1)} **{m.group(2)}**"
                count += 1
        out.append(line)
    return "\n".join(out), count


def targets(args, root):
    if args.files:
        return [Path(f).resolve() for f in args.files]
    found = []
    for sub in ("daily", "weekly"):
        d = root / "devlog" / sub
        if d.is_dir():
            found += [p for p in d.rglob("*.md")]
    return sorted(found)


def tidy_one(path, do_bold, dry):
    text = path.read_text(encoding="utf-8")
    meta, body = split_inline_meta(text)
    moved = 0
    if meta:
        mp = meta_path_for(path)
        lines = [f"{k}: {v}" for k, v in meta.items()]
        if not dry:
            mp.parent.mkdir(parents=True, exist_ok=True)
            mp.write_text("\n".join(lines) + "\n", encoding="utf-8")
        moved = 1
    bolded = 0
    if do_bold:
        body, bolded = bold_headings(body)
    if moved or bolded:
        if not dry:
            path.write_text(body, encoding="utf-8")
    return moved, bolded


def main():
    ap = argparse.ArgumentParser(description="元数据移出正文、标题加粗")
    ap.add_argument("files", nargs="*", help="要处理的文件，默认 daily 与 weekly 下全部 .md")
    ap.add_argument("--root", help="项目根目录，默认自动查找")
    ap.add_argument("--dry-run", action="store_true", help="只报告，不写文件")
    ap.add_argument("--no-bold", action="store_true", help="不处理标题")
    args = ap.parse_args()

    root = Path(args.root).resolve() if args.root else find_root(Path.cwd())
    if not args.files and not (root / "devlog").is_dir():
        print(f"[错误] {root} 下没有 devlog/", file=sys.stderr)
        return 2

    changed = moved_total = bold_total = 0
    for path in targets(args, root):
        if not path.exists():
            print(f"[跳过] 找不到 {path}")
            continue
        moved, bolded = tidy_one(path, not args.no_bold, args.dry_run)
        if moved or bolded:
            changed += 1
            moved_total += moved
            bold_total += bolded
            shown = path.relative_to(root) if root in path.parents else path
            print(f"  {shown}: 元数据{'已移出' if moved else '无'}，加粗标题 {bolded} 处")

    verb = "将会处理" if args.dry_run else "已处理"
    print(f"{verb} {changed} 个文件：移出元数据 {moved_total} 个，加粗标题 {bold_total} 处")
    return 0


if __name__ == "__main__":
    sys.exit(main())
