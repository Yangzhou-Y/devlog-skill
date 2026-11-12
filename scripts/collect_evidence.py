#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""收集某一天的工程证据，供开发日志引用。

只读：不修改项目里的任何文件（除 devlog/.evidence/ 下的证据快照）。
可在任意目录运行；Windows / Linux / macOS 均可。

用法：
    python collect_evidence.py --date 2026-11-11
    python collect_evidence.py --date 2026-11-11 --root C:/path/to/project
"""

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
from datetime import datetime, timedelta
from pathlib import Path

for stream in (sys.stdout, sys.stderr):
    try:
        stream.reconfigure(encoding="utf-8")
    except Exception:
        pass

SKIP_DIRS = {".git", "node_modules", "__pycache__", ".venv", "venv", ".devlog",
             ".idea", ".vscode", "TempData", ".Xil", "xsim.dir"}
SKIP_SUFFIXES = (".cache", ".runs", ".hw", ".gen", ".ip_user_files")

GROUP_DIRS = ["rtl", "tests", "board", "build", "docs", ".sim"]
SKIP_DIRS.update({"devlog"})

ARTIFACT_TYPES = {
    ".bit": "位流", ".dcp": "位流",
    ".bin": "数据集", ".mem": "数据集", ".npz": "数据集", ".csv": "数据集",
    ".rpt": "时序报告", ".log": "仿真日志",
    ".png": "图件", ".svg": "图件",
    ".vvp": "脚本产物",
}

HASH_EXTS = {".bit", ".dcp", ".bin"}

TEXT_REPORTS = {".rpt", ".log", ".txt"}


def sha256_of(path, chunk=1 << 20):
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for block in iter(lambda: fh.read(chunk), b""):
            h.update(block)
    return h.hexdigest()


def iter_files(root):
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames
                       if d not in SKIP_DIRS and not d.lower().endswith(SKIP_SUFFIXES)]
        if any(name.lower().endswith(".xpr") for name in filenames):
            dirnames[:] = []          # Vivado 工程树：只记 .xpr，不展开内部
        for name in filenames:
            yield Path(dirpath) / name


def group_of(rel):
    first = rel.parts[0] if rel.parts else ""
    return first if first in GROUP_DIRS else "其他"


def _is_float(token):
    try:
        float(token)
        return True
    except ValueError:
        return False


def read_metrics(path):
    """抽取时序余量。

    - report_timing_summary 的表格：取表头后第一行数值行，这是签核数值
    - 布线日志的 "Intermediate / Estimated Timing Summary"：取最后一条，这是过程值
    两者数值可能不同（中途 WHS 可以是负的），所以必须标明来源。
    """
    try:
        text = path.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return {}
    metrics = {}
    lines = text.splitlines()

    # 1) 签核表格
    for i, line in enumerate(lines):
        if "WNS(ns)" in line and "WHS(ns)" in line:
            for row in lines[i + 2:i + 6]:
                toks = row.split()
                if len(toks) >= 6 and _is_float(toks[0]) and _is_float(toks[4]):
                    metrics.update(WNS=toks[0], WHS=toks[4], source="报告表格")
                    break
            if metrics:
                break

    # 2) 过程日志：取最后一条 "WNS= ... WHS= ..."
    if not metrics:
        hits = [l for l in lines if re.search(r"WNS\s*=", l) and re.search(r"WHS\s*=", l)]
        if hits:
            last = hits[-1]
            wns = re.search(r"WNS\s*=\s*(-?\d+\.\d+)", last)
            whs = re.search(r"WHS\s*=\s*(-?\d+\.\d+)", last)
            if wns and whs:
                metrics.update(WNS=wns.group(1), WHS=whs.group(1), source="过程日志（最终一条）")

    if "Timing constraints are not met" in text:
        metrics["timing_met"] = False
    elif "All user specified timing constraints are met" in text:
        metrics["timing_met"] = True
    for word in ("PASS", "FAIL"):
        if re.search(rf"\b{word}\b", text):
            metrics.setdefault("flags", []).append(word)
    return metrics


def git(root, *args):
    try:
        out = subprocess.run(["git", "-C", str(root), *args],
                             capture_output=True, text=True,
                             encoding="utf-8", errors="replace")
    except FileNotFoundError:
        return ""
    return out.stdout.strip() if out.returncode == 0 else ""


def main():
    ap = argparse.ArgumentParser(description="收集某一天的工程证据")
    ap.add_argument("--date", help="YYYY-MM-DD，默认今天")
    ap.add_argument("--root", default=".", help="项目根目录，默认当前目录")
    ap.add_argument("--json-out", help="证据快照输出路径")
    args = ap.parse_args()

    root = Path(args.root).resolve()
    if not (root / "README.md").exists() and not (root / "devlog").exists():
        print(f"[错误] {root} 不像项目根：既没有 README.md 也没有 devlog/", file=sys.stderr)
        return 2

    day = datetime.strptime(args.date, "%Y-%m-%d") if args.date else datetime.now()
    start = day.replace(hour=0, minute=0, second=0, microsecond=0)
    end = start + timedelta(days=1)
    ts_start, ts_end = start.timestamp(), end.timestamp()

    changes, artifacts, reports = {}, [], []
    warnings = []
    total_seen = 0

    for path in iter_files(root):
        try:
            st = path.stat()
        except OSError:
            continue
        if not (ts_start <= st.st_mtime < ts_end):
            continue
        rel = path.relative_to(root)
        total_seen += 1
        group = group_of(rel)
        entry = {
            "path": rel.as_posix(),
            "time": datetime.fromtimestamp(st.st_mtime).strftime("%H:%M"),
            "size_kb": round(st.st_size / 1024, 1),
        }
        changes.setdefault(group, []).append(entry)

        ext = path.suffix.lower()
        if ext in ARTIFACT_TYPES and ext in {".bit", ".dcp", ".bin", ".rpt", ".png", ".csv"}:
            item = dict(entry)
            item["type"] = ARTIFACT_TYPES[ext]
            if ext in HASH_EXTS:
                item["sha256"] = sha256_of(path)
            artifacts.append(item)
        if ext in TEXT_REPORTS and st.st_size < 8 * 1024 * 1024:
            metrics = read_metrics(path)
            if metrics:
                reports.append({"path": rel.as_posix(), **metrics})

    for group in changes:
        changes[group].sort(key=lambda e: e["time"])

    commits = []
    total_commits = 0
    dirty = 0
    if (root / ".git").exists():
        total_commits = int(git(root, "rev-list", "--count", "HEAD") or 0)
        if total_commits:
            raw = git(root, "log", f"--since={start:%Y-%m-%d %H:%M}",
                      f"--until={end:%Y-%m-%d %H:%M}",
                      "--pretty=%h|%ad|%s", "--date=format:%H:%M")
            commits = [dict(zip(("hash", "time", "subject"), line.split("|", 2)))
                       for line in raw.splitlines() if line.count("|") >= 2]
        dirty = len([l for l in git(root, "status", "--porcelain").splitlines() if l.strip()])
    else:
        warnings.append("项目不是 git 仓库：代码无法用 commit 锚定")

    if total_commits == 0:
        warnings.append("仓库尚无提交：版本锚点只能靠 devlog/BUILDS.md 的 build id")

    if not artifacts:
        warnings.append("当天没有新的位流/报告/图件：若确有产出，检查是否写到了别的目录")

    result = {
        "date": day.strftime("%Y-%m-%d"),
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "root": str(root),
        "changed_file_count": total_seen,
        "changes": changes,
        "artifacts": sorted(artifacts, key=lambda e: e["time"]),
        "reports": reports,
        "git": {"total_commits": total_commits, "commits": commits, "dirty_files": dirty},
        "warnings": warnings,
    }

    out = Path(args.json_out) if args.json_out else root / "devlog" / ".evidence" / f"evidence-{result['date']}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"== {result['date']} 证据清单（{total_seen} 个文件变动）==")
    for group in GROUP_DIRS + ["其他"]:
        items = changes.get(group)
        if not items:
            continue
        names = "、".join(i["path"] for i in items[:4])
        more = f" 等 {len(items)} 个" if len(items) > 4 else ""
        print(f"  {group:<6} {names}{more}")
    if artifacts:
        print("-- 新产物 --")
        for a in artifacts:
            line = f"  [{a['type']}] {a['path']}  {a['time']}  {a['size_kb']} KB"
            if "sha256" in a:
                line += f"  sha256={a['sha256'][:16]}…"
            print(line)
    if reports:
        print("-- 报告指标 --")
        for r in reports:
            bits = [f"{k}={v}" for k, v in r.items() if k != "path"]
            print(f"  {r['path']}: {' '.join(bits)}")
    print(f"-- git -- 提交 {total_commits} 个，当天 {len(commits)} 个，未提交改动 {dirty} 个文件")
    for w in warnings:
        print(f"[提示] {w}")
    print(f"\n快照：{out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
