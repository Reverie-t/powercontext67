# 跑一局并留下证据

这份是一份**照着敲**的操作单，目标是产出赛题 §4.3 要的三样东西：可运行的应用、验证样例、
运行证据（截图 / 录屏 / 日志）。

> 为什么不能在 Windows 上直接跑：PowerContext 的嵌入式 seekdb 依赖 `pylibseekdb` 的 Linux
> wheel，Windows 没有。所以整条链路都放在 WSL2（或一台 Linux 机器）里跑，Windows 只负责开
> 浏览器。WSL2 的 `localhost` 会自动转发到 Windows，所以最后在 Windows 浏览器里访问
> `http://localhost` 是通的。

---

## 0. 前置检查（5 分钟）

在 **PowerShell（管理员）** 里：

```powershell
wsl --status
```

- 有输出、默认版本是 2 → 已就绪，跳到第 1 步。
- 提示"未安装"→ 执行下面这条，装完重启：

```powershell
wsl --install -d Ubuntu
```

重启后打开「Ubuntu」应用，设一个用户名密码。之后所有命令都在这个 Ubuntu 终端里执行，
**不要用 PowerShell**（除了这一步）。

进 Ubuntu 后先确认能访问项目目录：

```bash
ls /mnt/c/Users/qflsa/WorkBuddy/2026-10-28-19-21-25/repo/dify
```

能看到 `README.md`、`dsl/`、`scripts/` 就对了。

---

## 1. 装依赖（10 分钟，只需一次）

```bash
# 基础工具
sudo apt update && sudo apt install -y curl git python3 python3-venv

# uv（装 PowerContext 用）
curl -LsSf https://astral.sh/uv/install.sh | sh
source ~/.bashrc
uv --version

# Docker Engine + compose 插件
curl -fsSL https://get.docker.com | sudo sh
sudo usermod -aG docker $USER
newgrp docker          # 或者直接关掉终端重开，效果一样
docker version
```

`docker version` 同时打印 Client 和 Server 两段才算成功。只有 Client 说明守护进程没起：

```bash
sudo service docker start
```

---

## 2. 起 PowerContext（终端 A）

```bash
cd /mnt/c/Users/qflsa/WorkBuddy/2026-10-28-19-21-25/repo/dify
chmod +x scripts/start_powercontext.sh
./scripts/start_powercontext.sh
```

第一次会下载 `powercontext[cli,server,seekdb]==1.4.1` 和 pylibseekdb，两三分钟。

**成功的标志**：最后几行出现 `Uvicorn running on http://0.0.0.0:8000`，并且进程不退出。

如果它报 `unauthenticated` 或直接退出，检查脚本里有没有这一行（应该有）：

```bash
export POWERCONTEXT_SERVER_ALLOW_UNAUTHENTICATED_NON_LOOPBACK=true
```

验证（**另开一个终端 B**，A 不要关）：

```bash
curl -s http://127.0.0.1:8000/health/live
# 期望：{"status":"live"} 或类似 200 响应
```

---

## 3. 起 Dify（终端 B）

```bash
git clone https://github.com/langgenius/dify.git ~/dify
cd ~/dify/docker
cp .env.example .env
```

### 3.1 放行内网（必须，否则 HTTP 节点全被拦）

```bash
sed -i 's|^SSRF_PROXY_ALLOW_PRIVATE_IPS=.*|SSRF_PROXY_ALLOW_PRIVATE_IPS=10.0.0.0/8,172.16.0.0/12,192.168.0.0/16,127.0.0.0/8|' .env
grep SSRF_PROXY_ALLOW_PRIVATE_IPS .env
```

### 3.2 让容器解析宿主机

WSL2 里的 Docker 需要显式声明 `host.docker.internal`。**不要改官方 `docker-compose.yaml`**
（缩进容易改错，升级也冲突），加一个 override 文件就行：

```bash
cat > docker-compose.override.yaml <<'YAML'
services:
  api:
    extra_hosts:
      - "host.docker.internal:host-gateway"
  worker:
    extra_hosts:
      - "host.docker.internal:host-gateway"
YAML
```

Compose 会自动合并这个文件。验证：

```bash
docker compose config | grep -A2 extra_hosts
```

能看到两处 `host.docker.internal:host-gateway` 就对了。

### 3.3 起来

```bash
docker compose up -d
docker compose ps
```

> 如果 80 端口被别的程序占了（`netstat -ano | findstr :80` 能查），改 `.env` 里的
> `EXPOSE_NGINX_PORT=8080`，之后浏览器就用 `http://localhost:8080`。

等 `api`、`worker`、`web`、`db`、`redis`、`ssrf_proxy` 都是 `running`（`api` 首次启动要跑迁移，
大约 1-2 分钟，`docker compose logs -f api` 看到 `Application startup complete` 即可）。

### 3.4 打通性验证（**这一步别跳**）

```bash
docker compose exec api python -c "import urllib.request;print(urllib.request.urlopen('http://host.docker.internal:8000/health/live',timeout=5).status)"
```

> 用 python 而不是 curl：Dify 的 api 镜像是 slim 底包，不一定带 curl。

- 打印 `200` → 通了，继续。
- 打印 `000` → 容器解析不到宿主，或 PowerContext 没监听 `0.0.0.0`。
- 打印 `403` → SSRF 白名单没生效，`docker compose up -d` 重建一次 `ssrf_proxy`。

---

## 4. 配模型（2 分钟）

Windows 浏览器打开 `http://localhost`，第一次进要设管理员邮箱和密码。

头像 → **设置 → 模型供应商 → DeepSeek** → 填 API Key → 保存。

没有 DeepSeek 就装任意一个 OpenAI 兼容供应商，后面在 LLM 节点里换掉即可。

---

## 5. 导入 DSL（1 分钟）

**工作室 → 创建空白应用 → 导入 DSL 文件** → 选
`C:\Users\qflsa\WorkBuddy\2026-10-28-19-21-25\repo\dify\dsl\the-confession.chatflow.yml`

导入后检查两处：

1. 左侧「环境变量」里有 `PC_BASE_URL` = `http://host.docker.internal:8000`
2. `老严开口` 节点上如果显示"模型不可用"，点开重新选 DeepSeek / `deepseek-chat`

然后点右上角**发布** → **预览**。

---

## 6. 跑一局（3 分钟）

按这个顺序说，每一步都有用意：

| # | 你说 | 看什么 |
| --- | --- | --- |
| 1 | （打开应用，不发消息） | 开场白是不是老严的口吻，下面有没有 3 个建议问题 |
| 2 | `我昨晚在家看球赛，哪也没去。` | 老严追问细节；因为档案空，会说"档案室是空的" |
| 3 | `交代：我确实讨厌那条金鱼，它老盯着我看。` | 他抓住"讨厌"反问 |
| 4 | `我什么都不知道，我要走了。` | **他开始拿第 3 步的话压你**——这是记忆生效的第一个信号 |
| 5 | 关掉预览页，重新打开，发 `我真没干。` | **他仍然记得那条金鱼**——这是核心验收点 |

第 5 步如果失忆了，先回头看第 3 步的 `docker compose exec api curl` 是不是 200。

---

## 7. 截图清单（评审要看的就是这 5 张）

| # | 截什么 | 证明什么 | 放哪 |
| --- | --- | --- | --- |
| 1 | Dify 应用编辑页的**整张工作流图** | 9 个节点、8 条连线，Dify 承担编排 | `docs/shots/01-workflow.png` |
| 2 | 一局对话的前 4 轮 | 玩法成立、老严在审问 | `docs/shots/02-dialogue.png` |
| 3 | **重开之后**第 5 步的对话 | 跨会话记忆成立（核心） | `docs/shots/03-cross-session.png` |
| 4 | Dify **日志与标注**里某次运行，展开 `调取档案` 节点的输出 | 检索结果真的进了流程，不是模型编的 | `docs/shots/04-run-trace.png` |
| 5 | 终端里 `python scripts/verify_roundtrip.py --fresh` 的完整输出 | PowerContext 读写闭环，跨会话召回 | `docs/shots/05-roundtrip.png` |

截图放 `dify/docs/shots/`，然后在 `README.md` §5 里引用。

第 4 张最容易漏，但它恰好是赛题说的"节点执行记录 / 查询结果"，含金量最高。展开方法：
应用 → 右上角**日志与标注** → 点最近一次运行 → 找到 `调取档案` 节点 → 展开输出，能看到
`body` 里 `content` 字段就是档案原文。

补充一张也很有用：终端 A 里 PowerContext 的启动输出，能看到 `database_kind` 和 seekdb 数据目录。

---

## 8. 录屏（可选，30 秒够）

Windows 用 `Win + G` 录一段：打开应用 → 说两句话 → 关掉重开 → 老严提旧事。
这段比十张截图有说服力。

---

## 9. 跑通之后

```bash
cd /mnt/c/Users/qflsa/WorkBuddy/2026-10-28-19-21-25/repo/dify
python scripts/verify_roundtrip.py --fresh    # 把输出贴进 README §5.2
python scripts/seekdb_evidence.py             # 确认数据落在 seekdb
```

然后把 README §5.2 的"预期输出"换成你的真实输出，补上截图，一起提交。

---

## 卡住了看这里

| 症状 | 原因 | 处理 |
| --- | --- | --- |
| `start_powercontext.sh` 报 `Exec format error` | 在 Windows 的 Git Bash 里跑了 | 改用 WSL2 的 Ubuntu 终端 |
| `uv: command not found` | 装完没重开 shell | `source ~/.bashrc` |
| `docker: permission denied` | 没加进 docker 组 | `sudo usermod -aG docker $USER && newgrp docker` |
| `docker compose` 找不到 | 只有 docker 没有 compose 插件 | `sudo apt install docker-compose-plugin` |
| Dify 里 `调取档案` 返回 000 | `extra_hosts` 没配对 | `docker compose config \| grep -A2 extra_hosts` 检查 |
| Dify 里 `调取档案` 返回 403 | SSRF 白名单没生效 | 确认 `.env` 那行，`docker compose up -d` 重建 |
| 老严一直说"档案室是空的" | 三个 HTTP 节点在静默降级 | 看运行日志的 `status_code`，按上两行排查 |
| 导入 DSL 报版本错误 | Dify 版本太老 | 用 `main` 分支最新版；或照 README 附录手搭 |
