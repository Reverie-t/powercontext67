import path from "node:path";
import { fileURLToPath } from "node:url";
import {
  addDocuments,
  createKnowledgeBase,
  deleteKnowledgeBase,
  hybridSearch,
  openSeekdb,
  refreshKnowledgeBase,
} from "./db.js";

process.env.SEEKDB_PATH = path.resolve(
  path.dirname(fileURLToPath(import.meta.url)),
  "../data/smoke"
);

const dimension = 512;
const name = "smoke_bge_small_zh_v15_q8";

function vector(index) {
  const values = new Array(dimension).fill(0);
  values[index] = 1;
  return values;
}

const docs = [
  {
    id: "doc-tea__0",
    document: "西湖龙井产自杭州，明前茶的芽叶很嫩，冲泡水温不要太高。",
    metadata: { doc_id: "doc-tea", title: "龙井", chunk: 0 },
  },
  {
    id: "doc-refresh__0",
    document: "seekdb 从 1.3.0 起向量索引异步构建，写入后要调用 refresh_index，新文档才能被检索到。",
    metadata: { doc_id: "doc-refresh", title: "索引刷新", chunk: 0 },
  },
  {
    id: "doc-metro__0",
    document: "上海地铁二号线从徐泾东开到浦东机场，虹桥火车站也在这条线上。",
    metadata: { doc_id: "doc-metro", title: "地铁", chunk: 0 },
  },
];

const { client, cfg } = await openSeekdb();
console.log(`冒烟数据库模式=${cfg.mode} 路径=${cfg.dataPath || cfg.client.host}`);

try {
  await deleteKnowledgeBase(client, name).catch(() => {});
  const created = await createKnowledgeBase(client, name, dimension);
  console.log("集合", created);

  const added = await addDocuments(client, name, {
    ids: docs.map((doc) => doc.id),
    documents: docs.map((doc) => doc.document),
    embeddings: docs.map((_, index) => vector(index + 1)),
    metadatas: docs.map((doc) => doc.metadata),
  });
  console.log("写入", added);

  const refreshed = await refreshKnowledgeBase(client, name);
  console.log("刷新", refreshed);
  if (!refreshed.refreshInvoked) {
    throw new Error(refreshed.note);
  }

  const found = await hybridSearch(client, name, {
    queryText: "refresh_index 索引刷新",
    queryEmbedding: vector(2),
    nResults: 3,
  });
  console.log(
    "混合检索",
    found.searchMs + "ms",
    found.hits.map((hit) => `${hit.rank}:${hit.metadata?.doc_id}:${hit.score}`)
  );
  const topDoc = found.hits[0]?.metadata?.doc_id;
  if (topDoc !== "doc-refresh") {
    throw new Error(`期望第一条是 doc-refresh，实际是 ${topDoc || "空"}。hits=${JSON.stringify(found.hits)}`);
  }

  const again = await addDocuments(client, name, {
    ids: [docs[0].id],
    documents: [docs[0].document],
    embeddings: [vector(1)],
    metadatas: [docs[0].metadata],
  });
  if (again.added !== 0 || again.skipped !== 1) {
    throw new Error(`重复写入应该跳过，实际 ${JSON.stringify(again)}`);
  }
  console.log("重复写入已跳过");
  console.log("冒烟通过");
} finally {
  await deleteKnowledgeBase(client, name).catch((error) => {
    console.error("清理集合失败", error);
  });
  await client.close();
}
