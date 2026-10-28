#!/usr/bin/env python3
"""静态检查《口供》的 Dify DSL，尽量在导入前发现问题。

这不是 Dify 官方校验器（官方那个要连一个真实的 Dify Server），它只覆盖最容易让导入
或运行失败的结构性问题：

1. 顶层字段与 app.mode；
2. 节点 id 唯一、边的两端存在；
3. 除 answer 外都有出边，除 start 外都有入边（孤立节点在 Dify 里跑不到）；
4. 所有 ``{{#node.var#}}`` 引用都能解析到真实节点输出；
5. code 节点声明的 outputs 与 ``main()`` 返回的 key 一致；
6. http 节点的方法、URL、body 类型合法。

用法：
    python scripts/check_dsl.py [dsl/the-confession.chatflow.yml]
"""

from __future__ import annotations

import ast
import re
import sys
from pathlib import Path

import yaml

VAR_RE = re.compile(r"\{\{#([^#{}]+)#\}\}")

# 每个节点类型对外暴露的输出变量。
NODE_OUTPUTS = {
    "start": set(),
    "end": set(),
    "answer": {"output"},
    "llm": {"text", "usage", "reasoning_content", "files"},
    "http-request": {"body", "status_code", "headers", "files"},
    "code": set(),  # 由 data.outputs 决定
    "if-else": {"result"},
    "tool": {"text", "files", "json"},
    "assigner": {"output"},
}

HTTP_METHODS = {"get", "post", "put", "patch", "delete", "head", "options"}
BODY_TYPES = {"none", "form-data", "x-www-form-urlencoded", "raw-text", "json", "binary"}
MODES = {"advanced-chat", "workflow", "agent-chat", "chat", "completion"}


class Report:
    def __init__(self) -> None:
        self.errors: list[str] = []
        self.warnings: list[str] = []
        self.notes: list[str] = []

    def error(self, msg: str) -> None:
        self.errors.append(msg)

    def warn(self, msg: str) -> None:
        self.warnings.append(msg)

    def note(self, msg: str) -> None:
        self.notes.append(msg)


def walk_strings(value, path=""):
    if isinstance(value, str):
        yield path, value
    elif isinstance(value, dict):
        for k, v in value.items():
            yield from walk_strings(v, f"{path}/{k}")
    elif isinstance(value, list):
        for i, v in enumerate(value):
            yield from walk_strings(v, f"{path}[{i}]")


def code_returns(code: str, node_id: str, rep: Report) -> set[str]:
    """解析 code 节点 main() 里 return {...} 的字面量 key。"""
    try:
        tree = ast.parse(code)
    except SyntaxError as exc:
        rep.error(f"{node_id}: Python 语法错误 -> {exc}")
        return set()

    func = next((n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef) and n.name == "main"), None)
    if func is None:
        rep.error(f"{node_id}: 找不到 main() 函数，Dify 的 Code 节点必须有 main")
        return set()

    keys: set[str] = set()
    for node in ast.walk(func):
        if isinstance(node, ast.Return) and isinstance(node.value, ast.Dict):
            for k in node.value.keys:
                if isinstance(k, ast.Constant) and isinstance(k.value, str):
                    keys.add(k.value)
    if not keys:
        rep.warn(f"{node_id}: main() 里没找到字面量 return 字典，无法核对 outputs")
    return keys


def main() -> int:
    path = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).resolve().parent.parent / "dsl" / "the-confession.chatflow.yml"
    rep = Report()

    raw = path.read_text(encoding="utf-8")
    dsl = yaml.safe_load(raw)
    if not isinstance(dsl, dict):
        print("DSL 不是 YAML 映射")
        return 1

    # 1. 顶层
    if dsl.get("kind") != "app":
        rep.error(f"kind 应为 app，实际 {dsl.get('kind')!r}")
    version = str(dsl.get("version", ""))
    if not version:
        rep.error("缺少 version")
    else:
        rep.note(f"DSL version = {version}")

    app = dsl.get("app") or {}
    mode = app.get("mode")
    if mode not in MODES:
        rep.error(f"app.mode 非法：{mode!r}")
    for key in ("name", "icon", "icon_background", "description"):
        if not app.get(key):
            rep.warn(f"app.{key} 为空")

    wf = dsl.get("workflow") or {}
    graph = wf.get("graph") or {}
    nodes = graph.get("nodes") or []
    edges = graph.get("edges") or []

    if not nodes:
        rep.error("graph.nodes 为空")
        print_report(rep, path)
        return 1
    if not edges:
        rep.error("graph.edges 为空")

    # 2. 节点 id 与边
    by_id: dict[str, dict] = {}
    for n in nodes:
        nid = n.get("id")
        if not nid:
            rep.error("存在没有 id 的节点")
            continue
        if nid in by_id:
            rep.error(f"节点 id 重复：{nid}")
        by_id[nid] = n
        if not (n.get("data") or {}).get("type"):
            rep.error(f"{nid}: 缺少 data.type")

    for e in edges:
        src, dst = e.get("source"), e.get("target")
        if src not in by_id:
            rep.error(f"边 {e.get('id')} 的 source 不存在：{src}")
        if dst not in by_id:
            rep.error(f"边 {e.get('id')} 的 target 不存在：{dst}")
        if e.get("targetHandle") != "target":
            rep.warn(f"边 {e.get('id')} 的 targetHandle 不是 target：{e.get('targetHandle')!r}")

    # 3. 连通性
    out_deg = {nid: 0 for nid in by_id}
    in_deg = {nid: 0 for nid in by_id}
    for e in edges:
        if e.get("source") in out_deg:
            out_deg[e["source"]] += 1
        if e.get("target") in in_deg:
            in_deg[e["target"]] += 1

    for nid, n in by_id.items():
        dtype = (n.get("data") or {}).get("type")
        if dtype != "answer" and out_deg[nid] == 0:
            rep.error(f"{nid}({dtype}): 没有出边，流程会停在这里")
        if dtype != "start" and in_deg[nid] == 0:
            rep.error(f"{nid}({dtype}): 没有入边，永远执行不到")

    if mode == "advanced-chat" and not any((n.get("data") or {}).get("type") == "answer" for n in nodes):
        rep.error("Chatflow 至少需要一个 answer 节点")

    # 4. 变量引用
    outputs: dict[str, set[str]] = {}
    for nid, n in by_id.items():
        data = n.get("data") or {}
        dtype = data.get("type")
        if dtype == "code":
            outputs[nid] = set((data.get("outputs") or {}).keys())
        else:
            outputs[nid] = set(NODE_OUTPUTS.get(dtype, set()))

    sys_vars = {"query", "user_id", "files", "conversation_id", "dialogue_count", "app_id", "workflow_run_id", "timestamp"}
    env_vars = {v.get("name") for v in (wf.get("environment_variables") or [])}

    for nid, n in by_id.items():
        for path_, text in walk_strings(n.get("data") or {}):
            for ref in VAR_RE.findall(text):
                ref = ref.strip()
                if "." not in ref:
                    rep.warn(f"{nid}{path_}: 变量引用缺少点号 -> {ref}")
                    continue
                head, var = ref.split(".", 1)
                var = var.split(".")[0]
                if head == "sys":
                    if var not in sys_vars:
                        rep.error(f"{nid}{path_}: sys.{var} 不是已知的系统变量")
                elif head == "env":
                    if var not in env_vars:
                        rep.error(f"{nid}{path_}: env.{var} 未在 environment_variables 里定义")
                elif head == "conversation":
                    rep.warn(f"{nid}{path_}: 引用了会话变量 {ref}，确认它已在 conversation_variables 声明")
                elif head not in by_id:
                    rep.error(f"{nid}{path_}: 引用了不存在的节点 {head}")
                elif var not in outputs.get(head, set()):
                    rep.error(f"{nid}{path_}: {head} 没有输出 {var}（可用：{sorted(outputs.get(head, []))}）")

    # code 节点的输入选择器
    for nid, n in by_id.items():
        data = n.get("data") or {}
        if data.get("type") != "code":
            continue
        for item in data.get("variables") or []:
            sel = item.get("value_selector") or []
            if len(sel) != 2:
                rep.error(f"{nid}: variables 里的 value_selector 必须是 [节点, 变量]，实际 {sel}")
                continue
            src, var = sel
            if src == "sys":
                if var not in sys_vars:
                    rep.error(f"{nid}: 输入 {item.get('variable')} 引用了未知系统变量 sys.{var}")
            elif src == "env":
                if var not in env_vars:
                    rep.error(f"{nid}: 输入 {item.get('variable')} 引用了未定义的环境变量 env.{var}")
            elif src not in by_id:
                rep.error(f"{nid}: 输入 {item.get('variable')} 指向不存在的节点 {src}")
            elif var not in outputs.get(src, set()):
                rep.error(f"{nid}: 输入 {item.get('variable')} 引用了 {src}.{var}，但该节点没有这个输出")
        declared = set((data.get("outputs") or {}).keys())
        returned = code_returns(data.get("code") or "", nid, rep)
        if returned and declared != returned:
            rep.error(f"{nid}: outputs 声明 {sorted(declared)} 与 main() 返回 {sorted(returned)} 不一致")

    # 5. http 节点
    for nid, n in by_id.items():
        data = n.get("data") or {}
        if data.get("type") != "http-request":
            continue
        method = str(data.get("method") or "").lower()
        if method not in HTTP_METHODS:
            rep.error(f"{nid}: method 非法 {method!r}")
        if not data.get("url"):
            rep.error(f"{nid}: 缺少 url")
        body = data.get("body")
        if body is not None:
            btype = body.get("type")
            if btype not in BODY_TYPES:
                rep.error(f"{nid}: body.type 非法 {btype!r}")
            if btype == "json" and not body.get("data"):
                rep.error(f"{nid}: body.type=json 但 data 为空")

    # 6. answer 引用
    for nid, n in by_id.items():
        data = n.get("data") or {}
        if data.get("type") == "answer" and not (data.get("answer") or "").strip():
            rep.error(f"{nid}: answer 内容为空")

    print_report(rep, path)
    return 1 if rep.errors else 0


def print_report(rep: Report, path: Path) -> None:
    print(f"检查 {path}")
    for n in rep.notes:
        print(f"  · {n}")
    for w in rep.warnings:
        print(f"  ! {w}")
    for e in rep.errors:
        print(f"  x {e}")
    print()
    print(f"结论：{len(rep.errors)} 个错误，{len(rep.warnings)} 个警告")


if __name__ == "__main__":
    raise SystemExit(main())
