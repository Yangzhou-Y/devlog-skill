#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""生成 devlog/INDEX.md：按年月列出全部日志与一句话结论。

兼容两种布局：
    devlog/daily/2026-11-11.md
    devlog/daily/2026/11/2026-11-11.md

用法：
    python index_logs.py
    python index_logs.py --root C:/path/to/project
"""

import argparse
import re
import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _common import find_root, misplaced_devlog, relative_link  # noqa: E402

for stream in (sys.stdout, sys.stderr):
    try:
        stream.reconfigure(encoding="utf-8")
    except Exception:
        pass

NAME_RE = re.compile(r"^(\d{4})-(\d{2})-(\d{2})\.md$")
TITLE_RE = re.compile(r"^#\s+.+?·\s*(.+?)\s*$")
RESERVED = {"index.md", "readme.md"}


def collect(log_dir):
    logs, anomalies = {}, []
    for path in sorted(log_dir.rglob("*.md")):
        if path.name.lower() in RESERVED:
            continue
        m = NAME_RE.match(path.name)
        if not m:
            anomalies.append(path)
            continue
        key = path.name[:-3]
        if key in logs:
            anomalies.append(path)      # 同名文件出现在多个目录
            continue
        logs[key] = path
    return logs, anomalies


def strip_bold_all(line):
    """# 标题行里去掉加粗标记，便于取标题文字。"""
    return line.replace("**", "")


def title_of(path):
    try:
        with open(path, encoding="utf-8") as fh:
            for _ in range(40):
                line = fh.readline()
                if not line:
                    break
                m = TITLE_RE.match(strip_bold_all(line.strip()))
                if m:
                    return m.group(1)
    except OSError:
        pass
    return "（缺标题）"


def main():
    ap = argparse.ArgumentParser(description="生成日志索引")
    ap.add_argument("--root", help="项目根目录，默认自动查找（含 devlog/ 的祖先，docs/ 不算）")
    ap.add_argument("--out", help="输出路径，默认 devlog/INDEX.md")
    args = ap.parse_args()

    root = Path(args.root).resolve() if args.root else find_root(Path.cwd())
    log_dir = root / "devlog" / "daily"
    wrong = misplaced_devlog(root)
    if wrong and not log_dir.is_dir():
        print(f"[错误] 日志目录放错了位置：{wrong}\n"
              f"  应放在项目根：{root / 'devlog'}\n"
              f"  迁移：mv docs/devlog devlog && python scripts/relink.py", file=sys.stderr)
        return 2
    if not log_dir.is_dir():
        print(f"[错误] 找不到 {log_dir}", file=sys.stderr)
        return 2

    logs, anomalies = collect(log_dir)
    if not logs:
        print("[提示] devlog/daily 下还没有符合 YYYY-MM-DD.md 的日志")
        return 1

    months = defaultdict(list)
    for key, path in logs.items():
        months[key[:7]].append((key, path))

    out_path = Path(args.out) if args.out else root / "devlog" / "INDEX.md"
    lines = [
        "# 日志索引",
        "",
        f"> 由 devlog skill 生成，勿手改。最后更新：{datetime.now():%Y-%m-%d %H:%M}",
        f"> 共 {len(logs)} 篇，{min(logs)} ~ {max(logs)}。",
        "",
    ]

    for month in sorted(months, reverse=True):
        entries = sorted(months[month], reverse=True)
        lines += [f"## {month}（{len(entries)} 篇）", ""]
        for key, path in entries:
            rel = relative_link(out_path.parent, path)
            lines.append(f"- [{key}]({rel}) · {title_of(path)}")
        lines.append("")

    weekly_dir = root / "devlog" / "weekly"
    if weekly_dir.is_dir():
        weeks = sorted(p for p in weekly_dir.rglob("*.md")
                       if re.match(r"^\d{4}-W\d{2}\.md$", p.name))
        if weeks:
            lines += ["## 周报", ""]
            for path in sorted(weeks, reverse=True):
                rel = relative_link(out_path.parent, path)
                lines.append(f"- [{path.stem}]({rel})")
            lines.append("")

    if anomalies:
        lines += ["## 命名异常", "",
                  "以下文件不符合 `YYYY-MM-DD.md`，未计入索引：", ""]
        for path in anomalies:
            rel = path.relative_to(root).as_posix()
            lines.append(f"- `{rel}`")
        lines.append("")

    out_path.write_text("\n".join(lines), encoding="utf-8")
    print(f"索引已生成：{out_path}")
    print(f"  日志 {len(logs)} 篇，月份 {len(months)} 个")
    if anomalies:
        print(f"  命名异常 {len(anomalies)} 个，见索引末尾")
    return 0


if __name__ == "__main__":
    sys.exit(main())
