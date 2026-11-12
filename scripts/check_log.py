#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""校验一篇开发日志及其关联状态表。

用法：
    python check_log.py devlog/daily/2026-11-11.md
    python check_log.py devlog/daily/2026-11-11.md --root .

退出码：0 通过（可有 WARN），1 存在 ERROR，2 参数/文件问题。
"""

import argparse
import re
import subprocess
import sys
from pathlib import Path

for stream in (sys.stdout, sys.stderr):
    try:
        stream.reconfigure(encoding="utf-8")
    except Exception:
        pass

DEFAULT_STAGES = ["设计", "已实现", "仿真通过", "实机验证", "联调通过", "已交付"]
DEFAULT_STATES = ["待办", "进行中", "阻塞", "顺延", "完成", "放弃"]
DEFAULT_EVIDENCE_DIRS = [".sim", "build", "out"]

REQUIRED_SECTIONS = ["判断变化", "明早第一件事"]
OPTIONAL_SECTIONS = ["决策", "任务变化", "风险", "待补"]

ID_RE = {
    "B": re.compile(r"\bB-\d{4}\b"),
    "T": re.compile(r"\bT-\d{4}\b"),
    "R": re.compile(r"\bR-\d{4}\b"),
    "D": re.compile(r"\bD-\d{4}\b"),
}
LINK_RE = re.compile(r"\[[^\]]*\]\(([^)\s]+)\)")
ABS_PATH_RE = re.compile(r"(?<![\w/])(?:[A-Za-z]:[\\/]|file://)")
SECTION_RE = re.compile(r"^##\s+(.+?)\s*$", re.M)


class Report:
    def __init__(self):
        self.errors, self.warns, self.notes = [], [], []

    def error(self, msg):
        self.errors.append(msg)

    def warn(self, msg):
        self.warns.append(msg)

    def note(self, msg):
        self.notes.append(msg)

    def dump(self):
        for m in self.notes:
            print(f"  ✓ {m}")
        for m in self.warns:
            print(f"  ! {m}")
        for m in self.errors:
            print(f"  ✗ {m}")


def find_root(start):
    for p in [start] + list(start.parents):
        if (p / "devlog").is_dir() or (p / ".git").is_dir():
            return p
    return start


def parse_frontmatter(text):
    if not text.startswith("---"):
        return {}, text
    end = text.find("\n---", 3)
    if end == -1:
        return {}, text
    fm = {}
    for line in text[3:end].splitlines():
        if ":" in line and not line.startswith((" ", "\t")):
            k, v = line.split(":", 1)
            fm[k.strip()] = v.strip()
    return fm, text[end + 4:]


def load_config(root):
    cfg = {"stages": DEFAULT_STAGES, "task_states": DEFAULT_STATES,
           "evidence_dirs": DEFAULT_EVIDENCE_DIRS, "workflows": []}
    path = root / "devlog" / "config.yml"
    if not path.exists():
        return cfg
    key = None
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.split("#", 1)[0].rstrip()
        if not line.strip():
            continue
        stripped = line.strip()
        if stripped.startswith("- ") and key:
            cfg.setdefault(key, [])
            if isinstance(cfg[key], list):
                cfg[key].append(stripped[2:].strip())
        elif ":" in line and not line.startswith((" ", "\t")):
            key, val = line.split(":", 1)
            key = key.strip()
            if val.strip():
                cfg[key] = val.strip()
            else:
                cfg.setdefault(key, [])
    return cfg


def registry_ids(root):
    ids = {k: set() for k in ID_RE}
    for name, key in (("TASKS.md", "T"), ("RISKS.md", "R"),
                      ("DECISIONS.md", "D"), ("BUILDS.md", "B")):
        f = root / "devlog" / name
        if f.exists():
            ids[key] |= set(ID_RE[key].findall(f.read_text(encoding="utf-8")))
    return ids


def task_rows(text):
    rows = {}
    for line in text.splitlines():
        if not line.startswith("|"):
            continue
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if len(cells) >= 3 and re.fullmatch(r"T-\d{4}", cells[0]):
            rows[cells[0]] = {"text": cells[1], "state": cells[2]}
    return rows


def is_gitignored(root, relpath):
    try:
        out = subprocess.run(["git", "-C", str(root), "check-ignore", "-q", relpath],
                             capture_output=True)
        return out.returncode == 0
    except FileNotFoundError:
        return False


def check_location(log_path, root, rep):
    """日志必须放在 devlog/daily/ 下，层级不超过 devlog/daily/YYYY/MM/。"""
    try:
        rel = log_path.relative_to(root)
    except ValueError:
        rep.warn(f"日志不在项目目录内：{log_path}")
        return
    parts = rel.parts
    if len(parts) < 3 or parts[0] != "devlog" or parts[1] != "daily":
        rep.warn(f"日志不在 devlog/daily/ 下：{rel.as_posix()}")
    elif len(parts) - 3 > 2:
        rep.warn(f"日志目录层级过深：{rel.as_posix()}，建议 devlog/daily/YYYY/MM/")


def check_sections(text, rep):
    heads = SECTION_RE.findall(text)
    joined = " | ".join(heads)
    for need in REQUIRED_SECTIONS:
        if need not in joined:
            rep.error(f"缺少必需章节「## {need}」")
    for head in heads:
        rep.note(f"章节：{head}")


def check_ids(text, ids, rep):
    for key, pattern in ID_RE.items():
        used = set(pattern.findall(text))
        unknown = sorted(used - ids[key])
        if unknown:
            rep.error(f"引用了未登记的 {key}-ID：{', '.join(unknown)}")
        elif used:
            rep.note(f"{key}-ID 均已登记：{', '.join(sorted(used))}")


def check_links(text, root, log_path, cfg, rep):
    evidence_dirs = tuple(cfg.get("evidence_dirs") or DEFAULT_EVIDENCE_DIRS)
    for target in LINK_RE.findall(text):
        if target.startswith(("http://", "https://", "mailto:", "#")):
            continue
        clean = target.split("#", 1)[0]
        if not clean:
            continue
        resolved = (log_path.parent / clean).resolve()
        try:
            rel = resolved.relative_to(root).as_posix()
        except ValueError:
            rep.error(f"链接指向项目外：{target}")
            continue
        if not resolved.exists():
            rep.error(f"链接目标不存在：{target}")
            continue
        if is_gitignored(root, rel):
            if rel.startswith(evidence_dirs):
                rep.warn(f"链接指向被忽略的证据目录（需同时提供 build id）：{target}")
            else:
                rep.warn(f"链接指向被 .gitignore 忽略的文件：{target}")


def check_absolute_paths(text, rep):
    hits = ABS_PATH_RE.findall(text)
    if hits:
        rep.error(f"出现绝对路径 {len(hits)} 处，应改为项目内相对路径或外部资源+版本号")


def check_stages(text, cfg, rep):
    stages = set(cfg.get("stages") or DEFAULT_STAGES)
    found = re.findall(r"（阶段：([^）]+)）", text) + re.findall(r"阶段：([^，。\s）]+)", text)
    for s in dict.fromkeys(found):
        if s not in stages:
            rep.error(f"阶段「{s}」不在词表：{'、'.join(sorted(stages))}")


def check_task_table(text, root, cfg, rep):
    states = set(cfg.get("task_states") or DEFAULT_STATES)
    rows = task_rows(text)
    for tid, row in rows.items():
        if row["state"] not in states:
            rep.error(f"{tid} 状态「{row['state']}」不在词表：{'、'.join(sorted(states))}")
    registry = root / "devlog" / "TASKS.md"
    if registry.exists() and rows:
        master = task_rows(registry.read_text(encoding="utf-8"))
        for tid, row in rows.items():
            if tid not in master:
                rep.error(f"{tid} 未出现在 devlog/TASKS.md")
            elif master[tid]["state"] != row["state"]:
                rep.warn(f"{tid} 日志中的状态「{row['state']}」与 TASKS.md 的「{master[tid]['state']}」不一致")


def check_evidence_fields(text, rep):
    sections = re.split(SECTION_RE, text)
    # re.split with one group yields [pre, head1, body1, head2, body2, ...]
    early = {"设计", "已实现"}
    for i in range(1, len(sections) - 1, 2):
        head, body = sections[i], sections[i + 1]
        if not re.match(r"[1-9]", head):
            continue
        m = re.search(r"阶段：([^）]+)", head)
        if m and m.group(1) in early:
            continue          # 还在设计/实现阶段，不要求验证证据
        if "证据" not in body:
            rep.warn(f"章节「{head}」没有「证据」字段")
        if "复现" not in body:
            rep.warn(f"章节「{head}」没有「复现」字段")


def check_state(root, log_date, cfg, rep):
    state = root / "devlog" / "STATE.md"
    if not state.exists():
        rep.warn("devlog/STATE.md 不存在，状态表未同步")
        return
    text = state.read_text(encoding="utf-8")
    stages = set(cfg.get("stages") or DEFAULT_STAGES)
    m = re.search(r"最近更新：\s*(\d{4}-\d{2}-\d{2})", text)
    if m and log_date and m.group(1) < log_date:
        rep.warn(f"STATE.md 最近更新 {m.group(1)} 早于日志日期 {log_date}")
    for line in text.splitlines():
        if not line.startswith("|"):
            continue
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if len(cells) >= 2 and cells[1] and cells[0] not in ("工作流", "---") and not set(cells[0]) <= {"-", ":"}:
            if cells[1] not in stages:
                rep.error(f"STATE.md 工作流「{cells[0]}」的阶段「{cells[1]}」不在词表")


def check_todo_and_tags(text, rep):
    n = text.count("待补")
    if n > 5:
        rep.warn(f"「待补」出现 {n} 次，当天记录完整度偏低")
    untagged = 0
    for line in text.splitlines():
        if not line.strip().startswith(("-", "*")):
            continue
        if "做了什么" in line or "原以为" in line or "此前" in line:
            continue          # 动作描述与旧前提，不是今天的结论
        if re.search(r"(通过|一致)", line) and not re.search(r"\[(实测|仿真|模型)\]|证据|复现|判据", line):
            untagged += 1
    if untagged:
        rep.warn(f"{untagged} 条结论性表述没有口径标签或证据指向")


def main():
    ap = argparse.ArgumentParser(description="校验开发日志")
    ap.add_argument("log", help="日志文件路径")
    ap.add_argument("--root", help="项目根目录，默认自动向上查找 devlog/ 或 .git/")
    args = ap.parse_args()

    log_path = Path(args.log).resolve()
    if not log_path.exists():
        print(f"[错误] 找不到日志：{log_path}", file=sys.stderr)
        return 2
    root = Path(args.root).resolve() if args.root else find_root(log_path.parent)
    cfg = load_config(root)
    text = log_path.read_text(encoding="utf-8")

    rep = Report()
    fm, body = parse_frontmatter(text)

    date = fm.get("date", "")
    m = re.match(r"(\d{4}-\d{2}-\d{2})", date)
    if not m:
        rep.error("frontmatter 缺少合法的 date: YYYY-MM-DD")
        log_date = None
    else:
        log_date = m.group(1)
        if log_path.stem != log_date:
            rep.error(f"文件名 {log_path.name} 与 date {log_date} 不一致")

    for key in ("period", "builds", "commits", "sessions", "tasks_added", "tasks_closed"):
        if key not in fm:
            rep.warn(f"frontmatter 缺少字段 {key}")

    try:
        shown = log_path.relative_to(root)
    except ValueError:
        shown = log_path
    print(f"校验 {shown}")
    check_location(log_path, root, rep)
    check_sections(body, rep)
    check_ids(body, registry_ids(root), rep)
    check_links(body, root, log_path, cfg, rep)
    check_absolute_paths(body, rep)
    check_stages(body, cfg, rep)
    check_task_table(body, root, cfg, rep)
    check_evidence_fields(body, rep)
    check_todo_and_tags(body, rep)
    check_state(root, log_date, cfg, rep)

    rep.dump()
    print(f"\n结果：{len(rep.errors)} 个 ERROR，{len(rep.warns)} 个 WARN")
    return 1 if rep.errors else 0


if __name__ == "__main__":
    sys.exit(main())
