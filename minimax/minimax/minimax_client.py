"""把上下文交给 MiniMax，让它改 sample_app/tasks.py。"""

from __future__ import annotations

import json
import os
import re
from pathlib import Path

import httpx

from minimax.paths import RECORDS, TASKS_PATH

_DEFAULT_BASE_URL = "https://api.minimax.cn/v1"
_DEFAULT_MODEL = "MiniMax-M3"
_FENCE = re.compile(r"```(?:python)?\s*\n(.*?)```", re.DOTALL)
_THINK = re.compile(r"<think>.*?</think>\s*", re.DOTALL)


def api_key() -> str:
    return os.environ.get("MINIMAX_API_KEY", "").strip()


def apply_change(context: str) -> dict[str, str]:
    key = api_key()
    if not key:
        raise RuntimeError("缺少环境变量 MINIMAX_API_KEY，不能假装 MiniMax 改过代码")
    before = TASKS_PATH.read_text(encoding="utf-8")
    prompt = (
        context
        + "\n请只实现 filter_tasks，保持 sort_tasks 的排序规则。"
        + "\n只输出完整的 tasks.py，放在一个 python 代码块里。"
    )
    first = _chat(key, prompt)
    code = _extract_code(first["content"])
    error = _reject_code(code)
    second = None
    if error:
        second = _chat(key, prompt + "\n上次输出不能用：" + error + "\n请重新输出完整文件。")
        code = _extract_code(second["content"])
        error = _reject_code(code)
        if error:
            _write_exchange(before, first, second, "")
            raise RuntimeError(error)
    TASKS_PATH.write_text(code, encoding="utf-8")
    _write_exchange(before, first, second, code)
    return {"before": before, "after": code}


def _chat(key: str, prompt: str) -> dict[str, str]:
    base_url = os.environ.get("MINIMAX_BASE_URL", _DEFAULT_BASE_URL).rstrip("/")
    model = os.environ.get("MINIMAX_MODEL", _DEFAULT_MODEL)
    response = httpx.post(
        f"{base_url}/chat/completions",
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
        json={
            "model": model,
            "temperature": 0.1,
            "messages": [
                {
                    "role": "system",
                    "content": "你是改代码的助手。只输出一个 python 代码块，内容是完整文件。",
                },
                {"role": "user", "content": prompt},
            ],
        },
        timeout=120.0,
    )
    response.raise_for_status()
    payload = response.json()
    message = payload["choices"][0]["message"]
    content = message.get("content") or ""
    return {"model": model, "base_url": base_url, "content": content}


def _extract_code(content: str) -> str:
    visible = _THINK.sub("", content)
    matched = _FENCE.search(visible)
    code = matched.group(1) if matched else visible
    if not code.endswith("\n"):
        code += "\n"
    return code


def _reject_code(code: str) -> str:
    try:
        compile(code, str(TASKS_PATH), "exec")
    except SyntaxError as error:
        return f"语法错误: {error}"
    if "def sort_tasks" not in code or "def filter_tasks" not in code:
        return "输出里没有 sort_tasks 和 filter_tasks"
    if "NotImplementedError" in code:
        return "filter_tasks 仍然没有实现"
    return ""


def _write_exchange(before: str, first: dict[str, str], second: dict[str, str] | None, after: str) -> None:
    RECORDS.mkdir(parents=True, exist_ok=True)
    record = {
        "provider": "MiniMax",
        "base_url": first["base_url"],
        "model": first["model"],
        "task_file": str(Path("sample_app/tasks.py")),
        "before_sha256": _sha256(before),
        "after_sha256": _sha256(after) if after else "",
        "responses": [first["content"], *([second["content"]] if second else [])],
    }
    (RECORDS / "minimax_exchange.json").write_text(
        json.dumps(record, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def _sha256(value: str) -> str:
    import hashlib

    return hashlib.sha256(value.encode()).hexdigest()
