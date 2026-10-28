"""任务列表。

排序和状态筛选行为见 sample_app/spec.md。
"""

from __future__ import annotations


def sort_tasks(tasks: list[dict]) -> list[dict]:
    """按 priority 从高到低，相同 priority 再按 name 升序。不改原列表。"""

    return sorted(tasks, key=lambda item: (-item["priority"], item["name"]))


def filter_tasks(tasks: list[dict], status: str | None) -> list[dict]:
    """按状态精确筛选任务，保持原顺序且不修改传入的列表。"""

    if status is None or status == "":
        return list(tasks)

    return [task for task in tasks if task.get("status") == status]
