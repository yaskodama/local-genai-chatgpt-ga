# Python版AIPL 機能一覧

作成日: 2026-05-12

対象実装:

- ランタイム本体: `src/python-aipl/aipl_interp.py`
- パーサ/構文: `src/python-aipl/grammar.lark`, `src/python-aipl/aipl_parser.py`
- AST: `src/python-aipl/aipl_ast.py`
- 型検査: `src/python-aipl/aipl_typeck.py`
- 実行入口: `src/python-aipl/aipl_main.py`
- サンプル: `src/python-aipl/samples/`, `samples-ai/`, `samples-remote/`, `samples-mc/`

## 概要

Python版AIPLは、`src/python-aipl/` にある研究・拡張用ランタイムです。OCaml版よりも新しい言語機能を多く持っており、型注釈、効果注釈、所有権、線形型、構造化並行、動的コンパイル、AI呼び出し、モデル検査などを扱えます。

## 基本言語機能

Python版AIPLは、`class`、`method`、`var`、`function` を中心にしたアクター指向言語です。クラスから生成されたインスタンスはアクターとして動作し、`send`、`now`、`future`、`await` によって通信します。

- `send actor.method(args);` は非同期送信
- `now actor.method(args)` は同期呼び出し
- `future actor.method(args)` はFutureを返す非同期呼び出し
- `await(f)` または `await f` はFutureの結果待ち
- メソッド内では `self` と `sender` が使用可能

## 型システム

Python版AIPLは、OCaml版より新しい型付き構文を持ちます。変数、引数、戻り値に型注釈を書けます。

```abcl
method add(a: int, b: int) -> int {
  return a + b;
}
```

対応する主な型:

- `int`
- `float`
- `string`
- `bool`
- `array[T]`
- `tuple(...)`
- `record{...}`
- Union型
- 型変数
- 長さ付き配列
- `linear T`

`typeof(x)` により実行時の構造型も確認できます。

## Phase 11から17の機能

Python版AIPLには、Phase 11からPhase 17までの研究機能が実装されています。

| Phase | 機能 |
| --- | --- |
| Phase 11 | 型注釈、Union型、Generics、長さ付き配列 |
| Phase 12 | capability effects。例: `!{fs, ai, net, mut}` |
| Phase 13 | CSP風チャンネル |
| Phase 14 | `linear` による線形値、use-after-move検出 |
| Phase 15 | `pub` フィールドと所有権、外部書き込み禁止 |
| Phase 16 | transient cast、`any -> T` 境界の実行時検査 |
| Phase 17 | `scope { ... }` による構造化並行 |

## データ構造

配列、タプル、レコードを扱えます。

配列は `[1, 2, 3]` のようなリテラル、`array_push`、`array_get`、`array_set` などで操作します。多次元配列もあり、`var grid[rows][cols];` のように動的サイズで宣言できます。

タプルは `(1, "a")`、レコードは `{ name: "Alice", age: 30 }` のように書けます。レコードは `r.name` のようなドットアクセスに対応しています。

## 関数

トップレベル関数とクラス内関数を定義できます。関数は `return` によって同期的に値を返します。クラス内関数は、そのクラスのメソッドから補助関数として呼び出せます。

また、`typeof(function_name)` により、実行時に観測された呼び出し履歴から推定された関数シグネチャを表示できます。

## アクター機能

アクターはメッセージキューを持ち、非同期に動作します。`reply(value)` によって `now` や `future` の呼び出し元に値を返します。

`become Class(args);` によって、実行中のアクターの振る舞いを別クラスへ変更できます。

## チャンネル

CSP風のチャンネル機能があります。

```text
channel(capacity, type_name)
channel_send(ch, value)
channel_recv(ch)
channel_try_recv(ch)
channel_close(ch)
channel_size(ch)
select_recv([ch1, ch2], timeout_ms)
```

これにより、アクター間通信とは別に、明示的な同期キューを使えます。

## 動的コンパイルと動的生成

`compile(source)` により、文字列として渡したAIPLソースを実行中にコンパイルできます。`spawn(class_name, args...)` により、文字列で指定したクラスからアクターを生成できます。

さらに、以下のメソッドインジェクション機能があります。

```text
add_method(target, source)
remove_method(target, name)
methods_of(target)
```

これにより、クラスまたは特定アクターへメソッドを動的に追加・削除できます。

## AI連携

Python版AIPLは、生成AI呼び出しを組み込み関数として持っています。

```text
ai_call(prompt)
ai_call_with_system(system, prompt)
ai_call_priority(priority, prompt)
ai_call_retry(max_attempts, prompt)
ai_call_image(prompt, image)
ai_usage()
ai_remaining()
ai_cost()
```

Gemini、Anthropic Claude、OpenAIを切り替えられます。`AIPL_AI_PROVIDER=mock` を使うと、外部APIなしでテストできます。

また、起動時に `AI` アクターが自動生成され、`now AI.ask("...")` や `future AI.ask("...")` の形でAIをアクターとして扱えます。

## ファイル、JSON、画像処理

Python版AIPLには、アプリ生成やデータ処理向けの組み込みもあります。

```text
read_file
write_file
append_file
read_bytes
write_bytes
json_parse
json_stringify
image_load
image_save
image_create
image_pixel
image_set_pixel
image_size
```

画像処理はPillowを使います。AIPLだけでHTML、CSS、画像、JSON manifestを生成するサンプルもあります。

## 分散アクター

HTTP経由で別プロセス、別ランタイムのアクターと通信できます。

```text
web_listen(port)
web_expose(name, actor)
remote_call(host, actor, method, args...)
remote_now(host, actor, method, args...)
remote_future(host, actor, method, args...)
serve_forever()
```

OCaml版との相互通信も想定されており、JSON形式の `/api/json/send` と `/api/json/call` を使います。

## モデル検査

Python版AIPLには、アクタープログラムの bounded model checking 用モジュールがあります。`aipl_modelcheck.py`、`aipl_modelcheck_load.py` により、食事する哲学者やロック順序などのサンプルを検査できます。

また、Promela/SPIN向け出力とTLA+向け出力もあります。

- `aipl_to_promela.py`
- `aipl_to_tla.py`
- `samples-mc/*.abcl`

## 実行・テスト系

Python版AIPLのメイン実行ファイルは以下です。

```text
src/python-aipl/aipl_main.py
```

この環境ではラッパーとして次も使っています。

```text
scripts/run_aipl_python313.sh
```

サンプルは主に以下にあります。

```text
src/python-aipl/samples/
src/python-aipl/samples-ai/
src/python-aipl/samples-remote/
src/python-aipl/samples-mc/
```

テストは `_test_*.py` として多数用意されており、型検査、配列、タプル、レコード、チャンネル、線形型、所有権、メソッドインジェクション、AIアクター、モデル検査などを確認できます。

## まとめ

Python版AIPLは単なるABCL風アクター処理系ではなく、型付きアクター言語、AI統合言語、分散アクター実験基盤、モデル検査対象言語、動的自己拡張言語としての機能を持っています。

