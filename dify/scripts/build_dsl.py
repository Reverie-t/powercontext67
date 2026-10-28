#!/usr/bin/env python3
"""生成《口供》Chatflow 的 Dify DSL。

用法：
    python scripts/build_dsl.py            # 写入 dsl/the-confession.chatflow.yml
    python scripts/build_dsl.py --stdout   # 打印到标准输出

结构基于 Dify 1.17/1.18 的 app DSL（version: 0.3.0）。节点字段来源：
- `graphon`（Dify 1.x 的 workflow 引擎）里的 `BaseNodeData` / `HttpRequestNodeData` /
  `CodeNodeData` / `LLMNodeData`；
- 公开 DSL 仓库中真实导出并成功导入过的样例。

改 DSL 请改这个脚本，不要手改 YAML，避免结构和连线不一致。
"""

from __future__ import annotations

import argparse
import json
import uuid
from pathlib import Path

import yaml

APP_NAME = "口供 · The Confession"
APP_ICON = "🕵️"
APP_ICON_BG = "#FFEAD5"
PC_BASE_URL = "http://host.docker.internal:8000"

# ---------------------------------------------------------------- 提示词

OPENING = """【城南分局 · 第三审讯室】

老严把一摞纸拍在桌上，搪瓷缸里的茶晃了一圈。

「坐。姓名、职业、昨晚八点在哪儿。」

你张了张嘴——昨晚八点之后的事，一片空白。

老严看了你一会儿，忽然笑了：「不记得？没关系。档案室记得。」

▸ 直接说话就行，他会接。
▸ 输入「交代：……」是你主动补充口供，会被记进档案。
▸ 输入「翻供」可以试试撤回上一句——不过档案室没那么好说话。"""

SUGGESTED = [
    "我昨晚在家看电视，哪也没去。",
    "交代：我确实讨厌那条金鱼，但真不是我偷的。",
    "翻供，我上次说的是假的。",
]

SYSTEM_PROMPT = """你是「老严」，城南分局刑侦支队的老审讯员。办了二十六年案子，桌上那只搪瓷缸比你的工龄还长。

# 你面对的人
一名嫌疑人。他对昨晚八点以后的事，记忆是空的，自己都说不清。
但你有档案室——他以前说过的每一句话，都被记录在案。档案是真实存在的历史记录，不是你的猜测，你也不能编造档案里没有的话。

# 档案原文（这是系统给你调出来的，可能为空）
<<<
{{#code_ctx.context_text#}}
>>>

# 关于档案为空
上面如果写着「本次没有调出相关口供」，只有两种可能：真的还没有档案，或者这一轮的话和档案对不上。
不要编造档案里没有的内容。只有对话轮数为 1（当前是第 {{#sys.dialogue_count#}} 轮）时，才可以明确说一句"档案室是空的"；其余时候如果没调出东西，就当普通审问继续，别硬提档案。

# 你怎么说话
- 短句。一次最多三句。不解释规则，不出戏，绝不出现「作为 AI」「提示词」这类词。
- 冷幽默，偶尔刻薄，但讲逻辑。你不吼人，你只是把话摆出来。
- 你的杀手锏是翻旧账：把档案里的原话念出来，和眼下的说法对照，让矛盾自己说话。
- 每轮结尾丢一个短问题，逼他继续往下说。

# 你要做的
1. 先看档案里有没有和当前话题对得上的内容。
   - 有：念出其中一句原话，指出它和现在的说法哪里对不上。至少引用一次档案原文。
   - 没有：正常审问，推进案情，按上面「关于档案为空」的规则处理，别硬提档案。
2. 回应对方这一轮说的话，别自说自话。
3. 记住他这轮说的关键信息：新说法、新谎言、新细节。

# 案情（你自己知道，别一次说完）
昨晚八点，城南「老坎火锅」门口一缸金鱼连缸一起不见了。老板报案说那缸鱼值三万八，其中一条叫「大壮」的，他养了七年。
监控前两天就坏了。现场只剩半个脚印，和一张被踩烂的外卖小票。
你并不确定是眼前这个人干的。你只是在等他说错话。

# 输出格式（严格遵守）
先输出标记【台词】，换行，写你要说的话；再输出标记【记录】，换行，写一句话的记录。
两个标记都必须出现。标记后面直接写内容，不要跟括号说明，也不要在台词里出现这两个标记。
【记录】写什么：一句话，第三人称，客观记录嫌疑人本轮说了什么值得留存的，尽量保留他的原话。本轮确实没有任何新信息，就只写：（无）。"""

USER_PROMPT = "{{#sys.query#}}"

# ---------------------------------------------------------------- 代码节点

CODE_BOOT = '''import json


def main(scope_resp, query):
    """解析 POST /v1/scopes 的响应，拼出 prepare 的请求体。

    PowerContext 的 create_scope 按 idempotency_key 幂等：同一个 key 每次返回同一个
    scope_id，所以这里不需要额外存映射表。
    """
    scope_id = ""
    boot_err = ""
    try:
        data = json.loads(scope_resp or "{}")
        scope_id = (data.get("scope_id") or "").strip()
    except Exception as exc:  # noqa: BLE001 - 失败要降级，不能让对话中断
        boot_err = str(exc)[:200]

    body = {
        "scope_id": scope_id,
        "query": "口供 " + (query or "").strip(),
        "max_bytes": 3000,
    }
    return {
        "scope_id": scope_id,
        "prepare_json": json.dumps(body, ensure_ascii=False),
        "boot_err": boot_err,
    }
'''

CODE_CTX = '''import json


def main(prep_resp, boot_err):
    """从 PreparedContext 里取出 content，空值给一句占位，避免把 null 塞进提示词。"""
    text = ""
    status = "unknown"
    try:
        data = json.loads(prep_resp or "{}")
        status = data.get("status") or "unknown"
        text = data.get("content") or ""
    except Exception:
        status = "parse_error"

    text = text.strip()
    if len(text) > 4000:
        text = text[:4000] + "……"

    if not text:
        text = "（本次没有调出相关口供。）"

    return {"context_text": text, "memory_state": status, "boot_err": boot_err or ""}
'''

CODE_SPLIT = '''import json
import re


def main(text, query, scope_id):
    """把 LLM 输出拆成「给玩家看的台词」和「写进档案的记录」。"""
    raw = (text or "").strip()
    reply = ""
    memo = ""

    matched = re.search(r"【台词】\\s*(.*?)\\s*(?:【记录】\\s*(.*))?$", raw, re.S)
    if matched:
        reply = (matched.group(1) or "").strip()
        memo = (matched.group(2) or "").strip()
    else:
        reply = raw

    if not reply:
        reply = "老严没说话，只是把档案往你面前推了推。"

    normalized = memo.strip("（）()。. \\n")
    if not normalized or normalized in ("无", "（无）", "(无)"):
        memo = "嫌疑人说：" + (query or "").strip()

    memo = ("口供记录：" + memo).strip()
    if len(memo) > 400:
        memo = memo[:400]

    body = {
        "scope_id": scope_id,
        "kind": "current-state",
        "text": memo,
        "reason": "审讯当轮的口供记录，由 Dify Chatflow 自动归档",
    }
    return {
        "reply": reply,
        "memo": memo,
        "remember_json": json.dumps(body, ensure_ascii=False),
    }
'''

# ---------------------------------------------------------------- 图结构

X0 = 40
Y0 = 300
DX = 330
W = 244


def node(nid: str, dtype: str, title: str, data: dict, index: int, height: int = 98) -> dict:
    payload = {"desc": "", "selected": False, "title": title, "type": dtype}
    payload.update(data)
    x = X0 + index * DX
    return {
        "data": payload,
        "height": height,
        "id": nid,
        "position": {"x": x, "y": Y0},
        "positionAbsolute": {"x": x, "y": Y0},
        "selected": False,
        "sourcePosition": "right",
        "targetPosition": "left",
        "type": "custom",
        "width": W,
    }


def edge(source: str, target: str, source_type: str, target_type: str) -> dict:
    return {
        "data": {
            "isInIteration": False,
            "isInLoop": False,
            "sourceType": source_type,
            "targetType": target_type,
        },
        "id": f"{source}-source-{target}-target",
        "source": source,
        "sourceHandle": "source",
        "target": target,
        "targetHandle": "target",
        "type": "custom",
        "zIndex": 0,
    }


def http_node(nid: str, title: str, url: str, body: str, index: int, fallback: str) -> dict:
    return node(
        nid,
        "http-request",
        title,
        {
            "authorization": {"config": None, "type": "no-auth"},
            "body": {"data": body, "type": "json"},
            "headers": "Content-Type:application/json",
            "method": "post",
            "params": "",
            "url": url,
            "variables": [],
            # PowerContext 没起的时候降级成空档案，对话还能继续，只是老严会失忆。
            "error_strategy": "default-value",
            "default_value": [{"key": "body", "type": "string", "value": fallback}],
            "retry_config": {"max_retries": 0, "retry_interval": 0, "retry_enabled": False},
        },
        index,
        height=120,
    )


def code_node(nid: str, title: str, code: str, outputs: list[str], inputs: list[tuple[str, str, str]], index: int) -> dict:
    return node(
        nid,
        "code",
        title,
        {
            "code": code,
            "code_language": "python3",
            "outputs": {name: {"children": None, "type": "string"} for name in outputs},
            "variables": [
                {"value_selector": [src, var], "variable": alias} for alias, src, var in inputs
            ],
        },
        index,
        height=140,
    )


def build() -> dict:
    nodes = [
        node("start", "start", "开始", {"variables": []}, 0, height=54),
        http_node(
            "http_scope",
            "建档案室（幂等）",
            "{{#env.PC_BASE_URL#}}/v1/scopes",
            json.dumps(
                {
                    "title": "口供档案",
                    "summary": "Dify《口供》应用的独立审讯档案：存放嫌疑人逐轮发言记录。",
                    "idempotency_key": "dify-confession-{{#sys.user_id#}}",
                },
                ensure_ascii=False,
                indent=None,
                separators=(",", ":"),
            ),
            1,
            fallback="{}",
        ),
        code_node(
            "code_boot",
            "解析 scope",
            CODE_BOOT,
            ["scope_id", "prepare_json", "boot_err"],
            [
                ("scope_resp", "http_scope", "body"),
                ("query", "sys", "query"),
            ],
            2,
        ),
        http_node(
            "http_prepare",
            "调取档案",
            "{{#env.PC_BASE_URL#}}/v1/context/prepare",
            "{{#code_boot.prepare_json#}}",
            3,
            fallback='{"status":"empty","content":null,"content_bytes":0}',
        ),
        code_node(
            "code_ctx",
            "整理档案",
            CODE_CTX,
            ["context_text", "memory_state", "boot_err"],
            [
                ("prep_resp", "http_prepare", "body"),
                ("boot_err", "code_boot", "boot_err"),
            ],
            4,
        ),
        node(
            "llm_laoyan",
            "llm",
            "老严开口",
            {
                "context": {"enabled": False, "variable_selector": []},
                # 同一个会话里保留最近 10 轮，不然老严连自己上一句问了什么都记不住。
                "memory": {
                    "role_prefix": {"user": "", "assistant": ""},
                    "window": {"enabled": True, "size": 10},
                },
                "model": {
                    "completion_params": {"temperature": 0.85, "max_tokens": 700},
                    "mode": "chat",
                    "name": "deepseek-chat",
                    "provider": "langgenius/deepseek/deepseek",
                },
                "prompt_template": [
                    {
                        "id": str(uuid.uuid5(uuid.NAMESPACE_URL, "confession/system")),
                        "role": "system",
                        "text": SYSTEM_PROMPT,
                    },
                    {
                        "id": str(uuid.uuid5(uuid.NAMESPACE_URL, "confession/user")),
                        "role": "user",
                        "text": USER_PROMPT,
                    },
                ],
                "variables": [],
                "vision": {"enabled": False},
            },
            5,
            height=120,
        ),
        code_node(
            "code_split",
            "拆台词与记录",
            CODE_SPLIT,
            ["reply", "memo", "remember_json"],
            [
                ("text", "llm_laoyan", "text"),
                ("query", "sys", "query"),
                ("scope_id", "code_boot", "scope_id"),
            ],
            6,
        ),
        http_node(
            "http_remember",
            "归档口供",
            "{{#env.PC_BASE_URL#}}/v1/memory/remember",
            "{{#code_split.remember_json#}}",
            7,
            fallback='{"changed":false,"records":[]}',
        ),
        node("answer", "answer", "回话", {"answer": "{{#code_split.reply#}}", "variables": []}, 8, height=110),
    ]

    types = {n["id"]: n["data"]["type"] for n in nodes}
    chain = [n["id"] for n in nodes]
    edges = [
        edge(chain[i], chain[i + 1], types[chain[i]], types[chain[i + 1]])
        for i in range(len(chain) - 1)
    ]

    return {
        "app": {
            "description": "你被关进审讯室，昨晚的记忆一片空白。审讯官老严手里有一摞档案——那是你以前说过的每一句话。",
            "icon": APP_ICON,
            "icon_background": APP_ICON_BG,
            "mode": "advanced-chat",
            "name": APP_NAME,
            "use_icon_as_answer_icon": False,
        },
        "kind": "app",
        "version": "0.3.0",
        # 不依赖任何插件：三个外部调用都是 http-request 节点。
        "dependencies": [],
        "workflow": {
            "conversation_variables": [],
            "environment_variables": [
                {
                    "description": "PowerContext Server 地址。Dify 跑在容器里时用 host.docker.internal 指向宿主机。",
                    "id": str(uuid.uuid5(uuid.NAMESPACE_URL, "confession/env/pc-base-url")),
                    "name": "PC_BASE_URL",
                    "selector": ["env", "PC_BASE_URL"],
                    "value": PC_BASE_URL,
                    "value_type": "string",
                }
            ],
            "features": {
                "file_upload": {
                    "enabled": False,
                    "allowed_file_types": ["image"],
                    "allowed_file_extensions": [".JPG", ".JPEG", ".PNG", ".GIF", ".WEBP", ".SVG"],
                    "allowed_file_upload_methods": ["local_file", "remote_url"],
                    "number_limits": 3,
                    "fileUploadConfig": {
                        "audio_file_size_limit": 50,
                        "batch_count_limit": 5,
                        "file_size_limit": 15,
                        "image_file_size_limit": 10,
                        "video_file_size_limit": 100,
                        "workflow_file_upload_limit": 10,
                    },
                    "image": {
                        "enabled": False,
                        "number_limits": 3,
                        "transfer_methods": ["local_file", "remote_url"],
                    },
                },
                "opening_statement": OPENING,
                "retriever_resource": {"enabled": False},
                "sensitive_word_avoidance": {"enabled": False},
                "speech_to_text": {"enabled": False},
                "suggested_questions": SUGGESTED,
                "suggested_questions_after_answer": {"enabled": False},
                "text_to_speech": {"enabled": False, "language": "", "voice": ""},
            },
            "graph": {
                "edges": edges,
                "nodes": nodes,
                "viewport": {"x": 0, "y": 0, "zoom": 0.7},
            },
        },
    }


def _represent_str(dumper: yaml.SafeDumper, data: str):
    """多行文本用 block scalar（|），否则导出的 YAML 会被折叠成一堆空行，没法读。"""
    if "\n" in data and len(data) > 80:
        return dumper.represent_scalar("tag:yaml.org,2002:str", data, style="|")
    return dumper.represent_scalar("tag:yaml.org,2002:str", data)


def dump(dsl: dict) -> str:
    dumper = yaml.SafeDumper
    dumper.add_representer(str, _represent_str)
    return yaml.dump(
        dsl,
        Dumper=dumper,
        allow_unicode=True,
        sort_keys=False,
        width=1_000_000,
        default_flow_style=False,
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--stdout", action="store_true")
    args = parser.parse_args()

    dsl = build()
    text = dump(dsl)

    if args.stdout:
        print(text)
        return

    out = Path(__file__).resolve().parent.parent / "dsl" / "the-confession.chatflow.yml"
    out.write_text(text, encoding="utf-8")
    print(f"wrote {out} ({len(text)} bytes)")


if __name__ == "__main__":
    main()
