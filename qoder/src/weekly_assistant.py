"""
科研周报助手业务逻辑层
管理研究项目、记录、周报生成
"""
import json
import os
import tempfile
from datetime import datetime, date
from pathlib import Path
from typing import Optional
from dataclasses import dataclass, asdict, field
import uuid

from powercontext_service import PowerContextService


@dataclass
class ResearchRecord:
    """研究记录"""
    id: str
    project_id: str
    date: str  # YYYY-MM-DD
    record_type: str  # experiment, literature, issue, plan
    content: str
    created_at: str
    memory_artifact_id: Optional[str] = None  # PowerContext artifact ID
    memory_revision: Optional[int] = None  # PowerContext revision
    
    def to_dict(self):
        return asdict(self)
    
    @classmethod
    def from_dict(cls, data: dict):
        return cls(**data)


@dataclass
class WeeklyReport:
    """周报"""
    id: str
    project_id: str
    week_start: str  # YYYY-MM-DD
    week_end: str  # YYYY-MM-DD
    markdown: str
    generated_at: str
    memory_refs: list[dict] = field(default_factory=list)
    
    def to_dict(self):
        return asdict(self)
    
    @classmethod
    def from_dict(cls, data: dict):
        return cls(**data)


class ResearchWeeklyAssistant:
    """科研周报助手核心业务"""
    
    def __init__(self, data_dir: Path):
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.projects_file = self.data_dir / "projects.json"
        self.records_file = self.data_dir / "records.json"
        self.reports_file = self.data_dir / "reports.json"
        self.pc_service = PowerContextService(self.data_dir / "powercontext")
        
        self.projects: dict[str, dict] = {}
        self.records: list[ResearchRecord] = []
        self.reports: list[WeeklyReport] = []
        
    async def initialize(self):
        """初始化服务"""
        await self.pc_service.start()
        self._load_data()
    
    async def shutdown(self):
        """关闭服务"""
        self._save_data()
        await self.pc_service.stop()
    
    def _load_data(self):
        """加载本地数据"""
        if self.projects_file.exists():
            with open(self.projects_file, 'r', encoding='utf-8') as f:
                self.projects = json.load(f)
        
        if self.records_file.exists():
            with open(self.records_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
                self.records = [ResearchRecord.from_dict(r) for r in data]
        
        if self.reports_file.exists():
            with open(self.reports_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
                self.reports = [WeeklyReport.from_dict(r) for r in data]
        
    
    def _save_data(self):
        """保存本地数据（原子写入）"""
        self._atomic_write_json(self.projects_file, self.projects)
        self._atomic_write_json(self.records_file, [r.to_dict() for r in self.records])
        self._atomic_write_json(self.reports_file, [r.to_dict() for r in self.reports])
    
    def _atomic_write_json(self, file_path: Path, data):
        """原子写入 JSON 文件（先写临时文件，再重命名）"""
        temp_fd, temp_path = tempfile.mkstemp(
            dir=file_path.parent, 
            suffix='.tmp',
            prefix=f'.{file_path.name}.'
        )
        try:
            with os.fdopen(temp_fd, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            os.replace(temp_path, file_path)
        except Exception:
            # 清理临时文件
            try:
                os.unlink(temp_path)
            except Exception:
                pass
            raise
    
    async def create_project(self, name: str, direction: str, preferences: str) -> dict:
        """创建研究项目"""
        if not all(value.strip() for value in (name, direction, preferences)):
            raise ValueError("项目名称、研究方向和汇报偏好不能为空")
        project_id = f"proj_{uuid.uuid4().hex[:12]}"
        scope_id = await self.pc_service.create_scope(name, direction)
        
        project = {
            "id": project_id,
            "name": name,
            "direction": direction,
            "preferences": preferences,
            "scope_id": scope_id,
            "created_at": datetime.now().isoformat(),
        }
        
        # 保存偏好到 PowerContext
        await self.pc_service.remember(
            scope_id, 
            "preference", 
            preferences, 
            f"项目 {name} 的汇报偏好"
        )
        
        self.projects[project_id] = project
        self._save_data()
        return project
    
    async def get_project(self, project_id: str) -> Optional[dict]:
        """获取项目"""
        return self.projects.get(project_id)
    
    async def list_projects(self) -> list[dict]:
        """列出所有项目"""
        return list(self.projects.values())
    
    async def add_record(self, project_id: str, record_date: str, record_type: str, content: str) -> ResearchRecord:
        """添加研究记录"""
        if project_id not in self.projects:
            raise ValueError(f"项目 {project_id} 不存在")
        
        # 验证日期格式
        try:
            parsed_date = datetime.strptime(record_date, "%Y-%m-%d").date()
            if parsed_date.isoformat() != record_date:
                raise ValueError("日期需要补齐月份和日")
        except ValueError:
            raise ValueError("日期格式必须为 YYYY-MM-DD")
        
        # 验证记录类型
        valid_types = ["experiment", "literature", "issue", "plan"]
        if record_type not in valid_types:
            raise ValueError(f"记录类型必须为 {', '.join(valid_types)} 之一")
        
        # 验证内容非空
        if not content.strip():
            raise ValueError("记录内容不能为空")
        
        # 先保存到 PowerContext（确保持久化成功）
        scope_id = self.projects[project_id]["scope_id"]
        kind_map = {
            "experiment": "observation",
            "literature": "reference",
            "issue": "constraint",
            "plan": "decision",
        }
        kind = kind_map.get(record_type, "observation")
        
        memory_result = await self.pc_service.remember(
            scope_id,
            kind,
            f"[{record_date}] {content}",
            f"{record_type} 记录"
        )
        
        # PowerContext 成功后才创建本地记录
        record = ResearchRecord(
            id=f"rec_{uuid.uuid4().hex[:12]}",
            project_id=project_id,
            date=record_date,
            record_type=record_type,
            content=content,
            created_at=datetime.now().isoformat(),
            memory_artifact_id=memory_result["artifact_id"],
            memory_revision=memory_result["revision"],
        )
        self.records.append(record)
        self._save_data()
        
        return record
    
    async def get_records(self, project_id: str, start_date: Optional[str] = None, end_date: Optional[str] = None) -> list[ResearchRecord]:
        """获取项目记录"""
        records = [r for r in self.records if r.project_id == project_id]
        
        if start_date:
            records = [r for r in records if r.date >= start_date]
        if end_date:
            records = [r for r in records if r.date <= end_date]
        
        return sorted(records, key=lambda r: r.date)
    
    async def generate_weekly_report(self, project_id: str, week_start: str, week_end: str) -> WeeklyReport:
        """生成周报"""
        if project_id not in self.projects:
            raise ValueError(f"项目 {project_id} 不存在")
        
        # 验证日期
        try:
            start = datetime.strptime(week_start, "%Y-%m-%d").date()
            end = datetime.strptime(week_end, "%Y-%m-%d").date()
            if start.isoformat() != week_start or end.isoformat() != week_end:
                raise ValueError("日期格式必须为 YYYY-MM-DD")
            if start > end:
                raise ValueError("开始日期不能晚于结束日期")
        except ValueError as e:
            raise ValueError(f"日期格式错误：{e}")
        
        project = self.projects[project_id]
        scope_id = project["scope_id"]
        
        # 获取本周记录
        records = await self.get_records(project_id, week_start, week_end)
        
        # 从 PowerContext 获取所有活跃记忆（按 kind 分类）
        all_memories = await self.pc_service.list_memories(scope_id, include_inactive=False)
        
        # 分类记忆
        preferences = [m for m in all_memories if m["kind"] == "preference" and m["state"] == "active"]
        # 待办事项是 decision 类型且未停用且未完成的记忆
        todos = [
            m for m in all_memories 
            if m["kind"] == "decision" 
            and m["state"] == "active"
            and m["text"].startswith("[")
            and m["text"][1:11] < week_start
        ]
        
        # 从 PowerContext 获取记忆上下文（用于生成参考）
        context = await self.pc_service.prepare_context(
            scope_id,
            f"{week_start} 至 {week_end} 周报",
            max_bytes=8000
        )
        
        # 生成 Markdown 周报（规则模式，不使用 LLM）
        markdown = self._generate_markdown_report(
            project, records, preferences, todos, week_start, week_end, context,
            {m["artifact_id"] for m in all_memories if m["kind"] == "decision"},
        )
        
        # 收集记忆引用（用于证据展示）
        memory_refs = []
        for pref in preferences:
            memory_refs.append({
                "type": "preference",
                "artifact_id": pref["artifact_id"],
                "revision": pref["revision"],
                "text": pref["text"][:100],
            })
        for todo in todos:
            memory_refs.append({
                "type": "todo",
                "artifact_id": todo["artifact_id"],
                "revision": todo["revision"],
                "text": todo["text"][:100],
            })
        
        report = WeeklyReport(
            id=f"rpt_{uuid.uuid4().hex[:12]}",
            project_id=project_id,
            week_start=week_start,
            week_end=week_end,
            markdown=markdown,
            generated_at=datetime.now().isoformat(),
            memory_refs=memory_refs,
        )
        
        self.reports.append(report)
        self._save_data()
        return report
    
    def _generate_markdown_report(
        self, 
        project: dict, 
        records: list[ResearchRecord],
        preferences: list[dict],
        todos: list[dict],
        week_start: str,
        week_end: str,
        context: dict,
        active_task_ids: set[str],
    ) -> str:
        """生成 Markdown 格式周报"""
        lines = []
        lines.append(f"# {project['name']} 周报")
        lines.append(f"**周期**：{week_start} 至 {week_end}")
        lines.append(f"**研究方向**：{project['direction']}")
        lines.append("")
        
        # 应用偏好：检查是否需要先列量化结果
        prefer_quantitative_first = any("量化" in p["text"] or "结果" in p["text"] for p in preferences)
        
        # 本周进展
        lines.append("## 本周进展")
        lines.append("")
        
        experiments = [r for r in records if r.record_type == "experiment"]
        if experiments:
            lines.append("### 实验记录")
            # 如果偏好要求先列量化结果，排序把包含数字的放前面
            if prefer_quantitative_first:
                experiments = sorted(experiments, key=lambda r: any(c.isdigit() for c in r.content), reverse=True)
            
            for rec in experiments:
                # 添加引用：记录 ID 和 PowerContext artifact ID
                citation = f"`{rec.id}`"
                if rec.memory_artifact_id:
                    citation += f" / `{rec.memory_artifact_id}`"
                lines.append(f"- **{rec.date}**：{rec.content} [{citation}]")
            lines.append("")
        else:
            lines.append("*本周无实验记录*")
            lines.append("")
        
        # 文献阅读
        literature = [r for r in records if r.record_type == "literature"]
        if literature:
            lines.append("### 文献阅读")
            for rec in literature:
                citation = f"`{rec.id}`"
                if rec.memory_artifact_id:
                    citation += f" / `{rec.memory_artifact_id}`"
                lines.append(f"- **{rec.date}**：{rec.content} [{citation}]")
            lines.append("")
        
        # 问题与风险
        issues = [r for r in records if r.record_type == "issue"]
        if issues:
            lines.append("### 问题与风险")
            for rec in issues:
                citation = f"`{rec.id}`"
                if rec.memory_artifact_id:
                    citation += f" / `{rec.memory_artifact_id}`"
                lines.append(f"- **{rec.date}**：{rec.content} [{citation}]")
            lines.append("")
        
        # 下周计划
        plans = [r for r in records if r.record_type == "plan" and r.memory_artifact_id in active_task_ids]
        lines.append("## 下周计划")
        lines.append("")
        
        # 从记忆中提取未完成的待办（使用 kind=decision 且 state=active）
        if todos:
            lines.append("### 延续待办（来自 PowerContext 历史记忆）")
            for todo in todos:
                text = todo["text"]
                # 提取原始文本（去掉日期前缀）
                if "] " in text:
                    text = text.split("] ", 1)[1]
                # 添加 PowerContext artifact 引用
                citation = f"`{todo['artifact_id']}` (rev {todo['revision']})"
                lines.append(f"- {text} [{citation}]")
            lines.append("")
        
        if plans:
            lines.append("### 本周新增计划")
            for rec in plans:
                citation = f"`{rec.id}`"
                if rec.memory_artifact_id:
                    citation += f" / `{rec.memory_artifact_id}`"
                lines.append(f"- {rec.content} [{citation}]")
            lines.append("")
        
        if not todos and not plans:
            lines.append("*暂无明确计划*")
            lines.append("")
        
        # 汇报偏好说明（应用偏好到报告格式）
        if preferences:
            lines.append("## 汇报偏好（支持量化结果优先排序，其他要求供人工检查）")
            lines.append("")
            for pref in preferences[:3]:
                citation = f"`{pref['artifact_id']}` (rev {pref['revision']})"
                lines.append(f"- {pref['text']} [{citation}]")
            lines.append("")
        
        # PowerContext 记忆证据
        lines.append("## 记忆引用证据")
        lines.append("")
        lines.append(f"- PowerContext 上下文状态：{context['status']}")
        lines.append(f"- 上下文大小：{context['content_bytes']} 字节")
        lines.append(f"- 引用偏好数：{len(preferences)}（kind=preference, state=active）")
        lines.append(f"- 引用待办数：{len(todos)}（kind=decision, state=active）")
        lines.append("")
        
        # 原始记录列表（带完整引用）
        lines.append("## 原始记录清单")
        lines.append("")
        for rec in records:
            type_label = {
                "experiment": "实验",
                "literature": "文献",
                "issue": "问题",
                "plan": "计划",
            }.get(rec.record_type, rec.record_type)
            lines.append(f"- [{rec.id}] {rec.date} {type_label}：{rec.content[:80]}")
        lines.append("")
        
        return "\n".join(lines)
    
    async def get_report(self, report_id: str) -> Optional[WeeklyReport]:
        """获取周报"""
        for report in self.reports:
            if report.id == report_id:
                return report
        return None
    
    async def list_reports(self, project_id: Optional[str] = None) -> list[WeeklyReport]:
        """列出周报"""
        if project_id:
            return [r for r in self.reports if r.project_id == project_id]
        return self.reports
    
    async def update_report(self, report_id: str, markdown: str) -> Optional[WeeklyReport]:
        """更新周报内容"""
        for report in self.reports:
            if report.id == report_id:
                report.markdown = markdown
                self._save_data()
                return report
        return None
    
    async def get_memory_evidence(self, project_id: str) -> list[dict]:
        """获取项目的记忆证据（使用 list_memories 而非关键词搜索）"""
        if project_id not in self.projects:
            return []
        
        scope_id = self.projects[project_id]["scope_id"]
        
        # 获取所有记忆（包括已停用的）
        all_memories = await self.pc_service.list_memories(scope_id, include_inactive=True, limit=100)
        
        return all_memories
    
    async def complete_task(self, project_id: str, artifact_id: str, revision: int, reason: str = "") -> dict:
        """通过 PowerContext 的制品修订保存完成状态。"""
        if project_id not in self.projects:
            raise ValueError(f"项目 {project_id} 不存在")
        
        scope_id = self.projects[project_id]["scope_id"]
        return await self.pc_service.retire_memory(scope_id, artifact_id, revision, reason)
    
    async def update_preference(self, project_id: str, artifact_id: str, revision: int, 
                               new_text: str, reason: str = "") -> dict:
        """更新项目偏好（修订 PowerContext 记忆）"""
        if project_id not in self.projects:
            raise ValueError(f"项目 {project_id} 不存在")
        
        if not new_text.strip():
            raise ValueError("偏好内容不能为空")
        
        scope_id = self.projects[project_id]["scope_id"]
        current = await self.pc_service.get_memory(scope_id, artifact_id, revision)
        if current["kind"] != "preference":
            raise ValueError("该记忆不是汇报偏好")
        # 修订 PowerContext 记忆
        result = await self.pc_service.revise_memory(
            scope_id,
            artifact_id,
            revision,
            "preference",  # kind 保持不变
            new_text,
            reason or "用户更新偏好"
        )
        
        # 同时更新本地项目记录中的偏好文本
        self.projects[project_id]["preferences"] = new_text
        self._save_data()
        
        return result
