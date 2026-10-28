import { env, pipeline } from "@huggingface/transformers";
import { DIMENSION, MODEL_ID, QUERY_PREFIX } from "./config.js";

env.allowRemoteModels = false;
env.allowLocalModels = true;
env.localModelPath = "/models/";

if (env.backends?.onnx?.wasm) {
  env.backends.onnx.wasm.wasmPaths = "/ort/";
  // 多线程要再拉起 pthread worker。这条在当前页面里会卡住不返回，先固定单线程，保证 WASM 能把向量算完。
  env.backends.onnx.wasm.numThreads = 1;
}

let extractor = null;
let current = null;

async function hasWebGPU() {
  if (!("gpu" in navigator)) return false;
  try {
    const adapter = await navigator.gpu.requestAdapter();
    return adapter != null;
  } catch {
    return false;
  }
}

async function load(dtype, device) {
  self.postMessage({
    type: "progress",
    update: { status: "progress", file: `${device} 推理会话` },
  });
  const session = pipeline("feature-extraction", MODEL_ID, {
    dtype,
    device,
    local_files_only: true,
    progress_callback: (update) => {
      self.postMessage({ type: "progress", update });
    },
  });
  const timeoutMs = device === "webgpu" ? 45000 : 120000;
  let timer;
  const timeout = new Promise((_, reject) => {
    timer = setTimeout(() => {
      reject(new Error(`${device} 在 ${timeoutMs / 1000} 秒内没有准备好`));
    }, timeoutMs);
  });
  try {
    return await Promise.race([session, timeout]);
  } finally {
    clearTimeout(timer);
  }
}

self.onmessage = async (event) => {
  const message = event.data;
  try {
    if (message.type === "init") {
      const dtype = message.dtype || "q8";
      const gpu = message.device === "wasm" ? false : await hasWebGPU();
      let device = message.device || (gpu ? "webgpu" : "wasm");
      let fallbackFrom = null;
      const started = performance.now();
      try {
        extractor = await load(dtype, device);
      } catch (error) {
        if (device !== "wasm") {
          fallbackFrom = `WebGPU 初始化失败：${error.message}`;
          device = "wasm";
          extractor = await load(dtype, device);
        } else {
          throw error;
        }
      }
      const loadMs = performance.now() - started;
      current = { dtype, device, loadMs, fallbackFrom };
      self.postMessage({
        type: "ready",
        modelId: MODEL_ID,
        dimension: DIMENSION,
        ...current,
      });
      return;
    }

    if (message.type === "embed") {
      if (!extractor) throw new Error("模型还没加载完");
      const texts = message.texts.map((text) =>
        message.isQuery ? `${QUERY_PREFIX}${text}` : text
      );
      const started = performance.now();
      const output = await extractor(texts, { pooling: "mean", normalize: true });
      const vectors = output.tolist();
      const ms = performance.now() - started;
      self.postMessage({ type: "result", id: message.id, vectors, ms });
    }
  } catch (error) {
    self.postMessage({
      type: "error",
      id: message.id,
      message: error?.message || String(error),
    });
  }
};
