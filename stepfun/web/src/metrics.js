export function recallAtK(relevant, rankedDocs, k) {
  const top = new Set(rankedDocs.slice(0, k));
  const rel = [...new Set(relevant)];
  if (rel.length === 0) return 0;
  let hit = 0;
  for (const id of rel) {
    if (top.has(id)) hit += 1;
  }
  return hit / rel.length;
}

export function ndcgAtK(relevant, rankedDocs, k) {
  const rel = new Set(relevant);
  const gains = rankedDocs.slice(0, k).map((id) => (rel.has(id) ? 1 : 0));
  const dcg = gains.reduce((sum, gain, index) => sum + gain / Math.log2(index + 2), 0);
  const idealCount = Math.min(k, rel.size);
  let idcg = 0;
  for (let index = 0; index < idealCount; index += 1) {
    idcg += 1 / Math.log2(index + 2);
  }
  return idcg === 0 ? 0 : dcg / idcg;
}

export function median(values) {
  if (!values.length) return null;
  const sorted = [...values].sort((a, b) => a - b);
  const mid = Math.floor(sorted.length / 2);
  if (sorted.length % 2) return sorted[mid];
  return (sorted[mid - 1] + sorted[mid]) / 2;
}

export function docOrder(hits) {
  const seen = new Set();
  const ordered = [];
  for (const hit of hits) {
    const id = hit.metadata?.doc_id || hit.id;
    if (seen.has(id)) continue;
    seen.add(id);
    ordered.push(id);
  }
  return ordered;
}
