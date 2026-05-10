# サンプル問題カタログ

`src/evaluator.py` の `TASK_PROFILES` にある 6つの抽象タスクに対する具体問題定義。
各タスクの理想プロファイル (gene 値の組み合わせ) が、その問題を最も自然に解ける
パラダイム特性を表す。

## 1. TrafficLight — 信号機状態機械

**問題**: 信号機が `Red → Yellow → Green → Red` の順に状態遷移する。複数の
`tick` 要求が同時に来てもひとつの状態しか保持しない。`tick` を 4 回送ると
`Red → Yellow → Green → Red → Yellow` と進行する。

**理想プロファイル**:
- paradigm = ParallelOOP
- state_representation = symbol_owned
- concurrency_model = actor_messages
- type_safety = high

**問題が要求する性質**: 状態の単一所有 + 並行な tick 要求に対する安全な逐次化。

---

## 2. BankAccount — 銀行口座

**問題**: 残高を保持する口座に対し `deposit`/`withdraw`/`transfer` を提供。
複数スレッドからの同時操作で残高が壊れない。`withdraw` は残高不足で失敗する。
`transfer(A, B, x)` は原子的（A と B の両方が変わるか、両方変わらないか）。

**理想プロファイル**:
- paradigm = Java_OOP
- state_representation = enum_state
- concurrency_model = threads_locks
- type_safety = high
- ownership_model = gc

**問題が要求する性質**: カプセル化された状態 + ロックによる同期 + GC で扱える普通の参照。

---

## 3. Philosophers — 食事する哲学者

**問題**: 5人の哲学者が円卓で食事を取る。隣り合う哲学者はフォークを共有。
全員が同時に左フォークを取るとデッドロックが起きる。これを回避する
実装を作る (orderings / chopstick handoff / actor のいずれかで)。

**理想プロファイル**:
- paradigm = ParallelOOP
- concurrency_model = actor_messages
- ownership_model = borrow_check
- type_safety = high

**問題が要求する性質**: actor によるリソース所有 + 静的に検査される借用。

---

## 4. WebService — REST API + 認可

**問題**: HTTP リクエストを受け、認可情報を確認し、データを返す。
副作用 (DB 読み込み、外部 API 呼び出し、ログ記録) は明示的に追跡される。
構造化並行で同時複数リクエストを安全に処理。

**理想プロファイル**:
- paradigm = FunctionalOOP
- concurrency_model = structured
- type_safety = high
- effect_handling = algebraic_effects
- ownership_model = gc

**問題が要求する性質**: effect tracking + structured concurrency + capability 認可。

---

## 5. DataPipeline — ストリーミング ETL

**問題**: 入力ストリームから読み、複数の変換ステージ (filter / map /
aggregate) を経由して出力ストリームへ書く。各ステージは純粋関数として
記述され、ステージ間は backpressure 付きチャネルで接続される。

**理想プロファイル**:
- paradigm = Functional
- state_representation = ADT
- concurrency_model = csp_channels
- type_safety = high
- effect_handling = monadic

**問題が要求する性質**: 純粋関数 + ADT + チャネル + monadic effect。

---

## 6. Compiler — AST 変換

**問題**: 簡易言語のソースコードを受け、抽象構文木 (AST) を構築し、
型チェック → 最適化パス → コード生成の一連の変換を行う。各変換は
型安全に書き換える (例: λ式の β-簡約)。

**理想プロファイル**:
- paradigm = Functional
- state_representation = ADT
- concurrency_model = none
- type_safety = dependent
- ownership_model = gc

**問題が要求する性質**: ADT + パターンマッチ + 依存型 (証明付き変換)。

---

## 実験の構成

これら 6 タスクから別々の subset を選んだ 5 つの `.aice` を batch 実行：

| .aice | 採用タスク | 想定 domain |
|---|---|---|
| `NextLanguagePrediction.aice` | TrafficLight + BankAccount + Philosophers | 並行 + 状態機械 |
| `WebServiceEvolution.aice` | WebService + BankAccount + TrafficLight | リクエスト処理 |
| `DataPipelineEvolution.aice` | DataPipeline + Compiler + TrafficLight | 関数型 + 型 |
| `CompilerEvolution.aice` | Compiler + DataPipeline + BankAccount | 型システム |
| `UltimateNextLanguage.aice` | 全 6 タスク | 総合判定 |

5 runs を横断集計して universal direction を抽出する。
