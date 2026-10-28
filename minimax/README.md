# 规有所依：SDD 上下文模块

这是 MiniMax × OceanBase 那道题的作品，放在 `RYB/minimax/`。它给一个小任务列表配上下文：规格、要改的函数、测试，以及做到哪一步了。

业务例子只有一件事：给任务列表加上按状态筛选，原来的排序不能变。`filter_tasks` 现在会抛 `NotImplementedError`，所以功能测试在改之前失败。`sort_tasks` 已经按规格工作，回归测试现在就能过。

## 版本

- Python 3.11（本机用的是 PowerContext 仓库的 `.venv`，3.11.16）
- `pylibseekdb==1.4.0.post2`，嵌入式 seekdb，只支持 Linux 和 macOS
- PowerContext：比赛仓库 `/data02/quan24/powercontext` 的 builtin 运行时，SQLite 文件库
- MiniMax：OpenAI 兼容的 `POST {MINIMAX_BASE_URL}/chat/completions`，默认地址 `https://api.minimax.cn/v1`，默认模型 `MiniMax-M3`

密钥只放环境变量，不要写进仓库：

```bash
export MINIMAX_API_KEY="你的密钥"
# 可选
export MINIMAX_BASE_URL="https://api.minimax.cn/v1"
export MINIMAX_MODEL="MiniMax-M3"
```

## 准备

在 PowerContext 那个虚拟环境里装 seekdb 的 Python 包（本机已经装过）：

```bash
cd /data02/quan24/powercontext
uv pip install -r /data02/quan24/RYB/minimax/requirements.txt
```

## 调用

都在 `/data02/quan24/RYB/minimax` 里执行，解释器必须是上面那个虚拟环境，里面已经能 `import powercontext`。

```bash
cd /data02/quan24/RYB/minimax
PY=/data02/quan24/powercontext/.venv/bin/python

# 把规格、代码、测试导入 seekdb
$PY -m minimax init

# 打印这次任务的上下文。内容来自数据库查询和 PowerContext 里的进度
$PY -m minimax context

# 跑测试。改代码之前，功能测试失败，排序测试通过
$PY -m minimax test

# 有密钥时，让 MiniMax 按上下文改 sample_app/tasks.py
$PY -m minimax apply

# 清空 data/，并把 tasks.py 恢复成还没实现筛选的版本
$PY -m minimax reset

# 从头检查：改前失败、查询结果、规格改完再导入、进程重启后读进度
$PY -m minimax check
```

`context` 的输入是任务句子，默认读 `sample_app/manifest.json` 里的 `task`。输出四块：适用规格、要改的代码和符号、功能测试和回归测试、已完成 / 待办 / 验证结果。

## 已知限制

没有 `MINIMAX_API_KEY` 时，`check` 不会改代码。`apply` 会直接失败，避免把人手改的文件说成模型改的。

嵌入式 seekdb 一次只开一个进程。Windows 上这个包没有嵌入式库。

交到测评平台时，把整个 `minimax/` 目录放进 Fork 的 `2026-competition-ecosystem` 分支。平台不看 `RYB` 这个路径。
