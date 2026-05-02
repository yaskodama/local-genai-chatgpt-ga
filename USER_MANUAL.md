# ABCL/c+ ユーザーズマニュアル

ABCL/c+ は、東京工業大学・米澤明憲研究室で設計された並行オブジェクト指向言語 ABCL/1
を、現代的なシンタックスとマルチランタイム（OCaml ネイティブ／ブラウザ JS／C）で
再実装した言語です。本マニュアルは言語仕様の概要と、付属サンプルの解説をまとめます。

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

ABCL/c+ は **アクターモデル** に基づく並行プログラミング言語です。
プログラムは複数の独立した *アクター*（クラスのインスタンス）から構成され、
アクター同士は **非同期メッセージ** によって通信します。

- 各アクターは固有のメッセージキュー（メールボックス）を持つ
- 状態（フィールド）はアクター内に閉じ込められ、外部から直接読み書きできない
- メソッド呼び出しは **メッセージ送信 (`send`)** として表現される
- 受信側は到着順、または `select` 文で条件付きに処理する

伝統的な ABCL/1 にあった past/now/future の三種類の送信モードのうち、
ABCL/c+ では **past 型（fire-and-forget）** を `send`、**now 型（同期返答待ち）**
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

ABCL/c+ は弱い静的検査＋動的値表現を持ちます。値の種類は次のとおり。

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

> 設計思想についての補足：ABCL/c+ では「同期したいなら sender に reply、
> 待ちたいなら select、状態を切り替えたいなら become」と覚えておくと、
> 大半の並行パターンを言語機能だけで表現できます。
