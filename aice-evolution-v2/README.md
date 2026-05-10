# aice-evolution-v2

Phase 1〜7 + 9 まで動く状態です。多タスク横断で「次世代言語の方向ベクトル」を機械抽出し、
Phase 9 の `open_axes=true` ではスキーマ自体が探索中に成長します。

> **言語名について**: 本プロジェクトのアクター並列言語は **AIPL**
> (Actor-based Intelligent Parallel Language; 旧称 ABCL/c+) と呼びます。
> 実装内部のモジュール名 (`aipl_*.py`)・ファイル拡張子
> (`.abcl`)・環境変数 (`ABCL_AI_PROVIDER`) は後方互換のため維持。

## 何ができるか (現時点)

`.aice` v2 (DSL) または `.ga.json` (IR) を入力にとり、

0. `.aice` をパースして `.ga.json` に lowering (Phase 4)
1. MAP-Elites でセル単位の elite を 30 世代探索 (Phase 2)
2. 最深 lineage の champion から進化方向ベクトルを抽出 (Phase 3)
3. Pareto フロンティアの未充填セルを列挙 (Phase 3)
4. 3 シナリオ (conservative / innovative / general_purpose) でランキング (Phase 3)
5. Markdown レポートと JSON sidecar を出力 (Phase 3)
6. **(任意)** AIPL オーケストレータプログラムを生成 (Phase 5)
7. **(任意)** `--ai` で reviewer + ペアワイズ判定を実 LLM 化 (Phase 6)
8. **(任意)** `python -m src.batch` で複数タスクを横断集計 — 普遍方向と task-specific ノイズを分離 (Phase 7)

デフォルトでは決定的なモック評価 (`src/evaluator.py`)。`--ai` で
`src/ai_evaluator.py` の LLM-backed 評価に切り替わります。
`ABCL_AI_PROVIDER=mock` を指定すれば API キー無しで全パスを通せます。

## 動かす

```sh
cd aice-evolution-v2

# .aice 直入力 (推奨)
/usr/bin/python3 -m src.cli examples/NextLanguagePrediction.aice -o out

# 手書き .ga.json も受け付ける
/usr/bin/python3 -m src.cli examples/NextLanguagePrediction.ga.json -o out

# AIPL オーケストレータも一緒に生成 (Phase 5)
/usr/bin/python3 -m src.cli examples/NextLanguagePrediction.aice -o out --abcl

# 生成された AIPL プログラムを Python AIPL ランタイムで実行
ABCL_AI_PROVIDER=mock /usr/bin/python3 ../src/python-aipl/aipl_main.py \
    --timeout 60 out/NextLanguagePrediction.abcl

# Phase 6: 実 LLM 化 (mock provider なら課金なし)
ABCL_AI_PROVIDER=mock /usr/bin/python3 -m src.cli \
    examples/NextLanguagePrediction.aice -o out --ai

# 本物の LLM で走らせる場合 (お金がかかる)
ANTHROPIC_API_KEY=sk-... ABCL_AI_TOKEN_BUDGET=200000 \
    /usr/bin/python3 -m src.cli examples/NextLanguagePrediction.aice -o out --ai

# Phase 7: 複数タスクを横断集計 (普遍方向 vs ノイズの分離)
/usr/bin/python3 -m src.batch \
    examples/NextLanguagePrediction.aice \
    examples/WebServiceEvolution.aice \
    examples/DataPipelineEvolution.aice \
    examples/CompilerEvolution.aice \
    -o out --name cross_task
```

出力:

| ファイル | 内容 |
|---|---|
| `out/<name>.lineage.json`   | 全個体 (id, parents, genome, fitness, generation, cell, operator) |
| `out/<name>.elite_map.json` | 最終 cell -> champion テーブル |
| `out/<name>.ranking.json`   | trend, gaps, meta_fitness, scenario rankings |
| `out/<name>.report.md`      | 人間向けレポート (進化軌跡 / トレンド / Pareto gap / 3 シナリオ順位 / 詳細) |

テスト (全て ABCL_AI_PROVIDER=mock で API キー不要):

```sh
/usr/bin/python3 tests/test_smoke.py    # MAP-Elites end-to-end
/usr/bin/python3 tests/test_parser.py   # .aice v2 parser
/usr/bin/python3 tests/test_codegen.py  # AIPL コード生成 (parse-only)
/usr/bin/python3 tests/test_ai.py       # parse_score + AI evaluator + ai-mode codegen
/usr/bin/python3 tests/test_cross_task.py  # 多タスク横断集計 (Phase 7。事前に batch 実行が必要)
```

## ディレクトリ

```
aice-evolution-v2/
├── README.md                                this file
├── spec/ga_format.md                        .ga.json IR specification
├── schemas/programming_paradigm.schema.json shared gene schema
├── examples/NextLanguagePrediction.aice     Phase 4 target form (illustrative)
├── examples/NextLanguagePrediction.ga.json  Phase 2/3 input today
├── src/
│   ├── schema.py        gene schema + coherence rules
│   ├── operators.py     mutation / crossover (auto-derived from schema)
│   ├── evaluator.py     mock evaluator (replaced by ai_call in Phase 6)
│   ├── map_elites.py    MAP-Elites loop + lineage tracking
│   ├── analysis.py      trend vector, Pareto gap, evolvability
│   ├── ranking.py       multi-scenario ranking + pairwise win-rate proxy
│   ├── reporter.py      Markdown + JSON sidecar
│   ├── aice_parser.py   .aice v2 tokenizer + parser + lowering
│   ├── aipl_codegen.py  AIPL orchestrator codegen (Phase 5/6)
│   ├── ai_evaluator.py  LLM-backed evaluator + parse_score (Phase 6)
│   ├── cross_task.py    多タスク横断集計 (Phase 7)
│   ├── batch.py         batch CLI (Phase 7)
│   └── cli.py           entry point
├── tests/
│   ├── test_smoke.py    end-to-end sanity check
│   ├── test_parser.py   parser unit + real-file tests
│   ├── test_codegen.py  AIPL codegen smoke (parse-only)
│   ├── test_ai.py       Phase 6 AI wiring + parse_score
│   └── test_cross_task.py  Phase 7 cross-task aggregation
└── out/                 generated artifacts
```

## 設計のポイント

- **IR 先行**: `.ga.json` を真実の源にしてあるので、後から `.aice` v2
  パーサ (Phase 4) も AIPL コード生成 (Phase 5) も同じ IR を経由する。
- **Schema 駆動の operator**: mutations/crossovers は遺伝子スキーマから
  機械的に派生するので、新しいタスクごとに変異規則を書く必要はない。
- **Lineage 必携**: 進化「軌跡」を出すのが目的なので、全個体の親を
  保存し、deepest top champion からトレンドベクトルを抽出する。
- **Pareto + 多シナリオ**: 単一スカラーに潰さず、conservative /
  innovative / general_purpose の3シナリオで別ランキングを出す。
  `ranking.scenario_weights` を `.ga.json` に書けば自由に追加できる。

## DSL の文法 (Phase 4)

```
aice <Name> {
  task          = "...";
  gene_schema   = "schemas/<file>";
  evaluator     = "mock_v1";              // optional

  evaluation_tasks {
    task <TaskName> { spec = "..."; }
  }
  search {
    algorithm   = "map_elites";
    cell_axes   = "paradigm, concurrency_model, type_safety";  // CSV or list
    generations = 30;
    seed_count  = 8;
    open_axes   = true;
    rng_seed    = 42;
  }
  meta_fitness  { axis_name = 0.20; ... }
  ranking       {
    scenarios = ["conservative", "innovative", "general_purpose"];
    top_k     = 3;
    scenario_weights {
      conservative { trend_alignment = 0.45; ... }   // optional
      ...
    }
  }
  reviewers {
    reviewer <Name> { persona = "..."; weight = 0.4; }
  }
  operators { ... }   // optional; defaults are filled in
}
```

書かない場合に補われるデフォルト:

- `operators`: schema-derived `axis_resample` / `coherent_paradigm_shift` / `uniform` / `one_point`
- `ranking.scenario_weights`: 3 シナリオの標準重み
- `evaluator`: `mock_v1`
- `reviewers[*].weight`: 等分配

## AIPL オーケストレータ (Phase 5)

`--abcl` で `out/<Name>.abcl` を生成します。アクター構成:

```
Coordinator
  ├─ now ──> Generator       (seed / mutate / cross)
  ├─ now ──> Worker
  │            ├─ now ──> Util            (CSV / genome 文字列ヘルパ)
  │            ├─ now ──> Evaluator
  │            │            ├─ future ──> Reviewer1 (ai_call optional)
  │            │            ├─ future ──> Reviewer2 (ai_call optional)
  │            │            └─ future ──> Reviewer3 (ai_call optional)
  │            └─ now ──> TaskProfiles
  ├─ send ──> EliteMap       (cell -> champion)
  └─ send ──> Lineage        (全個体 dump)
```

Phase 5 の reviewer は決定的スコアリング (axis-match率)。Phase 6 で
`use_ai = 1` をフィールドにすると `ai_call_with_system(persona, prompt)`
が走り、その応答を解析して float スコアにする処理を加える計画です。

設計上の留意点 (実装で踏んだ罠):

- AIPL は **アクター内 self 再入禁止** なので、`now self.X()` はデッドロック
  します。コード生成は self 呼び出しを完全に排除し、Worker actor に複合操作を
  委譲する形にしてあります。
- Python ランタイムの `array_push` / `array_set` は **インプレース変更** で
  `None` を返します (OCaml ランタイムとは挙動が違う)。`xs = array_push(xs, v);`
  と書くと `xs = None` になってしまうので、生成コードでは戻り値を捨てています。
- `float` / `int` は **型キーワード予約** なので関数として呼べません。
  代わりに `(x + 0.0)` で float 化しています。
- `&&` / `||` も無いので、複合条件はネスト if で表現しています。

## Phase 6 — 実 LLM 結線

### Python 側 (`--ai` フラグ)

- `src/ai_evaluator.py` が `evaluator.py` の LLM 版。reviewer ごとに
  `aipl_ai.call_ai(prompt, system=persona)` を呼び、応答テキストから
  `parse_score()` で数値を抽出。
- `src/ranking.py` の `pairwise_winrate_ai()` は Pareto-1 候補の全ペアを
  「A or B?」で LLM に問い、勝率を集計。`(scenario, sorted_pair)` キーで
  キャッシュするので、シナリオ間で重複しない。

### AIPL 側 (`--abcl --ai`)

- 生成 AIPL に `class DigitOps` と `Util.parse_score(s, digits)` が追加され、
  Reviewer の `if (use_ai == 1)` 分岐が `ai_call_with_system` の応答を
  パースして float スコアにする。
- `parse_score` の self-call はないので Util と DigitOps を peer actor として
  分離 (Phase 5 で確立した設計を踏襲)。

### コスト面の留意

- reviewer 1人 × タスク 3個 × 個体 38個 ≈ **342 ai_call** / 探索1回。
  Anthropic Sonnet-4.6 で max_tokens=16 なら $0.5〜$1 程度のオーダー。
- 重い場合は `examples/<name>.aice` の `seed_count` / `generations` を
  小さくするか、`ABCL_AI_TOKEN_BUDGET` で上限を切る。
- 開発・CI は **`ABCL_AI_PROVIDER=mock`** で十分機能チェック可能。

### 設計上の留意

- `parse_score` は **失敗時 0.5 を返す neutral prior**。LLM が数値を返さない
  ケースで偏らないようにするため。
- 数値は `[0,1]` にクランプ。"75" のような無小数点値だけは `÷100` で
  パーセント解釈する (ヒューリスティック)。

## Phase 7 — 多タスク横断実験

### 出力

`python -m src.batch <a.aice> <b.aice> ...` を実行すると、各タスクで
個別にレポートを出した上で **cross-task 集計** が走り、

- `out/<name>.cross_task.report.md` — 軸別の安定性、universal direction、consensus genome
- `out/<name>.cross_task.json` — 機械可読版

を出します。

### 何が分かるか

| カテゴリ | 判定基準 | 解釈 |
|---|---|---|
| **Universal axes** | sign-agree ≥ 75% かつ \|mean\| > 0.05 | タスクを超えた進化圧力 — 「次世代言語が満たすべき真の方向」 |
| **Task-specific noise** | sign-agree < 75% | 個別タスクで揺れる軸 — 言語選好の自由度 |
| **Consensus genome** | Pareto-top の多数決 | 普遍 + 噪音をすべて踏まえた「機械的な提案」 |

### 同梱の Phase 7 サンプル

| .aice | タスク内訳 | 想定する domain |
|---|---|---|
| `NextLanguagePrediction.aice` | TrafficLight + BankAccount + Philosophers | 並行 + 状態機械 |
| `WebServiceEvolution.aice` | WebService + BankAccount + TrafficLight | リクエスト処理 + 認可 |
| `DataPipelineEvolution.aice` | DataPipeline + Compiler + TrafficLight | 関数型 + 型 |
| `CompilerEvolution.aice` | Compiler + DataPipeline + BankAccount | 型システム重視 |

4つを横断して集計すると `type_safety: +` と `concurrency_model: -` が 100% sign-agreement で
universal direction として抽出されます (現状のモック評価器の場合)。実 LLM (`--ai`) で
回せばより意味のある方向ベクトルが出ます。

### 設計上の留意

- Cross-task universality は **複数のシードで再現** することで初めて意味を持ちます。
  単一実行で 100% 一致しても 1 サンプルではノイズの可能性が排除できないので、
  本番では `--repeat N` 相当 (各 .aice を異なる rng_seed で複数回回す) が望ましい。
  Phase 7 では同一 seed で複数タスクを比較する形に留めています。
- Consensus genome は Pareto-top の **多数決** なので、僅差の場合は
  シナリオ重みに敏感です。`votes / total` 列を見てから採用判断すべき。

## Phase 9 — open_axes による動的スキーマ拡張

`search.open_axes = true` を `.aice` に書くと、MAP-Elites が以下の 2 操作子で
**スキーマ自体を探索中に成長させます**:

| operator | 動作 | 既定 weight |
|---|---|---|
| `llm_proposal` | 既存軸に新しい値を提案 (例: `paradigm` に `Gradual`) | 0.25 |
| `llm_new_axis` | 軸そのものを新規追加 (例: `differentiable_types`) | 0.05 |

提案は 2 モード: **mock** (デフォルト, テスト用; `src/ai_proposer.py` の
キュレーション bank から決定的に選ぶ) と **ai** (`--ai` 指定時; 実 LLM)。

発見された (axis, value) ペアは:
- `schema.discovered_axes` / `schema.discovered_values` に記録
- `report.md` の **5b 章**、`ranking.json` の `discoveries` ブロックに出力
- 後続の探索 (mutation/crossover) で他の値と同じく選択候補になる

```sh
# Phase 9 サンプル (open_axes=true)
/usr/bin/python3 -m src.cli examples/OpenAxesEvolution.aice -o out
```

## 次のフェーズ (任意の発展方向)

| Phase | 内容 |
|---|---|
| 8  | `--repeat N` でシード横断 + タスク横断の二重ノイズ除去 |
| 10 | Phase 7 結果を AIPL アクターとして実装 (cross-task メタ orchestrator) |
| 11 | Phase 9 の発見軸を Phase 7 の cross-task universal direction 抽出と統合 |
