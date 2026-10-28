#!/usr/bin/env bash
# libseekdb.so 太大，Node 事后 dlopen 会报 static TLS block 装不下。
# 进程启动前先预加载，这块内存才会留出来。
set -euo pipefail
root="$(cd "$(dirname "$0")/.." && pwd)"
so="$(find "$root/vendor/bindings" -name libseekdb.so -print -quit || true)"
if [[ -n "$so" ]]; then
  if [[ -n "${LD_PRELOAD:-}" ]]; then
    export LD_PRELOAD="$so:$LD_PRELOAD"
  else
    export LD_PRELOAD="$so"
  fi
fi
exec "$@"
