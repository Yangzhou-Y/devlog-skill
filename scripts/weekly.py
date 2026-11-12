#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""从日日志汇总周报草稿。

只读日日志，输出 devlog/weekly/YYYY-Www.md。判断性的两节（一句话结论、
下周第一个里程碑）留空，由人或 agent 补。

用法：
    python weekly.py                         汇总最近 7 天
    python weekly.py --end 2026-11-12        指定截止日
    python weekly.py --days 14               改变窗口
"""

import argparse
import re
import sys
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _common import find_root  # noqa: E402

for stream in (sys.stdout, sys.stderr):
    try:
        stream.reconfigure(encoding="utf-8")
    except Exception:
        pass

SECTION_RE = re.compile(r"^##\s+(.+?)\s*$", re.M)
TASK_ROW_RE = re.compile(r"^\|\s*(T-\d{4})\s*\|(.+)$")
ID_RE = re.compile(r"\b([RTD]-\d{4})\b")


def parse_frontmatter(text):
    if not text.startswith("---"):
        return {}
    end = text.find("\n---", 3)
    if end == -1:
        return {}
    fm = {}
    for line in text[3:end].splitlines():
        if ":" in line and not line.startswith((" ", "\t")):
            k, v = line.split(":", 1)
            fm[k.strip()] = v.strip()
    return fm


def split_sections(text):
    parts = SECTION_RE.split(text)
    return {parts[i]: parts[i + 1] for i in range(1, len(parts) - 1, 2)}


def bullets(body):
    out = []
    for line in body.splitlines():
        s = line.strip()
        if not s.startswith(("-", "*")):
            continue
        s = re.sub(r"^[-*]\s*", "", s).strip()
        if s.rstrip("。.") in ("无", "待补", ""):
            continue
        out.append(s)
    return out


def task_rows(body):
    rows = []
    for line in body.splitlines():
        if not TASK_ROW_RE.match(line.strip()):
            continue
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if len(cells) >= 5:
            rows.append({"id": cells[0], "text": cells[1], "state": cells[2],
                         "blocked": cells[3], "days": cells[4]})
    return rows


def load_days(log_dir, start, end):
    """递归查找，兼容 devlog/daily/YYYY-MM-DD.md 与 devlog/daily/YYYY/MM/YYYY-MM-DD.md。"""
    found = {}
    for path in log_dir.rglob("*.md"):
        m = re.match(r"^(\d{4}-\d{2}-\d{2})\.md$", path.name)
        if m:
            found[m.group(1)] = path

    days, cursor = [], start
    while cursor <= end:
        key = f"{cursor:%Y-%m-%d}"
        if key in found:
            days.append((cursor, found[key]))
        cursor += timedelta(days=1)
    return days


def newest_by_id(items):
    """同一编号出现多次时，保留文字最长的一条（信息最全），日期取最早一次。"""
    merged = {}
    for date, text in items:
        m = ID_RE.search(text)
        key = m.group(1) if m else text
        if key not in merged:
            merged[key] = [date, text]
        elif len(text) > len(merged[key][1]):
            merged[key] = [merged[key][0], text]
    return [f"- **{d}** {t}" for d, t in merged.values()]


def main():
    ap = argparse.ArgumentParser(description="汇总周报草稿")
    ap.add_argument("--end", help="截止日 YYYY-MM-DD，默认今天")
    ap.add_argument("--days", type=int, default=7, help="窗口天数，默认 7")
    ap.add_argument("--root", help="项目根目录，默认自动查找")
    args = ap.parse_args()

    end = datetime.strptime(args.end, "%Y-%m-%d") if args.end else datetime.now()
    end = end.replace(hour=0, minute=0, second=0, microsecond=0)
    start = end - timedelta(days=args.days - 1)
    root = Path(args.root).resolve() if args.root else find_root(Path.cwd())
    log_dir = root / "devlog" / "daily"

    if not log_dir.is_dir():
        print(f"[错误] 找不到 {log_dir}", file=sys.stderr)
        return 2

    days = load_days(log_dir, start, end)
    if not days:
        print(f"[提示] {start:%Y-%m-%d} ~ {end:%Y-%m-%d} 没有任何日日志，无法汇总")
        return 1

    judgement, risks, decisions = [], [], []
    tasks = {}            # id -> 最后一次出现
    builds = []

    for day, path in days:
        text = path.read_text(encoding="utf-8")
        fm = parse_frontmatter(text)
        sections = split_sections(text)
        date = f"{day:%m-%d}"

        for name, body in sections.items():
            if "判断变化" in name:
                judgement += [f"- **{date}** {b}" for b in bullets(body)]
            elif "风险" in name:
                risks += [(date, b) for b in bullets(body)]
            elif "决策" in name:
                decisions += [(date, b) for b in bullets(body)]
            elif "任务变化" in name:
                for row in task_rows(body):
                    prev = tasks.get(row["id"])
                    row["date"] = date
                    if prev is None:
                        row["first"] = date
                    else:
                        row["first"] = prev.get("first", date)
                    tasks[row["id"]] = row

        for token in re.findall(r"B-\d{4}", fm.get("builds", "")):
            if token not in builds:
                builds.append(token)

    def task_line(row):
        line = f"- `{row['id']}` {row['text']}（{row['state']}"
        if row["blocked"] not in ("—", "-", ""):
            line += f"；阻塞于 {row['blocked']}"
        line += f"；本周首见 {row['first']}）"
        return line

    in_progress = [task_line(r) for r in tasks.values() if r["state"] in ("待办", "进行中")]
    closed = [task_line(r) for r in tasks.values() if r["state"] == "完成"]
    blocked = [task_line(r) for r in tasks.values() if r["state"] in ("阻塞", "顺延")]

    iso = end.isocalendar()
    week_tag = f"{iso[0]}-W{iso[1]:02d}"
    out_dir = root / "devlog" / "weekly"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"{week_tag}.md"

    logged = {d.strftime("%m-%d") for d, _ in days}
    gaps = [f"{start + timedelta(days=i):%m-%d}" for i in range(args.days)
            if f"{start + timedelta(days=i):%m-%d}" not in logged]

    evidence = "、".join(f"`{b}`" for b in builds) if builds else "- 本周未登记新产物。"

    lines = [
        "---",
        f"week: {week_tag}",
        f"range: {start:%Y-%m-%d} ~ {end:%Y-%m-%d}",
        f"days_logged: {len(days)}/{args.days}",
        "---",
        "",
        f"# {week_tag} · 一句话结论",
        "",
        "> 待补：把哪条工作流推到哪个阶段，本周最重要的一个变化是什么。",
        "",
        "## 判断变化",
        "",
        *(judgement or ["- 本周日志未记录判断变化。"]),
        "",
        "## 任务",
        "",
        "### 新增或推进",
        "",
        *(in_progress or ["- 无。"]),
        "",
        "### 关闭",
        "",
        *(closed or ["- 无。"]),
        "",
        "### 阻塞与顺延",
        "",
        *(blocked or ["- 无。"]),
        "",
        "## 风险",
        "",
        *(newest_by_id(risks) or ["- 无新增。"]),
        "",
        "## 决策",
        "",
        *(newest_by_id(decisions) or ["- 无。"]),
        "",
        "## 证据",
        "",
        evidence,
        "",
        "## 下周第一个里程碑",
        "",
        "> 待补：一句话，可验收。",
        "",
    ]
    if gaps:
        lines += ["## 缺口", "", f"- 未记录日期：{'、'.join(gaps)}", ""]

    out_path.write_text("\n".join(lines), encoding="utf-8")

    print(f"== {week_tag}（{start:%Y-%m-%d} ~ {end:%Y-%m-%d}）==")
    print(f"  日日志 {len(days)}/{args.days} 篇，判断变化 {len(judgement)} 条，"
          f"任务 {len(tasks)} 个，风险 {len(risks)} 条")
    if gaps:
        print(f"  缺口：{'、'.join(gaps)}")
    print(f"  草稿：{out_path}")
    print("  提醒：一句话结论与下周里程碑需人工补，其余为机械汇总。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
