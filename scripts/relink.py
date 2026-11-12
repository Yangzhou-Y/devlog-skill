#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""补对日志里链接的相对层级，修复搬家后失效的链接。

写日志时链接统一写成 [简要说明](从项目根起的路径)，例如
    [DDR3 位流复测日志](.sim/ddr3_shot/previous_slow_console.txt)
不用手算 ../。本脚本把它改成相对本日志的正确路径；日志从 daily/ 归档进
daily/2025/、或整个目录搬动后，再运行一次即可修复。

链接文字必须是说明而不是路径，这一点由 check_log.py 检查；脚本无法替你编说明。
旧日志里裸写的 `path` 可以用 --wrap-bare 临时包成链接，文字仍是路径，
之后请手工改成简要说明。

幂等：重复运行不会改动已经正确的内容。代码围栏与 frontmatter 不处理。

用法：
    python relink.py                    处理 devlog/ 下全部 Markdown
    python relink.py devlog/daily/2026-11-11.md
    python relink.py --dry-run          只报告，不写文件
    python relink.py --wrap-bare        另把裸写的存在路径包成链接
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


def process(text, file_path, root, wrap_bare=False):
    base = file_path.parent
    out, healed, linked, unresolved = [], 0, 0, []
    for _, line, skip in body_lines(text):
        if not skip:
            line, n = heal_links(line, base, root, unresolved)
            healed += n
            if wrap_bare:
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
    ap.add_argument("--wrap-bare", action="store_true",
                    help="把裸写的存在路径包成链接（链接文字仍是路径，需事后改成说明）")
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
        new, linked, healed, bad = process(old, path, root, args.wrap_bare)
        total_linked += linked
        total_healed += healed
        all_bad += [(path, t) for t in bad]
        if new != old:
            changed += 1
            if not args.dry_run:
                path.write_text(new, encoding="utf-8")
            shown = path.relative_to(root) if root in path.parents else path
            print(f"  {shown}: 修复 {healed} 处，包裹 {linked} 处")

    verb = "将会" if args.dry_run else "已"
    print(f"{verb}处理 {changed} 个文件：修复 {total_healed} 处，包裹 {total_linked} 处")
    for path, target in all_bad:
        print(f"[无法解析] {path.name}: {target}")
    return 1 if all_bad else 0


if __name__ == "__main__":
    sys.exit(main())

