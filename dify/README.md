# 口供 · The Confession

> 你被关进审讯室，昨晚八点之后的记忆一片空白。
> 审讯官老严手里有一摞纸——那是**你以前说过的每一句话**。
> 他一句一句念出来，问你这次怎么解释。

一个用 Dify Chatflow 编排、PowerContext 存记忆、seekdb 做持久化底座的文字审讯游戏。
**记忆不是附加功能，是玩法本身**：你这一轮说的话，会变成下一轮钉死你的证据。

---

## 一、作品是什么

### 1.1 玩法

你是一名嫌疑人，患了"隔夜失忆"。审讯官老严不问你昨晚干了什么——他问你**以前说过什么**。

| 你做的事 | 发生什么 |
| --- | --- |
| 随便说话 | 老严正常审问；如果他手里有你相关的旧口供，会念出来和你的新说法对照 |
| 输入 `交代：……` | 你主动补一条口供，会被记进档案，之后可能被拿来对付你 |
| 输入 `翻供` | 试试撤回上一句。档案室不会真的删，但你可以看看老严的反应 |
| 退出重进 | **老严还记得**。这是整个作品的题眼 |

案件是固定的：城南「老坎火锅」门口一缸金鱼连缸失踪，老板说值三万八，其中一条叫「大壮」，养了七年。监控坏了，现场只有半个脚印和一张被踩烂的外卖小票。老严不确定是不是你干的，他只是在等你说错话。

### 1.2 为什么好玩

- **你说的话会反过来对付你。** 这是审讯题材天然的戏剧张力，而它需要一个真的记得住的东西。PowerContext 就是这个东西。
- **可以主动埋钩子。** 有经验的玩家会故意留一句含糊的口供，看下一轮能不能圆回来。
- **每一局都在积累。** 第 1 次玩是空白档案，第 5 次玩老严手里已经有二十条你说的原话。
- **喜剧底色。** 案子荒诞（三万八的金鱼、叫大壮的那条），老严一本正经地较真，压迫感和好笑同时存在。

### 1.3 体验方式

Dify 自带 Web App 就是入口，不需要另做前端。打开应用 → 直接打字。开场白和三个建议问题已经把玩法说完了，评审不需要读文档也能上手。

---

## 二、技术架构与分工

```
玩家
 │
 ▼
Dify Chatflow（Web App）
 │  ① POST /v1/scopes            建/取本玩家的档案室（按 idempotency_key 幂等）
 │  ② POST /v1/context/prepare   按玩家这句话去调档，拿回有字节上限的历史口供
 │  ③ LLM（DeepSeek）            老严带着档案说话，同时产出「台词」和「记录」
 │  ④ POST /v1/memory/remember   把这一轮的口供归档
 ▼
PowerContext Server 1.4.1
 │  记忆的语义层：Scope / Atomic Memory / PreparedContext / 检索
 ▼
seekdb（嵌入式）— 真实承载 Scope、Memory、Source 的全部数据
```

| 组件 | 担什么 | 对应赛题要求 |
| --- | --- | --- |
| **Dify** | 全部流程编排：建档案室、调档、调模型、拆台词、归档、回话；DSL 可导入 | 必选，承担核心流程 |
| **PowerContext** | 记忆的写入、检索、按字节预算装配成可注入的上下文；跨会话复用 | 记忆与上下文能力 |
| **seekdb** | PowerContext 的存储后端，口供、Scope 元数据、检索索引都落在 seekdb 里 | 数据存储职责 |

### 2.1 为什么不用官方 Dify 插件，而走 HTTP Request

PowerContext 仓库里已经有官方 Dify 插件（`integrations/dify/plugin`，安装标识 `knqiufan/powercontext` 0.0.1，20 个工具）。它能用，但**它的 `scope_id` 是配在 provider 凭证里的固定值**，官方 README 写得很清楚：

> All users and conversations using one credential share its Scope. This is a fixed application/team boundary, not automatic personal or conversation isolation.

也就是说，用插件的话所有玩家共用一本档案——第一个人说"我讨厌金鱼"，第十个人进来老严也会拿这句话怼他。这直接毁掉作品的核心设定。

所以这里用 **HTTP Request 节点直连 PowerContext 的 HTTP API**，把 `idempotency_key` 拼成 `dify-confession-{{sys.user_id}}`：

- `POST /v1/scopes` 在 `idempotency_key` 相同且请求摘要相同时，返回**同一个** `scope_id`（实现见 `ScopeApplication._create`），所以每次会话调一次也不会重复建，不需要额外的映射表或配套服务；
- Dify 的 Web App 给每个 end user 一个稳定的 `sys.user_id`，于是**每个玩家天然一本独立档案**。

插件本身是 experimental，且 README 明确说 "does not provide automatic recall or capture"，需要工作流显式串 `pc_prepare_context`。既然都要显式编排，直连 HTTP 反而更简单、更可控。

### 2.2 seekdb 的分工

seekdb 不是"装了个组件"，它是这个应用唯一的持久化位置：

- PowerContext 用 `POWERCONTEXT_SERVER_DATABASE_KIND=seekdb` 启动，嵌入式 seekdb 实例的目录由 `POWERCONTEXT_HOME` 决定；
- 玩家每一轮的口供（Atomic Memory）、档案室（Scope）、Source 证据、检索索引全部写在这一个实例里；
- 停掉服务再起，数据还在，老严照样记得。

Dify 工作流里没有直接连 seekdb 的节点——赛题也明确说明这不需要：

> 只要 seekdb 实际承担所声明的数据存储职责，且应用的主要功能可按说明正常体验，即满足 seekdb 的使用要求，无需在工作流中额外增加直接调用 seekdb 的节点。

怎么核对它真的在起作用，见 [§6 技术结合证据](#六技术结合证据怎么核对)。

---

## 三、目录结构

```
dify/
├── dsl/
│   └── the-confession.chatflow.yml   # 提交的 Dify DSL（Chatflow，version 0.3.0）
├── scripts/
│   ├── build_dsl.py                  # 生成 DSL（改流程改这里，别手改 YAML）
│   ├── check_dsl.py                  # 导入前的静态检查：连线、变量引用、code 输出
│   ├── test_flow.py                  # 用 DSL 里的真实 Code 节点跑 14 条边界用例
│   ├── start_powercontext.sh         # 用 seekdb 后端启动 PowerContext
│   ├── verify_roundtrip.py           # 不起 Dify，复现跨会话记忆闭环
│   └── seekdb_evidence.py            # 收集 seekdb 数据落地证据
├── docs/
│   └── run-and-capture.md            # 从零跑到出截图的操作单（含截图清单）
└── README.md
```

`scripts/` 里除了启动脚本，其余都是**可复现的举证工具**：不启动 Dify 也能验证 DSL 里的代码逻辑和整条记忆链路。

---

## 四、从零跑起来

> 只想尽快跑通并留下证据，直接看 [`docs/run-and-capture.md`](docs/run-and-capture.md)——那份是
> 照着敲的操作单，含截图清单。下面是完整的说明和取舍。

### 4.0 环境清单

| 项 | 版本 / 说明 |
| --- | --- |
| Dify | 1.17.x 或 1.18.x（DSL `version: 0.3.0`）。用官方 `docker/docker-compose.yaml` 部署 |
| PowerContext | `1.4.1`，装 `powercontext[cli,server,seekdb]` |
| Python | 3.11+（PowerContext 的要求；本仓库脚本用 3.9+ 语法即可） |
| uv | 装 PowerContext 用 |
| Node / 浏览器 | 无特殊要求，Chrome / Edge 最新版 |
| 模型 | 任意对话模型。DSL 默认 DeepSeek（`deepseek-chat`） |
| 操作系统 | **Linux / macOS**。嵌入式 seekdb 依赖 `pylibseekdb` 的原生 wheel，Windows 没有；Windows 请用 WSL2 |
| Embedding | 不需要。本作只用 PowerContext 的显式记忆与最小检索，不依赖向量服务 |

磁盘：seekdb 实例目录初始几十 MB，按口供量增长；Dify 官方 compose 约 2 GB 镜像。

### 4.1 启动 PowerContext（seekdb 后端）

```bash
cd dify
chmod +x scripts/start_powercontext.sh
./scripts/start_powercontext.sh
```

脚本做五件事：装 `powercontext[cli,server,seekdb]==1.4.1`、清掉会冲突的 `POWERCONTEXT_SERVER_DATABASE_URL`、
把后端切成 seekdb、监听 `0.0.0.0:8000`、关鉴权并显式 opt-in
`POWERCONTEXT_SERVER_ALLOW_UNAUTHENTICATED_NON_LOOPBACK=true`。

最后那个 opt-in 不能少：PowerContext 默认**拒绝**在非 loopback 地址上无鉴权启动，少了它会直接退出。

> 为什么要监听 `0.0.0.0` 而不是默认的 `127.0.0.1`：Dify 跑在容器里，容器访问宿主机的 loopback 是不通的。**这个配置只适合本机演示**，别把 8000 端口暴露到公网。要鉴权就把 `POWERCONTEXT_SERVER_ACCESS_MODE` 改成 `enforced` 并设 `POWERCONTEXT_SERVER_AUTH_TOKEN`，再给 DSL 里三个 HTTP 节点加 `Authorization: Bearer <token>` 头。

另开一个终端确认：

```bash
powercontext doctor
curl --silent --show-error http://127.0.0.1:8000/health/live
curl --silent --show-error http://127.0.0.1:8000/v1/capabilities
```

`/v1/capabilities` 的输出里能看到当前后端。数据目录默认在：

```bash
echo "${POWERCONTEXT_HOME:-$HOME/.local/share/powercontext}/seekdb"
```

### 4.2 启动 Dify

```bash
git clone https://github.com/langgenius/dify.git
cd dify/docker
cp .env.example .env
docker compose up -d
```

等 `docker compose ps` 里 `api`、`worker`、`web`、`db`、`redis` 都起来，浏览器打开 `http://localhost`，第一次进会要求设置管理员账号。

**但先别急着导入 DSL——必须做两处配置，否则 HTTP 节点连不到宿主机的 PowerContext。**

#### ① 放行内网地址（SSRF 白名单）

Dify 的 HTTP Request 节点默认走 `ssrf_proxy`，它**默认拒绝所有私有网段**。PowerContext 在宿主机内网，会被直接拦掉。官方 `.env.example` 里对这项的说明就是"当 Dify 需要从 HTTP Request 节点访问内网接口时必须设置"。

编辑 `dify/docker/.env`：

```dotenv
# 本地演示放行全部私有网段。只在本机跑时这样写没问题，别把这个 Dify 暴露到公网。
SSRF_PROXY_ALLOW_PRIVATE_IPS=10.0.0.0/8,172.16.0.0/12,192.168.0.0/16,127.0.0.0/8
```

要更收敛的话，只放行宿主机所在网段即可（`docker network inspect` 里的 Subnet，或 `host.docker.internal` 解析出的地址）。

#### ② 让容器能解析宿主机（Linux / WSL2 需要）

macOS / Windows 的 Docker Desktop 自带 `host.docker.internal`，跳过这步。

Linux 上别去手改官方 `docker-compose.yaml`（缩进容易改错，升级也冲突），加一个 override 文件：

```bash
cd dify/docker
cat > docker-compose.override.yaml <<'YAML'
services:
  api:
    extra_hosts:
      - "host.docker.internal:host-gateway"
  worker:
    extra_hosts:
      - "host.docker.internal:host-gateway"
YAML
docker compose config | grep -A2 extra_hosts   # 应该能看到两处
```

#### ③ 重建并验证

```bash
docker compose up -d
docker compose exec api python -c "import urllib.request;print(urllib.request.urlopen('http://host.docker.internal:8000/health/live',timeout=5).status)"
```

> 用 python 而不是 curl：Dify 的 api 镜像是 slim 底包，不一定带 curl。

打印 `200` 就通了。其余按下面排查：

| 现象 | 原因 |
| --- | --- |
| `URLError` / `Name or service not known` | 容器解析不到 `host.docker.internal`，`extra_hosts` 没配对；或 PowerContext 没在 `0.0.0.0` 上监听 |
| `HTTP Error 403` | `SSRF_PROXY_ALLOW_PRIVATE_IPS` 没生效，`docker compose up -d` 时没重建 `ssrf_proxy` |
| `403` 且上面都配了 | HTTP 节点的请求会带 `HTTP_PROXY` 环境变量；确认 `api` 容器的 `SSRF_PROXY_HTTP_URL` 指向的代理能访问该地址 |

### 4.3 配置模型

Dify 控制台 → 右上角头像 → **设置 → 模型供应商 → DeepSeek** → 填入你的 API Key。

没有 DeepSeek 也可以：装任意 OpenAI 兼容供应商，然后打开应用 → `老严开口` 节点 → 把模型换成你自己的。**只要是一个能稳定输出中文、听话照格式输出的对话模型就行。**

### 4.4 导入 DSL

Dify 控制台 → **工作室 → 创建空白应用 → 导入 DSL 文件** → 选择 `dsl/the-confession.chatflow.yml`。

导入后检查两处：

1. **环境变量**：左侧「环境变量」里应该有 `PC_BASE_URL`，默认 `http://host.docker.internal:8000`。Dify 和 PowerContext 不在一台机器时改这里，**不要改 DSL 文件**。
2. **模型**：`老严开口` 节点上如果显示"模型不可用"，重新选一次 DeepSeek / `deepseek-chat`。

然后点右上角**发布 → 运行**（或直接「预览」）。

### 4.5 应用入口

- 调试：应用编辑页右上角「预览」
- 对外：**发布 → 访问 API / 嵌入网站**，Dify 会给出 Web App 地址

---

### 4.6 备选：Dify 云版 + 公网隧道（没有 Docker 权限时）

如果手边只有一台不能装 Docker 的机器（比如只给了普通账号的实验室服务器），可以这样跑：

1. PowerContext 照 §4.1 起在那台机器上，监听 `0.0.0.0:8000`；
2. 用 Cloudflare 隧道把它变成一个公网 HTTPS 地址（单二进制，不需要 root）：

```bash
curl -sL -o cloudflared https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64
chmod +x cloudflared
nohup ./cloudflared tunnel --url http://localhost:8000 > ~/tunnel.log 2>&1 &
grep -o "https://[a-z0-9-]*\.trycloudflare\.com" ~/tunnel.log | head -1
```

3. 打开 [cloud.dify.ai](https://cloud.dify.ai) 注册，导入 DSL，把 `PC_BASE_URL` 填成隧道地址；
4. 云版没有 DeepSeek，用自带的 `gpt-6-luna` 即可——**但它不支持 `temperature`**，节点里要把这个
   参数删掉，否则报"temperature 无效"。

注意事项：

- `trycloudflare.com` 是临时域名，cloudflared 一重启就变；演示期间别重启，跑通先截图。
- 隧道是**无鉴权直通**，拿到地址的人都能读写档案。演示完记得 `pkill -f cloudflared`。
- 云版发消息要克制，试用模型有月度额度。

## 五、验证样例

### 5.1 一局完整对话（预计 3 分钟）

**初始状态**：全新玩家（Dify Web App 首次进入，`sys.user_id` 是新的），档案室为空。

| 步骤 | 输入 | 预期表现 |
| --- | --- | --- |
| 1 | （打开应用） | 老严开场："坐。姓名、职业、昨晚八点在哪儿。"，下方有三个建议问题 |
| 2 | `我昨晚在家看球赛，哪也没去。` | 老严追问细节（哪场球、几点）。因为档案为空，他会明确点一句"档案室是空的"之类的话 |
| 3 | `交代：我确实讨厌那条金鱼，它老盯着我看。` | 老严抓住"讨厌"这个词反问。**这句话已经进档案了** |
| 4 | `我什么都不知道，我要走了。` | 老严用上一轮的"讨厌金鱼"压你，指出这和"什么都不知道"对不上 |
| 5 | 关掉页面，重新打开同一个应用 | **新会话**。随便说一句 `我真没干。` |
| 6 | — | 老严仍然能念出你之前说的"讨厌那条金鱼"。**这是核心验收点** |

第 6 步如果没出现记忆，说明 `PC_BASE_URL` 不通或 PowerContext 没起，应用本身还能聊（HTTP 节点配了 `default-value` 降级），但老严会"失忆"。

> 关于"重新打开"：Dify Web App 的 `sys.user_id` 跟浏览器里的 end user 绑定，同一个浏览器重开就是同一个人。换浏览器 / 无痕窗口会是新用户、新档案——这正好可以用来演示"另一个人进来，档案是空的"。

### 5.2 自动验证跨会话记忆（不需要 Dify）

这是最硬的证据：脚本从 DSL 里**原样读出三个 Code 节点的代码**执行，HTTP 打到真实的 PowerContext，完全复现工作流的数据流。

```bash
cd dify
python scripts/verify_roundtrip.py --fresh
```

预期输出（节选）：

```
① 建档案室（POST /v1/scopes，按 idempotency_key 幂等）
HTTP 201  scope_id = scope_xxxxxxxx

② 会话 A：第一次进审讯室
玩家：我昨晚在家看球赛，哪也没去。
调档状态：empty
注入提示词的档案：（本次没有调出相关口供。）
老严：在家看球？哪场？

③ 归档口供（POST /v1/memory/remember）
HTTP 200  changed=true  records=1
  · atomic-memory/mem_xxxxxxxx@rev1
    正文：口供记录：嫌疑人称昨晚在家看球赛，没有外出。

④ 会话 B：关掉再开，同一档案室
玩家：我再说一遍，我跟那条金鱼一点关系都没有。
调档状态：ready
注入提示词的档案：
  - 口供记录：嫌疑人称昨晚在家看球赛，没有外出。

结论
✓ 会话 B 召回到了会话 A 的口供——跨会话记忆成立。
```

这一段同时证明了四件事：Scope 幂等创建、记忆写入、按 query 召回、跨会话复用。

### 5.3 DSL 自身的检查

```bash
python scripts/check_dsl.py     # 连线 / 变量引用 / code 输出 一致性
python scripts/test_flow.py     # 14 条边界用例（含服务挂掉、模型不守格式、超长截断）
```

`check_dsl.py` 覆盖的是最容易让导入失败的结构问题：孤立节点、`sourceHandle` 写错、引用了不存在的节点输出、`code` 节点声明的 `outputs` 和 `main()` 返回对不上。

### 5.4 如何恢复初始状态

| 想回到 | 做法 |
| --- | --- |
| 同一个玩家、清空档案 | 停掉 PowerContext，删掉 `$POWERCONTEXT_HOME/seekdb`（默认 `~/.local/share/powercontext/seekdb`），重启 |
| 换一个全新玩家 | 换浏览器 / 无痕窗口 / 清站点数据，Dify 会分配新的 `sys.user_id` |
| 只重跑自动验证 | `python scripts/verify_roundtrip.py --fresh`（每次换一个新档案室） |

---

### 5.5 实机验证记录（2026-10-28）

这一节是真跑出来的，不是设计稿。

**环境**：Dify 云版（`gpt-6-luna`）+ 一台 Ubuntu 22.04 服务器上的 PowerContext 1.4.1
（seekdb 后端）+ Cloudflare 隧道。Dify 在公网，PowerContext 在内网，中间靠隧道打通。

**对话实录**：

| 轮次 | 玩家 | 老严 |
| --- | --- | --- |
| 1 | 你好 | 你好。档案室是空的。昨晚八点以后，你记得什么？ |
| 2 | 交代：我确实讨厌那条金鱼，它老盯着我看。 | 讨厌一条鱼，不算交代完整，但算个头。你说它"老盯着我看"，昨晚八点后你去过老坎火锅门口吗？ |
| 3 | 我什么都不知道，我要走了。 | 刚才你说那条鱼老盯着你，现在又说什么都不知道。**鱼不会作证，但你前后两句话会。** |

第 3 轮那句"鱼不会作证，但你前后两句话会"，就是这个作品想要的调子。

**跨会话验证**（关掉预览，重新开一个会话）：

| 轮次 | 玩家 | 老严 |
| --- | --- | --- |
| 4 | 我真没干。 | **档案里你说过："我真没干。"现在还是这句，前后倒是整齐，细节呢？**昨晚八点后你去了哪儿？ |
| 5 | 我根本不认识那条鱼。 | **档案里你说过："我确实讨厌那条金鱼，它老盯着我看。"**现在又说根本不认识它，陌生鱼倒挺会盯人。你怎么解释？ |

第 4、5 轮是核心证据：**新会话里模型的对话历史是空的**，他不可能"记得"上一轮说过什么，
唯一来源就是 PowerContext 检索出来的档案。

**服务端日志**（`~/pc-server.log`，时为 UTC）：

```
13:12:02  create_scope      201
13:12:03  prepare_context   200
13:12:09  remember_memory   200
13:14:10  remember_memory   200
13:14:29  remember_memory   200
```

**跑完后库里的档案**（`POST /v1/memory/search`，query=`口供记录`，共 6 条）：

```
1. 口供记录：嫌疑人说："你好。"
2. 口供记录：嫌疑人称："我真没干。"
3. 口供记录：嫌疑人称："我真没干。"
4. 口供记录：嫌疑人称："我根本不认识那条鱼。"
5. 口供记录：嫌疑人称"我什么都不知道"，并表示"我要走了"。
6. 口供记录：嫌疑人称："我确实讨厌那条金鱼，它老盯着我看。"
```

每一条都带独立的 `artifact_id` 和 `revision`，可以在 Dashboard 里逐条查看。

**这次实测暴露并修掉的三个问题**（都已进代码）：

1. `prepare` 返回的是英文前言 + JSON 包装，直接塞进提示词会让老严看见 "untrusted historical context"；
2. 检索前缀只写了「口供」，而全文检索把「口供记录」当一个整体词，导致**跨会话一条都召不回**——
   这个问题最隐蔽，因为同一会话里 LLM 自带 10 轮上下文，看起来"会翻旧账"，其实是假象；
3. 环境变量粘贴时带了换行，HTTP 节点报 `Invalid non-printable ASCII character in URL`。

## 六、技术结合证据（怎么核对）

评审要确认"指定技术真的在起作用"，按下面三步看：

### 6.1 Dify 承担核心流程

打开导入的应用，工作流图上是一条完整的链：

```
开始 → 建档案室(HTTP) → 解析scope(Code) → 调取档案(HTTP) → 整理档案(Code)
     → 老严开口(LLM) → 拆台词与记录(Code) → 归档口供(HTTP) → 回话(Answer)
```

跑一局，然后在 Dify 的**日志与标注**里点开这次运行，能看到每个节点的输入输出：`调取档案` 返回的 `content`、`拆台词与记录` 产出的 `memo`、`归档口供` 的响应。这就是"检索结果如何进入互动流程"的节点级证据。

### 6.2 PowerContext 真的在存、真的在取

```bash
python scripts/verify_roundtrip.py --fresh   # 写入 + 召回，两个会话
python scripts/seekdb_evidence.py            # 库里的条数与正文
```

后者会打出：数据目录里 seekdb 实例的文件清单和体积、`/v1/capabilities` 里的后端、`/v1/memory/search` 命中的口供正文。

也可以在 Dify 跑完一局之后直接查：

```bash
curl -s -X POST http://127.0.0.1:8000/v1/memory/search \
  -H 'Content-Type: application/json' \
  -d '{"scope_id":"<你的 scope_id>","query":"口供 金鱼","limit":8}'
```

`scope_id` 可以在 Dify 那次运行的 `解析scope` 节点输出里看到，或者用 `GET /v1/scopes?limit=20` 列出来。

### 6.3 seekdb 是真实存储

- 启动脚本把 `POWERCONTEXT_SERVER_DATABASE_KIND` 设成 `seekdb`，`seekdb_evidence.py` 会打印数据目录里**一个 seekdb 实例目录**（不是 SQLite 的单文件）；
- 写入口供后目录体积增长；
- 停掉 PowerContext、重启，再 `verify_roundtrip.py`（不带 `--fresh`），老严仍然记得——数据在 seekdb 里，不在进程内存里。

对比方法：不设 `POWERCONTEXT_SERVER_DATABASE_KIND` 时 PowerContext 用 SQLite，数据目录里是一个 `.db` 文件，形状完全不同。

---

## 七、已知限制与排错

| 现象 | 原因 / 处理 |
| --- | --- |
| 老严不失忆、永远说"档案室是空的" | 先查 SSRF 白名单（§4.2 ①），这是最常见的原因：Dify 的 HTTP 节点被 `ssrf_proxy` 拦了。其次查 `PC_BASE_URL` 是否指向容器能解析的地址 |
| 应用能聊但从不提旧事 | 三个 HTTP 节点都配了 `default-value` 降级，服务连不上不会报错，只会静默失忆。看 Dify 运行日志里 `调取档案` 的 `status_code`：`0` 或 `403` 就是没连通 |
| 导入 DSL 报 `version` 或字段错误 | 确认 Dify ≥ 1.17。更早的 1.x 会走 DSL 迁移，一般能导入，但 `environment_variables` 可能需要手动补 `PC_BASE_URL` |
| `老严开口` 节点显示模型不可用 | 没配模型供应商，或你的账号没有 DeepSeek。换成任意对话模型即可 |
| 写完记忆下一轮立刻召回不到 | 检索有可见性延迟，等几秒；`verify_roundtrip.py` 里也是同样情况 |
| `start_powercontext.sh` 一启动就退出，报 `unauthenticated` | 缺 `POWERCONTEXT_SERVER_ALLOW_UNAUTHENTICATED_NON_LOOPBACK=true`，脚本里本该有，检查是不是被改掉了 |
| Windows 上 `start_powercontext.sh` 直接退出 | 嵌入式 seekdb 没有 Windows wheel，用 WSL2（见 `docs/run-and-capture.md` 第 0 步） |
| 云版报 `temperature 无效` | 换的模型不支持该参数，点模型右侧滑杆把 temperature 清空，或换回支持的模型 |
| HTTP 节点报 `Invalid non-printable ASCII character in URL` | 环境变量值末尾多了换行（粘贴带进去的）。编辑时全选重输，末尾别留回车 |
| 同一会话会翻旧账，跨会话就不记得 | 检索前缀写短了。全文检索把「口供记录」当一个整体词，只写「口供」匹配不上。见 §5.5 |
| 中文全文检索召回偏低 | PowerContext 最小配置走全文检索，不配 Embedding 时靠关键词匹配。所以记忆正文统一加了 `口供记录：` 前缀，`query` 也加了 `口供 ` 前缀来提升命中率。要更好的召回可以给 PowerContext 配 Embedding（见其 `configure-vector-search` 文档），本作不依赖 |

**降级行为说明**：三个 HTTP 节点都是 `error_strategy: default-value`。PowerContext 挂掉时，建档案室返回 `{}`、调档返回空、归档被忽略，对话本身不会报错——这是刻意设计的，保证"评审至少能玩到对话"，但**记忆功能需要服务在线**。

---

## 八、复用与来源声明

| 内容 | 来源 | 改动 |
| --- | --- | --- |
| Dify | [langgenius/dify](https://github.com/langgenius/dify)（Apache-2.0） | 未改源码，按官方 `docker/docker-compose.yaml` 部署 |
| PowerContext | [oceanbase/powercontext](https://github.com/oceanbase/powercontext)（Apache-2.0） | 未改源码，以 `powercontext[cli,server,seekdb]==1.4.1` 安装使用 |
| seekdb | 由 PowerContext 的 `seekdb` extra 提供（`pylibseekdb`） | 未改 |
| DSL 结构 | 参考 Dify 1.x 导出的 `version: 0.3.0` 样例，节点字段与 `graphon`（Dify 工作流引擎）的 pydantic 模型逐项对齐 | 本作原创编排 |
| 案件设定 / 老严人设 / 提示词 | 本作原创 | — |

没有复用第三方工作流的 DSL，没有引入自定义插件，也没有配套后端服务——`scripts/` 里的东西是举证工具，不是运行依赖。

配置示例里的 API Key、token 一律是占位值，仓库里不含任何真实凭据。

---

## 九、提交物清单

| 赛题要求 | 对应文件 |
| --- | --- |
| Dify DSL | `dsl/the-confession.chatflow.yml` |
| DSL 用途与导入顺序 | 本文 §4.4（只有一份 DSL，无导入顺序问题） |
| 运行说明 | 本文 §4 |
| 验证样例 | 本文 §5.1（手动一局）、§5.2（自动跨会话） |
| 运行证据 | §5.2 的脚本输出 + §6 的核对步骤 |
| 数据 / 初始化 | 不需要预置数据：档案室由工作流自己建，口供边玩边写 |
| 自定义插件 | 无（见 §2.1 为什么不用插件） |
| 配套源码 | `scripts/`（生成、检查、测试、验证） |
| 现成插件 | 无 |

---

## 附录：DSL 导入失败时的手工搭建

DSL 是标准 `version: 0.3.0` 导出格式，正常情况下导入即可。如果目标 Dify 版本不认这份
DSL，按下面这张表在「创建空白应用 → Chatflow」里搭一遍：9 个节点、8 条连线。

新建 Chatflow 后先加一个环境变量：**设置 → 环境变量 → 新增** `PC_BASE_URL`，值填
`http://host.docker.internal:8000`。

| 顺序 | 节点类型 | 标题 | 关键配置 |
| --- | --- | --- | --- |
| 1 | 开始 | 开始 | 不加自定义变量，玩家输入走 `sys.query` |
| 2 | HTTP 请求 | 建档案室 | `POST {{env.PC_BASE_URL}}/v1/scopes`，Body 选 JSON：`{"title":"口供档案","summary":"Dify《口供》应用...","idempotency_key":"dify-confession-{{sys.user_id}}"}`；异常处理选**默认值**，`body` = `{}` |
| 3 | 代码 | 解析 scope | 语言 Python3，输入 `scope_resp`←节点2的 `body`、`query`←`sys.query`，输出 `scope_id`/`prepare_json`/`boot_err`（代码见 `scripts/build_dsl.py` 的 `CODE_BOOT`） |
| 4 | HTTP 请求 | 调取档案 | `POST {{env.PC_BASE_URL}}/v1/context/prepare`，Body JSON 直接引用 `{{节点3.prepare_json}}`；异常处理默认值 = `{"status":"empty","content":null,"content_bytes":0}` |
| 5 | 代码 | 整理档案 | 输入 `prep_resp`←节点4的 `body`、`boot_err`←节点3的 `boot_err`，输出 `context_text`/`memory_state`/`boot_err` |
| 6 | LLM | 老严开口 | 模型任意对话模型；**记忆 → 开启，窗口 10**；System 提示词里用 `{{节点5.context_text}}` 插入档案（完整提示词见 `build_dsl.py` 的 `SYSTEM_PROMPT`）；User 提示词 `{{sys.query}}` |
| 7 | 代码 | 拆台词与记录 | 输入 `text`←节点6的 `text`、`query`←`sys.query`、`scope_id`←节点3的 `scope_id`，输出 `reply`/`memo`/`remember_json` |
| 8 | HTTP 请求 | 归档口供 | `POST {{env.PC_BASE_URL}}/v1/memory/remember`，Body JSON 引用 `{{节点7.remember_json}}`；异常处理默认值 = `{"changed":false,"records":[]}` |
| 9 | 直接回复 | 回话 | `{{节点7.reply}}` |

连线：1→2→3→4→5→6→7→8→9，全部走默认出口。

三个 HTTP 节点的 **异常处理选「默认值」** 这一步别省：它让 PowerContext 掉线时对话还能继续，
否则评审看到的就是一个报错。

搭完点「运行」验证一局，然后照 §5.1 走一遍。
