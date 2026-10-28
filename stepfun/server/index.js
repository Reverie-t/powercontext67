import express from "express";
import path from "node:path";
import {
  ROOT,
  addDocuments,
  countKnowledgeBase,
  createKnowledgeBase,
  deleteKnowledgeBase,
  hybridSearch,
  listKnowledgeBases,
  openSeekdb,
  readVersion,
  refreshKnowledgeBase,
  seekdbConfig,
} from "./db.js";

const PORT = Number(process.env.PORT || 8787);
const cfg = seekdbConfig();
const { client } = await openSeekdb();

const app = express();
app.use(express.json({ limit: "32mb" }));

app.use((req, res, next) => {
  res.setHeader("Access-Control-Allow-Origin", "*");
  res.setHeader("Access-Control-Allow-Headers", "Content-Type");
  res.setHeader("Access-Control-Allow-Methods", "GET,POST,DELETE,OPTIONS");
  if (req.method === "OPTIONS") {
    res.status(204).end();
    return;
  }
  next();
});

app.use("/eval", express.static(path.join(ROOT, "eval")));
app.use(
  "/ort",
  express.static(path.join(ROOT, "vendor", "ort"), {
    setHeaders(res) {
      res.setHeader("Cross-Origin-Resource-Policy", "cross-origin");
    },
  })
);

function sendError(res, error) {
  const status = error.status || 500;
  if (status >= 500) console.error(error);
  res.status(status).json({ error: error.message || String(error) });
}

app.get("/api/health", async (_req, res) => {
  try {
    const version = await readVersion(client);
    res.json({
      ok: true,
      mode: cfg.mode,
      database: cfg.database,
      dataPath: cfg.dataPath || null,
      host: cfg.mode === "server" ? cfg.client.host : null,
      port: cfg.mode === "server" ? cfg.client.port : null,
      ...version,
    });
  } catch (error) {
    sendError(res, error);
  }
});

app.get("/api/collections", async (_req, res) => {
  try {
    res.json({ collections: await listKnowledgeBases(client) });
  } catch (error) {
    sendError(res, error);
  }
});

app.post("/api/collections", async (req, res) => {
  try {
    const created = await createKnowledgeBase(
      client,
      req.body?.name,
      Number(req.body?.dimension)
    );
    res.json(created);
  } catch (error) {
    sendError(res, error);
  }
});

app.delete("/api/collections/:name", async (req, res) => {
  try {
    res.json(await deleteKnowledgeBase(client, req.params.name));
  } catch (error) {
    sendError(res, error);
  }
});

app.get("/api/collections/:name", async (req, res) => {
  try {
    res.json(await countKnowledgeBase(client, req.params.name));
  } catch (error) {
    sendError(res, error);
  }
});

app.post("/api/collections/:name/documents", async (req, res) => {
  try {
    res.json(await addDocuments(client, req.params.name, req.body || {}));
  } catch (error) {
    sendError(res, error);
  }
});

app.post("/api/collections/:name/refresh", async (req, res) => {
  try {
    res.json(await refreshKnowledgeBase(client, req.params.name));
  } catch (error) {
    sendError(res, error);
  }
});

app.post("/api/collections/:name/search", async (req, res) => {
  try {
    res.json(await hybridSearch(client, req.params.name, req.body || {}));
  } catch (error) {
    sendError(res, error);
  }
});

const server = app.listen(PORT, "127.0.0.1", () => {
  const where =
    cfg.mode === "embedded" ? cfg.dataPath : `${cfg.client.host}:${cfg.client.port}`;
  console.log(`seekdb 接口已启动 http://127.0.0.1:${PORT}  模式=${cfg.mode}  位置=${where}`);
});

async function shutdown() {
  server.close();
  await client.close();
  process.exit(0);
}

process.on("SIGINT", shutdown);
process.on("SIGTERM", shutdown);
