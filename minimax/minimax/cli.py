"""命令行入口。"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys

from minimax.context_builder import build_context
from minimax.db import Catalog
from minimax.minimax_client import apply_change
from minimax.paths import BEFORE_TASKS, DATA, RECORDS, ROOT, SPEC_PATH, TASKS_PATH, task_text
from minimax.state import load_state


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="SDD 上下文模块")
    parser.add_argument("command", choices=("init", "context", "state-show", "test", "apply", "reset", "check"))
    parser.add_argument("--task", default="")
    args = parser.parse_args(argv)
    if args.command == "init":
        return _init()
    if args.command == "context":
        print(build_context(args.task or task_text()), end="")
        return 0
    if args.command == "state-show":
        print(load_state())
        return 0
    if args.command == "test":
        return _run_tests("manual")
    if args.command == "apply":
        apply_change(build_context(args.task or task_text()))
        print(f"已写回 {TASKS_PATH}")
        return 0
    if args.command == "reset":
        _reset_workspace()
        print("已重置")
        return 0
    from minimax.check import run_check

    return run_check()


def _init() -> int:
    with Catalog() as catalog:
        imported = catalog.import_materials()
    print(f"已导入 {len(imported)} 条资料到 seekdb")
    return 0


def _reset_workspace() -> None:
    if DATA.exists():
        shutil.rmtree(DATA)
    TASKS_PATH.write_text(BEFORE_TASKS.read_text(encoding="utf-8"), encoding="utf-8")


def _run_tests(label: str) -> int:
    """分别跑功能测试和回归测试，并把命令、退出码写进记录。"""

    RECORDS.mkdir(parents=True, exist_ok=True)
    chunks = [f"label: {label}"]
    exit_code = 0
    for module in ("sample_app.tests.test_filter", "sample_app.tests.test_sort"):
        command = [sys.executable, "-m", "unittest", module]
        completed = subprocess.run(command, cwd=ROOT, capture_output=True, text=True, check=False)
        chunks.append(f"$ {' '.join(command)}")
        chunks.append(f"exit_code: {completed.returncode}")
        chunks.append(completed.stdout)
        chunks.append(completed.stderr)
        if completed.returncode != 0:
            exit_code = completed.returncode
    (RECORDS / f"test_{label}.log").write_text("\n".join(chunks), encoding="utf-8")
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
