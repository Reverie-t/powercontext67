# 科研周报助手

基于 PowerContext 1.4.1 的科研项目周报生成工具，帮助科研人员管理分散的实验记录、文献阅读、问题与待办，自动生成有出处、可修改、可导出的周报。

作品网站：[科研周报助手（Qoder Sites）](https://67d782369a0b46c19ea5eef369627671-0bxo40pomch.qoder.zone)。网站公开访问，提供合成流程演示、真实本地运行截图与运行指南；完整应用按下面的步骤在本地运行。

实际验证记录见 [VERIFICATION_LOG.md](docs/VERIFICATION_LOG.md)，Qoder 开发记录见 [QODER_DEVELOPMENT.md](docs/QODER_DEVELOPMENT.md)。

## 核心特性

- **真实记忆持久化**：使用 PowerContext 1.4.1 存储项目偏好、研究记录和待办事项，支持跨会话、跨服务重启读取
- **项目隔离**：每个研究项目独立的 scope，记忆互不干扰
- **按周生成周报**：选择日期范围，自动整理本周记录和历史待办
- **任务完成跟踪**：标记已完成的任务不会继续出现在后续周报中
- **偏好管理**：更新汇报偏好后，后续周报自动应用新版本
- **可编辑导出**：周报支持 Markdown 编辑和导出
- **记忆证据透明**：清晰展示 PowerContext 的读写引用，包括 artifact_id 和 revision

## 技术栈

- **后端**：Python 3.11 + FastAPI + PowerContext 1.4.1
- **存储**：SQLite（PowerContext 内置）+ JSON（业务数据）
- **前端**：原生 HTML5 + CSS3 + JavaScript（无框架）

## 快速开始

### 1. 环境要求

- Python 3.11 或更高版本
- Git（用于克隆仓库）
- 现代浏览器（Chrome、Firefox、Edge 等）

### 2. 克隆仓库

```bash
git clone https://github.com/Reverie-t/powercontext67
cd powercontext67
git checkout qoder-research-weekly
```

### 3. 创建虚拟环境并安装依赖

```bash
cd qoder
python -m venv .venv

# Windows
.venv\Scripts\activate
pip install -r requirements.txt

# macOS / Linux
source .venv/bin/activate
python -m pip install -r requirements.txt

# 或使用国内镜像
pip install -i https://pypi.tuna.tsinghua.edu.cn/simple -r requirements.txt
```

### 4. 启动服务

```bash
python src/server.py
```

服务将在 `http://127.0.0.1:8000` 启动。

### 5. 访问应用

打开浏览器访问 [http://127.0.0.1:8000](http://127.0.0.1:8000)

### 6. 初始化合成样例数据（可选）

```bash
python scripts/init_sample_data.py
```

这将创建两个示例项目和两周的研究记录，用于演示和测试。

### 7. 运行验收测试

```bash
# 运行完整验收测试（包括跨周、重启、项目隔离）
python -m pytest tests/test_acceptance.py -v

# 完整应用进程终止后重启，以真实 HTTP 请求验证并导出证据
python scripts/verify_process_restart.py --output docs/evidence
```

## 使用流程

### 第一步：创建研究项目

1. 点击"研究项目"标签
2. 点击"新建项目"
3. 填写项目名称、研究方向和汇报偏好
4. 点击"创建"

**汇报偏好示例**：
- "中文、简洁；先列量化结果；未完成任务必须出现在下周计划中"
- "先列量化结果；保留实验条件与未完成事项"

当前规则模式自动应用量化结果优先排序；其他语言、风格等自由文本偏好会保留并展示，供人工检查，不自动翻译或改写内容。

### 第二步：添加研究记录

1. 切换到"研究记录"标签
2. 从下拉框选择项目
3. 点击"添加记录"
4. 选择日期、类型（实验/文献/问题/计划）
5. 填写内容
6. 点击"保存"

### 第三步：生成周报

1. 切换到"周报管理"标签
2. 从下拉框选择项目
3. 点击"生成周报"
4. 选择周报的起止日期
5. 点击"生成"

周报将自动：
- 整理本周所有记录
- 从 PowerContext 读取项目偏好
- 从 PowerContext 读取未完成的待办事项
- 生成带引用的 Markdown 格式周报

### 第四步：编辑和导出

1. 点击"查看"打开周报预览
2. 点击"编辑"修改内容
3. 点击"保存"保存修改
4. 点击"导出 Markdown"下载文件

### 第五步：标记任务完成

1. 在"记忆证据"标签查看项目的所有记忆
2. 找到需要标记完成的任务（kind=decision）
3. 点击"完成"按钮
4. 后续周报将不再包含此任务

### 第六步：更新偏好

1. 在"记忆证据"标签查看偏好记忆（kind=preference）
2. 点击"编辑"按钮
3. 修改偏好内容
4. 点击"保存"
5. 后续周报将应用新的偏好

## 项目结构

```
qoder/
├── src/                          # 源代码
│   ├── server.py                 # FastAPI HTTP 服务器
│   ├── weekly_assistant.py       # 业务逻辑层
│   └── powercontext_service.py   # PowerContext 服务封装
├── static/                       # Web 前端
│   ├── index.html
│   ├── style.css
│   └── app.js
├── site/                         # 静态展示站点
│   ├── index.html
│   ├── style.css
│   └── demo.js
├── tests/                        # 验收测试
│   └── test_acceptance.py
├── scripts/                      # 工具脚本
│   └── init_sample_data.py
├── data/                         # 运行时数据（自动生成）
│   ├── projects.json
│   ├── records.json
│   ├── reports.json
│   └── powercontext/
│       └── powercontext.db
├── docs/                         # 文档
│   ├── PROJECT_BRIEF.md
│   ├── ACCEPTANCE_PLAN.md
│   └── QODER_DEVELOPMENT.md
├── requirements.txt              # Python 依赖
└── README.md                     # 本文件
```

## PowerContext 集成说明

### 使用的 API

本项目使用 PowerContext 1.4.1 的以下真实 API：

- **CreateScopeRequest**：创建研究项目 scope
- **RememberMemoryRequest**：保存偏好、记录、待办
- **ListMemoryEntriesRequest**：列出所有记忆（按 kind 分类，游标分页）
- **GetArtifact + GetAtomicMemoryState**：获取单条记忆的当前内容和状态
- **ReplaceArtifactRequest**：修订偏好内容或标记任务完成（kind 从 decision 变为 completed-task）
- **PrepareContextRequest**：准备上下文用于周报生成

### 记忆类型映射

- **preference**：项目汇报偏好
- **observation**：实验记录
- **reference**：文献阅读
- **constraint**：问题与风险
- **decision**：计划与待办（活跃）
- **completed-task**：已完成的计划（由 decision 修订而来）

### 任务完成状态

本项目通过 PowerContext 1.4.1 的 `replace_artifact` API 实现任务完成跟踪：

- 当用户标记一个待办为已完成时，系统将该记忆的 `kind` 从 `decision` 修订为 `completed-task`
- 原始文本和历史版本保留在 PowerContext 中
- 周报生成时只筛选 `kind=decision` 且 `state=active` 的记忆作为待办
- 已完成的任务（`kind=completed-task`）自动排除在后续周报的"下周计划"之外

### 偏好更新

通过 `replace_artifact` API 修订 `kind=preference` 的记忆，更新后立即生效：
- 保留完整修订历史（revision 递增）
- 使用 If-Match ETag 确保并发安全
- 下次生成周报时自动使用最新偏好

### 数据一致性

- **写入顺序**：先调用 PowerContext API，成功后再写入本地 JSON
- **原子保存**：JSON 文件使用临时文件 + rename 的原子写入方式
- **失败处理**：PowerContext 调用失败时，不会保存本地数据

## 验收场景

### 场景 A：跨周与重启后的记忆复用

1. 创建项目"混合检索实验"，设置偏好
2. 第一周添加实验、文献、问题记录，并以“计划”类型添加待办
3. 生成第一周周报
4. 关闭服务并重启
5. 第二周添加新记录
6. 生成第二周周报

**预期结果**：
- 偏好从 PowerContext 自动读取
- 第一周未完成的待办出现在第二周计划中
- 不把第一周成果误认为第二周新增
- 记忆证据显示实际 PowerContext 引用

### 场景 B：项目隔离

1. 创建项目 A 和项目 B
2. 分别添加记录
3. 查看各自的记忆证据

**预期结果**：
- 项目 A 的记忆中不包含项目 B 的记录
- 周报和引用严格隔离

### 场景 C：任务完成与偏好更新

1. 在记忆证据页面标记某个待办为已完成（kind 从 decision 变为 completed-task）
2. 生成新周报
3. 编辑项目偏好（通过 replace_artifact 修订）
4. 生成新周报

**预期结果**：
- 已完成的任务不出现在后续周报的"下周计划"中
- 新偏好应用到后续周报

### 场景 D：日期与错误处理

1. 生成日期范围错误的周报
2. 添加格式错误的记录

**预期结果**：
- 开始日期晚于结束日期时返回验证错误
- 日期格式错误时返回明确提示
- 无记录时给出空状态，不编造进展

## 已知限制

1. **无 LLM 增强**：当前版本使用规则模式生成周报，不调用大语言模型
2. **单用户本地运行**：设计为个人科研工具，不支持多用户并发
3. **PowerContext 服务器生命周期**：服务器随应用启动，应用关闭时停止
4. **合成样例数据**：演示和测试中使用的研究内容为合成样例

## 依赖版本

```
powercontext[server,client]==1.4.1
fastapi==0.162.0
uvicorn[standard]==0.54.0
pydantic==2.14.1
pydantic-settings==2.16.1
aiosqlite==0.22.1
httpx==0.28.1
pytest==9.2.0
pytest-asyncio==1.4.1
```

## 仓库信息

- **代码仓库**：https://github.com/Reverie-t/powercontext67
- **开发分支**：`qoder-research-weekly`
- **基线分支**：`2026-competition-ecosystem`
- **赛事**：2026 OceanBase Qoder 赛道

## 许可证

本项目遵循原仓库的许可证。

## 联系方式

如有问题或建议，请通过 GitHub Issues 反馈。
