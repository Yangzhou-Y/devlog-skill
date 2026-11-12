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

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _common import (CODE_SPAN_RE, LINK_RE, body_lines, find_root,  # noqa: E402
                     is_external, is_link_label, linkable_path,
                     misplaced_devlog, parse_meta, resolve_target)

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
    """日志必须放在项目根的 devlog/daily/ 下，层级不超过 devlog/daily/YYYY/MM/。"""
    if misplaced_devlog(root):
        rep.error("日志目录放错了位置：docs/devlog/ 应位于项目根的 devlog/，"
                  "不要放进 docs/。迁移：mv docs/devlog devlog，再运行 python scripts/relink.py")
        return
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


def looks_like_path(label):
    """链接文字是否只是一个路径（去掉反引号后含 / 或以文件扩展名结尾，且没有空格）。"""
    s = label.strip().strip("`").strip()
    if not s or any(c.isspace() for c in s):
        return False
    return "/" in s or bool(re.search(r"\.\w{1,6}$", s))


def check_links(text, root, log_path, cfg, rep):
    evidence_dirs = tuple(cfg.get("evidence_dirs") or DEFAULT_EVIDENCE_DIRS)
    base = log_path.parent
    stale = unlinked = path_label = 0
    for _, line, skip in body_lines(text):
        if skip:
            continue
        for m in LINK_RE.finditer(line):
            target = m.group(2)
            if is_external(target) or not target.split("#", 1)[0]:
                continue
            if looks_like_path(m.group(1)):
                path_label += 1
            dest, by_root = resolve_target(base, root, target)
            if dest is None:
                rep.error(f"链接目标不存在：{target}")
                continue
            if by_root:
                stale += 1
                continue
            try:
                rel = dest.resolve().relative_to(root).as_posix()
            except ValueError:
                rep.error(f"链接指向项目外：{target}")
                continue
            if is_gitignored(root, rel):
                if not rel.startswith(evidence_dirs):
                    rep.warn(f"链接指向被 .gitignore 忽略的文件：{target}")
                elif not ID_RE["B"].search(line):
                    rep.warn(f"链接指向会被清理的证据目录，请在同一行写 build id：{target}")
        for m in CODE_SPAN_RE.finditer(line):
            token = m.group(1)
            if is_link_label(line, m) or any(c.isspace() for c in token):
                continue
            if linkable_path(token, root):
                unlinked += 1
    if stale:
        rep.warn(f"{stale} 个链接按当前位置已失效，运行 python scripts/relink.py 修复")
    if unlinked:
        rep.warn(f"{unlinked} 处证据路径是裸写的，请写成 [简要说明](路径)，让读者不点开也知道是什么")
    if path_label:
        rep.warn(f"{path_label} 个链接的文字本身就是路径，请改成简要说明，如 [DDR3 位流复测日志](路径)")


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


FIELD_RE = re.compile(r"\*\*(目标|做了什么|结果|证据|复现|遗留)\*\*")
PASS_RE = re.compile(r"(通过|一致|成功|达标|符合|满足|匹配)")
# 普通条目里的结论：只认出现在分句末尾、标点或口径标签之前的词，
# 以免把介词“通过 JTAG 下载”当成结论。
STRICT_PASS_RE = re.compile(
    r"(?:通过|一致|成功|达标|匹配|符合预期|满足要求)(?=\s*(?:[，。；;,.\[（(]|$))")
EMPTY_VALUES = {"无", "—", "-", "暂无", "没有", "略", "同上", "n/a", "na", "不适用"}


def section_fields(body):
    """取出小节里的 **字段** 与值；每个字段只取所在行、到下一个字段标记之前。"""
    fields = {}
    for line in body.split("\n"):
        marks = list(FIELD_RE.finditer(line))
        for k, m in enumerate(marks):
            end = marks[k + 1].start() if k + 1 < len(marks) else len(line)
            fields[m.group(1)] = line[m.end():end].strip(" ：:\t")
    return fields


def is_empty_value(value):
    v = value.strip().rstrip("。.;；,，").strip().lower()
    return v == "" or v in EMPTY_VALUES


def claims_pass(value):
    """文字里是否出现未被否定的“通过/一致/成功…”。"""
    for m in PASS_RE.finditer(value):
        if not re.search(r"(未|不|没有|无法)(能|再|完全)?$", value[:m.start()]):
            return True
    return False


def plain_claim(line):
    """没有 **字段** 标记的普通条目里，是否有未被否定的通过类结论。"""
    s = line.strip()
    if not s.startswith(("-", "*")) or FIELD_RE.search(s):
        return False
    for m in STRICT_PASS_RE.finditer(s):
        if not re.search(r"(未|不|没有|无法)(能|再|完全)?$", s[:m.start()]):
            return True
    return False


def evidence_locatable(value, sessions):
    """证据里是否有能定位的东西：编号、链接、路径、会话，或明写的待补。"""
    if "待补" in value or "会话" in value:
        return True
    if re.search(r"\bB-\d{4}\b", value) or LINK_RE.search(value):
        return True
    if any(s[:8] in value for s in sessions):
        return True
    return any(" " not in t and ("/" in t or re.search(r"\.\w{1,6}$", t))
               for t in CODE_SPAN_RE.findall(value))


def check_verification(text, fm, rep):
    """通过类结论必须带可定位的证据；证据写“无”按错误处理，缺项请明写“待补”。"""
    sessions = re.findall(r"[0-9a-f]{8}-[0-9a-f-]{4,}", fm.get("sessions", ""))
    parts = SECTION_RE.split(text)
    for i in range(1, len(parts) - 1, 2):
        head, body = parts[i], parts[i + 1]
        if not re.match(r"[1-9]", head):
            continue
        name = f"章节「{head}」"
        f = section_fields(body)
        stage = re.search(r"阶段：([^）]+)", head)
        early = bool(stage) and stage.group(1) in {"设计", "已实现"}
        field_claim = "结果" in f and claims_pass(f["结果"])
        bullet_claim = any(plain_claim(ln) for ln in body.splitlines())
        claims = field_claim or bullet_claim
        if bullet_claim and "结果" not in f:
            rep.warn(f"{name}有通过类结论写在普通条目里，请改写进「结果」字段并给出判据")
        if claims:
            ev = f.get("证据")
            if ev is None:
                rep.error(f"{name}声称通过，但没有「证据」字段（缺项请明写『待补』）")
            elif is_empty_value(ev):
                rep.error(f"{name}的「证据」为空或写成「无」，通过结论需要可定位的证据（缺项请写『待补』）")
            elif not evidence_locatable(ev, sessions):
                rep.warn(f"{name}的「证据」没有编号、路径或会话可定位")
            if "结果" in f and "判据" not in f["结果"]:
                rep.warn(f"{name}的「结果」没有写判据（什么算通过）")
        elif not early and "证据" not in f:
            rep.warn(f"{name}没有「证据」字段")
        if claims or not early:
            rv = f.get("复现")
            if rv is None:
                rep.warn(f"{name}没有「复现」字段")
            elif is_empty_value(rv):
                rep.warn(f"{name}的「复现」写成了「无」，请说明原因，如「无（现场操作）」")


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
    fm, body = parse_meta(text)
    if text.startswith("---"):
        rep.warn("元数据用的是 --- frontmatter，不少渲染器会把它显示在页面顶部；"
                 "运行 python scripts/hide_meta.py 改成不可见的注释块")

    date = fm.get("date", "")
    m = re.match(r"(\d{4}-\d{2}-\d{2})", date)
    if not m:
        rep.error("元数据缺少合法的 date: YYYY-MM-DD")
        log_date = None
    else:
        log_date = m.group(1)
        if log_path.stem != log_date:
            rep.error(f"文件名 {log_path.name} 与 date {log_date} 不一致")

    for key in ("period", "builds", "commits", "sessions", "tasks_added", "tasks_closed"):
        if key not in fm:
            rep.warn(f"元数据缺少字段 {key}")

    try:
        shown = log_path.relative_to(root)
    except ValueError:
        shown = log_path
    print(f"校验 {shown}")
    check_location(log_path, root, rep)
    if misplaced_devlog(root):          # 目录都放错了，其余检查只会产生连带噪音
        rep.dump()
        print(f"\n结果：{len(rep.errors)} 个 ERROR，先把目录迁到项目根再校验")
        return 1
    check_sections(body, rep)
    check_ids(body, registry_ids(root), rep)
    check_links(body, root, log_path, cfg, rep)
    check_absolute_paths(body, rep)
    check_stages(body, cfg, rep)
    check_task_table(body, root, cfg, rep)
    check_verification(body, fm, rep)
    check_todo_and_tags(body, rep)
    check_state(root, log_date, cfg, rep)

    rep.dump()
    print(f"\n结果：{len(rep.errors)} 个 ERROR，{len(rep.warns)} 个 WARN")
    return 1 if rep.errors else 0


if __name__ == "__main__":
    sys.exit(main())
