#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""自测：正常日志应通过，错误日志应报出指定问题。

用法：python tests/selftest.py
"""

import subprocess
import sys
from pathlib import Path

for stream in (sys.stdout, sys.stderr):
    try:
        stream.reconfigure(encoding="utf-8")
    except Exception:
        pass

HERE = Path(__file__).resolve().parent
SKILL = HERE.parent
FIXTURE = HERE / "fixture"

CASES = [
    {
        "name": "正常日志",
        "log": FIXTURE / "devlog" / "daily" / "2026-11-11.md",
        "expect_exit": 0,
        "expect_text": ["0 个 ERROR"],
    },
    {
        "name": "错误日志",
        "log": FIXTURE / "bad" / "2026-11-12.md",
        "expect_exit": 1,
        "expect_text": ["缺少必需章节「## 判断变化」", "未登记的 B-ID：B-9999",
                        "链接目标不存在", "绝对路径", "不在词表"],
    },
]


def run(case):
    proc = subprocess.run(
        [sys.executable, str(SKILL / "scripts" / "check_log.py"),
         str(case["log"]), "--root", str(FIXTURE)],
        capture_output=True, text=True, encoding="utf-8", errors="replace")
    out = proc.stdout + proc.stderr
    ok = proc.returncode == case["expect_exit"]
    missing = [t for t in case["expect_text"] if t not in out]
    return ok and not missing, proc.returncode, missing, out


def main():
    failed = 0
    for case in CASES:
        ok, code, missing, out = run(case)
        if ok:
            print(f"[PASS] {case['name']}（退出码 {code}）")
        else:
            failed += 1
            print(f"[FAIL] {case['name']}（退出码 {code}，期望 {case['expect_exit']}）")
            for m in missing:
                print(f"       未出现预期信息：{m}")
            print(out)

    ev = subprocess.run(
        [sys.executable, str(SKILL / "scripts" / "collect_evidence.py"),
         "--date", "2026-11-11", "--root", str(FIXTURE),
         "--json-out", str(HERE / "_tmp_evidence.json")],
        capture_output=True, text=True, encoding="utf-8", errors="replace")
    if ev.returncode == 0 and (HERE / "_tmp_evidence.json").exists():
        print("[PASS] 证据收集（夹具）")
        (HERE / "_tmp_evidence.json").unlink()
    else:
        failed += 1
        print("[FAIL] 证据收集（夹具）")
        print(ev.stdout + ev.stderr)

    wk = subprocess.run(
        [sys.executable, str(SKILL / "scripts" / "weekly.py"),
         "--end", "2026-11-11", "--root", str(FIXTURE)],
        capture_output=True, text=True, encoding="utf-8", errors="replace")
    out = (FIXTURE / "devlog" / "weekly" / "2026-W46.md")
    if wk.returncode == 0 and out.exists():
        content = out.read_text(encoding="utf-8")
        checks = ["## **判断变化", "## **任务**", "## **下周第一个里程碑**", "未记录日期"]
        missing = [c for c in checks if c not in content]
        if missing:
            failed += 1
            print(f"[FAIL] 周报汇总，缺少：{'、'.join(missing)}")
        else:
            print("[PASS] 周报汇总")
    else:
        failed += 1
        print("[FAIL] 周报汇总")
        print(wk.stdout + wk.stderr)

    idx = subprocess.run(
        [sys.executable, str(SKILL / "scripts" / "index_logs.py"), "--root", str(FIXTURE)],
        capture_output=True, text=True, encoding="utf-8", errors="replace")
    idx_file = FIXTURE / "devlog" / "INDEX.md"
    if idx.returncode == 0 and idx_file.exists():
        content = idx_file.read_text(encoding="utf-8")
        checks = ["## 2026-11", "## 2025-12", "2025/2025-12-30.md", "命名异常", "old-format-log.md"]
        missing = [c for c in checks if c not in content]
        if missing:
            failed += 1
            print(f"[FAIL] 日志索引，缺少：{'、'.join(missing)}")
        else:
            print("[PASS] 日志索引（含跨年分层与命名异常）")
    else:
        failed += 1
        print("[FAIL] 日志索引")
        print(idx.stdout + idx.stderr)

    sys.path.insert(0, str(HERE))
    import regress
    for name, ok, detail in regress.run_all():
        if ok:
            print(f"[PASS] {name}")
        else:
            failed += 1
            print(f"[FAIL] {name}")
            print(detail)

    print(f"\n{'全部通过' if not failed else f'{failed} 项失败'}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
