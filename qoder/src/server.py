"""
科研周报助手 HTTP API 服务器
"""
import asyncio
import os
import sys
from pathlib import Path
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, FileResponse
from pydantic import BaseModel
from typing import Optional

# 添加 src 目录到路径
sys.path.insert(0, str(Path(__file__).parent))

from weekly_assistant import ResearchWeeklyAssistant


# 全局助手实例
assistant: Optional[ResearchWeeklyAssistant] = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期管理"""
    global assistant
    data_dir = Path(os.environ.get("RESEARCH_WEEKLY_DATA_DIR",
                                    str(Path(__file__).parent.parent / "data")))
    assistant = ResearchWeeklyAssistant(data_dir)
    await assistant.initialize()
    print(f"科研周报助手已启动，数据目录：{data_dir}")
    yield
    await assistant.shutdown()
    print("科研周报助手已关闭")


app = FastAPI(
    title="科研周报助手",
    description="基于 PowerContext 的科研项目周报生成工具",
    version="1.0.0",
    lifespan=lifespan,
)

# 同源策略：只允许本地访问，不使用通配符 CORS
# 前端页面通过同源静态文件服务，无需跨域


# 请求/响应模型
class CreateProjectRequest(BaseModel):
    name: str
    direction: str
    preferences: str


class AddRecordRequest(BaseModel):
    project_id: str
    date: str
    record_type: str
    content: str


class GenerateReportRequest(BaseModel):
    project_id: str
    week_start: str
    week_end: str


class UpdateReportRequest(BaseModel):
    markdown: str


class CompleteTaskRequest(BaseModel):
    project_id: str
    artifact_id: str
    revision: int
    reason: Optional[str] = ""


class UpdatePreferenceRequest(BaseModel):
    project_id: str
    artifact_id: str
    revision: int
    new_text: str
    reason: Optional[str] = ""


# API 路由
@app.get("/")
async def root():
    """根路径重定向到前端页面"""
    return FileResponse(Path(__file__).parent.parent / "static" / "index.html")


@app.get("/api/health")
async def health():
    """健康检查"""
    return {"status": "ok", "service": "research-weekly-assistant"}


@app.post("/api/projects")
async def create_project(req: CreateProjectRequest):
    """创建研究项目"""
    try:
        project = await assistant.create_project(req.name, req.direction, req.preferences)
        return {"success": True, "project": project}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.get("/api/projects")
async def list_projects():
    """列出所有项目"""
    projects = await assistant.list_projects()
    return {"projects": projects}


@app.get("/api/projects/{project_id}")
async def get_project(project_id: str):
    """获取项目详情"""
    project = await assistant.get_project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="项目不存在")
    return {"project": project}


@app.post("/api/records")
async def add_record(req: AddRecordRequest):
    """添加研究记录"""
    try:
        record = await assistant.add_record(
            req.project_id, req.date, req.record_type, req.content
        )
        return {"success": True, "record": record.to_dict()}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/projects/{project_id}/records")
async def get_records(project_id: str, start_date: Optional[str] = None, end_date: Optional[str] = None):
    """获取项目记录"""
    records = await assistant.get_records(project_id, start_date, end_date)
    return {"records": [r.to_dict() for r in records]}


@app.post("/api/reports/generate")
async def generate_report(req: GenerateReportRequest):
    """生成周报"""
    try:
        report = await assistant.generate_weekly_report(
            req.project_id, req.week_start, req.week_end
        )
        return {"success": True, "report": report.to_dict()}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/reports/{report_id}")
async def get_report(report_id: str):
    """获取周报"""
    report = await assistant.get_report(report_id)
    if not report:
        raise HTTPException(status_code=404, detail="周报不存在")
    return {"report": report.to_dict()}


@app.get("/api/projects/{project_id}/reports")
async def list_reports(project_id: str):
    """列出项目周报"""
    reports = await assistant.list_reports(project_id)
    return {"reports": [r.to_dict() for r in reports]}


@app.put("/api/reports/{report_id}")
async def update_report(report_id: str, req: UpdateReportRequest):
    """更新周报内容"""
    report = await assistant.update_report(report_id, req.markdown)
    if not report:
        raise HTTPException(status_code=404, detail="周报不存在")
    return {"success": True, "report": report.to_dict()}


@app.get("/api/projects/{project_id}/memory")
async def get_memory_evidence(project_id: str):
    """获取项目记忆证据"""
    memories = await assistant.get_memory_evidence(project_id)
    return {"memories": memories}


@app.post("/api/tasks/complete")
async def complete_task(req: CompleteTaskRequest):
    """标记任务为已完成"""
    try:
        result = await assistant.complete_task(
            req.project_id, req.artifact_id, req.revision, req.reason
        )
        return {"success": True, "result": result}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.put("/api/preferences")
async def update_preference(req: UpdatePreferenceRequest):
    """更新项目偏好"""
    try:
        result = await assistant.update_preference(
            req.project_id, req.artifact_id, req.revision, req.new_text, req.reason
        )
        return {"success": True, "result": result}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# 挂载静态文件
static_dir = Path(__file__).parent.parent / "static"
if static_dir.exists():
    app.mount("/static", StaticFiles(directory=static_dir), name="static")


def main():
    """启动服务器"""
    import argparse
    import uvicorn
    parser = argparse.ArgumentParser(description="科研周报助手 HTTP 服务")
    parser.add_argument("--host", default="127.0.0.1", help="监听地址")
    parser.add_argument("--port", type=int, default=8000, help="监听端口")
    parser.add_argument("--data-dir", default=None, help="数据目录（默认 qoder/data 或 RESEARCH_WEEKLY_DATA_DIR）")
    args = parser.parse_args()
    if args.data_dir:
        os.environ["RESEARCH_WEEKLY_DATA_DIR"] = args.data_dir
    uvicorn.run(app, host=args.host, port=args.port, log_level="info")


if __name__ == "__main__":
    main()
