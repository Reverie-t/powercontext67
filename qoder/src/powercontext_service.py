"""
PowerContext 服务管理层
提供本地 PowerContext 服务器的启动、停止和记忆操作接口
"""
import asyncio
import socket
import threading
import time
from pathlib import Path
from typing import Optional
import uvicorn
from pydantic import SecretStr

from powercontext.server.factory import create_server_app
from powercontext.server.settings import (
    ServerSettings,
    HttpConfig,
    BearerAuthConfig,
    AccessControlConfig,
    RuntimeConfig,
    ExternalSkillsConfig,
    McpConfig,
    MetricsConfig,
    TracingConfig,
    InferenceConfig,
)
from powercontext.builtin.persistence.sqlite import SQLiteConfig
from powercontext.client import PowerContextClient
from powercontext.http import (
    CreateScopeRequest,
    RememberMemoryRequest,
    SearchMemoryRequest,
    PrepareContextRequest,
    ListMemoryEntriesRequest,
    ReplaceAtomicMemoryArtifactRequest,
    AtomicMemoryWriteContent,
    ReplaceArtifactRequest,
)


class PowerContextService:
    """管理 PowerContext 服务器和客户端连接"""

    def __init__(self, data_dir: Path):
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.db_path = self.data_dir / "powercontext.db"
        self.server: Optional[uvicorn.Server] = None
        self.server_thread: Optional[threading.Thread] = None
        self.listener: Optional[socket.socket] = None
        self.client: Optional[PowerContextClient] = None
        self.base_url: str = ""

    async def start(self) -> None:
        """启动 PowerContext 服务器"""
        if self.server is not None:
            return

        database = SQLiteConfig(url=f"sqlite+aiosqlite:///{self.db_path}")
        settings = ServerSettings(
            workspace=self.data_dir,
            database=database,
            http=HttpConfig(host="127.0.0.1"),
            auth=BearerAuthConfig(enabled=False),
            access=AccessControlConfig(mode="disabled"),
            inference=InferenceConfig(),
            runtime=RuntimeConfig(schedule_seconds=None, experience_schedule_seconds=None),
            external_skills=ExternalSkillsConfig(),
            mcp=McpConfig(enabled=False),
            metrics=MetricsConfig(enabled=False),
            tracing=TracingConfig(enabled=False),
        )

        app = create_server_app(settings=settings, scheduler_path=self.data_dir / "scheduler.db")
        self.listener = socket.socket()
        self.listener.bind(("127.0.0.1", 0))
        port = self.listener.getsockname()[1]
        self.base_url = f"http://127.0.0.1:{port}"

        self.server = uvicorn.Server(
            uvicorn.Config(app, log_level="warning", access_log=False, lifespan="on")
        )
        self.server_thread = threading.Thread(
            target=self.server.run, kwargs={"sockets": [self.listener]}, daemon=True
        )
        self.server_thread.start()

        deadline = time.monotonic() + 30
        while self.server_thread.is_alive() and not self.server.started and time.monotonic() < deadline:
            time.sleep(0.05)

        if not self.server.started:
            await self.stop()
            raise RuntimeError("PowerContext 服务器启动失败")

        self.client = PowerContextClient(self.base_url, timeout=60)

    async def stop(self) -> None:
        """停止服务器"""
        if self.client is not None:
            await self.client.aclose()
            self.client = None

        if self.server is not None:
            self.server.should_exit = True

        if self.server_thread is not None:
            self.server_thread.join(timeout=10)
            self.server_thread = None

        if self.listener is not None:
            self.listener.close()
            self.listener = None

        self.server = None

    async def restart(self) -> None:
        """重启服务器（用于测试持久化）"""
        await self.stop()
        await asyncio.sleep(0.5)
        await self.start()

    async def create_scope(self, title: str, summary: str = "") -> str:
        """创建研究项目 scope"""
        if self.client is None:
            raise RuntimeError("服务器未启动")

        import uuid
        scope = await self.client.create_scope(
            CreateScopeRequest(
                title=title,
                summary=summary or title,
                idempotency_key=f"{uuid.uuid4().hex}",
            )
        )
        return scope.scope_id

    async def remember(self, scope_id: str, kind: str, text: str, reason: str = "") -> dict:
        """保存记忆"""
        if self.client is None:
            raise RuntimeError("服务器未启动")

        result = await self.client.remember_memory(
            RememberMemoryRequest(
                scope_id=scope_id,
                kind=kind,
                text=text,
                reason=reason or None,
            )
        )
        if not result.records:
            raise RuntimeError("记忆保存失败：未返回记录")
        
        record = result.records[0]
        return {
            "artifact_id": record.artifact.artifact_id,
            "revision": record.artifact.revision,
            "text": record.text,
            "kind": record.kind,
            "state": record.state.value,
        }

    async def search(self, scope_id: str, query: str, limit: int = 20) -> list[dict]:
        """搜索记忆"""
        if self.client is None:
            raise RuntimeError("服务器未启动")

        result = await self.client.search_memory(
            SearchMemoryRequest(
                scope_id=scope_id,
                query=query,
                limit=limit,
                mode="fts",
            )
        )
        return [
            {
                "artifact_id": hit.memory.artifact.artifact_id,
                "revision": hit.memory.artifact.revision,
                "text": hit.memory.text,
                "kind": hit.memory.kind,
                "score": hit.score,
            }
            for hit in result.hits
        ]

    async def prepare_context(self, scope_id: str, query: str, max_bytes: int = 8000) -> dict:
        """准备上下文（用于生成周报）"""
        if self.client is None:
            raise RuntimeError("服务器未启动")

        result = await self.client.prepare_context(
            PrepareContextRequest(
                scope_id=scope_id,
                query=query,
                max_bytes=max_bytes,
            )
        )
        return {
            "status": result.status,
            "content": result.content,
            "content_bytes": result.content_bytes,
        }

    async def list_scopes(self) -> list[dict]:
        """列出所有 scope"""
        if self.client is None:
            raise RuntimeError("服务器未启动")

        from powercontext.http import ListScopesRequest
        result = await self.client.list_scopes(ListScopesRequest())
        return [
            {
                "scope_id": scope.scope_id,
                "title": scope.title,
                "summary": scope.summary,
            }
            for scope in result.scopes
        ]

    async def list_memories(self, scope_id: str, include_inactive: bool = False, limit: int = 100) -> list[dict]:
        """列出所有记忆条目（按 kind 分类，不依赖关键词搜索）"""
        if self.client is None:
            raise RuntimeError("服务器未启动")

        entries = []
        cursor = None
        while True:
            result = await self.client.list_memory_entries(ListMemoryEntriesRequest(
                scope_id=scope_id, include_inactive=include_inactive,
                limit=min(100, max(1, limit)), cursor=cursor,
            ))
            entries.extend({
                "artifact_id": entry.artifact.artifact_id,
                "revision": entry.artifact.revision,
                "kind": entry.kind,
                "text": entry.text,
                "state": entry.state.value,
                "state_version": entry.state_version,
            } for entry in result.entries)
            if result.next_cursor is None:
                return entries
            cursor = result.next_cursor

    async def get_memory(self, scope_id: str, artifact_id: str, revision: int) -> dict:
        """获取单个记忆条目"""
        if self.client is None:
            raise RuntimeError("服务器未启动")

        entry = await self.client.get_artifact(scope_id, "atomic-memory", artifact_id)
        if entry is None or entry.revision != revision:
            raise ValueError("记忆版本已变化，请刷新后重试")
        state = await self.client.get_atomic_memory_state(scope_id, artifact_id)
        return {
            "artifact_id": entry.artifact_id,
            "revision": entry.revision,
            "kind": entry.content["kind"],
            "text": entry.content["text"],
            "state": state.state.value,
            "state_version": state.state_version,
        }

    async def revise_memory(self, scope_id: str, artifact_id: str, revision: int, 
                           kind: str, text: str, reason: str = "") -> dict:
        """修订记忆条目（更新内容）"""
        if self.client is None:
            raise RuntimeError("服务器未启动")

        await self.get_memory(scope_id, artifact_id, revision)
        record = await self.client.replace_artifact(
            scope_id, "atomic-memory", artifact_id,
            ReplaceArtifactRequest(root=ReplaceAtomicMemoryArtifactRequest(
                content=AtomicMemoryWriteContent(kind=kind, text=text))),
            expected_etag=f'"revision:{revision}"',
        )
        return {
            "artifact_id": record.artifact_id,
            "revision": record.revision,
            "text": record.content["text"],
            "kind": record.content["kind"],
            "state": "active",
        }

    async def retire_memory(self, scope_id: str, artifact_id: str, revision: int, 
                           reason: str = "") -> dict:
        """用真实制品修订记录任务完成，保留原始内容和历史版本。"""
        current = await self.get_memory(scope_id, artifact_id, revision)
        if current["kind"] != "decision":
            raise ValueError("只能完成尚未完成的计划任务")
        return await self.revise_memory(scope_id, artifact_id, revision,
                                        "completed-task", current["text"], reason)
