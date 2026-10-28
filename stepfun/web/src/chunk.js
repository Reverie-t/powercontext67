export function chunkText(text, size = 400, overlap = 50) {
  const clean = String(text).replace(/\r\n/g, "\n").trim();
  if (!clean) return [];
  if (clean.length <= size) return [clean];
  const parts = [];
  let start = 0;
  while (start < clean.length) {
    const end = Math.min(clean.length, start + size);
    parts.push(clean.slice(start, end));
    if (end === clean.length) break;
    start = end - overlap;
  }
  return parts;
}
