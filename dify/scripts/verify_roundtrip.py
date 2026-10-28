#!/usr/bin/env python3
"""不启动 Dify，用真实 PowerContext 复现《口供》的一次跨会话记忆闭环。

它做的事和 Chatflow 完全一致——Code 节点的代码直接从 DSL 里读出来执行，HTTP 请求打
到真实的 PowerContext：

    POST /v1/scopes            建档案室（幂等）
    POST /v1/context/prepare   调取档案
    POST /v1/memory/remember   归档口供
    POST /v1/context/prepare   下一次审讯再调档案

所以这个脚本跑通，就等于「DSL 里的数据流 + PowerContext 服务」这条链路是通的；Dify
只负责把它串起来和调用模型。

    python scripts/verify_roundtrip.py            # 复用 demo 档案，观察记忆累积
    python scripts/verify_roundtrip.py --fresh    # 换一个新档案室，从零开始
"""

from __future__ import annotations

import argparse
import json
import os
import time
import urllib.error
import urllib.request
from pathlib import Path

import yaml

BASE = os.environ.get("PC_BASE_URL", "http://127.0.0.1:8000").rstrip("/")
DSL = Path(__file__).resolve().parent.parent / "dsl" / "the-confession.chatflow.yml"


def post(path: str, payload: dict) -> tuple[int, dict]:
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(
        f"{BASE}{path}",
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            return resp.status, json.load(resp)
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise SystemExit(f"POST {path} -> HTTP {exc.code}\n{body}") from exc
    except urllib.error.URLError as exc:
        raise SystemExit(f"连不上 {BASE}：{exc.reason}\n先运行 scripts/start_powercontext.sh") from exc


def load_code() -> dict[str, str]:
    dsl = yaml.safe_load(DSL.read_text(encoding="utf-8"))
    return {
        n["id"]: n["data"]["code"]
        for n in dsl["workflow"]["graph"]["nodes"]
        if n["data"]["type"] == "code"
    }


def call(code: str, **kwargs):
    scope: dict = {}
    exec(compile(code, "<dify-code-node>", "exec"), scope)  # noqa: S102
    return scope["main"](**kwargs)


def rule(title: str) -> None:
    print(f"\n{'=' * 62}\n{title}\n{'=' * 62}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--fresh", action="store_true", help="用一个新的 idempotency_key，从零开始")
    args = parser.parse_args()

    code = load_code()
    user_key = f"demo-{int(time.time())}" if args.fresh else "demo"
    idem = f"dify-confession-{user_key}"

    print(f"PowerContext: {BASE}")
    print(f"档案室 key  : {idem}")

    rule("① 建档案室（POST /v1/scopes，按 idempotency_key 幂等）")
    status, scope = post(
        "/v1/scopes",
        {
            "title": f"口供档案-{user_key}",
            "summary": "Dify《口供》应用的独立审讯档案：存放嫌疑人逐轮发言记录。",
            "idempotency_key": idem,
        },
    )
    scope_id = scope.get("scope_id", "")
    print(f"HTTP {status}  scope_id = {scope_id}")
    if not scope_id:
        raise SystemExit("没有拿到 scope_id，检查 PowerContext 版本")

    # ---- 会话 A -------------------------------------------------------
    rule("② 会话 A：第一次进审讯室")
    first_words = "我昨晚在家看球赛，哪也没去。"
    boot = call(code["code_boot"], scope_resp=json.dumps(scope, ensure_ascii=False), query=first_words)

    _, prepared = post("/v1/context/prepare", json.loads(boot["prepare_json"]))
    ctx_a = call(code["code_ctx"], prep_resp=json.dumps(prepared, ensure_ascii=False), boot_err="")
    print(f"玩家：{first_words}")
    print(f"调档状态：{ctx_a['memory_state']}")
    print(f"注入提示词的档案：{ctx_a['context_text'][:120]}")

    # 模拟模型输出（真实运行时由 LLM 生成，格式要求见 system prompt）
    llm_output = (
        "【台词】\n在家看球？哪场？\n"
        "【记录】\n嫌疑人称昨晚在家看球赛，没有外出。"
    )
    split = call(code["code_split"], text=llm_output, query=first_words, scope_id=scope_id)
    print(f"老严：{split['reply']}")

    rule("③ 归档口供（POST /v1/memory/remember）")
    status, saved = post("/v1/memory/remember", json.loads(split["remember_json"]))
    records = saved.get("records") or []
    print(f"HTTP {status}  changed={saved.get('changed')}  records={len(records)}")
    for rec in records:
        art = rec.get("artifact") or {}
        print(f"  · {art.get('family')}/{art.get('artifact_id')}@rev{art.get('revision')}")
        text = ((rec.get("content") or {}).get("text") or "").strip()
        print(f"    正文：{text}")

    # ---- 会话 B -------------------------------------------------------
    rule("④ 会话 B：关掉再开，同一档案室")
    second_words = "我再说一遍，我跟那条金鱼一点关系都没有。"
    boot_b = call(code["code_boot"], scope_resp=json.dumps(scope, ensure_ascii=False), query=second_words)
    _, prepared_b = post("/v1/context/prepare", json.loads(boot_b["prepare_json"]))
    ctx_b = call(code["code_ctx"], prep_resp=json.dumps(prepared_b, ensure_ascii=False), boot_err="")
    print(f"玩家：{second_words}")
    print(f"调档状态：{ctx_b['memory_state']}")
    print("注入提示词的档案：")
    for line in ctx_b["context_text"].splitlines():
        print(f"  {line}")

    rule("结论")
    recalled = "球赛" in ctx_b["context_text"] or "看球" in ctx_b["context_text"]
    if recalled:
        print("✓ 会话 B 召回到了会话 A 的口供——跨会话记忆成立。")
        print("  真实运行时，老严会拿这句话质问玩家，这就是《口供》的核心机制。")
        return 0

    print("✗ 会话 B 没有召回到会话 A 的内容。")
    print("  常见原因：记忆刚写入、索引还没可见。等几秒重跑本脚本。")
    print("  仍失败时，检查 PowerContext 日志里 prepare 的检索分支。")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
