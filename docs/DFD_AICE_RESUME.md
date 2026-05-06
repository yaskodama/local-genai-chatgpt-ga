# DFD-driven 進化合成 / AICE メタ言語 — 再開ノート

最終更新: 2026-05-06

このメモは、`docs/SESSION_RESUME.md`（プロジェクト全体の状況）とは独立した、
**DFD 仕様からプログラムを進化計算で自動合成する** ワークストリームの再開ノート。

---

## 1. このワークストリームの目的

DFD（Data Flow Diagram）で書かれた仕様を入力に、

1. **メタ言語**で DFD を宣言的に書き下し
2. **abcl/c+** 上の合成器が `EvolveLanguagesGA` 系のパターンで GA 進化計算を実行
3. ターゲット言語（Python など）の動作プログラムを自動生成

を行う。題材は「**受付業務 DFD**」（参加者→受付の3階層図）。

---

## 2. 既に作成済みの成果物

すべて `/Users/kodamay/ocaml-app/abclcp-evolve/` 配下:

| 種別 | パス |
|---|---|
| **DFD 用 CFG**（自前のメタ言語の文法定義） | `abclc/ai-samples/dfd_meta.bnf` |
| **DFD インスタンス**（受付業務の仕様） | `abclc/ai-samples/reception.dfd` |
| **abcl 合成器**（R1〜R6 評価器） | `abclc/ai-samples/SynthesizeFromDFD.abcl` |
| **進化計算ログ**（手動シミュレートの GA トレース） | `dfd_reception_synth.log` |
| **合成された Python プログラム** | `dfd_reception_synth.py` （スモーク 3/3 通過） |
| **AICE メタファイル**（nodes セクションのみ） | `abclc/ai-samples/reception.aice` |

並行して、別件で `EvolveLanguagesGA.abcl` の prompt 改善も完了:
- 改善前ログ: `gemini-1st.log`（出力途中切れ・フォーマット混在等あり）
- 改善内容: prompt に OUTPUT FORMAT 強制、persona 厳格化（OCaml↔Haskell の取り違え防止 等）
- 改善後ログ: 未生成（API キーが立った端末で `--gemini` 再実行待ち）

---

## 3. ★ 中断時点の TODO（再開時の最初のアクション）

ユーザから **AICE メタ言語の残り 3 セクション** の文法を受け取る。

提示済の文法は:
```bnf
<program>  ::= "aice" <IDENT> "{" <section-list> "}"
<section>  ::= <nodes-section> | <memory-section>
             | <names-section>  | <evolution-section>
<nodes-section> ::= "nodes" "{" <node-list> "}"
<node-decl>     ::= "node" <IDENT> "{" <node-property-list> "}"
<node-property> ::= "runtime" "=" <STRING> ";"
                  | "host"    "=" <STRING> ";"
                  | "port"    "=" <INT>    ";"
```

未提示で待機中:
- `<memory-section>` の BNF
- `<names-section>` の BNF
- `<evolution-section>` の BNF

ユーザは「次回提示する」と明言済。

---

## 4. 文法を受け取ったら直ちにやる作業（4 ステップ）

1. **`aice_meta.bnf` の作成**
   - `dfd_meta.bnf` の隣に置く。
   - `<program>` から `<evolution-section>` まで自己完結した CFG として保存。
   - 字句規約（IDENT / STRING / INT / コメント）も明文化。

2. **`reception.aice` の拡張**
   現在 `nodes` セクションだけで失われている DFD 情報を、適切なセクションに振り分けて埋め込む。想定マッピング（実際の文法を見てから確定）:

   | DFD 情報 | 想定セクション |
   |---|---|
   | データストア（登録者台帳・当日登録者台帳） | `memory` |
   | 外部実体・データ型・名前解決 | `names` |
   | GA パラメータ（変種数・選別基準・反復上限） | `evolution` |
   | 階層分解 / I/O シグネチャ / order 制約 / `uses` 関係 | nodes プロパティ拡張 or memory/names のいずれか |

3. **適合性チェック表の作成**
   `reception.dfd` の各要素 → AICE のどのセクションのどの非終端から派生するか、機械的な対応表を作って文法的に閉じていることを示す。

4. **合成器の入力切り替え検討**
   `SynthesizeFromDFD.abcl` を `reception.dfd` ではなく `reception.aice` 経由で読めるようにするか検討。原則として **DFD 仕様（reception.dfd）が one-source-of-truth** で、AICE はそれを実装トポロジに射影したもの、という整理が綺麗。

---

## 5. 本物の進化計算を回したい時のレシピ

`dfd_reception_synth.log` は私（Claude）が手動で R1〜R6 を評価したトレース。
本物の AI で回すには:

```bash
cd /Users/kodamay/ocaml-app/abclcp-evolve
GEMINI_API_KEY=... \
  printf 'load abclc/ai-samples/SynthesizeFromDFD.abcl\ncompile\nquit\n' \
  | ABCL_AI_PROVIDER=gemini \
    /Users/kodamay/ocaml-app/abclcp-project/_build/default/src/repl_thread.exe \
  | tee dfd_reception_synth.gemini.log
```

REPL バイナリのリビルドが必要なら:
```bash
cd /Users/kodamay/ocaml-app/abclcp-project && dune build
```

---

## 6. 設計上の決定事項（覚えておくべき判断）

- **メタ言語は 2 種類ある**:
  - `dfd_meta.bnf`: DFD そのものを記述する CFG（自前設計、Japanese identifier 対応）
  - `aice_meta.bnf`（予定）: 実装トポロジ・メモリ・名前空間・進化計算パラメータを記述する CFG（ユーザ提示）
- **合成戦略は固定**: bottom-up + per-node GA + balanced-DFD check（R1〜R6）
- **Composer は子コードを逐語使用**: 合成過程で子を書き換えない、という不変条件が品質安定の核
- **per-node GA 変種**: brevity / clarity / defensive の 3 系統（`SynthesizeFromDFD.abcl` の `GAProc`, `GAStore` で実装）
- **balance check は AI ジャッジ**: 軽量な textual check。記号的検査に置き換える余地あり。

---

## 7. オープン課題（時間があれば）

- balance check を AI ジャッジから記号的（多重集合の差を計算する純粋ルーチン）に置換
- DFD パーサを実装（現状は abcl 側で文字列ハードコード — 本来は `reception.dfd` を読み込んで木にする）
- `gemini-1st.log` 改善後の `gemini-2nd.log` をユーザ環境で生成し、prompt 改修の効果を確認
- AICE グラマが揃ったら、合成器を `.aice` ファイル駆動にすることで運用情報も含めた end-to-end 自動化が可能になる
