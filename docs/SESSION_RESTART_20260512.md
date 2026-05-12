# セッション再起動メモ: 2026-05-12

この文書は、次回セッション開始時に作業状態を復元するための最小メモです。
作業ディレクトリ、生成済みファイル、再生成コマンド、注意点をまとめています。

## 作業ディレクトリ

```bash
cd /Users/yaskodama/local-genai-chatgpt-ga/aios-claude
```

親ディレクトリは次です。

```bash
/Users/yaskodama/local-genai-chatgpt-ga
```

## 直近の成果物

### AIPLユーザー図ガイド

以下のユーザー図ガイドを LaTeX で作成し、PDF化済みです。
全ての著者欄は次で統一済みです。

```tex
児玉靖司（Yasushi Kodama）\\法政大学（Hosei University）
```

生成済みファイル:

- `docs/OCAML_AIPL_USER_GUIDE.tex`
- `docs/OCAML_AIPL_USER_GUIDE.pdf`
- `docs/PYTHON_AIPL_USER_GUIDE.tex`
- `docs/PYTHON_AIPL_USER_GUIDE.pdf`
- `docs/JS_AIPL_USER_GUIDE.tex`
- `docs/JS_AIPL_USER_GUIDE.pdf`
- `docs/C_AIPL_USER_GUIDE.tex`
- `docs/C_AIPL_USER_GUIDE.pdf`

JS版ガイドでは、サーバ有りとサーバ無しの実行形態を分けて説明済みです。

### AIPL機能一覧

以下の機能一覧を作成済みです。

- `docs/OCAML_AIPL_FEATURES.md`
- `docs/PYTHON_AIPL_FEATURES.md`

### 論文

タイトル:

```text
型付きAIエージェント記述言語の設計と実装
```

作成済みファイル:

- `docs/TYPED_AI_AGENT_LANGUAGE_PAPER.tex`
- `docs/TYPED_AI_AGENT_LANGUAGE_PAPER.pdf`

論文は8ページです。内容は、AIPLを型付きAIエージェント記述言語として整理し、
アクター、AI呼び出し、型システム、効果、所有権、線形型、構造化並行、
OCaml/Python/JS/C の複数実装、評価、制限、今後の課題を記述しています。

### 発表スライド

論文の発表用スライドを PowerPoint 互換ファイルとして作成済みです。

- `docs/TYPED_AI_AGENT_LANGUAGE_PAPER_SLIDES.pptx`
- `scripts/generate_typed_ai_agent_slides.py`

スライドは12枚構成です。

構成:

1. タイトル
2. 背景と問題意識
3. 研究の貢献
4. AIPLの基本モデル
5. 言語機能
6. 型システム
7. AI効果・所有権・線形型
8. 実装構成
9. 評価: サンプルプログラム
10. 議論
11. 現時点の制限
12. まとめと今後の課題

`python-pptx` は未インストールだったため、標準ライブラリのみで `.pptx`
を生成するスクリプトを作成しました。ZIP構造チェックは通っています。

## PDF再生成コマンド

日本語PDFは `lualatex` ではなく、`uplatex` + `dvipdfmx` で生成しています。
`lualatex` は `luaotfload` のキャッシュ書き込み問題で失敗することがありました。

単体再生成:

```bash
uplatex -interaction=nonstopmode -halt-on-error -output-directory docs docs/TYPED_AI_AGENT_LANGUAGE_PAPER.tex
uplatex -interaction=nonstopmode -halt-on-error -output-directory docs docs/TYPED_AI_AGENT_LANGUAGE_PAPER.tex
dvipdfmx -o docs/TYPED_AI_AGENT_LANGUAGE_PAPER.pdf docs/TYPED_AI_AGENT_LANGUAGE_PAPER.dvi
```

ユーザー図ガイドをまとめて再生成:

```bash
for f in OCAML_AIPL_USER_GUIDE PYTHON_AIPL_USER_GUIDE JS_AIPL_USER_GUIDE C_AIPL_USER_GUIDE; do
  uplatex -interaction=nonstopmode -halt-on-error -output-directory docs docs/${f}.tex
  uplatex -interaction=nonstopmode -halt-on-error -output-directory docs docs/${f}.tex
  dvipdfmx -o docs/${f}.pdf docs/${f}.dvi
done
```

スライド再生成:

```bash
python3 scripts/generate_typed_ai_agent_slides.py
unzip -t docs/TYPED_AI_AGENT_LANGUAGE_PAPER_SLIDES.pptx
```

## AIPLドキュメント作成時に参照した主な実装

OCaml版:

- `src/eval_thread.ml`
- `src/parser.mly`
- `src/lexer.mll`
- `src/ast.ml`
- `src/typing_env.ml`
- `src/infer.ml`
- `src/repl_thread.ml`

Python版:

- `src/python-aipl/aipl_interp.py`
- `src/python-aipl/grammar.lark`
- `src/python-aipl/aipl_parser.py`
- `src/python-aipl/aipl_ast.py`
- `src/python-aipl/aipl_typeck.py`
- `src/python-aipl/aipl_main.py`

JavaScript版:

- `src/browser-abcl/grammar.jison`
- `src/browser-abcl/src/runtime.js`
- `src/browser-abcl/package.json`

C版:

- `src/abcl2c.ml`
- `src/c_translator.ml`
- `src/abcl_gui_runtime.c`

## 重要な注意点

- LaTeX編集は `.tex` を更新してから `uplatex` を2回実行し、最後に `dvipdfmx` を実行する。
- 日本語文書は `jsarticle`、`uplatex`、`dvipdfmx` で作成している。
- `.pptx` は `scripts/generate_typed_ai_agent_slides.py` から再生成できる。
- `docs/*.aux`, `docs/*.dvi`, `docs/*.log`, `docs/*.out`, `docs/*.toc` はLaTeX生成物。
- Git作業ツリーには未コミットファイルが多数ある。再起動後にコミットする場合は、対象ファイルを確認してから行う。
- 以前の `git push` はDNS解決の失敗やbundle remote設定で詰まっていた。GitHubへpushする場合はremote設定を再確認する。

## 現在の未コミット変更の概要

ドキュメント関連で新規または更新された主なファイル:

- `docs/OCAML_AIPL_FEATURES.md`
- `docs/PYTHON_AIPL_FEATURES.md`
- `docs/OCAML_AIPL_USER_GUIDE.tex`
- `docs/OCAML_AIPL_USER_GUIDE.pdf`
- `docs/PYTHON_AIPL_USER_GUIDE.tex`
- `docs/PYTHON_AIPL_USER_GUIDE.pdf`
- `docs/JS_AIPL_USER_GUIDE.tex`
- `docs/JS_AIPL_USER_GUIDE.pdf`
- `docs/C_AIPL_USER_GUIDE.tex`
- `docs/C_AIPL_USER_GUIDE.pdf`
- `docs/TYPED_AI_AGENT_LANGUAGE_PAPER.tex`
- `docs/TYPED_AI_AGENT_LANGUAGE_PAPER.pdf`
- `docs/TYPED_AI_AGENT_LANGUAGE_PAPER_SLIDES.pptx`
- `docs/SESSION_RESTART_20260512.md`
- `scripts/generate_typed_ai_agent_slides.py`

local-genai の進化計算関連では、MeCab対応、BPE tokenizer、Transformerモデル、
サンプル出力、GAレポートなどの未コミット成果物も残っています。

## 次回の推奨開始手順

1. 作業ディレクトリへ移動する。

```bash
cd /Users/yaskodama/local-genai-chatgpt-ga/aios-claude
```

2. 状態を確認する。

```bash
git status --short
ls -lh docs/TYPED_AI_AGENT_LANGUAGE_PAPER.pdf docs/TYPED_AI_AGENT_LANGUAGE_PAPER_SLIDES.pptx
```

3. PDFやPPTXが必要なら再生成する。

```bash
python3 scripts/generate_typed_ai_agent_slides.py
uplatex -interaction=nonstopmode -halt-on-error -output-directory docs docs/TYPED_AI_AGENT_LANGUAGE_PAPER.tex
uplatex -interaction=nonstopmode -halt-on-error -output-directory docs docs/TYPED_AI_AGENT_LANGUAGE_PAPER.tex
dvipdfmx -o docs/TYPED_AI_AGENT_LANGUAGE_PAPER.pdf docs/TYPED_AI_AGENT_LANGUAGE_PAPER.dvi
```

4. コミットする場合は、まずドキュメントだけを分けて確認する。

```bash
git status --short docs scripts
```

