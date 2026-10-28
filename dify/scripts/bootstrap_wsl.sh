#!/usr/bin/env bash
# 在 WSL2 的 Ubuntu 里跑一遍，把 uv、Docker、compose 都装好。
#
#   cd /mnt/c/Users/qflsa/WorkBuddy/2026-10-28-19-21-25/repo/dify
#   bash scripts/bootstrap_wsl.sh
#
# 中途会让你输一次 sudo 密码。

set -euo pipefail

if [[ "$(uname -s)" != "Linux" ]]; then
  echo "这个脚本要在 WSL2 的 Ubuntu 终端里跑，不是在 Windows 的 Git Bash。" >&2
  exit 1
fi

if grep -qi microsoft /proc/version 2>/dev/null; then
  echo "==> 检测到 WSL，继续"
else
  echo "==> 不是 WSL，也按普通 Ubuntu 处理"
fi

echo
echo "==> [1/3] 装基础工具"
sudo apt-get update -qq
sudo apt-get install -y -qq curl git python3 python3-venv ca-certificates

echo
echo "==> [2/3] 装 uv"
if command -v uv >/dev/null 2>&1; then
  echo "已经装了：$(uv --version)"
else
  curl -LsSf https://astral.sh/uv/install.sh | sh
  export PATH="$HOME/.local/bin:$PATH"
  echo "装好了：$(uv --version)"
fi

echo
echo "==> [3/3] 装 Docker"
if command -v docker >/dev/null 2>&1; then
  echo "已经装了：$(docker --version)"
else
  curl -fsSL https://get.docker.com | sudo sh
  sudo usermod -aG docker "$USER"
  echo "装好了，但要把你加进 docker 组才生效"
fi

echo
echo "===== 结果 ====="
echo "uv     : $(uv --version 2>/dev/null || echo '没装上')"
echo "docker : $(docker --version 2>/dev/null || echo '没装上')"
echo "compose: $(docker compose version 2>/dev/null || echo '需要重开终端后再看')"
echo
echo "下一步："
echo "  1. 关掉这个终端，重新打开（让 docker 组生效）"
echo "  2. cd $(pwd)"
echo "  3. ./scripts/start_powercontext.sh"
