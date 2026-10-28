import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const candidates = [
  path.join(root, "web", "node_modules", "onnxruntime-web", "dist"),
  path.join(root, "web", "node_modules", "@huggingface", "transformers", "node_modules", "onnxruntime-web", "dist"),
];
const source = candidates.find((dir) => fs.existsSync(dir));
if (!source) {
  console.error("没找到 onnxruntime-web。先在 web 目录执行 npm install。");
  process.exit(1);
}
const dest = path.join(root, "vendor", "ort");
fs.mkdirSync(dest, { recursive: true });
let copied = 0;
for (const name of fs.readdirSync(source)) {
  if (!name.endsWith(".wasm") && !name.endsWith(".mjs")) continue;
  fs.copyFileSync(path.join(source, name), path.join(dest, name));
  copied += 1;
}
console.log(`已从 ${source} 复制 ${copied} 个 wasm/mjs 到 vendor/ort`);
