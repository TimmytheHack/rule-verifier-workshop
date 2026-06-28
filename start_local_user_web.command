#!/bin/zsh
set -e

# 双击此文件可启动本地用户 Web。
cd "$(dirname "$0")"
make bootstrap
.venv/bin/python scripts/run_local_user_web.py
