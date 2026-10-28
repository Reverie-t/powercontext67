import { spawn, spawnSync } from "node:child_process";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const node = process.execPath;

function findSeekdbSo(dir) {
  if (!fs.existsSync(dir)) return null;
  const stack = [dir];
  while (stack.length) {
    const current = stack.pop();
    for (const name of fs.readdirSync(current)) {
      const full = path.join(current, name);
      if (fs.statSync(full).isDirectory()) stack.push(full);
      else if (name === "libseekdb.so") return full;
    }
  }
  return null;
}

function start(args, cwd, env) {
  const child = spawn(node, args, { cwd, stdio: "inherit", env });
  child.on("exit", (code) => {
    if (code) {
      process.exitCode = code;
      process.kill(process.pid, "SIGTERM");
    }
  });
  return child;
}

const so = findSeekdbSo(path.join(root, "vendor", "bindings"));
spawnSync(node, ["scripts/copy-ort.mjs"], { cwd: root, stdio: "inherit" });
const serverEnv = { ...process.env };
if (so) {
  serverEnv.LD_PRELOAD = serverEnv.LD_PRELOAD ? `${so}:${serverEnv.LD_PRELOAD}` : so;
}
const webEnv = { ...process.env };
delete webEnv.LD_PRELOAD;

const server = start(["server/index.js"], root, serverEnv);
const web = start(
  ["node_modules/vite/bin/vite.js", "--host", "127.0.0.1", "--port", "5173"],
  path.join(root, "web"),
  webEnv
);

function stop() {
  server.kill("SIGTERM");
  web.kill("SIGTERM");
}

process.on("SIGINT", () => {
  stop();
  process.exit(0);
});
process.on("SIGTERM", stop);

console.log("页面 http://127.0.0.1:5173");
console.log("数据库接口 http://127.0.0.1:8787/api/health");
