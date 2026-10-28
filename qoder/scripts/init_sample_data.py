"""
初始化合成样例数据
创建两周的研究记录，用于演示和测试
所有数据均为合成样例，非真实科研数据
"""
import asyncio
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from weekly_assistant import ResearchWeeklyAssistant


async def init_sample_data():
    """初始化合成样例数据（幂等：已有项目时跳过）"""
    data_dir = Path(os.environ.get(
        "RESEARCH_WEEKLY_DATA_DIR",
        str(Path(__file__).parent.parent / "data")
    ))
    assistant = ResearchWeeklyAssistant(data_dir)

    print("正在初始化科研周报助手...")
    print(f"数据目录：{data_dir}")
    await assistant.initialize()

    projects = await assistant.list_projects()
    if projects:
        print(f"已存在 {len(projects)} 个项目，跳过初始化。")
        print("如需独立体验，请指定一个新的 RESEARCH_WEEKLY_DATA_DIR；现有数据将保留。")
        await assistant.shutdown()
        return

    print("创建合成样例项目...")

    project1 = await assistant.create_project(
        name="混合检索实验",
        direction="中文科研笔记的混合检索",
        preferences="中文、简洁；先列量化结果；未完成任务必须出现在下周计划中"
    )
    print(f"[OK] 创建项目：{project1['name']} (ID: {project1['id']})")

    print("\n添加第一周研究记录...")

    await assistant.add_record(
        project1['id'], "2026-10-20", "experiment",
        "在合成数据集上，关键词检索 Recall@10 为 0.62，混合检索为 0.74；本轮仅测试 100 条查询，尚未做显著性检验"
    )
    print("  [OK] 2026-10-20 实验记录")

    await assistant.add_record(
        project1['id'], "2026-10-21", "literature",
        "阅读样例文献摘要，整理稀疏与稠密检索的差异。该记录是演示资料，无真实 DOI"
    )
    print("  [OK] 2026-10-21 文献记录")

    await assistant.add_record(
        project1['id'], "2026-10-23", "issue",
        "长查询结果不稳定，计划扩大查询集并按长度分组"
    )
    print("  [OK] 2026-10-23 问题记录")

    await assistant.add_record(
        project1['id'], "2026-10-24", "plan",
        "扩大查询集并按长度分组"
    )
    print("  [OK] 2026-10-24 待办（将在第二周从 PowerContext 继续读取）")

    print("\n生成第一周周报...")
    report1 = await assistant.generate_weekly_report(
        project1['id'], "2026-10-19", "2026-10-25"
    )
    print(f"  [OK] 第一周周报已生成 (ID: {report1.id})")

    print("\n添加第二周研究记录...")

    await assistant.add_record(
        project1['id'], "2026-10-27", "experiment",
        "扩充至 200 条查询，尚未完成长度分组分析"
    )
    print("  [OK] 2026-10-27 实验记录")

    await assistant.add_record(
        project1['id'], "2026-10-29", "plan",
        "计划下周完成长度分组分析，并验证混合检索在不同长度区间的表现"
    )
    print("  [OK] 2026-10-29 计划记录")

    print("\n生成第二周周报...")
    report2 = await assistant.generate_weekly_report(
        project1['id'], "2026-10-26", "2026-11-01"
    )
    print(f"  [OK] 第二周周报已生成 (ID: {report2.id})")

    print("\n创建第二个项目（用于验证项目隔离）...")
    project2 = await assistant.create_project(
        name="细胞图像标注",
        direction="基于深度学习的细胞图像自动标注方法",
        preferences="英文为主；重点说明模型架构和准确率；附带可视化样例"
    )
    print(f"[OK] 创建项目：{project2['name']} (ID: {project2['id']})")

    await assistant.add_record(
        project2['id'], "2026-10-22", "experiment",
        "使用 U-Net 基线模型在细胞数据集上测试，Dice 系数达到 0.85"
    )
    print("  [OK] 2026-10-22 实验记录")

    all_projects = await assistant.list_projects()
    print("\n" + "=" * 60)
    print("合成样例数据初始化完成")
    print("=" * 60)
    print(f"项目数量：{len(all_projects)}")
    print(f"记录数量：{len(assistant.records)}")
    print(f"周报数量：{len(assistant.reports)}")
    print("\n启动服务：qoder/.venv/Scripts/python.exe qoder/src/server.py")
    print("访问地址：http://127.0.0.1:8000")

    await assistant.shutdown()


if __name__ == "__main__":
    asyncio.run(init_sample_data())
