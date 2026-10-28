export const MODEL_ID = "Xenova/bge-small-zh-v1.5";
export const MODEL_SOURCE = "https://huggingface.co/Xenova/bge-small-zh-v1.5";
export const BASE_MODEL = "BAAI/bge-small-zh-v1.5";
export const DIMENSION = 512;
export const QUERY_PREFIX = "为这个句子生成表示以用于检索相关文章：";
export const DEFAULT_DTYPE = "q8";
export const DTYPES = ["q8", "fp16", "fp32"];

export function collectionName(dtype) {
  return `kb_bge_small_zh_v15_${dtype}`;
}

export function dtypeLabel(dtype) {
  if (dtype === "q8") return "INT8";
  if (dtype === "fp16") return "FP16";
  return "FP32";
}
