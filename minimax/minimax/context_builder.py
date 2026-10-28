"""上下文只从 seekdb 的查询行和 PowerContext 的状态拼出来。"""

from __future__ import annotations

from minimax.db import Catalog
from minimax.state import load_state


def build_context(task: str) -> str:
    with Catalog() as catalog:
        queried = catalog.query_for_task(task)
    state = load_state()
    lines = [f"任务: {task}", "", "下面的规格、代码和测试来自 seekdb 查询结果。", ""]
    for row in queried["rows"]:
        lines.extend(
            [
                f"## {row['kind']}",
                f"来源: {row['path']}",
                f"符号: {row['symbol']}",
                row["body"].rstrip(),
                "",
            ]
        )
    lines.append("## 任务状态")
    if state is None:
        lines.append("来源: powercontext")
        lines.append("尚无已保存状态")
    else:
        payload = state["payload"]
        lines.append(f"来源: powercontext:{state['source_id']}")
        lines.append("已完成: " + _join(payload.get("done", [])))
        lines.append("待办: " + _join(payload.get("todo", [])))
        verification = payload.get("verification", {})
        rendered = ", ".join(f"{key}={value}" for key, value in verification.items())
        lines.append(f"验证结果: {rendered}")
    lines.append("")
    return "\n".join(lines)


def _join(items: object) -> str:
    if isinstance(items, list) and items:
        return "；".join(str(item) for item in items)
    return "无"
