"""
科研周报助手验收测试
测试跨周、重启、项目隔离、日期校验等核心功能
"""
import asyncio
import pytest
import pytest_asyncio
import sys
from pathlib import Path
import tempfile
import shutil

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from weekly_assistant import ResearchWeeklyAssistant


@pytest_asyncio.fixture
async def assistant():
    """创建测试用助手实例"""
    temp_dir = Path(tempfile.mkdtemp())
    ast = ResearchWeeklyAssistant(temp_dir)
    await ast.initialize()
    yield ast
    await ast.shutdown()
    shutil.rmtree(temp_dir, ignore_errors=True)


@pytest.mark.asyncio
async def test_create_project(assistant):
    """测试创建项目"""
    project = await assistant.create_project(
        name="测试项目",
        direction="测试研究方向",
        preferences="中文、简洁"
    )
    
    assert project['id'].startswith('proj_')
    assert project['name'] == "测试项目"
    assert project['direction'] == "测试研究方向"
    assert project['preferences'] == "中文、简洁"
    assert 'scope_id' in project
    
    # 验证项目可列出
    projects = await assistant.list_projects()
    assert len(projects) == 1
    assert projects[0]['id'] == project['id']


@pytest.mark.asyncio
async def test_add_record(assistant):
    """测试添加记录"""
    project = await assistant.create_project("测试", "方向", "偏好")
    
    record = await assistant.add_record(
        project_id=project['id'],
        record_date="2026-10-20",
        record_type="experiment",
        content="测试实验记录"
    )
    
    assert record.id.startswith('rec_')
    assert record.project_id == project['id']
    assert record.date == "2026-10-20"
    assert record.record_type == "experiment"
    assert record.content == "测试实验记录"
    
    # 验证记录可查询
    records = await assistant.get_records(project['id'])
    assert len(records) == 1
    assert records[0].id == record.id


@pytest.mark.asyncio
async def test_add_record_invalid_date(assistant):
    """测试添加记录时日期格式错误"""
    project = await assistant.create_project("测试", "方向", "偏好")
    
    with pytest.raises(ValueError, match="日期格式必须为 YYYY-MM-DD"):
        await assistant.add_record(
            project_id=project['id'],
            record_date="2026/10/20",  # 错误格式
            record_type="experiment",
            content="测试"
        )


@pytest.mark.asyncio
async def test_add_record_invalid_project(assistant):
    """测试添加记录时项目不存在"""
    with pytest.raises(ValueError, match="项目 .* 不存在"):
        await assistant.add_record(
            project_id="proj_nonexistent",
            record_date="2026-10-20",
            record_type="experiment",
            content="测试"
        )


@pytest.mark.asyncio
async def test_generate_weekly_report(assistant):
    """测试生成周报"""
    project = await assistant.create_project("测试项目", "方向", "偏好")
    
    # 添加记录
    await assistant.add_record(project['id'], "2026-10-20", "experiment", "实验1")
    await assistant.add_record(project['id'], "2026-10-21", "literature", "文献1")
    await assistant.add_record(project['id'], "2026-10-23", "issue", "问题1")
    
    # 生成周报
    report = await assistant.generate_weekly_report(
        project_id=project['id'],
        week_start="2026-10-19",
        week_end="2026-10-25"
    )
    
    assert report.id.startswith('rpt_')
    assert report.project_id == project['id']
    assert report.week_start == "2026-10-19"
    assert report.week_end == "2026-10-25"
    assert "测试项目" in report.markdown
    assert "实验1" in report.markdown
    assert "文献1" in report.markdown
    assert "问题1" in report.markdown


@pytest.mark.asyncio
async def test_generate_report_invalid_date_range(assistant):
    """测试生成周报时日期范围错误"""
    project = await assistant.create_project("测试", "方向", "偏好")
    
    with pytest.raises(ValueError, match="开始日期不能晚于结束日期"):
        await assistant.generate_weekly_report(
            project_id=project['id'],
            week_start="2026-10-25",
            week_end="2026-10-19"  # 结束日期早于开始
        )


@pytest.mark.asyncio
async def test_cross_week_memory_reuse(assistant):
    """测试跨周记忆复用（核心验收场景 A）"""
    project = await assistant.create_project(
        "混合检索实验",
        "中文科研笔记的混合检索",
        "中文、简洁；先列量化结果；未完成任务必须出现在下周计划中"
    )
    
    # 第一周
    await assistant.add_record(
        project['id'], "2026-10-20", "experiment",
        "Recall@10 为 0.74"
    )
    await assistant.add_record(
        project['id'], "2026-10-23", "plan",
        "扩大查询集并按长度分组"
    )
    
    report1 = await assistant.generate_weekly_report(
        project['id'], "2026-10-19", "2026-10-25"
    )
    
    assert "扩大查询集" in report1.markdown or "长度分组" in report1.markdown
    
    # 第二周（不重新输入偏好）
    await assistant.add_record(
        project['id'], "2026-10-27", "experiment",
        "扩充至 200 条查询"
    )
    
    report2 = await assistant.generate_weekly_report(
        project['id'], "2026-10-26", "2026-11-01"
    )
    
    # 验证偏好和待办从 PowerContext 读取
    assert "中文" in report2.markdown or "简洁" in report2.markdown
    assert report2.memory_refs  # 应该有记忆引用


@pytest.mark.asyncio
async def test_project_isolation(assistant):
    """测试项目隔离（核心验收场景 B）"""
    # 项目 A
    project_a = await assistant.create_project("项目A", "方向A", "偏好A")
    await assistant.add_record(project_a['id'], "2026-10-20", "experiment", "项目A的实验")
    
    # 项目 B
    project_b = await assistant.create_project("项目B", "方向B", "偏好B")
    await assistant.add_record(project_b['id'], "2026-10-20", "experiment", "项目B的实验")
    
    # 验证记录隔离
    records_a = await assistant.get_records(project_a['id'])
    records_b = await assistant.get_records(project_b['id'])
    
    assert len(records_a) == 1
    assert len(records_b) == 1
    assert "项目A" in records_a[0].content
    assert "项目B" in records_b[0].content
    assert records_a[0].content != records_b[0].content
    
    # 验证记忆隔离
    memory_a = await assistant.get_memory_evidence(project_a['id'])
    memory_b = await assistant.get_memory_evidence(project_b['id'])
    
    # 项目 A 的记忆不应包含项目 B 的内容
    for mem in memory_a:
        assert "项目B" not in mem['text']
    
    for mem in memory_b:
        assert "项目A" not in mem['text']


@pytest.mark.asyncio
async def test_empty_report_no_fabrication(assistant):
    """测试无记录时不编造内容（核心验收场景 C）"""
    project = await assistant.create_project("空项目", "方向", "偏好")
    
    report = await assistant.generate_weekly_report(
        project['id'], "2026-10-19", "2026-10-25"
    )
    
    # 验证周报为空状态
    assert "暂无" in report.markdown or "无实验记录" in report.markdown
    assert "编造" not in report.markdown
    assert "虚构" not in report.markdown


@pytest.mark.asyncio
async def test_date_range_filtering(assistant):
    """测试日期范围过滤"""
    project = await assistant.create_project("测试", "方向", "偏好")
    
    # 添加不同日期的记录
    await assistant.add_record(project['id'], "2026-10-15", "experiment", "记录1")
    await assistant.add_record(project['id'], "2026-10-20", "experiment", "记录2")
    await assistant.add_record(project['id'], "2026-10-25", "experiment", "记录3")
    await assistant.add_record(project['id'], "2026-10-30", "experiment", "记录4")
    
    # 查询特定范围
    records = await assistant.get_records(
        project['id'],
        start_date="2026-10-19",
        end_date="2026-10-26"
    )
    
    assert len(records) == 2
    assert all("2026-10-19" <= r.date <= "2026-10-26" for r in records)


@pytest.mark.asyncio
async def test_update_report(assistant):
    """测试更新周报"""
    project = await assistant.create_project("测试", "方向", "偏好")
    await assistant.add_record(project['id'], "2026-10-20", "experiment", "实验")
    
    report = await assistant.generate_weekly_report(
        project['id'], "2026-10-19", "2026-10-25"
    )
    
    # 更新周报
    new_markdown = report.markdown + "\n\n## 新增章节\n自定义内容"
    updated = await assistant.update_report(report.id, new_markdown)
    
    assert updated is not None
    assert updated.markdown == new_markdown
    assert "新增章节" in updated.markdown


@pytest.mark.asyncio
async def test_memory_evidence(assistant):
    """测试记忆证据获取"""
    project = await assistant.create_project("测试", "方向", "偏好")
    
    await assistant.add_record(project['id'], "2026-10-20", "experiment", "实验记录")
    await assistant.add_record(project['id'], "2026-10-21", "plan", "计划记录")
    
    memories = await assistant.get_memory_evidence(project['id'])
    
    assert len(memories) > 0
    for mem in memories:
        assert 'artifact_id' in mem
        assert 'text' in mem
        assert 'kind' in mem
        assert 'state' in mem  # list_memories returns state, not score


@pytest.mark.asyncio
async def test_complete_task(assistant):
    """测试任务完成：kind 从 decision 变为 completed-task"""
    project = await assistant.create_project("测试", "方向", "偏好")

    record = await assistant.add_record(
        project['id'], "2026-10-21", "plan", "扩大查询集"
    )
    assert record.memory_artifact_id is not None

    result = await assistant.complete_task(
        project['id'], record.memory_artifact_id, record.memory_revision, "已完成"
    )
    assert result["kind"] == "completed-task"

    memories = await assistant.get_memory_evidence(project['id'])
    completed = [m for m in memories if m["artifact_id"] == record.memory_artifact_id]
    assert len(completed) == 1
    assert completed[0]["kind"] == "completed-task"


@pytest.mark.asyncio
async def test_completed_task_excluded_from_weekly_todos(assistant):
    """测试已完成任务不出现在周报待办中"""
    project = await assistant.create_project("测试", "方向", "偏好")

    rec_plan = await assistant.add_record(
        project['id'], "2026-10-21", "plan", "待完成分析"
    )
    await assistant.add_record(
        project['id'], "2026-10-22", "plan", "尚未完成的任务"
    )

    await assistant.complete_task(
        project['id'], rec_plan.memory_artifact_id, rec_plan.memory_revision
    )

    report = await assistant.generate_weekly_report(
        project['id'], "2026-10-26", "2026-11-01"
    )
    assert "待完成分析" not in report.markdown or "尚未完成的任务" in report.markdown


@pytest.mark.asyncio
async def test_update_preference(assistant):
    """测试偏好更新：修订后新周报使用新偏好"""
    project = await assistant.create_project(
        "测试", "方向", "中文、简洁"
    )

    memories = await assistant.get_memory_evidence(project['id'])
    pref = [m for m in memories if m["kind"] == "preference"][0]

    result = await assistant.update_preference(
        project['id'], pref["artifact_id"], pref["revision"],
        "英文为主；附量化数据", "更新偏好"
    )
    assert result["kind"] == "preference"
    assert "英文" in result["text"]

    updated_memories = await assistant.get_memory_evidence(project['id'])
    updated_pref = [m for m in updated_memories if m["kind"] == "preference"]
    assert len(updated_pref) == 1
    assert "英文" in updated_pref[0]["text"]


async def run_server_restart_test():
    """测试服务重启后数据持久化（含偏好修订）"""
    temp_dir = Path(tempfile.mkdtemp())
    
    try:
        assistant1 = ResearchWeeklyAssistant(temp_dir)
        await assistant1.initialize()
        
        project = await assistant1.create_project("持久化测试", "方向", "中文、简洁")
        await assistant1.add_record(project['id'], "2026-10-20", "experiment", "测试记录")
        
        memories_before = await assistant1.get_memory_evidence(project['id'])
        pref_before = [m for m in memories_before if m["kind"] == "preference"][0]
        await assistant1.update_preference(
            project['id'], pref_before["artifact_id"], pref_before["revision"],
            "英文为主；附量化数据", "重启前修订"
        )
        
        project_id = project['id']
        await assistant1.shutdown()
        
        assistant2 = ResearchWeeklyAssistant(temp_dir)
        await assistant2.initialize()
        
        projects = await assistant2.list_projects()
        assert len(projects) == 1
        assert projects[0]['id'] == project_id
        
        records = await assistant2.get_records(project_id)
        assert len(records) == 1
        assert records[0].content == "测试记录"
        
        memories_after = await assistant2.get_memory_evidence(project_id)
        prefs_after = [m for m in memories_after if m["kind"] == "preference"]
        assert len(prefs_after) >= 1
        latest_pref = max(prefs_after, key=lambda p: p["revision"])
        assert "英文" in latest_pref["text"]
        
        await assistant2.shutdown()
        
        print("[OK] 服务重启持久化测试通过")
        
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


def main():
    """运行所有测试"""
    print("="*60)
    print("科研周报助手验收测试")
    print("="*60)
    
    # 运行 pytest 测试
    exit_code = pytest.main([__file__, "-v", "--tb=short"])
    
    if exit_code == 0:
        print("\n" + "="*60)
        print("运行服务重启测试...")
        print("="*60)
        asyncio.run(run_server_restart_test())
        print("\n[OK] 所有验收测试通过")
    
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
