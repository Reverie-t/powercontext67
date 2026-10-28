"""从空目录跑一遍：改前失败、查库、改规格、重启后读状态。"""

from __future__ import annotations

import difflib
import shutil
import subprocess
import sys

from minimax.cli import _init, _reset_workspace, _run_tests
from minimax.context_builder import build_context
from minimax.paths import (
    BEFORE_TASKS,
    RECORDS,
    ROOT,
    SPEC_PATH,
    SPEC_TOKEN,
    TASKS_PATH,
    UPDATED_SPEC_TOKEN,
    task_text,
)
from minimax.state import save_state


def run_check() -> int:
    original_spec = SPEC_PATH.read_text(encoding="utf-8")
    _reset_workspace()
    if RECORDS.exists():
        shutil.rmtree(RECORDS)
    RECORDS.mkdir(parents=True)
    try:
        _require_before_tests()
        _init()
        first = build_context(task_text())
        _require_sources(first, SPEC_TOKEN)
        marker = "pc-restart-7f3a"
        save_state(
            {
                "task": task_text(),
                "done": ["已导入规格、代码和测试"],
                "todo": ["实现 filter_tasks"],
                "verification": {"filter": "failed", "sort": "passed", "marker": marker},
            }
        )
        restarted = _restart_context()
        if marker not in restarted:
            raise SystemExit("重启后的上下文没有读到 PowerContext 里的验证记号")
        if "实现 filter_tasks" not in restarted:
            raise SystemExit("重启后的上下文没有用已保存的待办")
        SPEC_PATH.write_text(original_spec.replace(SPEC_TOKEN, UPDATED_SPEC_TOKEN), encoding="utf-8")
        _init()
        updated = build_context(task_text())
        (RECORDS / "context_after_spec_update.txt").write_text(updated, encoding="utf-8")
        if UPDATED_SPEC_TOKEN not in updated or SPEC_TOKEN in updated:
            raise SystemExit("规格更新并重新导入后，上下文仍是旧内容")
        _report_minimax(updated)
    finally:
        SPEC_PATH.write_text(original_spec, encoding="utf-8")
        _init()
    print("本地检查通过：改前失败、seekdb 查询、规格更新、状态重启后复用")
    return 0


def _require_before_tests() -> None:
    filter_log = _one_test("sample_app.tests.test_filter")
    sort_log = _one_test("sample_app.tests.test_sort")
    (RECORDS / "test_before.log").write_text(filter_log + "\n" + sort_log, encoding="utf-8")
    if "NotImplementedError" not in filter_log or _exit_line(filter_log) == "exit_code: 0":
        raise SystemExit("功能测试应该因为 filter_tasks 还没实现而失败")
    if _exit_line(sort_log) != "exit_code: 0":
        raise SystemExit("回归测试在修改前应该通过")


def _one_test(module: str) -> str:
    command = [sys.executable, "-m", "unittest", module]
    completed = subprocess.run(command, cwd=ROOT, capture_output=True, text=True, check=False)
    return "\n".join(
        [
            f"$ {' '.join(command)}",
            f"exit_code: {completed.returncode}",
            completed.stdout,
            completed.stderr,
        ]
    )


def _exit_line(log: str) -> str:
    for line in log.splitlines():
        if line.startswith("exit_code:"):
            return line
    return ""


def _require_sources(context: str, spec_token: str) -> None:
    required = (
        "sample_app/spec.md",
        "sample_app/tasks.py",
        "filter_tasks",
        "sample_app/tests/test_filter.py",
        "sample_app/tests/test_sort.py",
        spec_token,
    )
    missing = [item for item in required if item not in context]
    if missing:
        raise SystemExit("上下文缺少来源: " + ", ".join(missing))


def _restart_context() -> str:
    completed = subprocess.run(
        [sys.executable, "-m", "minimax", "context"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    if completed.returncode != 0:
        raise SystemExit(completed.stderr or completed.stdout)
    (RECORDS / "context_after_restart.txt").write_text(completed.stdout, encoding="utf-8")
    return completed.stdout


def _write_diff() -> None:
    before = BEFORE_TASKS.read_text(encoding="utf-8").splitlines(keepends=True)
    after = TASKS_PATH.read_text(encoding="utf-8").splitlines(keepends=True)
    diff = difflib.unified_diff(before, after, fromfile="snapshots/before/tasks.py", tofile="sample_app/tasks.py")
    (RECORDS / "tasks.diff").write_text("".join(diff), encoding="utf-8")


def _report_minimax(context: str) -> None:
    from minimax.minimax_client import api_key

    note = RECORDS / "minimax_status.txt"
    if not api_key():
        note.write_text(
            "未设置 MINIMAX_API_KEY。上下文已经交给 apply 命令使用，但这次没有调用模型，也没有改 tasks.py。\n",
            encoding="utf-8",
        )
        return
    from minimax.minimax_client import apply_change

    apply_change(context)
    code = _run_tests("after")
    if code != 0:
        raise SystemExit("MiniMax 改完后测试没有通过，见 records/test_after.log")
    _write_diff()
    note.write_text("MiniMax 已改 tasks.py，功能测试和回归测试都通过。\n", encoding="utf-8")
