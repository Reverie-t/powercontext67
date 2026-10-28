#!/usr/bin/env bash
# 启动 PowerContext Server（嵌入式 seekdb 作为存储后端）。
#
#   ./scripts/start_powercontext.sh
#
# 只在 Linux / macOS 上可用：嵌入式 seekdb 依赖 pylibseekdb 的原生 wheel，Windows 没有。
# Windows 请用 WSL2。
#
# 默认监听 0.0.0.0:8000，因为 Dify 跑在容器里，需要从容器内通过 host.docker.internal
# 访问宿主机；只绑 127.0.0.1 时容器连不上。仅限本机演示，别把这个配置暴露到公网。

set -euo pipefail

PC_VERSION="${PC_VERSION:-1.4.1}"
PC_HOST="${PC_HOST:-0.0.0.0}"
PC_PORT="${PC_PORT:-8000}"

if [[ "$(uname -s)" == MINGW* || "$(uname -s)" == MSYS* || "$(uname -s)" == CYGWIN* ]]; then
  echo "Windows 不支持嵌入式 seekdb。请改用 WSL2，或参考 README 的「Windows」一节。" >&2
  exit 1
fi

if ! command -v uv >/dev/null 2>&1; then
  echo "没有找到 uv。先装：https://docs.astral.sh/uv/getting-started/installation/" >&2
  exit 1
fi

echo "==> 安装 powercontext[cli,server,seekdb]==${PC_VERSION}"
uv tool install --force "powercontext[cli,server,seekdb]==${PC_VERSION}"

# seekdb 不接受显式的 SQLAlchemy URL，切后端前必须清掉它。
unset POWERCONTEXT_SERVER_DATABASE_URL 2>/dev/null || true

export POWERCONTEXT_SERVER_DATABASE_KIND=seekdb
export POWERCONTEXT_SERVER_HTTP_HOST="${PC_HOST}"
export POWERCONTEXT_SERVER_HTTP_PORT="${PC_PORT}"
# 本地演示关掉鉴权；要开的话改成 enforced 并设置 POWERCONTEXT_SERVER_AUTH_TOKEN，
# 同时给 DSL 里三个 HTTP 节点加 Authorization 头。
export POWERCONTEXT_SERVER_ACCESS_MODE=disabled

echo "==> 数据库后端：seekdb（嵌入式）"
echo "==> 监听：${PC_HOST}:${PC_PORT}"
echo "==> 数据目录：${POWERCONTEXT_HOME:-$HOME/.local/share/powercontext}/seekdb"
echo

exec powercontext server run
