"""任务列表。

排序已经按规格实现。按状态筛选还没有实现，功能测试会因此失败。
规格见 sample_app/spec.md。
"""

from __future__ import annotations


def sort_tasks(tasks: list[dict]) -> list[dict]:
    """按 priority 从高到低，相同 priority 再按 name 升序。不改原列表。"""

    return sorted(tasks, key=lambda item: (-item["priority"], item["name"]))


def filter_tasks(tasks: list[dict], status: str | None) -> list[dict]:
    """按状态留下任务。规格要求的行为还没写。"""

    raise NotImplementedError("filter_tasks 尚未实现")
