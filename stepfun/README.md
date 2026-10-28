# 浏览器本地知识库

文档和查询的向量在浏览器里算。seekdb 只负责保存，并用一次混合检索把全文和向量排好。服务端不算向量。

## 环境

需要 Node.js 20 或更高。先看 `node -v`。低于 20 就换成你自己的 Node 20 以上，再跑后面的命令。开发这套代码的机器上，系统自带的 Node 是 12，实际用的是 `$HOME/.local/opt/node-v22/bin`。

浏览器用 Chrome 或 Edge 最新版。页面地址必须是 `http://127.0.0.1:5173`，不要用文件协议打开，否则 WASM 线程起不来。

## 启动

在本仓库根目录执行，进入 `stepfun/`：

```bash
cd stepfun
npm install
npm --prefix web install
npm run download-models
node scripts/fetch-bindings.mjs
npm run smoke
npm run dev
```

`npm run smoke` 和 `npm run dev` 会先预加载 `libseekdb.so`。这个库的静态 TLS 很大，Node 启动后再 `dlopen` 会报 `cannot allocate memory in static TLS block`。不要直接 `node server/index.js`。

打开 http://127.0.0.1:5173 。地址后面加 `?device=wasm` 可以跳过 WebGPU，直接用 WASM。

`download-models` 把 `Xenova/bge-small-zh-v1.5` 的 FP32、FP16、INT8 权重放到 `web/public/models/`。仓库里已经带了这次下好的文件，再跑会跳过已有文件。

`fetch-bindings.mjs` 把嵌入式 seekdb 的原生库放到 `vendor/bindings/`。`npm install` 下来的 `@seekdb/js-bindings` 默认不含 `.node`，第一次会从对象存储拉。拉完之后，服务启动会优先用 `vendor/bindings`。`libseekdb.so` 大约 146MB，超过 GitHub 单文件 100MB 限制，所以没有放进仓库，这一步需要能访问对象存储。

Windows 上嵌入式是实验功能。连不上就改用本机 seekdb server：

```bash
export SEEKDB_HOST=127.0.0.1
export SEEKDB_PORT=2881
export SEEKDB_USER=root
export SEEKDB_PASSWORD=
export SEEKDB_DATABASE=test
```

设了 `SEEKDB_HOST` 就走 server，否则走嵌入式，数据目录是 `data/seekdb`。嵌入式一次只能开一个进程。`npm run smoke` 用的是 `data/smoke`，不要和 `npm run dev` 同时跑同一个目录。

## 页面上做什么

1. 等右上角出现 `INT8 · wasm` 或 `INT8 · webgpu`。没有 WebGPU，或 WebGPU 初始化失败，会自动改用 WASM，并在页面上写出来。
2. 点「导入样例语料」。向量化结束后会调用 `refresh_index`，再用最后一段做一次探针。
3. 在检索框输入问题。查询向量会加上 `为这个句子生成表示以用于检索相关文章：`，全文这一路用你输入的原句。
4. 换精度会换集合：`kb_bge_small_zh_v15_q8`、`kb_bge_small_zh_v15_fp16`、`kb_bge_small_zh_v15_fp32`。旧集合不会被自动改写。
5. 「用样例算 Recall@5」会导入样例并按文档 id 算二值 Recall@5 和 nDCG@5。

模型文件只从 `/models/` 读，`allowRemoteModels` 是关的。接口在 `http://127.0.0.1:8787`，开发时由 Vite 代理到同源。
