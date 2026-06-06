#!/usr/bin/env bash
set -euo pipefail

INSTALL_DIR="$(pwd)"
DEFAULT_WORKDIR="$HOME/.stock_tools"
PATH_FILE="$HOME/.stock_tools_path"

echo "StockTools setup"
read -r -p "工作目录 [$DEFAULT_WORKDIR]: " WORKDIR
WORKDIR="${WORKDIR:-$DEFAULT_WORKDIR}"
WORKDIR="${WORKDIR/#\~/$HOME}"

if [ -d "$WORKDIR" ]; then
  echo "工作目录已存在，跳过创建: $WORKDIR"
else
  mkdir -p "$WORKDIR"
  echo "已创建工作目录: $WORKDIR"
fi

if [ -f "$PATH_FILE" ]; then
  CURRENT_PATH="$(cat "$PATH_FILE" || true)"
  if [ "$CURRENT_PATH" = "$WORKDIR" ]; then
    echo "工作目录记录已存在，跳过: $PATH_FILE"
  else
    read -r -p "已存在 $PATH_FILE，是否覆盖？[y/N] " REPLACE_PATH
    if [ "$REPLACE_PATH" = "y" ] || [ "$REPLACE_PATH" = "Y" ]; then
      printf '%s\n' "$WORKDIR" > "$PATH_FILE"
      echo "已更新工作目录记录。"
    else
      echo "跳过工作目录记录更新。"
    fi
  fi
else
  printf '%s\n' "$WORKDIR" > "$PATH_FILE"
  echo "已写入工作目录记录: $PATH_FILE"
fi

export STOCKTOOLS_HOME="$WORKDIR"
python3 - <<'PY'
from stocktools.infra.paths import Paths

paths = Paths.resolve()
paths.init_databases()
print(f"数据库结构已初始化: {paths.database_path}")
print(f"模型配置库已初始化: {paths.config_path}")
PY

RC_FILE="$HOME/.zshrc"
if [ ! -f "$RC_FILE" ] && [ -f "$HOME/.bashrc" ]; then
  RC_FILE="$HOME/.bashrc"
fi

if [ -f "$RC_FILE" ] && grep -q "# StockTools begin" "$RC_FILE"; then
  echo "shell 配置片段已存在，跳过: $RC_FILE"
else
  {
    echo ""
    echo "# StockTools begin"
    echo "function st() { python3 \"$INSTALL_DIR/st.py\" \"\$@\"; }"
    echo "# StockTools end"
  } >> "$RC_FILE"
  echo "已写入 st 命令到: $RC_FILE"
fi

HAS_MODEL_CONFIG="$(python3 - <<'PY'
from stocktools.config.model_config_repo import ModelConfigRepo
from stocktools.infra.paths import Paths

print("yes" if ModelConfigRepo(Paths.resolve().config_path).get() else "no")
PY
)"

WRITE_MODEL="n"
if [ "$HAS_MODEL_CONFIG" = "yes" ]; then
  read -r -p "模型配置已存在，是否覆盖？[y/N] " WRITE_MODEL
else
  read -r -p "是否现在配置模型？[Y/n] " WRITE_MODEL
  WRITE_MODEL="${WRITE_MODEL:-y}"
fi

if [ "$WRITE_MODEL" = "y" ] || [ "$WRITE_MODEL" = "Y" ]; then
  read -r -p "base_url: " MODEL_BASE_URL
  read -r -p "api_key: " MODEL_API_KEY
  read -r -p "model_name [deepseek-chat]: " MODEL_NAME
  MODEL_NAME="${MODEL_NAME:-deepseek-chat}"
  MODEL_BASE_URL="$MODEL_BASE_URL" MODEL_API_KEY="$MODEL_API_KEY" MODEL_NAME="$MODEL_NAME" python3 - <<'PY'
import os
from stocktools.config.model_config_repo import ModelConfigRepo
from stocktools.infra.paths import Paths

ModelConfigRepo(Paths.resolve().config_path).upsert(
    os.environ["MODEL_BASE_URL"],
    os.environ["MODEL_API_KEY"],
    os.environ["MODEL_NAME"],
)
print("模型配置已写入。")
PY
else
  echo "跳过模型配置。"
fi

read -r -p "是否配置每日自动 update cron？默认 15:05 [Y/n] " SET_CRON
SET_CRON="${SET_CRON:-y}"
if [ "$SET_CRON" = "y" ] || [ "$SET_CRON" = "Y" ]; then
  CRON_EXISTS="no"
  if crontab -l 2>/dev/null | grep -q "# StockTools cron begin"; then
    CRON_EXISTS="yes"
  fi
  REPLACE_CRON="y"
  if [ "$CRON_EXISTS" = "yes" ]; then
    read -r -p "StockTools cron 已存在，是否替换？[y/N] " REPLACE_CRON
  fi
  if [ "$CRON_EXISTS" = "no" ] || [ "$REPLACE_CRON" = "y" ] || [ "$REPLACE_CRON" = "Y" ]; then
    read -r -p "小时 [15]: " CRON_HOUR
    read -r -p "分钟 [05]: " CRON_MINUTE
    CRON_HOUR="${CRON_HOUR:-15}"
    CRON_MINUTE="${CRON_MINUTE:-05}"
    python3 "$INSTALL_DIR/st.py" cron set "$CRON_HOUR" "$CRON_MINUTE"
  else
    echo "跳过 cron 替换。"
  fi
else
  echo "跳过 cron 配置。"
fi

echo "setup 完成。重新打开终端或执行 source \"$RC_FILE\" 后即可使用 st。"
