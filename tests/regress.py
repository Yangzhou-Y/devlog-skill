# -*- coding: utf-8 -*-
"""回归用例：每条对应一个真实出过问题的场景。由 selftest.py 调用。"""

import re
import shutil
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
SCRIPTS = HERE.parent / "scripts"
FIXTURE = HERE / "fixture"
LINK = re.compile(r"(?<!!)\[[^\]]*\]\(([^)\s]+)\)")


def run(script, *args, cwd=None):
    proc = subprocess.run(
        [sys.executable, str(SCRIPTS / script), *map(str, args)],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
        cwd=cwd)
    return proc.returncode, proc.stdout + proc.stderr


def fresh_project(tmp, layout="devlog"):
    """把夹具复制成临时项目；layout=docs 时放进 docs/devlog（错误布局）。"""
    root = Path(tmp) / "proj"
    root.mkdir()
    (root / "README.md").write_text("# demo\n", encoding="utf-8")
    shutil.copytree(FIXTURE / "build", root / "build")
    dest = root / "docs" / "devlog" if layout == "docs" else root / "devlog"
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(FIXTURE / "devlog", dest,
                    ignore=shutil.ignore_patterns("INDEX.md", "weekly"))
    return root


def case_index_links(tmp):
    """索引里的每个链接都必须能打开（曾经漏了 daily/ 前缀）。"""
    root = fresh_project(tmp)
    code, out = run("index_logs.py", "--root", root)
    index = root / "devlog" / "INDEX.md"
    if code != 0 or not index.exists():
        return False, out
    targets = LINK.findall(index.read_text(encoding="utf-8"))
    broken = [t for t in targets if not (index.parent / t).exists()]
    if len(targets) < 4 or broken:
        return False, f"链接 {len(targets)} 个，失效：{broken}"
    return True, ""


def case_weak_evidence(tmp):
    """“证据：无”的通过结论必须报错；写“待补”则允许（曾经 0 错误放行）。"""
    root = fresh_project(tmp)
    weak = (FIXTURE / "bad" / "weak-evidence.md").read_text(encoding="utf-8")
    log = root / "devlog" / "daily" / "2026-11-13.md"
    log.write_text(weak, encoding="utf-8")
    code, out = run("check_log.py", log, "--root", root)
    if code != 1 or "「证据」为空或写成「无」" not in out:
        return False, f"弱证据没有被拦住：exit={code}\n{out}"
    log.write_text(weak.replace("**证据** 无", "**证据** 待补"), encoding="utf-8")
    code, out = run("check_log.py", log, "--root", root)
    if code != 0:
        return False, f"明写“待补”不应报错：exit={code}\n{out}"
    return True, ""


def case_misplaced(tmp):
    """日志目录被放进 docs/ 时必须明确报错，并给出迁移办法。"""
    root = fresh_project(tmp, layout="docs")
    log = root / "docs" / "devlog" / "daily" / "2026-11-11.md"
    code, out = run("check_log.py", log)
    if code != 1 or "放错了位置" not in out:
        return False, f"校验没有报放错位置：exit={code}\n{out}"
    code, out = run("index_logs.py", cwd=log.parent)
    if code != 2 or "放错了位置" not in out:
        return False, f"索引没有报放错位置：exit={code}\n{out}"
    return True, ""


RELINK_LOG = """---
date: 2026-11-14
period: "10:00–12:00"
builds: [B-0001]
commits: []
sessions: []
tasks_added: []
tasks_closed: []
---

# 2026-11-14 · 链接测试

## 0. 判断变化

- 无。

## 1. 采集链路（阶段：仿真通过）

- **结果** 判据：时序达标｜结果：WNS +0.905 ns 通过 [仿真]
- **证据** B-0001 · `build/timing.rpt` · `build/missing.rpt`
- **复现** `bash tests/run_sim.sh`

## 明早第一件事

```bash
echo `build/timing.rpt`
```
"""


def case_relink(tmp):
    """证据路径可点击；归档进年份目录后能修复；重复运行不再改动。"""
    root = fresh_project(tmp)
    log = root / "devlog" / "daily" / "2026-11-14.md"
    log.write_text(RELINK_LOG, encoding="utf-8")
    code, out = run("check_log.py", log, "--root", root)
    if "还不是可点击链接" not in out:
        return False, f"未提示链接化：\n{out}"
    run("relink.py", "--root", root)
    text = log.read_text(encoding="utf-8")
    if "[`build/timing.rpt`](../../build/timing.rpt)" not in text:
        return False, f"没有链接化：\n{text}"
    if "`build/missing.rpt`" not in text or "[`build/missing" in text:
        return False, "不存在的路径不应被链接化"
    if "echo `build/timing.rpt`" not in text:
        return False, "代码围栏内不应被改动"
    _, out = run("relink.py", "--root", root)
    if "已处理 0 个文件" not in out:
        return False, f"重复运行应无改动：\n{out}"
    moved = log.parent / "2025" / "2026-11-14.md"
    moved.parent.mkdir(exist_ok=True)
    shutil.move(str(log), str(moved))
    _, out = run("check_log.py", moved, "--root", root)
    if "已失效" not in out:
        return False, f"归档后应提示链接失效：\n{out}"
    run("relink.py", "--root", root)
    if "](../../../build/timing.rpt)" not in moved.read_text(encoding="utf-8"):
        return False, "归档后链接没有被修复"
    return True, ""


CASES = [
    ("索引链接全部可打开", case_index_links),
    ("弱证据被拦住、待补可放行", case_weak_evidence),
    ("docs/devlog 放错位置会报错", case_misplaced),
    ("证据链接化与归档后修复", case_relink),
]


def run_all():
    import tempfile
    results = []
    for name, fn in CASES:
        with tempfile.TemporaryDirectory() as tmp:
            ok, detail = fn(tmp)
        results.append((name, ok, detail))
    return results
