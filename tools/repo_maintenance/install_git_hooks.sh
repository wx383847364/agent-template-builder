#!/bin/sh
set -eu

REPO_ROOT="$(git rev-parse --show-toplevel)"

chmod +x "${REPO_ROOT}/.githooks/commit-msg"
git -C "${REPO_ROOT}" config core.hooksPath .githooks

echo "[ok] Git hooks installed: core.hooksPath=.githooks"
