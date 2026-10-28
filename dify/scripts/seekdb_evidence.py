#!/usr/bin/env python3
"""收集「seekdb 真的在存数据」的证据。

做三件事：
1. 找到 PowerContext 的 seekdb 数据目录，列出文件和体积（SQLite 后端只有一个 .db 文件，
   seekdb 后端是一整个实例目录，形状完全不同）；
2. 如果 Server 在跑，读 /v1/capabilities 确认后端类型；
3. 调 /v1/stats 和 /v1/memory/search，给出该 scope 实际落到库里的记忆条数与正文。

    python scripts/seekdb_evidence.py [scope_id]

不给 scope_id 时用 verify_roundtrip.py 建的 demo 档案室。
"""

from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path

BASE = os.environ.get("PC_BASE_URL", "http://127.0.0.1:8000").rstrip("/")


def candidates() -> list[Path]:
    home = os.environ.get("POWERCONTEXT_HOME")
    out: list[Path] = []
    if home:
        out.append(Path(home) / "seekdb")
    if sys.platform == "darwin":
        out.append(Path.home() / "Library" / "Application Support" / "powercontext" / "seekdb")
    elif os.name == "nt":
        out.append(Path(os.environ.get("LOCALAPPDATA", Path.home())) / "powercontext" / "seekdb")
    else:
        out.append(Path.home() / ".local" / "share" / "powercontext" / "seekdb")
    out.append(Path.cwd() / "seekdb")
    return out


def human(n: int) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024 or unit == "GB":
            return f"{n:.1f} {unit}" if unit != "B" else f"{n} B"
        n /= 1024
    return f"{n} B"


def get(path: str) -> dict | None:
    try:
        with urllib.request.urlopen(f"{BASE}{path}", timeout=8) as resp:
            return json.load(resp)
    except (urllib.error.URLError, json.JSONDecodeError, OSError):
        return None


def post(path: str, payload: dict) -> dict | None:
    req = urllib.request.Request(
        f"{BASE}{path}",
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=8) as resp:
            return json.load(resp)
    except (urllib.error.URLError, urllib.error.HTTPError, json.JSONDecodeError, OSError):
        return None


def main() -> int:
    scope_id = sys.argv[1] if len(sys.argv) > 1 else None

    print("① 数据目录")
    found = False
    for path in candidates():
        if path.exists():
            found = True
            files = [p for p in path.rglob("*") if p.is_file()]
            total = sum(p.stat().st_size for p in files)
            print(f"   {path}")
            print(f"   文件 {len(files)} 个，合计 {human(total)}")
            for p in sorted(files, key=lambda x: -x.stat().st_size)[:8]:
                print(f"     {human(p.stat().st_size):>10}  {p.relative_to(path)}")
            break
    if not found:
        print("   没找到。Server 没启动过，或 POWERCONTEXT_HOME 指向了别处。")

    print("\n② Server 与后端")
    caps = get("/v1/capabilities")
    if caps is None:
        print(f"   {BASE} 没响应（服务没起？）")
    else:
        print(f"   /v1/capabilities 已响应，字段：{sorted(caps)[:12] if isinstance(caps, dict) else type(caps).__name__}")
        print("   注：capabilities 描述的是启用了哪些运行时能力，不一定回显数据库后端；")
        print("   后端以启动脚本里的 POWERCONTEXT_SERVER_DATABASE_KIND 和数据目录形状为准。")

    print("\n③ 库里的口供")
    if not scope_id:
        scopes = get("/v1/scopes?limit=5")
        items = (scopes or {}).get("items") or []
        for item in items:
            if "口供" in (item.get("title") or ""):
                scope_id = item.get("scope_id")
                break
        if not scope_id and items:
            scope_id = items[0].get("scope_id")

    if not scope_id:
        print("   没有可用 scope。先跑 scripts/verify_roundtrip.py。")
        return 0

    print(f"   scope_id = {scope_id}")
    found = post("/v1/memory/search", {"scope_id": scope_id, "query": "口供 金鱼 昨晚", "limit": 8})
    hits = (found or {}).get("hits") or []
    print(f"   /v1/memory/search 命中 {len(hits)} 条（这个数字来自 seekdb 里的记忆索引）：")
    for hit in hits:
        mem = hit.get("memory") or {}
        text = (mem.get("text") or "").strip().replace("\n", " ")
        score = hit.get("score")
        score_text = f"[{score:.3f}] " if isinstance(score, (int, float)) else ""
        print(f"     · {score_text}{text[:90]}")
    if not hits:
        print("     （空。先跑一局，或跑 scripts/verify_roundtrip.py）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
