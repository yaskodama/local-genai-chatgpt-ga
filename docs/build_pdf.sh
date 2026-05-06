#!/bin/bash
# docs/SESSION_RESUME.md (および渡されたその他の .md) を PDF に変換する。
# NotebookLM へのアップロード用に日本語+コードブロックがきれいに出るよう
# 設定済み (xelatex + ヒラギノ角ゴ ProN + tango ハイライト + 目次)。
#
# 使い方:
#   bash docs/build_pdf.sh                       # SESSION_RESUME.md だけ
#   bash docs/build_pdf.sh foo.md bar.md         # 任意の .md
#   OPEN=1 bash docs/build_pdf.sh                # ビルド後に PDF を open
#
# 依存:
#   - pandoc        (brew install pandoc)
#   - xelatex       (brew install --cask mactex か basictex など)
#   - ヒラギノ角ゴ ProN (macOS デフォルト)

set -u

DOCS_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$DOCS_DIR"

# ---- 依存チェック -------------------------------------------------------
need_cmd() {
  if ! command -v "$1" >/dev/null 2>&1; then
    echo "[abort] $1 が見つかりません。"
    case "$1" in
      pandoc)  echo "  → brew install pandoc" ;;
      xelatex) echo "  → brew install --cask mactex (大きい) または basictex (軽量)" ;;
    esac
    exit 1
  fi
}
need_cmd pandoc
need_cmd xelatex

# ---- 引数 ---------------------------------------------------------------
if [ "$#" -eq 0 ]; then
  set -- SESSION_RESUME.md
fi

build_one() {
  local md="$1"
  if [ ! -f "$md" ]; then
    echo "[skip] $md が存在しません"
    return 1
  fi
  local pdf="${md%.md}.pdf"
  echo "=== $md → $pdf ==="

  pandoc "$md" -o "$pdf" \
    --pdf-engine=xelatex \
    -V CJKmainfont="Hiragino Kaku Gothic ProN" \
    -V mainfont="Hiragino Kaku Gothic ProN" \
    -V monofont="Menlo" \
    -V geometry:margin=2cm \
    -V geometry:a4paper \
    -V linkcolor=blue \
    -V urlcolor=blue \
    -V toccolor=gray \
    --syntax-highlighting=tango \
    --toc --toc-depth=2 \
    --metadata title="$(head -1 "$md" | sed 's/^# *//')" \
    --metadata date="$(date '+%Y-%m-%d')" \
    && echo "    ✓ $(ls -lh "$pdf" | awk '{print $5}')"
}

ok=0; fail=0
for md in "$@"; do
  if build_one "$md"; then ok=$((ok+1)); else fail=$((fail+1)); fi
done

echo ""
echo "==== summary: pass=$ok fail=$fail ===="

# ---- 後処理: open --------------------------------------------------------
if [ "${OPEN:-0}" = "1" ] && [ "$ok" -gt 0 ]; then
  for md in "$@"; do
    pdf="${md%.md}.pdf"
    [ -f "$pdf" ] && open "$pdf"
  done
fi

exit "$fail"
