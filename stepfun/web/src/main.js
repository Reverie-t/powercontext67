import { api } from "./api.js";
import { chunkText } from "./chunk.js";
import {
  DIMENSION,
  DEFAULT_DTYPE,
  MODEL_ID,
  QUERY_PREFIX,
  collectionName,
  dtypeLabel,
} from "./config.js";
import { docOrder, median, ndcgAtK, recallAtK } from "./metrics.js";

const $ = (id) => document.getElementById(id);

const state = {
  dtype: DEFAULT_DTYPE,
  device: "检测中",
  fallbackFrom: "",
  loadMs: null,
  health: null,
  count: 0,
  busy: false,
};

let worker = null;
let ready = Promise.resolve();
let readyResolve = () => {};
let readyReject = () => {};
let bootToken = 0;
let seq = 0;
const pending = new Map();
const lines = [];

function log(line) {
  lines.push(line);
  if (lines.length > 40) lines.shift();
  $("log").textContent = lines.join("\n");
}

function escapeHtml(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;");
}

function renderBadges() {
  const health = state.health;
  const badges = [
    `${dtypeLabel(state.dtype)} · ${state.device}`,
    state.fallbackFrom ? "已降级" : "",
    health ? `seekdb ${health.mode}` : "数据库未连接",
    health?.refreshSupported ? "refresh_index 可用" : "refresh_index 不可用",
    `库内 ${state.count} 段`,
  ].filter(Boolean);
  $("badges").innerHTML = badges
    .map((text, index) => {
      const warn = text.includes("不可用") || text.includes("未连接") || text.includes("已降级");
      const ok = text.includes("可用") || text.startsWith("seekdb");
      const klass = warn ? "warn" : ok ? "ok" : "";
      return `<span class="badge ${klass}">${escapeHtml(text)}</span>`;
    })
    .join("");
  $("collection-line").textContent = `当前集合 ${collectionName(state.dtype)} · ${MODEL_ID} · ${DIMENSION} 维`;
}

function setBusy(busy) {
  state.busy = busy;
  for (const id of ["import-paste", "import-sample", "run-eval", "search", "clear-kb", "reload-model", "dtype"]) {
    $(id).disabled = busy;
  }
}

function boot(dtype, forceDevice, fallbackFrom = "") {
  const token = ++bootToken;
  if (worker) worker.terminate();
  state.dtype = dtype;
  state.device = "加载中";
  state.fallbackFrom = fallbackFrom;
  renderBadges();
  $("progress").textContent = forceDevice
    ? `正在用 ${forceDevice} 加载 ${dtypeLabel(dtype)} 模型。`
    : `正在加载 ${dtypeLabel(dtype)} 模型。`;
  ready = new Promise((resolve, reject) => {
    readyResolve = resolve;
    readyReject = reject;
  });
  const limitMs = forceDevice === "wasm" ? 120000 : 45000;
  const timer = setTimeout(() => {
    if (token !== bootToken) return;
    if (forceDevice === "wasm") {
      const message = "WASM 也没有在两分钟内准备好。";
      $("progress").textContent = message;
      log(message);
      readyReject(new Error(message));
      return;
    }
    log("WebGPU 45 秒内没有准备好，改用 WASM。");
    boot(dtype, "wasm", "WebGPU 45 秒内没有准备好，已改用 WASM。");
  }, limitMs);
  worker = new Worker(new URL("./worker.js", import.meta.url), { type: "module" });
  worker.onmessage = (event) => {
    if (token !== bootToken) return;
    const message = event.data;
    if (message.type === "progress") {
      const update = message.update || {};
      if (update.file) {
        const pct = update.total ? Math.round((update.loaded / update.total) * 100) : "";
        $("progress").textContent = `读取 ${update.file} ${pct ? pct + "%" : ""}`;
      }
      return;
    }
    if (message.type === "ready") {
      clearTimeout(timer);
      state.device = message.device;
      state.fallbackFrom = message.fallbackFrom || state.fallbackFrom || "";
      state.loadMs = message.loadMs;
      $("progress").textContent = state.fallbackFrom
        ? `模型已加载。${state.fallbackFrom} 当前后端是 ${message.device}。`
        : `模型已加载，后端 ${message.device}，耗时 ${Math.round(message.loadMs)} ms。`;
      log(`模型就绪 ${message.device} ${message.dtype} ${Math.round(message.loadMs)} ms`);
      if (state.fallbackFrom) log(state.fallbackFrom);
      renderBadges();
      readyResolve(message);
      return;
    }
    if (message.type === "result") {
      pending.get(message.id)?.resolve(message);
      pending.delete(message.id);
      return;
    }
    if (message.type === "error") {
      if (message.id != null) {
        pending.get(message.id)?.reject(new Error(message.message));
        pending.delete(message.id);
      } else if (!forceDevice && /webgpu/i.test(message.message)) {
        clearTimeout(timer);
        log(`WebGPU 失败：${message.message}`);
        boot(dtype, "wasm", `WebGPU 初始化失败：${message.message}`);
      } else {
        clearTimeout(timer);
        $("progress").textContent = message.message;
        log(message.message);
        readyReject(new Error(message.message));
      }
    }
  };
  worker.onerror = (event) => {
    if (token !== bootToken) return;
    event.preventDefault();
    const message = event.message || "模型线程出错";
    log(message);
  };
  worker.postMessage({ type: "init", dtype, device: forceDevice || "" });
}

async function embed(texts, isQuery) {
  await ready;
  const id = ++seq;
  const message = await new Promise((resolve, reject) => {
    pending.set(id, { resolve, reject });
    worker.postMessage({ type: "embed", id, texts, isQuery });
  });
  return { vectors: message.vectors, ms: message.ms };
}

async function refreshHealth() {
  try {
    state.health = await api.health();
    const name = collectionName(state.dtype);
    const listed = await api.list();
    const found = listed.collections.find((item) => item.name === name);
    if (found) {
      const info = await api.info(name);
      state.count = info.count;
    } else {
      state.count = 0;
    }
  } catch (error) {
    state.health = null;
    log(`数据库连不上：${error.message}`);
  }
  renderBadges();
}

async function ensureCollection() {
  const created = await api.create(collectionName(state.dtype), DIMENSION);
  log(`集合 ${created.name} 维度 ${created.dimension}`);
  return created.name;
}

async function importDocuments(docs) {
  if (!docs.length) throw new Error("没有可导入的文本");
  const name = await ensureCollection();
  const chunks = [];
  for (const doc of docs) {
    const parts = chunkText(doc.text);
    parts.forEach((text, index) => {
      chunks.push({
        id: `${doc.doc_id}__${index}`,
        document: text,
        metadata: {
          doc_id: doc.doc_id,
          title: doc.title,
          chunk: index,
          source: doc.title,
        },
      });
    });
  }
  if (!chunks.length) throw new Error("切段后是空的");
  const batchSize = state.device === "webgpu" ? 32 : 8;
  let embedMs = 0;
  let writeMs = 0;
  let added = 0;
  let skipped = 0;
  for (let start = 0; start < chunks.length; start += batchSize) {
    const batch = chunks.slice(start, start + batchSize);
    $("progress").textContent = `向量化 ${Math.min(start + batch.length, chunks.length)} / ${chunks.length}`;
    const embedded = await embed(batch.map((item) => item.document), false);
    embedMs += embedded.ms;
    const wrote = await api.add(name, {
      ids: batch.map((item) => item.id),
      documents: batch.map((item) => item.document),
      embeddings: embedded.vectors,
      metadatas: batch.map((item) => item.metadata),
    });
    writeMs += wrote.writeMs;
    added += wrote.added;
    skipped += wrote.skipped;
    state.count = wrote.count;
    renderBadges();
  }
  $("progress").textContent = "正在刷新向量索引。";
  const refreshed = await api.refresh(name);
  log(
    `写入 ${added} 段，跳过 ${skipped} 段。向量化 ${Math.round(embedMs)} ms，写入 ${writeMs} ms，刷新 ${refreshed.refreshMs} ms。`
  );
  if (!refreshed.refreshInvoked) log(refreshed.note);

  const probe = chunks[chunks.length - 1];
  const probeEmbed = await embed([probe.document], false);
  const probeStarted = performance.now();
  const probeResult = await api.search(name, {
    queryText: probe.document.slice(0, 32),
    queryEmbedding: probeEmbed.vectors[0],
    nResults: 5,
  });
  const probeMs = performance.now() - probeStarted;
  const hit = probeResult.hits.some((item) => item.id === probe.id);
  log(hit ? `探针命中 ${probe.id}，检索 ${Math.round(probeMs)} ms。` : `探针没找到 ${probe.id}。刷新可能没生效。`);
  $("progress").textContent = hit ? "新内容已经能检索到。" : "刷新后探针没有命中。";
  state.count = (await api.info(name)).count;
  renderBadges();
  return { embedMs, writeMs, refresh: refreshed, probeMs, hit, added, skipped, chunks: chunks.length };
}

function readFiles(fileList) {
  return Promise.all(
    [...fileList].map(
      (file) =>
        new Promise((resolve, reject) => {
          const reader = new FileReader();
          reader.onload = () => {
            const title = file.name.replace(/\.(txt|md)$/i, "");
            resolve({
              doc_id: `file_${title}`.replace(/[^\w\u4e00-\u9fff-]+/g, "_").slice(0, 48),
              title,
              text: String(reader.result || ""),
            });
          };
          reader.onerror = () => reject(reader.error);
          reader.readAsText(file);
        })
    )
  );
}

function renderHits(hits) {
  if (!hits.length) {
    $("results").innerHTML = "<p class='muted'>没有结果。</p>";
    return;
  }
  $("results").innerHTML = hits
    .map((hit) => {
      const title = hit.metadata?.title || hit.metadata?.doc_id || hit.id;
      const score = hit.score == null ? "" : Number(hit.score).toFixed(4);
      return `<article>
        <h3>${hit.rank}. ${escapeHtml(title)} <span class="muted">${escapeHtml(hit.metadata?.doc_id || "")} · 融合分 ${score}</span></h3>
        <p>${escapeHtml(hit.document || "")}</p>
      </article>`;
    })
    .join("");
}

async function search() {
  const query = $("query").value.trim();
  if (!query) throw new Error("先写查询");
  const name = collectionName(state.dtype);
  const nResults = Number($("k").value || 5);
  const started = performance.now();
  const embedded = await embed([query], true);
  const result = await api.search(name, {
    queryText: query,
    queryEmbedding: embedded.vectors[0],
    nResults,
    rankWindowSize: 40,
    rankConstant: 60,
  });
  const e2eMs = performance.now() - started;
  renderHits(result.hits);
  const timing = {
    dtype: state.dtype,
    device: state.device,
    queryEmbedMs: Math.round(embedded.ms),
    seekdbSearchMs: result.searchMs,
    e2eMs: Math.round(e2eMs),
    rankWindowSize: result.rankWindowSize,
    rankConstant: result.rankConstant,
    queryPrefix: QUERY_PREFIX,
    note: "queryEmbedMs 含浏览器推理。seekdbSearchMs 只含服务端 hybridSearch。e2eMs 从点击检索到结果返回。",
  };
  $("timing").textContent = JSON.stringify(timing, null, 2);
  log(`检索完成，端到端 ${Math.round(e2eMs)} ms，库内 ${result.searchMs} ms。`);
}

async function runEval() {
  const corpus = await (await fetch("/eval/corpus.json")).json();
  const queries = await (await fetch("/eval/queries.json")).json();
  await importDocuments(corpus);
  const name = collectionName(state.dtype);
  const rows = [];
  for (const query of queries) {
    const started = performance.now();
    const embedded = await embed([query.text], true);
    const result = await api.search(name, {
      queryText: query.text,
      queryEmbedding: embedded.vectors[0],
      nResults: 5,
      rankWindowSize: 40,
      rankConstant: 60,
    });
    const ranked = docOrder(result.hits);
    rows.push({
      id: query.id,
      recallAt5: recallAtK(query.relevant, ranked, 5),
      ndcgAt5: ndcgAtK(query.relevant, ranked, 5),
      queryEmbedMs: embedded.ms,
      seekdbSearchMs: result.searchMs,
      e2eMs: performance.now() - started,
      top: ranked[0] || null,
    });
  }
  const repeats = [];
  for (let i = 0; i < 5; i += 1) {
    const started = performance.now();
    const embedded = await embed([queries[0].text], true);
    const result = await api.search(name, {
      queryText: queries[0].text,
      queryEmbedding: embedded.vectors[0],
      nResults: 5,
    });
    repeats.push({
      queryEmbedMs: embedded.ms,
      seekdbSearchMs: result.searchMs,
      e2eMs: performance.now() - started,
    });
  }
  const summary = {
    dtype: state.dtype,
    device: state.device,
    loadMs: state.loadMs == null ? null : Math.round(state.loadMs),
    docs: corpus.length,
    queries: queries.length,
    relevance: "二值，粒度是 doc_id。一段命中就算这篇命中。",
    meanRecallAt5: rows.reduce((sum, row) => sum + row.recallAt5, 0) / rows.length,
    meanNdcgAt5: rows.reduce((sum, row) => sum + row.ndcgAt5, 0) / rows.length,
    medianRepeat: {
      queryEmbedMs: Math.round(median(repeats.map((item) => item.queryEmbedMs))),
      seekdbSearchMs: median(repeats.map((item) => item.seekdbSearchMs)),
      e2eMs: Math.round(median(repeats.map((item) => item.e2eMs))),
    },
    rows,
  };
  $("timing").textContent = JSON.stringify(summary, null, 2);
  log(
    `样例 Recall@5=${summary.meanRecallAt5.toFixed(3)} nDCG@5=${summary.meanNdcgAt5.toFixed(3)} 后端=${state.device}`
  );
}

$("dtype").addEventListener("change", async () => {
  boot($("dtype").value);
  await refreshHealth();
});

$("reload-model").addEventListener("click", () => boot($("dtype").value));

$("files").addEventListener("change", async (event) => {
  setBusy(true);
  try {
    const docs = await readFiles(event.target.files);
    await importDocuments(docs);
  } catch (error) {
    log(error.message);
    $("progress").textContent = error.message;
  } finally {
    setBusy(false);
    event.target.value = "";
  }
});

$("import-paste").addEventListener("click", async () => {
  setBusy(true);
  try {
    const text = $("paste").value.trim();
    const title = $("paste-title").value.trim() || "粘贴";
    await importDocuments([
      {
        doc_id: `paste_${Date.now()}`,
        title,
        text,
      },
    ]);
    $("paste").value = "";
  } catch (error) {
    log(error.message);
    $("progress").textContent = error.message;
  } finally {
    setBusy(false);
  }
});

$("import-sample").addEventListener("click", async () => {
  setBusy(true);
  try {
    const corpus = await (await fetch("/eval/corpus.json")).json();
    await importDocuments(corpus);
  } catch (error) {
    log(error.message);
    $("progress").textContent = error.message;
  } finally {
    setBusy(false);
  }
});

$("clear-kb").addEventListener("click", async () => {
  setBusy(true);
  try {
    const name = collectionName(state.dtype);
    await api.remove(name);
    state.count = 0;
    log(`已删除集合 ${name}`);
    renderBadges();
  } catch (error) {
    log(error.message);
  } finally {
    setBusy(false);
  }
});

$("search").addEventListener("click", async () => {
  setBusy(true);
  try {
    await search();
  } catch (error) {
    log(error.message);
  } finally {
    setBusy(false);
  }
});

$("run-eval").addEventListener("click", async () => {
  setBusy(true);
  try {
    await runEval();
  } catch (error) {
    log(error.message);
    $("progress").textContent = error.message;
  } finally {
    setBusy(false);
  }
});

const forcedDevice = new URLSearchParams(location.search).get("device");
boot(DEFAULT_DTYPE, forcedDevice === "wasm" || forcedDevice === "webgpu" ? forcedDevice : undefined);
refreshHealth();
