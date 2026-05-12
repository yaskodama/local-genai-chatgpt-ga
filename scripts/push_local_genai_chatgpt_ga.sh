#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "$0")/.." && pwd)"
git_dir="$repo_root/codex_saved_gitdir_218932d"

if [ ! -d "$git_dir" ]; then
  echo "missing saved git dir: $git_dir" >&2
  exit 1
fi

export GIT_DIR="$git_dir"
export GIT_WORK_TREE="$repo_root"

git remote set-url origin https://github.com/yaskodama/local-genai-chatgpt-ga.git
git fetch origin main

if git merge-base --is-ancestor origin/main main; then
  git push -u origin main
else
  git rebase origin/main
  git push -u origin main
fi
