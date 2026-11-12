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
- **证据** B-0001 · [布线时序报告](build/timing.rpt) · 裸写 `build/timing.rpt` · [build/timing.rpt](build/timing.rpt)
- **复现** `bash tests/run_sim.sh`

## 明早第一件事

```bash
echo `build/timing.rpt`
```
"""


def case_relink(tmp):
    """链接要写说明；裸路径与“文字就是路径”各提示一次；搬家后可修复；幂等。"""
    root = fresh_project(tmp)
    log = root / "devlog" / "daily" / "2026-11-14.md"
    log.write_text(RELINK_LOG, encoding="utf-8")

    _, out = run("check_log.py", log, "--root", root)
    if "是裸写的" not in out:
        return False, f"裸写路径未被提示：\n{out}"
    if "链接的文字本身就是路径" not in out:
        return False, f"文字就是路径的链接未被提示：\n{out}"

    # 项目根写法的链接 -> 补成相对本日志的路径；说明文字保持不变
    run("relink.py", "--root", root)
    text = log.read_text(encoding="utf-8")
    if "[布线时序报告](../../build/timing.rpt)" not in text:
        return False, f"层级没有补对：\n{text}"
    if "裸写 `build/timing.rpt`" not in text:
        return False, "默认不应自动包裹裸路径"
    if "echo `build/timing.rpt`" not in text:
        return False, "代码围栏内不应被改动"
    _, out = run("relink.py", "--root", root)
    if "已处理 0 个文件" not in out:
        return False, f"重复运行应无改动：\n{out}"

    # 显式开关才包裹裸路径
    run("relink.py", "--root", root, "--wrap-bare")
    if "[`build/timing.rpt`](../../build/timing.rpt)" not in log.read_text(encoding="utf-8"):
        return False, "--wrap-bare 没有生效"

    # 归档进年份目录后修复
    moved = log.parent / "2025" / "2026-11-14.md"
    moved.parent.mkdir(exist_ok=True)
    shutil.move(str(log), str(moved))
    _, out = run("check_log.py", moved, "--root", root)
    if "已失效" not in out:
        return False, f"归档后应提示链接失效：\n{out}"
    run("relink.py", "--root", root)
    if "[布线时序报告](../../../build/timing.rpt)" not in moved.read_text(encoding="utf-8"):
        return False, "归档后链接没有被修复"
    return True, ""


def case_tidy(tmp):
    """元数据移出正文、标题加粗；移出后校验/周报/索引仍能读到；重复运行无改动。"""
    root = fresh_project(tmp)
    log = root / "devlog" / "daily" / "2026-11-11.md"
    meta = root / "devlog" / ".meta" / "2026-11-11.yml"
    # 夹具是整理后的样子；还原成“元数据写在顶部、标题未加粗”的原始写法
    body = "\n".join(
        ln.replace("**", "") if ln.startswith("#") else ln
        for ln in log.read_text(encoding="utf-8").split("\n"))
    head = meta.read_text(encoding="utf-8")
    log.write_text("<!--\n" + head + "-->\n\n" + body, encoding="utf-8")
    meta.unlink()

    _, out = run("check_log.py", log, "--root", root)
    if "元数据还写在日志顶部" not in out:
        return False, f"内联元数据应被提示：\n{out}"

    run("tidy.py", "--root", root)
    new = log.read_text(encoding="utf-8")
    if new.lstrip().startswith(("<!--", "---")):
        return False, f"元数据仍在日志正文里：\n{new[:160]}"
    if not meta.exists() or "date: 2026-11-11" not in meta.read_text(encoding="utf-8"):
        return False, "元数据没有写进 devlog/.meta/"
    if "## **0. 判断变化" not in new or not new.lstrip().startswith("# **"):
        return False, f"标题没有加粗：\n{new[:200]}"
    if "```bash" in new and "**" in new.split("```bash", 1)[1].split("```", 1)[0]:
        return False, "代码围栏内不应被加粗"

    code, out = run("check_log.py", log, "--root", root)
    if code != 0 or "元数据还写在" in out:
        return False, f"整理后校验应通过且无元数据提示：exit={code}\n{out}"
    _, out = run("tidy.py", "--root", root)
    if "已处理 0 个文件" not in out:
        return False, f"重复运行应无改动：\n{out}"

    code, out = run("weekly.py", "--end", "2026-11-11", "--root", root)
    wk = root / "devlog" / "weekly" / "2026-W46.md"
    if code != 0 or not wk.exists():
        return False, f"周报读不到 .meta 里的元数据：\n{out}"
    if wk.read_text(encoding="utf-8").lstrip().startswith(("<!--", "---")):
        return False, "周报正文不应带元数据"
    code, out = run("index_logs.py", "--root", root)
    index = (root / "devlog" / "INDEX.md").read_text(encoding="utf-8")
    if code != 0 or "**" in index:
        return False, f"索引里不应带加粗标记：\n{index}"
    return True, ""


CASES = [
    ("索引链接全部可打开", case_index_links),
    ("弱证据被拦住、待补可放行", case_weak_evidence),
    ("docs/devlog 放错位置会报错", case_misplaced),
    ("链接写说明、补层级、归档后修复", case_relink),
    ("元数据移出正文、标题加粗", case_tidy),
]


def run_all():
    import tempfile
    results = []
    for name, fn in CASES:
        with tempfile.TemporaryDirectory() as tmp:
            ok, detail = fn(tmp)
        results.append((name, ok, detail))
    return results
