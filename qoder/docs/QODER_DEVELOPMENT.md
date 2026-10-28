# QODER_DEVELOPMENT.md

开发记录与决策说明。所有样例数据均为合成数据，不代表真实科研内容。

## 实际 Qoder 会话与开发分工

- 工具：Qoder CN CLI `1.1.80`，本机已登录个人账号。
- 主要开发会话：`2e6369c5-1f51-4db2-890b-5f830eb3f767`。
- 该真实会话完成应用主体、Web 界面、静态展示站点、样例脚本、15 项测试与运行文档；不是仅用于网站发布。
- Codex 协助需求整理、独立验收、PowerContext 新旧接口兼容修正、数据校验与 Git 交付；完整 HTTP 进程重启验证脚本由独立复核补充。
- 真实 CLI 工具调用摘录和最终文件哈希见 [qoder-provenance.json](evidence/qoder-provenance.json)。原始 CLI 会话保存在本机 Qoder 历史中，可用 `qoderclicn --resume 2e6369c5-1f51-4db2-890b-5f830eb3f767` 核对。
- 账号 UID 应以 Qoder 个人资料或平台官方返回值为准，本文不从头像地址推测 UID。提交表若另需 UID，请在个人资料页核对填写。

## 实际运行证据

- [完整 HTTP 进程重启验证](evidence/process-restart.json)：Python 3.11.9、PowerContext 1.4.1，9 项实际检查通过。
- [真实浏览器验收](evidence/browser-acceptance.json)：1440×1000 与 390×844，项目选择、偏好更新、任务完成、Markdown 保存与导出通过，无页面脚本错误。
- [第二周周报](evidence/week-two.md)、[浏览器导出结果](evidence/browser-export.md)。
- [本地周报截图](evidence/report-desktop-full.png)、[真实记忆截图](evidence/memory-desktop.png)、[手机截图](evidence/report-mobile-full.png)。

截图中的研究内容全部为合成样例。HTTP 验证使用全新临时数据，并终止完整应用进程后重启，不使用接口模拟或本地 JSON 冒充 PowerContext 记忆。

## 开发环境

- Python 3.11+
- 虚拟环境：`qoder/.venv/`（使用 `qoder/.venv/Scripts/python.exe` 执行）
- 操作系统：Windows 10/11
- 分支：`qoder-research-weekly`
- 基线分支：`2026-competition-ecosystem`

## 依赖安装

```bash
cd qoder
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

`requirements.txt` 中所有版本均为实际测试通过的精确版本。

## 架构决策

### 1. PowerContext 服务器生命周期

PowerContext 服务器作为进程内嵌服务启动，与 FastAPI 应用共享同一进程：

- `PowerContextService.start()` 在后台线程启动 uvicorn 服务器
- 使用随机端口绑定 `127.0.0.1`，避免端口冲突
- 通过 `PowerContextClient` 与服务器通信
- `lifespan` 上下文管理器确保启动和关闭顺序

### 2. 记忆类型映射

| 业务概念 | PowerContext kind | 说明 |
|---------|-------------------|------|
| 汇报偏好 | `preference` | 项目创建时保存 |
| 实验记录 | `observation` | 每次添加记录时保存 |
| 文献阅读 | `reference` | 每次添加记录时保存 |
| 问题与风险 | `constraint` | 每次添加记录时保存 |
| 计划与待办 | `decision` | 活跃待办 |
| 已完成任务 | `completed-task` | 由 decision 修订而来 |

### 3. 任务完成机制

使用 `replace_artifact` API 将 `kind=decision` 的记忆修订为 `kind=completed-task`：

- 保留原始文本和历史版本
- 使用 If-Match ETag（`"revision:N"`）确保并发安全
- 周报生成时只筛选 `kind=decision` 且 `state=active` 的记忆
- 不使用 `retire_memory_entry`（该 API 不支持 atomic-memory family）

### 4. 偏好更新机制

使用 `replace_artifact` API 修订 `kind=preference` 的记忆：

- kind 保持不变，text 更新为新内容
- revision 自动递增
- 本地 `projects.json` 中的偏好文本同步更新

### 5. 数据一致性

- 写入顺序：先调用 PowerContext API，成功后再写入本地 JSON
- 原子保存：JSON 文件使用 `tempfile.mkstemp` + `os.replace` 实现原子写入
- 失败处理：PowerContext 调用失败时不保存本地数据

### 6. 记忆列表查询

使用 `list_memory_entries` API（游标分页），按 kind 字段分类过滤：

- 不使用关键词搜索（`search_memory`），避免遗漏
- 周报生成时获取所有活跃记忆，按 kind 分类
- 记忆证据页面获取所有记忆（含已停用）

### 7. 前端项目选择

三个面板（记录、周报、记忆）各自维护独立的项目选择状态：

- `state.recordProjectId`、`state.reportProjectId`、`state.memoryProjectId`
- 下拉框事件监听器只绑定一次（`state.selectListenersBound` 标志）
- 项目卡片提供快捷按钮直接跳转到对应面板

### 8. 跨域策略

不使用通配符 CORS。前端页面通过同源静态文件服务（`/static`），API 请求同源，无需跨域。

## 数据目录

默认数据目录：`qoder/data/`

可通过环境变量指定独立数据目录：

```bash
set RESEARCH_WEEKLY_DATA_DIR=C:\path\to\data
qoder/.venv/Scripts/python.exe qoder/src/server.py
```

## 验收测试

```bash
cd qoder
.venv/Scripts/python.exe -m pytest tests/test_acceptance.py -v
```

测试覆盖：
- 项目创建与列出
- 记录添加与日期验证
- 周报生成与日期范围验证
- 跨周记忆复用（场景 A）
- 项目隔离（场景 B）
- 空报告不编造内容（场景 C）
- 任务完成（kind 从 decision 变为 completed-task）
- 偏好更新（revision 递增）
- 服务重启后数据持久化（含偏好修订）

## 样例数据

```bash
cd qoder
.venv/Scripts/python.exe scripts/init_sample_data.py
```

幂等设计：已有项目时跳过初始化。所有样例数据均为合成数据。

## 已知限制

1. 无 LLM 增强：当前版本使用规则模式生成周报
2. 单用户本地运行：不支持多用户并发
3. PowerContext 服务器随应用启动/停止
4. 周报生成模式说明：
   - 自动应用：量化结果优先排序（当偏好包含"量化"或"结果"时）
   - 人工参考：其他自由文本偏好显示在周报中供人工检查
   - 不声称自动翻译、智能总结或语义理解

## 文件清单

```
qoder/
  src/
    server.py                 FastAPI HTTP 服务器
    weekly_assistant.py       业务逻辑层
    powercontext_service.py   PowerContext 服务封装
  static/
    index.html                前端页面
    style.css                 样式表
    app.js                    前端逻辑
  site/
    index.html                静态展示站点
    style.css                 展示站点样式
    demo.js                   演示交互
  tests/
    test_acceptance.py        验收测试
  scripts/
    init_sample_data.py       样例数据初始化
  data/                       运行时数据（自动生成）
  docs/
    ACCEPTANCE_PLAN.md        验收场景计划
    QODER_DEVELOPMENT.md      本文件
  requirements.txt            Python 依赖
  README.md                   项目说明
```
