"""用 PowerContext 保存任务进度，关掉再打开还能读到。"""

from __future__ import annotations

import asyncio
import json
from typing import Any

from minimax.paths import DATA, POWERCONTEXT_DB

_IDEMPOTENCY_KEY = "ryb-minimax-sdd"
_DRAFT_TITLE = "SDD 任务"
_DRAFT_SUMMARY = "筛选任务的进度和验证结果"
_KIND = "task-state"


def _config():
    from powercontext.builtin.persistence.sqlite import SQLiteConfig
    from powercontext.builtin.runtime import BuiltinConfig

    DATA.mkdir(parents=True, exist_ok=True)
    return BuiltinConfig(database=SQLiteConfig(url=f"sqlite+aiosqlite:///{POWERCONTEXT_DB}"))


def _draft():
    from powercontext.builtin.scope import ScopeDraft

    return ScopeDraft(title=_DRAFT_TITLE, summary=_DRAFT_SUMMARY, idempotency_key=_IDEMPOTENCY_KEY)


async def _save(payload: dict[str, Any]) -> dict[str, Any]:
    from powercontext.builtin.runtime import CaptureSource, open_builtin_contexts, open_builtin_runtime

    config = _config()
    content = json.dumps(payload, ensure_ascii=False, sort_keys=True)
    async with open_builtin_runtime(config) as runtime:
        scope = await runtime.scopes.create(_draft())
        scope_id = scope.scope_id
    async with open_builtin_contexts(config) as contexts:
        entries = await (await contexts.get(scope_id)).sources.journal.entries()
    sequence = 1 + sum(1 for entry in entries if entry.source.metadata.get("kind") == _KIND)
    source_id = f"task-state-{sequence}"
    async with open_builtin_runtime(config) as runtime:
        receipt = await runtime.sources.for_scope(scope_id).capture(
            CaptureSource(source_id=source_id, content=content, metadata={"kind": _KIND})
        )
    saved = {"source_id": source_id, "sequence": receipt.sequence, "scope_id": scope_id, "payload": payload}
    _write_record(saved)
    return saved


async def _load() -> dict[str, Any] | None:
    from powercontext.builtin.runtime import open_builtin_contexts, open_builtin_runtime

    if not POWERCONTEXT_DB.exists():
        return None
    config = _config()
    async with open_builtin_runtime(config) as runtime:
        scope = await runtime.scopes.create(_draft())
        scope_id = scope.scope_id
    async with open_builtin_contexts(config) as contexts:
        entries = await (await contexts.get(scope_id)).sources.journal.entries()
    chosen = None
    for entry in entries:
        source = entry.source
        if source.metadata.get("kind") != _KIND:
            continue
        chosen = {
            "source_id": source.name,
            "sequence": entry.position,
            "scope_id": scope_id,
            "payload": json.loads(source.content),
        }
    return chosen


def save_state(payload: dict[str, Any]) -> dict[str, Any]:
    return asyncio.run(_save(payload))


def load_state() -> dict[str, Any] | None:
    return asyncio.run(_load())


def _write_record(saved: dict[str, Any]) -> None:
    from minimax.paths import RECORDS

    RECORDS.mkdir(parents=True, exist_ok=True)
    (RECORDS / "powercontext_state.json").write_text(
        json.dumps(saved, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
