# AIPL ユーザーズマニュアル

**AIPL** (Actor-based Intelligent Parallel Language; 旧称 ABCL/c+) は、
東京工業大学・米澤明憲研究室で設計された並行オブジェクト指向言語 ABCL/1 を、
現代的なシンタックスとマルチランタイム（OCaml ネイティブ／ブラウザ JS／C）で
再実装した言語です。本マニュアルは言語仕様の概要と、付属サンプルの解説をまとめます。

> 後方互換のため、ファイル拡張子 \`.abcl\`、Python ランタイムのモジュール名
> (\`aipl_main.py\` 等)、環境変数 \`ABCL_AI_PROVIDER\` などは旧称のまま維持しています。

- 対象バージョン: 本リポジトリ (`abclcp-project`) 同梱の OCaml REPL 実装
- 主要ソース: `src/lexer.mll`, `src/parser.mly`, `src/eval_thread.ml`
- サンプル群: `abclc/*.abcl`, `src/*.abcl`

---

## 目次

1. [はじめに](#1-はじめに)
2. [処理系のビルドと実行](#2-処理系のビルドと実行)
3. [言語仕様](#3-言語仕様)
   - 3.1 [字句要素](#31-字句要素)
   - 3.2 [型と値](#32-型と値)
   - 3.3 [式と文](#33-式と文)
   - 3.4 [クラスとアクター](#34-クラスとアクター)
   - 3.5 [メッセージ送信 (`send` / `send!` / `call`)](#35-メッセージ送信-send--send--call)
   - 3.6 [`select` による選択受信](#36-select-による選択受信)
   - 3.7 [`become` による振る舞い更新](#37-become-による振る舞い更新)
   - 3.8 [`reply` と `sender`](#38-reply-と-sender)
   - 3.9 [リモート送信](#39-リモート送信)
4. [組込み関数リファレンス](#4-組込み関数リファレンス)
5. [サンプルプログラム](#5-サンプルプログラム)
   - 5.1 [Hello — 最小サンプル](#51-hello--最小サンプル)
   - 5.2 [Counter — 自己メッセージとフィールド](#52-counter--自己メッセージとフィールド)
   - 5.3 [PingPong — 二者間メッセージ往復](#53-pingpong--二者間メッセージ往復)
   - 5.4 [Become — 振る舞いの動的入れ替え](#54-become--振る舞いの動的入れ替え)
   - 5.5 [BoundedBuffer — 生産者・消費者問題](#55-boundedbuffer--生産者消費者問題)
   - 5.6 [Philosophers — 食事する哲学者](#56-philosophers--食事する哲学者)
   - 5.7 [Rotate4Lines — SDL 描画とタイマー](#57-rotate4lines--sdl-描画とタイマー)
   - 5.8 [WebCalc — HTTP ゲートウェイと `select`](#58-webcalc--http-ゲートウェイと-select)
6. [付録：トラブルシューティング](#6-付録トラブルシューティング)

---

## 1. はじめに

AIPL は **アクターモデル** に基づく並行プログラミング言語です。
プログラムは複数の独立した *アクター*（クラスのインスタンス）から構成され、
アクター同士は **非同期メッセージ** によって通信します。

- 各アクターは固有のメッセージキュー（メールボックス）を持つ
- 状態（フィールド）はアクター内に閉じ込められ、外部から直接読み書きできない
- メソッド呼び出しは **メッセージ送信 (`send`)** として表現される
- 受信側は到着順、または `select` 文で条件付きに処理する

伝統的な ABCL/1 にあった past/now/future の三種類の送信モードのうち、
AIPL では **past 型（fire-and-forget）** を `send`、**now 型（同期返答待ち）**
相当を `reply` + `select`、というかたちで提供します。

---

## 2. 処理系のビルドと実行

### 2.1 ビルド

トップディレクトリで `make` を実行すると OCaml 実装と JS 実装の両方をビルドします。

```bash
make            # = make all（OCaml + JS）
make ocaml      # OCaml REPL のみ (_build/default/src/repl_thread.exe)
make js         # ブラウザ用パーサ再生成
```

### 2.2 サンプル実行

```bash
make run-hello             # abclc/Hello.abcl
make run-philosophers      # 5哲学者
make run-rotate4           # SDL 描画デモ
./run_bounded_buffer.sh    # 有界バッファ
./run_pingpong_xinu.sh     # PingPong（XINU バックエンド）
```

任意のソースを直接食わせるには：

```bash
_build/default/src/repl_thread.exe abclc/Hello.abcl
```

### 2.3 ブラウザ実行

`src/browser-abcl/` 以下に Web 版がある。`make serve-js` で
`http://localhost:3000/` から各デモ HTML（`viz_philosophers.html` 等）が開ける。

---

## 3. 言語仕様

### 3.1 字句要素

#### コメント

```
// 行コメント
/* ブロック
   コメント */
```

#### キーワード

```
class  method  var  float  new  become
send   send!   call  remote  reply
if  then  else  while  do
select  case  timeout  ->
self  sender
```

#### 演算子

| 種別 | 演算子 |
|------|--------|
| 算術 | `+` `-` `*` `/` |
| 比較 | `==` `!=` `<` `<=` `>` `>=` |
| 代入 | `=` |

`+` は数値加算と文字列連結の両方に使われます。
片方が文字列なら他方は自動で文字列化されます（`"count = " + 5`）。

#### リテラル

- 整数: `0`, `42`
- 浮動小数: `3.14`, `100.`（末尾ドット可）
- 文字列: `"hello\n"`（エスケープは `\\` `\"` `\n` `\t` `\r`）
- 識別子: `[A-Za-z_][A-Za-z0-9_]*`

### 3.2 型と値

AIPL は弱い静的検査＋動的値表現を持ちます。値の種類は次のとおり。

| 型名 | 例 | 備考 |
|------|----|------|
| `int` | `42` | 64bit 整数 |
| `float` | `3.14`, `100.` | 倍精度 |
| `string` | `"abc"` | UTF-8 |
| `bool` | 比較演算の結果 | |
| `actor(C)` | `new C()` の結果 | クラス `C` のインスタンス |
| `array` | `array_empty()` 〜 | 要素は同型に揃える運用 |
| `unit` | `print(...)` の戻り | |

`typeof(x)` で実行時に型名（文字列）を取得できます。

### 3.3 式と文

#### 式

```
expr := リテラル
      | 識別子                  // 変数参照、self、sender
      | expr op expr            // 二項演算
      | new C(arg, ...)         // アクター生成（式中）
      | f(arg, ...)             // 組込み関数呼び出し
      | (expr)
```

#### 文

```
stmt := var x = expr ;                 // ローカル変数宣言
      | x = expr ;                     // 代入
      | f(arg, ...) ;                  // 関数呼び出し（戻り値破棄）
      | call f(arg, ...) ;             // 同上（明示形）
      | send target.method(args) ;     // 非同期メッセージ送信
      | send! target.method(args) ;    // 型検査をバイパスする送信
      | become C(args) ;               // 自己の振る舞い置換
      | if (expr) stmt [else stmt]
      | while expr do stmt
      | { stmt; stmt; ... }            // ブロック
      | select { case ... timeout ... }
```

`if` の条件は `expr` で、`==`, `!=`, `<`, `<=`, `>`, `>=` を組み合わせます。

### 3.4 クラスとアクター

```
class ClassName {
  // フィールド宣言（初期化必須）
  var fieldA = 0;
  var fieldB = 0.0;
  float fieldC = 1.5;     // 型付き宣言（float のみ専用キーワード）

  method init(args...) { ... }      // インスタンス生成時に自動起動
  method other(args...) { ... }
}
```

- フィールドは **必ず初期化付き** で宣言する
- `init` メソッドが定義されていれば `new` 時に自動で実行される
- 未定義の場合、生成時のメッセージはスキップされ警告ログが出る

トップレベルで実体化：

```
var name = new ClassName(args);
```

`name` がそのままアクター名（メールボックス参照）になります。

### 3.5 メッセージ送信 (`send` / `send!` / `call`)

#### `send` — 非同期メッセージ送信（推奨）

```
send target.method(args);
```

- `target` はトップレベルで作ったアクター変数か、`self` / `sender`
- 呼び出しは即座に戻り、メッセージは相手のメールボックスに積まれる
- 型検査が通ったメッセージのみ送る

#### `send!` — 型検査をバイパス

リモート相手やインタプリタが完全に型を見切れない動的状況のための
エスケープハッチ。**通常は `send` を使う**。

#### `call` — 組込み関数の呼び出し

組込み関数（`print`, `sdl_*`, `wait` など）に対しては `call f(...)` または
単に `f(...);` を使います。これは戻りを待つ通常の関数呼び出しで、
他アクターのメソッド呼び出しではありません。

### 3.6 `select` による選択受信

メールボックスから **特定のメッセージだけ** を待ち受けたい場合に使います。

```
select {
  case add(a, b) -> {
    reply(a + b);
  }
  case mul(a, b) -> {
    reply(a * b);
  }
  timeout 15000 -> {
    print("15 秒待っても来なかった");
  }
}
```

- 各 `case` のパターンは `メソッド名(変数名, ...)` だけを書ける（ガード式は無し）
- 一致しないメッセージはキューに残る（消費されない）
- `timeout N` はミリ秒。`N` 経過すると対応するブロックが実行される
- `timeout` 節は省略可（その場合は永久に待つ）

### 3.7 `become` による振る舞い更新

アクター自身を別のクラスに「化ける」ことができます。

```
class A {
  method ping() {
    print("A.ping");
    become B();
  }
}
class B {
  method ping() {
    print("B.ping");
    become A();
  }
}
```

`become` はメソッド本体内でのみ使え、現在のアクターのフィールドとメソッドを
新クラスの `init` 結果で置き換えます。メールボックスは保持されます。

### 3.8 `reply` と `sender`

メソッド本体では暗黙の変数 `sender` が使えます（直近にこのメッセージを送った
アクター）。

```
method add(a, b) {
  reply(a + b);            // sender に "戻り値" メッセージを送る
}
```

- `reply(v)` は `sender` 側に値 `v` を返す
- 送信側が Web ゲートウェイ（HTTP）経由なら、HTTP 応答ボディとして返る
- 送信側がアクターなら、待ちパターン（`select`）に届く

`send sender.X(args)` のように `sender` に対して任意のメソッドを送ることも可能です。

### 3.9 リモート送信

別ホストや別プロセスのアクターには次の構文で送れます。

```
send remote("localhost:8080", "fork2").take(0);
```

- 第1引数: ホストとポート（OCaml 側 `web_listen` で待ち受ける）
- 第2引数: 相手プロセス内のアクター名

ブラウザ側のサンプル `distributed_philosophers_browser.abcl` では、
`fork2` などの変数に `"@fork2"` という文字列を入れておき、
ランタイムが `@` 始まりを見て自動で HTTP に流します（`send` の解釈拡張）。

---

## 4. 組込み関数リファレンス

`src/eval_thread.ml` の `prim_table` に登録されている関数群です。
すべて `f(args)` または `call f(args);` で呼び出します。

### 4.1 入出力

| 関数 | 説明 |
|------|------|
| `print(v)` | 値を文字列化して標準出力へ。Web UI のログにも残る |
| `typeof(v)` | 型名（`"int"`, `"float"`, `"string"`, `"actor(C)"` …）を返す |

### 4.2 制御

| 関数 | 説明 |
|------|------|
| `wait(ms)` | 現在のアクター（スレッド）を `ms` ミリ秒スリープ |

### 4.3 数学関数

`sin`, `cos`, `tan`, `asin`, `acos`, `atan`, `sqrt`, `exp`, `log10`,
`abs`, `floor`, `ceil`, `round` — いずれも `float -> float`。

### 4.4 配列

| 関数 | 説明 |
|------|------|
| `array_empty()` | 空配列を生成 |
| `array_len(a)` | 要素数 |
| `array_get(a, i)` | i番目の要素（範囲外は例外） |
| `array_set(a, i, v)` | i番目を v に置換した **新しい配列** を返す |
| `array_push(a, v)` | 末尾に v を追加した **新しい配列** を返す |

> 配列は永続的データ構造として扱われる（破壊的更新は無い）。
> したがって `a = array_set(a, 0, 99.);` のように再代入する。

### 4.5 SDL 描画

| 関数 | 説明 |
|------|------|
| `sdl_init(w, h)` | ウィンドウを開く |
| `sdl_clear()` | 画面クリア |
| `sdl_present()` | フロントバッファ反映 |
| `sdl_line(x1,y1,x2,y2)` | 白線 |
| `sdl_line_c(x1,y1,x2,y2,r,g,b)` | RGB 指定線 |
| `sdl_erase_line(x1,y1,x2,y2)` | 線を消去（背景色で再描画） |
| `sdl_poll_key()` | キーのスキャンコード（押されてなければ 0） |
| `sdl_mouse_x() / sdl_mouse_y()` | マウス座標 |
| `sdl_mouse_down()` | 左ボタン状態 (0/1) |

### 4.6 Web ゲートウェイ

| 関数 | 説明 |
|------|------|
| `web_listen(port)` | 内蔵 HTTP サーバを起動 |
| `web_expose(path, actorName)` | フレンドリーパスを公開 |
| `reply(v)` | HTTP リクエスト発のメッセージなら応答ボディとして返す |

`POST /api/json/send` または `POST /api/x/<path>` で外部からアクターを呼べる。

### 4.7 デバッグ

| 関数 | 説明 |
|------|------|
| `actor_dump(a)` | アクターの型情報（クラス名・メソッド一覧）を整形出力 |

### 4.7k Phase 11 — gradual 静的型検査 (Python ランタイム)

**型注釈** を変数 / フィールド / 関数に付けると、実行前に型不整合を検出
できる。**注釈なしの場所は `any` 扱い** で警告されない (gradual)。

```
var p: int = 42;                                 // OK
var s: string = "hi";                            // OK
var bad: int = "thirty";                          // ✗ 警告

function add(a: int, b: int) -> int { return a + b; }  // OK
function bad_return(a: int) -> int { return "x"; }     // ✗ 警告

class Counter {
  var count: int = 0;
  method tick() { count = count + 1; }
  method get() -> int { return count; }            // method の return も OK
}
```

**型表現** (注釈シンタックス):

| 形 | 例 |
|----|----|
| atomic | `int`, `float`, `string`, `bool`, `any`, `unit`, `image`, `actor`, `future` |
| 配列 | `array[int]`, `array[array[int]]` |
| タプル | `tuple(int, string)` |
| レコード | `record{a: int, b: string}` |

**実行方法**:

```sh
# CLI で事前検査 (issue を stderr へ)
python3 aipl_main.py --type-check program.abcl

# 厳格モード — issue があれば exit 2 で停止
python3 aipl_main.py --type-check --strict program.abcl

# プログラム内から呼ぶ
var issues = type_check();      // array[string] of issue messages
```

**`typeof` への波及**: ユーザー関数の signature が **annotation で初期化**
され、トレース観測でさらに洗練される:

```
function add(a: int, b: int) -> int { ... }
typeof(add)   → "function(a:int, b:int) -> int"  // annotation 由来
```

サンプル: `src/python-aipl/samples/Typecheck.abcl`

#### Phase 11b の追加検査 (call-site)

- **関数呼び出しの引数型** — `f("hi", 1)` で `f(a:int, b:int)` 宣言なら flag
- **ビルトインの引数型** — `read_file(42)` を flag (signature が `path:string`)
- **メソッド呼び出しの引数型** — `now c.tick("x")` を flag (`tick(by:int)` 宣言)
- **`new C(...)` のコンストラクタ引数** — `init` の注釈と照合
- **`now obj.method()` の戻り型** — クラスの method 宣言から推論
- **可変長 `+` シグネチャ** — `path_join("a", 42, "c")` の `42` を flag
- **オプション引数 `[provider,]`** — provider あり/なしの両 arity 受理

```
function add(a: int, b: int) -> int { return a + b; }
class Counter {
  var count: int = 0;
  method init(start: int) { count = start; }
  method tick(by: int) { count = count + by; }
  method get() -> int { return count; }
}

read_file(42);                       // ✗ int vs string
add("nope", 1);                      // ✗ string vs int
add(1, 2, 3);                        // ✗ arity 3 vs 2
var c = new Counter("ten");          // ✗ string vs int
now c.tick("nope");                  // ✗ method arg
var n: int = now c.get();            // ✓ method return inferred from -> int
```

サンプル: `src/python-aipl/samples/Typecheck11b.abcl`

#### Phase 11c: Union 型 + シンプル generics

- **Union 型注釈** — `var x: int | string = ...;` で複数の型を許容
- **型変数** — 単一文字大文字 (`T`, `U`, ...) を generics に使う

```
function id(x: T) -> T { return x; }            // 型変数 T
function pair(a: T, b: T) -> tuple(T, T) { ... }
function head(arr: array[T]) -> T { return arr[0]; }

function describe(x: int | string) -> string {  // union 引数
  return "got " + x;
}

var n: int = id(42);              // T = int  → 戻り int
var s: string = id("hello");      // T = string (別の call)
var u: int | string = 42;         // OK
var u2: int | string = "x";       // OK
var u3: int | string = 3.14;      // ✗ float は不一致

pair(1, 2);                       // OK: T = int
pair(1, "two");                   // ✗ T が int に bind 済 → string と衝突
head(42);                         // ✗ array[T] が必要、int を渡された
```

generics は **per-call binding**: 各呼び出しで T が新たに束縛される。引数間で
T が複数回現れた場合 (例: `pair(a: T, b: T)`) は **同一の型でなければならない**。

サンプル: `src/python-aipl/samples/Typecheck11c.abcl`

#### Phase 11d: 制御フロー感応 (`typeof`-based narrowing)

`if (typeof(x) == "T")` の形式の guard を検出して、
**then-branch 内では `x` が `T` に narrow される** ように。
`!=` の場合は逆方向 (then-branch で `x` が `T` を除いた union に narrow)。

```
function describe(x: int | string) -> string {
  if (typeof(x) == "int") {
    var n: int = x + 1;        // ← x は int に narrow されているので OK
    return "int: " + n;
  }
  var s: string = x;            // ← else-branch では x は string に narrow
  return "str: " + s;
}

function safe_len(x: int | string) -> int {
  if (typeof(x) != "string") {
    return 0;                   // ← x は string ではないので int
  }
  var s: string = x;            // ← then-branch (反転) で x は string
  return str_len(s);
}
```

#### Phase 11e: 依存型ライト (固定長配列)

`array[T, N]` で **長さ N が型の一部** になり、

- 初期化値の長さが N と一致するか検査
- 定数インデックスでの out-of-bound を検査
- field/var への代入時にも長さチェック

```
class Demo {
  var counts: array[int, 3] = [10, 20, 30];     // OK
  method run() {
    var trio: array[int, 3] = [1, 2, 3];        // OK
    var first: int = trio[0];                   // OK
    var oops:  int = trio[5];                   // ✗ out of bounds (5 >= 3)
    var short: array[int, 5] = [1, 2];          // ✗ length 2 != 5
    counts = [1, 2];                            // ✗ length 2 != 3
  }
}
```

配列リテラル `[1, 2, 3]` の `_infer` 結果も `array[int, 3]` という長さ付き
型に強化されたので、`array[int]` (長さ未指定) と `array[int, N]` (長さ指定)
の双方向で互換性が判定される。

サンプル: `src/python-aipl/samples/Typecheck11de.abcl`

### 4.7l Phase 12 — Capability ベース効果系

関数 / メソッドの宣言末尾に `!{...}` を書くと、その関数が出してよい
**副作用カテゴリ** を宣言できる:

```
function read_config(p: string) -> string !{fs} { ... }
function classify(text: string) -> string !{ai, net} { ... }
function pipeline(p: string) -> string !{fs, ai, net} { ... }
```

主要なエフェクトカテゴリ:

| カテゴリ | ビルトイン |
|---|---|
| `fs` | `read_file` / `write_file` / `list_dir` / `mkdir` / `image_load` / ... |
| `net` | `web_listen` / `remote_*` |
| `ai` (`+ net`) | `ai_call_*` / `ai_call_image_*` (LLM 呼び出し) |
| `mut` | `compile` / `add_method` / `remove_method` / `spawn` |

**静的伝播**: 関数 A が関数 B (effect `e`) を呼んだら A の observed effect
にも `e` が混入。検査器は **declared が observed の superset でない** 場合
に flag を出す:

```
function bad(path: string) -> string !{fs} {
  return ai_call(read_file(path));      // ✗ uses {ai, fs, net}, declared only {fs}
}
```

**Gradual**: `!{...}` 注釈を **書かない** 関数は検査スキップ
(既存コード破壊回避)。書いた関数だけ厳密に検査される。

サンプル: `src/python-aipl/samples/Effects.abcl`

### 4.7j AI アクター — 自動起動・now / future 対応 (Python ランタイム)

AIPL ランタイムは **`AI` という名前のグローバルアクターを起動時に自動生成**
します (SDL ライブラリ初期化と同じ感覚)。これにより、`ai_call_*` ビルトインを
直接叩く代わりに、AIPL 標準のアクターメッセージプロトコルで AI を扱えます:

```
var r = now AI.ask("hello");           // 同期 (reply 待ち)
var f = future AI.ask("long task");    // 並列 (Future 取得)
var a = await(f);                       // 後で取り出す
send AI.ask("fire and forget");         // 戻り値捨てる
```

> 注: `call` は AIPL 予約語 (`call f(args);` 文用) なので、AI のメソッド名は
> 文脈に応じて **`ask` (テキスト) / `see` (画像) / `usage` (集計)** に
> しています。

| メソッド | 役割 |
|---------|------|
| `AI.ask(prompt)` | テキスト (auto provider) |
| `AI.ask_p(provider, prompt)` | テキスト + provider 指定 |
| `AI.ask_sys(system, prompt)` | system プロンプト付き |
| `AI.ask_sys_p(provider, system, prompt)` | 上記 + provider 指定 |
| `AI.see(prompt, image)` | マルチモーダル (画像入力) |
| `AI.see_p(provider, prompt, image)` | 上記 + provider 指定 |
| `AI.see_sys(system, prompt, image)` | 画像 + system |
| `AI.see_sys_p(provider, system, prompt, image)` | 全部入り |
| `AI.usage()` / `AI.cost()` / `AI.remaining()` | モニタリング |

並列実行が必要なら **`new AI()` で複数インスタンスを生成** すれば各々が独立に
進む (1 アクター = 1 メッセージ逐次処理)。

```
var ai_a = new AI();
var ai_b = new AI();
var fa = future ai_a.ask_p(2, "task A");
var fb = future ai_b.ask_p(3, "task B");
print(await(fa)); print(await(fb));
```

`typeof` での型推論:

| 式 | typeof 結果 |
|----|-------------|
| `AI` (autospawned) | `actor(AI, methods=[ask, ask_p, ask_sys, ...])` |
| `now AI.ask("x")` | `string` |
| `future AI.ask("x")` | `future` |
| `now AI.see("x", img)` | `string` |

サンプル: `src/python-aipl/samples/AIActor.abcl`

### 4.7h AI 呼び出し — プロバイダ指定とマルチモーダル (Python ランタイム)

すべての `ai_call_*` は **第一引数として provider を任意指定** できる:

| 値 | 指定先 |
|----|--------|
| `1` / `"gemini"` | Gemini (デフォルト) |
| `2` / `"anthropic"` / `"claude"` / `"claudecode"` | Anthropic Claude |
| `3` / `"openai"` / `"chatgpt"` / `"gpt"` | OpenAI ChatGPT |
| `0` / `"auto"` / 省略 | 環境変数 + API キーから自動選択 |

`AIPL_AI_PROVIDER=mock` を設定すれば全部 mock に流れる (テスト/デモ用)。

```
ai_call("hello")              // 自動選択
ai_call(1, "hello")           // Gemini
ai_call(2, "hello")           // Claude
ai_call(3, "hello")           // ChatGPT
ai_call("anthropic", "hello") // 文字列エイリアス
ai_call_with_system(2, "be brief", "hi")
```

**マルチモーダル (画像入力)** — `ai_call_image` ファミリーを追加:

```
var img = image_load("photo.png");
ai_call_image("describe this", img);              // 自動選択
ai_call_image(2, "describe this", img);           // Claude vision
ai_call_image(2, "compare these", img1, img2);    // 複数画像 OK
ai_call_image_with_system(2, "be brief",
                          "describe", img);
```

画像入力の型: image-load/create の結果、`read_bytes(path)` の `array[int]`、
raw `bytes`、`{ path: "x.png" }` レコードのいずれも受け付ける。MIME は PNG/
JPEG/GIF/WebP の magic bytes から自動判定。

サンプル: `src/python-aipl/samples/MultiProvider.abcl`

### 4.7g アプリ／Web サイト生成系 — ファイル / 画像 / ディレクトリ / JSON (Python ランタイム)

| 関数 | 説明 |
|------|------|
| `read_file(path)` / `write_file(p, s)` / `append_file(p, s)` / `file_exists(p)` | 既存テキスト I/O |
| `read_bytes(p)` / `write_bytes(p, bytes)` / `append_bytes(p, bytes)` | バイナリ I/O (バイトは 0-255 の int 配列) |
| `image_load(p)` | 画像読み込み (RGBA に正規化、Pillow) |
| `image_save(img, p)` | 画像保存 (拡張子から形式判定) |
| `image_create(w, h, r, g, b, a=255)` | 単色 RGBA 画像生成 |
| `image_pixel(img, x, y)` | `tuple(int, int, int, int)` を返す |
| `image_set_pixel(img, x, y, r, g, b, a=255)` | 画素書き換え (mutates) |
| `image_size(img)` | `tuple(width, height)` |
| `list_dir(p)` / `mkdir(p)` / `path_join(...)` / `path_basename(p)` / `path_dirname(p)` | ディレクトリ・パス操作 |
| `json_parse(s)` / `json_stringify(v, indent=2)` | JSON 入出力 |

`typeof` は新たに **`image(WxH, MODE)`** と **`bytes(N)`** を返します。
画像は record として `.width` / `.height` / `.mode` が読めるので、
テンプレート HTML 文字列に直接埋められます。

```
class SiteGen {
  function build_logo() {
    var img = image_create(64, 64, 0, 0, 0, 0);
    var y = 0;
    while (y < 64) do {
      var x = 0;
      while (x < 64) do {
        image_set_pixel(img, x, y, x*4, y*3, 128, 255);
        x = x + 1;
      } y = y + 1;
    }
    return img;
  }
  method generate(config) {
    mkdir("out_site");
    image_save(build_logo(), "out_site/logo.png");
    write_file("out_site/index.html",
               "<h1>" + config.site_name + "</h1>");
    write_file("out_site/manifest.json", json_stringify(config, 2));
  }
}
```

サンプル: `src/python-aipl/samples/SiteGen.abcl`
(HTML + CSS + 動的生成 PNG ロゴ + JSON manifest を 100% AIPL で出力)

### 4.7f 動的メソッド注入 / 削除 (Python ランタイム)

| 関数 | 説明 |
|------|------|
| `add_method(target, source)` | `target` がクラス名 (string) ならそのクラス全体に、actor 参照ならその個体だけに、`source` 文字列内の `method ...` 宣言を登録 |
| `remove_method(target, name)` | 名前指定でメソッドを取り除く |
| `methods_of(target)` | 現在使えるメソッド名の配列を返す |

`typeof(actor)` の出力にもメソッド一覧が含まれる:
`"actor(Greeter, methods=[greet, init, shout, whisper])"`

per-actor 注入は **そのインスタンスだけに反映** され、メソッド解決では
クラスレベルより優先される。

```
class Greeter {
  var label = "g1";
  method greet(n) { print("[" + label + "] hello, " + n); }
}
var g = new Greeter();
add_method("Greeter",
  "method shout(n) { print(\"[\" + label + \"] HEY!! \" + n); }");
var _ = now g.shout("Alice");            // [g1] HEY!! Alice
remove_method("Greeter", "shout");
```

サンプル: `src/python-aipl/samples/MethodPatch.abcl`

> メモ: メソッドはアクターの非同期メールボックスに乗るため、`send a.m()`
> の連発と `add_method` を交互にすると **タイミング順序が崩れます** (全
> send が enqueue されたあと最終状態のメソッドで処理される)。デモで
> パッチの順序を観察したい場合は `now` (同期) 経由で呼ぶこと。

### 4.7i ビルトイン関数の型シグネチャ (Python ランタイム)

`typeof(name)` は **ビルトイン名そのもの** に対しても署名文字列を返す:

```
typeof(read_bytes)
   → "function(path:string) -> array[int]"
typeof(image_create)
   → "function(w:int, h:int, r:int, g:int, b:int [, a:int=255]) -> image"
typeof(ai_call_image)
   → "function([provider,] prompt:string, image+) -> string"
typeof(json_stringify)
   → "function(value:any [, indent:int]) -> string"
typeof(typeof)
   → "function(value:any) -> string"
```

ビルトインは内部で `BuiltinRef(name)` 値として返され、署名は
`aipl_interp.py:BUILTIN_SIGNATURES` に集約。一方、**呼び出し結果**の
`typeof` は値の構造的型を返す:

```
typeof(image_create(8,8,0,200,100,255))   → "image(8x8, RGBA)"
typeof(image_pixel(img, 0, 0))             → "tuple(int, int, int, int)"
typeof(json_stringify({a:1}, 2))           → "string"
```

サンプル: `src/python-aipl/samples/Signatures.abcl`

### 4.7e ユーザー定義関数 (Python ランタイム)

```
function name(p1, p2) {
  ...
  return expr;       // 同期的な戻り値
}
```

**トップレベル** にも **クラス本体内** にも書ける。クラス内関数はその
クラスのメソッドから無修飾で呼べ、呼び出し元アクターのコンテキストを
継承するので **フィールドにアクセスでき、兄弟の関数も呼べる**。

```
class StatActor {
  var samples = [];

  function clamp(x, lo, hi) {            // クラス内ヘルパー
    if (x < lo) { return lo; }
    if (x > hi) { return hi; }
    return x;
  }

  method summary() {
    var v = clamp(samples_avg(), 0, 100);   // 兄弟関数を無修飾呼び出し
    reply(v);
  }
}
```

**トレース型推論**: 関数名を裸で書くと `FunctionRef` 値になる。
`typeof(f)` は観測されたコールから蓄積した型シグネチャを返す:

```
function describe(x) { return typeof(x) + ":" + x; }
describe(1); describe("a"); describe(3.14);
typeof(describe)
   → "function(x:float | int | string) -> string"
```

サンプル: `src/python-aipl/samples/Functions.abcl`

### 4.7d 組型 (タプル, Python ランタイム)

| 記法 | 意味 |
|------|------|
| `()` | 空タプル |
| `(x,)` | 1-タプル (末尾カンマ必須 — グルーピング `(x)` と区別) |
| `(1, 20, "test")` | N-タプル (各スロットの型は異なって良い) |
| `(2, (3, 4))` | ネストタプル |
| `t[i]` | 位置アクセス (読み取りのみ。タプルは不変) |

`typeof` はスロットごとの型を **長さも含めて** 返す:

```
typeof((1, 20, "test"))  → "tuple(int, int, string)"
typeof((2, (3, 4)))      → "tuple(int, tuple(int, int))"
typeof(())               → "tuple()"
typeof((42,))            → "tuple(int)"
```

配列との違い: 配列は同一型・可変長 (長さは型に含まれない)、
組型は位置別型・不変・**長さが型に含まれる**。

サンプル: `src/python-aipl/samples/Tuples.abcl`

### 4.7c レコード型 (Python ランタイム)

| 記法 | 意味 |
|------|------|
| `{ k1: v1, k2: v2, ... }` | レコードリテラル (Python dict として実行) |
| `r.field` | フィールド読み (チェーン可: `r.a.b.c`) |
| `r.field = v;` | フィールド書き (チェーン可) |
| `typeof(v)` | **構造的型推論** — 値のシェイプを文字列で返す |

`typeof` は再帰的に走査して構造を出します:

```
typeof({ name: "Alice", age: 30 })
   → "record{name:string, age:int}"
typeof({ owner: { id: 1, label: "ops" } })
   → "record{owner:record{id:int, label:string}}"
typeof([1, 2, 3])     → "array[int]"
typeof([1, "a"])      → "array[int | string]"
typeof(42)            → "int"
typeof(actor_ref)     → "actor(ClassName)"
```

レコードはクラスフィールドにもメソッドのローカル変数にも持たせられる:

```
class Profile {
  var owner = { id: 0, label: "anonymous" };
  var stats = { hits: 0, misses: 0 };
  method touch_hit() { stats.hits = stats.hits + 1; }
}
```

サンプル: `src/python-aipl/samples/Records.abcl`

### 4.7b 配列リテラルとインデックス記法 (Python ランタイム)

| 記法 | 意味 |
|------|------|
| `var x = [];` | 空配列 |
| `var x = [1, 2, 3];` | 配列リテラル |
| `var x[N];` | **N 要素配列を宣言** (デフォルト値 0) |
| `var x[N] = init;` | N 個全て `init` で初期化 |
| `var grid[R][C];` | **2 次元** (R×C、デフォルト 0) |
| `var grid[R][C] = init;` | 2 次元、全セル `init` |
| `var cube[A][B][C];` | 3 次元 (任意の次元数) |
| `x[i]`, `grid[i][j]`, ... | 要素読み出し |
| `x[i] = v;`, `grid[i][j] = v;`, ... | 要素書き込み |
| `array_len(x)` | (1次元の) 要素数 |
| `array_push(x, v)` | 末尾追加 (in-place、None を返す) |

**サイズ指定は任意の式**: 変数、フィールド、パラメータ、算術式が使える。

```
class Matrix {
  var rows = 4;
  var cols = 5;
  var cells[rows][cols];                  // フィールド参照で動的サイズ
  method poke(i, j, v) { cells[i][j] = v; }
}

var R = 3;
var pad[R][R + 1] = -1;                   // ローカル変数+式
```

`var x[N];` はクラスのフィールド宣言にもメソッドのローカル変数にも使える。
詳細は `src/python-aipl/samples/Arrays.abcl` (1次元) と
`samples/MultiDimArrays.abcl` (多次元) 参照。

### 4.8 動的コンパイル & 動的アクター生成 (Python ランタイム拡張)

| 関数 | 説明 |
|------|------|
| `compile(source)` | AIPL ソース文字列をパースして `class` 宣言をクラステーブルに登録。トップレベル文も実行。登録済みクラス数を返す |
| `spawn(name, args...)` | 文字列で指定したクラス名 (静的に書かれたクラス、もしくは `compile` 経由で登録されたクラス) のインスタンスをアクターとして生成。`init(args...)` も呼ぶ |

これにより **メッセージ受信を契機にアクターを動的生成する factory** が
書ける。サンプルは `src/python-aipl/samples/Dynamic.abcl` と
`samples/DynamicWorkerPool.abcl` 参照。

```
class Factory {
  method create(name, source) {
    compile(source);
    reply(spawn(name));
  }
}
var f = new Factory();
var greeter = now f.create("Greeter",
  "class Greeter { method hi(n) { print(\"hello \" + n); } }");
send greeter.hi("world");
```

---

## 5. サンプルプログラム

### 5.1 Hello — 最小サンプル

`abclc/Hello.abcl`

```
class Hello {
  float count = 0.;

  method init(n) {
    count = n;
    print("Hello object initialized with " + n);
  }

  method greet() {
    print("Hello! count = " + count);
  }

  method inc() {
    count = count + 1.;
    print("count incremented to " + count);
  }
}

var h = new Hello(5);     // ← init(5) が自動呼び出し
send h.greet();           // Hello! count = 5
send h.inc();             // count incremented to 6
send h.greet();           // Hello! count = 6
```

**学べること**: フィールド宣言、`init` の自動呼び出し、`send` による
非同期メッセージ、文字列連結 `+`。

実行：

```bash
make run-hello
```

### 5.2 Counter — 自己メッセージとフィールド

`abclc/counter.abcl`

```
class Counter {
  var count = 0.;
  method inc() {
    count = count + 1.;
    print("count:" + count);
    send self.dec(3.);
  }
  method dec(x) {
    count = count - x;
    print(count);
  }
}

var c1 = new Counter();
var c2 = new Counter();
send c1.inc();
send c2.inc();
```

**学べること**: `self` を使って自分自身にメッセージを送る、
複数アクターが独立したメールボックスを持つこと。

### 5.3 PingPong — 二者間メッセージ往復

`abclc/PingPong.abcl`

```
class Pinger {
  method init() {
    print("Pinger starting");
    send ponger.ping();
  }
  method pong() {
    print("Pinger got pong");
    send sender.ping();
  }
}

class Ponger {
  method ping() {
    print("Ponger got ping");
    send sender.pong();
  }
}

var pinger = new Pinger();
var ponger = new Ponger();
```

**学べること**: `sender` による「直前の送信元」への返信、循環メッセージで
ずっと走り続けるアクター。`init` の中から外部アクターへ `send` できる。

### 5.4 Become — 振る舞いの動的入れ替え

`abclc/become.abcl`

```
class A {
  method ping() {
    print("A.ping");
    become B();
  }
}

class B {
  method ping() {
    print("B.ping");
    become A();
  }
}

var x = new A();
send x.ping();   // A.ping  → B 化
send x.ping();   // B.ping  → A 化
send x.ping();   // A.ping
```

**学べること**: 同じアクター変数 `x` の振る舞いが受信ごとに切り替わる。
メッセージの順序は保たれ、`become` は次のメッセージから効く。

### 5.5 BoundedBuffer — 生産者・消費者問題

`abclc/bounded_buffer.abcl` （抜粋）

```
class Buffer {
  var cap = 4;
  var s0 = 0; var s1 = 0; var s2 = 0; var s3 = 0;
  var head = 0; var tail = 0; var count = 0;
  var pwaiter = ""; var pitem = 0;
  var cwaiter = "";

  method put(item) {
    if (cwaiter != "") {
      send sender.put_ok();
      send cwaiter.got(item);
      cwaiter = "";
    } else {
      if (count == cap) {
        pwaiter = sender;     // 満杯 → 生産者を待たせる
        pitem   = item;
      } else {
        // ... スロットに格納 ...
        send sender.put_ok();
      }
    }
  }
  method get() { ... }
}
```

**学べること**:

- ロックを **使わずに** 同期する手法（待機キューを自前のフィールドに保持）
- `sender` を保存しておき、後で `send pwaiter.put_ok();` のように
  「呼び出し側に応答を返す」非同期パターン
- 配列ではなくスロット変数で容量4を表現（言語の最小機能で書ける例）

実行：

```bash
./run_bounded_buffer.sh
```

### 5.6 Philosophers — 食事する哲学者

`abclc/philosophers.abcl` （抜粋）

```
object Fork {
  int taken = 0;
  method take() {
    if (taken == 0) { taken = 1; }
    else            { send self take; }   // 取られていたらリトライ
  }
  method release() { taken = 0; }
}

object Philosopher {
  int id = 0;
  object leftFork;
  object rightFork;

  method think()  { send self hungry; }
  method hungry() {
    send leftFork take;
    send rightFork take;
    send self eat;
  }
  method eat() {
    send leftFork release;
    send rightFork release;
    send self think;
  }
}
```

> 注: 上記の旧構文（`object`/`int`/`send X m` のスペース構文）は古いサンプル
> 用に互換が残されています。新しいサンプル（`Philosophers5.abcl` 等）は
> `class` ベースで書かれており、こちらが推奨スタイルです。

**学べること**: 5 つのアクター間の対称デッドロック、ハンドオフによる
回避手法、SDL 版（`Philosophers5.abcl`）ではビジュアライズも可能。

実行：

```bash
make run-philosophers     # コンソール
./run_viz_philosophers.sh # SDL ビジュアル
```

### 5.7 Rotate4Lines — SDL 描画とタイマー

`abclc/Rotate4Lines.abcl`

```
class Line {
  var cx = 0.0; var cy = 0.0;
  var angle = 0.0; var len = 50.0;
  var r = 255; var g = 255; var b = 255;
  var x1 = 0.0; var y1 = 0.0; var x2 = 0.0; var y2 = 0.0;
  var drawn = 0;

  method init(startCx, startCy, startAngle, cr, cg, cb) {
    cx = startCx; cy = startCy; angle = startAngle;
    r = cr; g = cg; b = cb;
  }

  method rotate() {
    if (drawn == 1) { call sdl_erase_line(x1, y1, x2, y2); }
    angle = angle + 3.0;
    var rad = angle * 3.14159 / 180.0;
    var dx = cos(rad) * len;
    var dy = sin(rad) * len;
    x1 = cx - dx; y1 = cy - dy;
    x2 = cx + dx; y2 = cy + dy;
    call sdl_line_c(x1, y1, x2, y2, r, g, b);
    call sdl_present();
    drawn = 1;
    call wait(32);
    send self.rotate();
  }
}

sdl_init(500, 500);
var li1 = new Line(125.0, 125.0,   0.0, 255,  80,  80);
var li2 = new Line(375.0, 125.0,  90.0,  80, 255, 120);
var li3 = new Line(125.0, 375.0, 180.0,  80, 160, 255);
var li4 = new Line(375.0, 375.0, 270.0, 255, 200,  40);
send li1.rotate(); send li2.rotate(); send li3.rotate(); send li4.rotate();
```

**学べること**: `wait(ms)` と `send self.rotate()` の組み合わせによる
「自前のタイマーループ」、4 つのアクターが独立 30FPS で回るマルチスレッド描画。

### 5.8 WebCalc — HTTP ゲートウェイと `select`

`src/web_calc1.abcl`

```
class Calc {
  method init() {
    print("Calc initialized");
    send self.main();
  }

  method add(a, b) {
    reply(999);            // すぐ来た add は 999 を返す
  }

  method main() {
    print("waiting...");
    select {
      case add(a, b) -> {
        reply(a + b);     // main 待ちの間に来た add だけ正規計算
      }
      timeout 15000 -> {
        print("timeout occurred");
      }
    }
    print("select finished");
  }
}

var calc = new Calc();
web_listen(8080);
web_expose("/calc", "calc");
print("Open http://localhost:8080/ and send to actor 'calc'");
```

**学べること**:

- `select` で「特定のメッセージだけ」を待つ書き方
- `timeout` 節
- `reply` で HTTP 応答に値を返す
- `web_listen` + `web_expose` による外部 API 化

ブラウザで `http://localhost:8080/` を開き、actor `calc` に
`{"method":"add","args":[3,4]}` を POST すると 7 が返ってきます。

---

## 6. 付録：トラブルシューティング

| 症状 | 対処 |
|------|------|
| `Unknown function: foo` | 組込みの綴り誤り。`prim_table` (`src/eval_thread.ml`) の登録名と照合 |
| `Actor X not found` | `var X = new ...;` より前に `send X....` していないか確認 |
| `[Actor] X.init arity mismatch` | `new C(args)` の引数数と `init` の仮引数数が違う |
| `select` がいつまでも返らない | パターンが受信メッセージと一致していない／`timeout` 未指定 |
| SDL ウィンドウが反応しない | `sdl_present()` を毎フレーム呼ぶ／`wait` で yield する |
| HTTP リクエストでハング | `reply` を呼んでいない or `select` が適切な `case` を持たない |

> 設計思想についての補足：AIPL では「同期したいなら sender に reply、
> 待ちたいなら select、状態を切り替えたいなら become」と覚えておくと、
> 大半の並行パターンを言語機能だけで表現できます。
