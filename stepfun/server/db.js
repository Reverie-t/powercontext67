import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import {
  FulltextIndexConfig,
  Schema,
  SeekdbAdminClient,
  SeekdbClient,
  VectorIndexConfig,
} from "seekdb";

const SERVER_DIR = path.dirname(fileURLToPath(import.meta.url));
export const ROOT = path.resolve(SERVER_DIR, "..");

const vendorBindings = path.join(ROOT, "vendor", "bindings");

function hasNativeBinding(dir) {
  if (!fs.existsSync(dir)) return false;
  const stack = [dir];
  while (stack.length) {
    const current = stack.pop();
    for (const name of fs.readdirSync(current)) {
      const full = path.join(current, name);
      if (fs.statSync(full).isDirectory()) stack.push(full);
      else if (name === "seekdb.node") return true;
    }
  }
  return false;
}

if (!process.env.SEEKDB_BINDINGS_CACHE_DIR && hasNativeBinding(vendorBindings)) {
  process.env.SEEKDB_BINDINGS_CACHE_DIR = vendorBindings;
}

const NAME_RE = /^[A-Za-z][A-Za-z0-9_]{0,63}$/;
const MIN_REFRESH = [1, 3, 0];

export function assertCollectionName(name) {
  if (typeof name !== "string" || !NAME_RE.test(name)) {
    const error = new Error(
      "集合名只能用字母开头，后面是字母、数字或下划线，最长 64 个字符"
    );
    error.status = 400;
    throw error;
  }
}

export function seekdbConfig() {
  const database = process.env.SEEKDB_DATABASE || "test";
  if (process.env.SEEKDB_HOST) {
    return {
      mode: "server",
      database,
      client: {
        host: process.env.SEEKDB_HOST,
        port: Number(process.env.SEEKDB_PORT || 2881),
        user: process.env.SEEKDB_USER || "root",
        password: process.env.SEEKDB_PASSWORD ?? "",
        database,
      },
    };
  }
  const dataPath = process.env.SEEKDB_PATH
    ? path.resolve(process.env.SEEKDB_PATH)
    : path.join(ROOT, "data", "seekdb");
  return {
    mode: "embedded",
    database,
    dataPath,
    client: {
      path: dataPath,
      database,
    },
  };
}

function databaseName(entry) {
  if (typeof entry === "string") return entry;
  if (entry && typeof entry === "object") {
    return entry.name || entry.database || entry.databaseName || "";
  }
  return "";
}

async function ensureDatabase(cfg) {
  const adminArgs =
    cfg.mode === "embedded"
      ? { path: cfg.dataPath }
      : {
          host: cfg.client.host,
          port: cfg.client.port,
          user: cfg.client.user,
          password: cfg.client.password,
        };
  if (cfg.mode === "embedded") {
    fs.mkdirSync(cfg.dataPath, { recursive: true });
  }
  const admin = new SeekdbAdminClient(adminArgs);
  try {
    const existing = await admin.listDatabases();
    const names = existing.map(databaseName);
    if (!names.includes(cfg.database)) {
      await admin.createDatabase(cfg.database);
    }
  } finally {
    await admin.close();
  }
}

export async function openSeekdb() {
  const cfg = seekdbConfig();
  await ensureDatabase(cfg);
  const client = new SeekdbClient(cfg.client);
  return { client, cfg };
}

function makeSchema(dimension) {
  return new Schema({
    vectorIndex: new VectorIndexConfig({
      hnsw: { dimension, distance: "cosine" },
      embeddingFunction: null,
    }),
    fulltextIndex: new FulltextIndexConfig("ngram", {
      ngram_token_size: 2,
    }),
  });
}

export function assertNoServerEmbed(collection) {
  if (collection.embeddingFunction) {
    const error = new Error(
      `集合 ${collection.name} 挂了服务端向量函数 ${collection.embeddingFunction.name}。向量只能在浏览器里算。`
    );
    error.status = 500;
    throw error;
  }
}

async function loadCollection(client, name) {
  assertCollectionName(name);
  const exists = await client.hasCollection(name);
  if (!exists) {
    const error = new Error(`集合 ${name} 不存在`);
    error.status = 404;
    throw error;
  }
  const collection = await client.getCollection({
    name,
    embeddingFunction: null,
  });
  assertNoServerEmbed(collection);
  return collection;
}

export async function listKnowledgeBases(client) {
  const collections = await client.listCollections({
    withEmbeddingFunction: false,
  });
  return collections.map((collection) => ({
    name: collection.name,
    dimension: collection.dimension,
    distance: collection.distance,
  }));
}

export async function createKnowledgeBase(client, name, dimension) {
  assertCollectionName(name);
  if (!Number.isInteger(dimension) || dimension <= 0) {
    const error = new Error("dimension 必须是正整数");
    error.status = 400;
    throw error;
  }
  if (await client.hasCollection(name)) {
    const current = await loadCollection(client, name);
    if (current.dimension !== dimension) {
      const error = new Error(
        `集合 ${name} 的维度是 ${current.dimension}，和这次的 ${dimension} 对不上。换模型或换精度要换一个集合名，再重新导入。`
      );
      error.status = 409;
      throw error;
    }
    return describeCollection(current);
  }
  const created = await client.createCollection({
    name,
    schema: makeSchema(dimension),
    embeddingFunction: null,
  });
  assertNoServerEmbed(created);
  if (created.dimension !== dimension) {
    const error = new Error(
      `集合建出来的维度是 ${created.dimension}，期望 ${dimension}`
    );
    error.status = 500;
    throw error;
  }
  return describeCollection(created);
}

function describeCollection(collection) {
  return {
    name: collection.name,
    dimension: collection.dimension,
    distance: collection.distance,
  };
}

export async function deleteKnowledgeBase(client, name) {
  assertCollectionName(name);
  if (!(await client.hasCollection(name))) return { deleted: false };
  await client.deleteCollection(name);
  return { deleted: true };
}

export async function countKnowledgeBase(client, name) {
  const collection = await loadCollection(client, name);
  const count = await collection.count();
  return { name, count: Number(count), ...describeCollection(collection) };
}

function asArray(value) {
  if (value === undefined || value === null) return [];
  return Array.isArray(value) ? value : [value];
}

export async function addDocuments(client, name, body) {
  const collection = await loadCollection(client, name);
  const ids = asArray(body.ids).map(String);
  const documents = asArray(body.documents).map(String);
  const embeddings = body.embeddings;
  const metadatas = body.metadatas ? asArray(body.metadatas) : undefined;
  if (ids.length === 0) {
    const error = new Error("ids 不能是空的");
    error.status = 400;
    throw error;
  }
  if (ids.length > 64) {
    const error = new Error("一次最多写 64 条");
    error.status = 400;
    throw error;
  }
  if (documents.length !== ids.length || !Array.isArray(embeddings) || embeddings.length !== ids.length) {
    const error = new Error("ids、documents、embeddings 的条数要一致");
    error.status = 400;
    throw error;
  }
  if (metadatas && metadatas.length !== ids.length) {
    const error = new Error("metadatas 的条数要和 ids 一致");
    error.status = 400;
    throw error;
  }
  for (let i = 0; i < embeddings.length; i += 1) {
    const vector = embeddings[i];
    if (!Array.isArray(vector) || vector.length !== collection.dimension) {
      const error = new Error(
        `第 ${i} 条向量维度是 ${Array.isArray(vector) ? vector.length : "空"}，集合要 ${collection.dimension}`
      );
      error.status = 400;
      throw error;
    }
  }

  const existing = await collection.get({
    ids,
    include: ["documents"],
  });
  const have = new Set(existing.ids.map(String));
  const keep = [];
  for (let i = 0; i < ids.length; i += 1) {
    if (!have.has(ids[i])) keep.push(i);
  }
  if (keep.length === 0) {
    return {
      name,
      added: 0,
      skipped: ids.length,
      writeMs: 0,
      count: Number(await collection.count()),
    };
  }

  const started = Date.now();
  await collection.add({
    ids: keep.map((i) => ids[i]),
    documents: keep.map((i) => documents[i]),
    embeddings: keep.map((i) => embeddings[i]),
    metadatas: metadatas ? keep.map((i) => metadatas[i]) : undefined,
  });
  const writeMs = Date.now() - started;
  return {
    name,
    added: keep.length,
    skipped: ids.length - keep.length,
    writeMs,
    count: Number(await collection.count()),
  };
}

function versionText(rows) {
  if (!rows || rows.length === 0) return "";
  const row = rows[0];
  for (const [key, value] of Object.entries(row)) {
    if (key.toLowerCase().includes("version") && value != null) {
      return String(value);
    }
  }
  const first = Object.values(row)[0];
  return first == null ? "" : String(first);
}

export function parseSeekdbVersion(text) {
  const match = String(text).match(/seekdb(?:[-_\s]*v)?[-_\s]*(\d+)\.(\d+)\.(\d+)/i);
  if (!match) return null;
  return [Number(match[1]), Number(match[2]), Number(match[3])];
}

function atLeast(version, min) {
  if (!version) return false;
  for (let i = 0; i < 3; i += 1) {
    if (version[i] !== min[i]) return version[i] > min[i];
  }
  return true;
}

export async function readVersion(client) {
  const rows = await client.execute("SELECT VERSION() AS version");
  const version = versionText(rows);
  const parsed = parseSeekdbVersion(version);
  return {
    version,
    refreshSupported: atLeast(parsed, MIN_REFRESH),
  };
}

export async function refreshKnowledgeBase(client, name) {
  const collection = await loadCollection(client, name);
  const info = await readVersion(client);
  if (!info.refreshSupported) {
    return {
      name,
      refreshMs: 0,
      refreshInvoked: false,
      version: info.version,
      note: "版本不到 1.3.0，或版本字符串解析失败。refresh_index 在这种情况下会静默跳过，所以这里没有调用它。",
    };
  }
  const started = Date.now();
  await collection.refresh_index();
  return {
    name,
    refreshMs: Date.now() - started,
    refreshInvoked: true,
    version: info.version,
    note: "已调用 collection.refresh_index()，也就是 CALL dbms_index_manager.refresh()。",
  };
}

export async function hybridSearch(client, name, body) {
  const collection = await loadCollection(client, name);
  const queryText = typeof body.queryText === "string" ? body.queryText.trim() : "";
  const queryEmbedding = body.queryEmbedding;
  const nResults = Number(body.nResults || 8);
  if (!queryText) {
    const error = new Error("queryText 不能是空的，全文这一路需要它");
    error.status = 400;
    throw error;
  }
  if (!Array.isArray(queryEmbedding) || queryEmbedding.length !== collection.dimension) {
    const error = new Error(
      `queryEmbedding 维度是 ${Array.isArray(queryEmbedding) ? queryEmbedding.length : "空"}，集合要 ${collection.dimension}`
    );
    error.status = 400;
    throw error;
  }
  const rankWindowSize = Number(body.rankWindowSize ?? 40);
  const rankConstant = Number(body.rankConstant ?? 60);
  const knnResults = Math.max(nResults, Math.min(rankWindowSize, 100));
  const started = Date.now();
  const result = await collection.hybridSearch({
    query: { whereDocument: { $contains: queryText } },
    knn: {
      queryEmbeddings: [queryEmbedding],
      nResults: knnResults,
    },
    rank: {
      rrf: {
        rankWindowSize,
        rankConstant,
      },
    },
    nResults,
    include: ["documents", "metadatas", "distances"],
  });
  const searchMs = Date.now() - started;
  const ids = result.ids?.[0] ?? [];
  const documents = result.documents?.[0] ?? [];
  const metadatas = result.metadatas?.[0] ?? [];
  const distances = result.distances?.[0] ?? [];
  const hits = ids.map((id, index) => ({
    id: String(id),
    document: documents[index] ?? null,
    metadata: metadatas[index] ?? null,
    score: distances[index] == null ? null : Number(distances[index]),
    rank: index + 1,
  }));
  return {
    name,
    searchMs,
    nResults,
    rankWindowSize,
    rankConstant,
    hits,
  };
}
