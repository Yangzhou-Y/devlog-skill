#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""让日志里的证据路径可以点击跳转，并修复搬家后失效的相对链接。

做两件事：
  1. 链接化：正文里写成 `path/to/file` 且文件真实存在的路径，改成
     [`path/to/file`](相对本日志的链接)。相对层级由脚本算，不用手写 ../
  2. 修复：链接按当前位置找不到目标，但按项目根能找到时，重写为正确的相对路径。
     日志从 daily/ 归档进 daily/2025/、或整个目录搬动后，运行一次即可。

幂等：重复运行不会改动已经正确的内容。代码围栏与 frontmatter 不处理。

用法：
    python relink.py                    处理 devlog/ 下全部 Markdown
    python relink.py devlog/daily/2026-11-11.md
    python relink.py --dry-run          只报告，不写文件
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _common import (CODE_SPAN_RE, LINK_RE, body_lines, find_root,  # noqa: E402
                     is_external, is_link_label, linkable_path,
                     relative_link, resolve_target, split_anchor)

for stream in (sys.stdout, sys.stderr):
    try:
        stream.reconfigure(encoding="utf-8")
    except Exception:
        pass


def heal_links(line, base, root, unresolved):
    count = 0

    def fix(m):
        nonlocal count
        label, target = m.group(1), m.group(2)
        if is_external(target) or not split_anchor(target)[0]:
            return m.group(0)
        dest, by_root = resolve_target(base, root, target)
        if dest is None:
            unresolved.append(target)
            return m.group(0)
        if not by_root:
            return m.group(0)
        count += 1
        return f"[{label}]({relative_link(base, dest)}{split_anchor(target)[1]})"

    return LINK_RE.sub(fix, line), count


def linkify(line, base, root):
    count = 0

    def fix(m):
        nonlocal count
        if is_link_label(line, m) or any(c.isspace() for c in m.group(1)):
            return m.group(0)
        hit = linkable_path(m.group(1), root)
        if not hit:
            return m.group(0)
        path, anchor = hit
        count += 1
        return f"[`{m.group(1)}`]({relative_link(base, Path(root) / path)}{anchor})"

    return CODE_SPAN_RE.sub(fix, line), count


def process(text, file_path, root):
    base = file_path.parent
    out, healed, linked, unresolved = [], 0, 0, []
    for _, line, skip in body_lines(text):
        if not skip:
            line, n = heal_links(line, base, root, unresolved)
            healed += n
            line, n = linkify(line, base, root)
            linked += n
        out.append(line)
    return "\n".join(out), linked, healed, unresolved


def targets(args, root):
    if args.files:
        return [Path(f).resolve() for f in args.files]
    base = root / "devlog"
    return sorted(p for p in base.rglob("*.md") if ".evidence" not in p.parts)


def main():
    ap = argparse.ArgumentParser(description="链接化证据路径并修复失效链接")
    ap.add_argument("files", nargs="*", help="要处理的文件，默认 devlog/ 下全部 .md")
    ap.add_argument("--root", help="项目根目录，默认自动查找")
    ap.add_argument("--dry-run", action="store_true", help="只报告，不写文件")
    args = ap.parse_args()

    root = Path(args.root).resolve() if args.root else find_root(Path.cwd())
    if not args.files and not (root / "devlog").is_dir():
        print(f"[错误] {root} 下没有 devlog/", file=sys.stderr)
        return 2

    total_linked = total_healed = changed = 0
    all_bad = []
    for path in targets(args, root):
        if not path.exists():
            print(f"[跳过] 找不到 {path}")
            continue
        old = path.read_text(encoding="utf-8")
        new, linked, healed, bad = process(old, path, root)
        total_linked += linked
        total_healed += healed
        all_bad += [(path, t) for t in bad]
        if new != old:
            changed += 1
            if not args.dry_run:
                path.write_text(new, encoding="utf-8")
            shown = path.relative_to(root) if root in path.parents else path
            print(f"  {shown}: 链接化 {linked} 处，修复 {healed} 处")

    verb = "将会" if args.dry_run else "已"
    print(f"{verb}处理 {changed} 个文件：链接化 {total_linked} 处，修复 {total_healed} 处")
    for path, target in all_bad:
        print(f"[无法解析] {path.name}: {target}")
    return 1 if all_bad else 0


if __name__ == "__main__":
    sys.exit(main())

