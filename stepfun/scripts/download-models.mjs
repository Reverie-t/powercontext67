import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const destRoot = path.join(root, "web", "public", "models", "Xenova", "bge-small-zh-v1.5");
const repo = "Xenova/bge-small-zh-v1.5";
const files = [
  "config.json",
  "tokenizer.json",
  "tokenizer_config.json",
  "special_tokens_map.json",
  "vocab.txt",
  "quantize_config.json",
  "onnx/model.onnx",
  "onnx/model_fp16.onnx",
  "onnx/model_quantized.onnx",
];

const mirrors = [
  process.env.HF_ENDPOINT,
  "https://hf-mirror.com",
  "https://huggingface.co",
].filter(Boolean);

function minBytes(file) {
  if (file.endsWith(".onnx")) return 1_000_000;
  if (file.endsWith("tokenizer.json")) return 10_000;
  return 50;
}

async function download(file) {
  const dest = path.join(destRoot, file);
  if (fs.existsSync(dest) && fs.statSync(dest).size >= minBytes(file)) {
    console.log(`已有 ${file} ${fs.statSync(dest).size} 字节`);
    return;
  }
  fs.mkdirSync(path.dirname(dest), { recursive: true });
  let lastError = null;
  for (const mirror of mirrors) {
    const url = `${mirror.replace(/\/$/, "")}/${repo}/resolve/main/${file}`;
    try {
      console.log(`下载 ${url}`);
      const response = await fetch(url, { redirect: "follow" });
      if (!response.ok) throw new Error(`${response.status}`);
      const buffer = Buffer.from(await response.arrayBuffer());
      const head = buffer.subarray(0, 64).toString("utf8").toLowerCase();
      if (head.includes("<!doctype") || head.includes("<html")) {
        throw new Error("返回了网页，不是模型文件");
      }
      if (buffer.length < minBytes(file)) {
        throw new Error(`文件太小 ${buffer.length}`);
      }
      fs.writeFileSync(dest, buffer);
      console.log(`写好 ${file} ${buffer.length} 字节`);
      return;
    } catch (error) {
      lastError = error;
      console.error(`失败 ${url} ${error.message}`);
    }
  }
  throw lastError || new Error(`下不下来 ${file}`);
}

for (const file of files) {
  await download(file);
}

const weightNames = ["onnx/model.onnx", "onnx/model_fp16.onnx", "onnx/model_quantized.onnx"];
const weights = Object.fromEntries(
  weightNames.map((file) => [file, fs.statSync(path.join(destRoot, file)).size])
);
const fp32 = weights["onnx/model.onnx"];
const sizes = {
  model: repo,
  base_model: "BAAI/bge-small-zh-v1.5",
  scope: "只比较单个 ONNX 权重文件。tokenizer 三种精度共用，不放进压缩比。",
  bytes: weights,
  compression_ratio_fp32_over_q8: fp32 / weights["onnx/model_quantized.onnx"],
  compression_ratio_fp32_over_fp16: fp32 / weights["onnx/model_fp16.onnx"],
  measured_at: new Date().toISOString(),
};
const sizePath = path.join(root, "eval", "model-sizes.json");
fs.writeFileSync(sizePath, JSON.stringify(sizes, null, 2));
console.log(JSON.stringify(sizes, null, 2));
