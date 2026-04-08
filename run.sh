#!/usr/bin/env bash
#
# run.sh — Serve the OpenWordnet-PT web UI locally.
#
# Usage: bash run.sh

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
CYGNET_DIR="$(cd "$SCRIPT_DIR/../cygnet" && pwd)"
exec bash "$CYGNET_DIR/run.sh" "$SCRIPT_DIR/docs"
