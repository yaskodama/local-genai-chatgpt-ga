# OCaml版AIPL 機能一覧

作成日: 2026-05-12

対象実装:

- ランタイム本体: `src/eval_thread.ml`
- 構文定義: `src/parser.mly`, `src/lexer.mll`
- AST: `src/ast.ml`
- 型推論プレリュード: `src/typing_env.ml`, `src/infer.ml`
- REPL/バッチ実行: `src/repl_thread.ml`
- サンプル: `abclc/*.abcl`, `abclc/ai-samples/*.abcl`

## 概要

OCaml版AIPLは、Actor-based Intelligent Parallel Language のOCaml実装です。
各 `class` のインスタンスがアクターとして生成され、メッセージキューと
OCaml Thread によって並行実行されます。

Python版AIPLにあるPhase 11以降の新しい表面構文、たとえば引数型注釈、
`pub`、`linear T`、能力エフェクト注釈、transient cast構文などは、
OCaml版のパーサでは直接扱いません。ただし、OCaml版にもHM風の簡易型推論、
`now` / `future` / `await`、リモートアクター、AI呼び出し、SDL描画、
Web gatewayなどの実行機能があります。

## 言語構文

| 分類 | 機能 | 例 |
| --- | --- | --- |
| クラス定義 | `class Name { ... }` | `class Hello { ... }` |
| フィールド | `var x = expr;`, `float x = expr;` | `var count = 0;` |
| メソッド | `method name(params) { ... }` | `method greet() { print("hi"); }` |
| オブジェクト生成 | `new Class(args)` | `var h = new Hello(5);` |
| 自動初期化 | `init` メソッドがあれば生成時に送信 | `new Hello(5)` -> `init(5)` |
| 代入 | `x = expr;` | `count = count + 1;` |
| ローカル変数 | `var x = expr;` | `var i = 0;` |
| 関数/組み込み呼び出し | `f(args)` または `call f(args);` | `print(x);`, `call print(x);` |
| 非同期送信 | `send target.method(args);` | `send h.greet();` |
| unsafe送信 | `send! target.method(args);` | `send! h.greet();` |
| 同期呼び出し | `now target.method(args)` | `var r = now calc.add(1, 2);` |
| Future | `future target.method(args)` | `var f = future w.ask(q);` |
| Await | `await expr` | `var r = await f;` |
| リモート対象 | `remote("host:port", "actor")` | `now remote("localhost:9100","reviewer").review(x)` |
| 条件分岐 | `if (cond) stmt else stmt` | `if (n < 10) { ... } else { ... }` |
| ループ | `while cond do stmt` | `while i < 10 do { ... }` |
| ブロック | `{ stmt ... }` | `{ x = x + 1; print(x); }` |
| 振る舞い変更 | `become Class(args);` | `become B();` |
| メールボックス選択 | `select { case m(args) -> { ... } timeout ms -> { ... } }` | `select { case put(x) -> { ... } }` |
| 特殊変数 | `self`, `sender` | `send self.tick();`, `send sender.reply();` |
| コメント | `// ...`, `/* ... */` | `// line comment` |

## データ型と式

| 分類 | 内容 |
| --- | --- |
| 整数 | `123` |
| 浮動小数 | `123.`, `123.45` |
| 文字列 | `"hello"` |
| 真偽値 | 比較式などから生成される内部値 |
| Unit | 組み込み関数や文の戻り値 |
| Actor参照 | `new` で生成されたアクター |
| Array | `array_empty`, `array_push`, `array_get`, `array_set` で操作 |
| Future | `future` の戻り値 |
| 算術 | `+`, `-`, `*`, `/` |
| 比較 | `>`, `<`, `>=`, `<=`, `==`, `!=` |
| 文字列連結 | `+` は片側が文字列なら文字列化して連結 |

## アクター/並行実行

| 機能 | 説明 |
| --- | --- |
| アクター生成 | `new Class(args)` でインスタンスごとにアクターを作成 |
| メッセージキュー | 各アクターが自身のキューを持つ |
| スレッド実行 | 各アクターはOCaml Threadでループ実行 |
| 非同期メッセージ | `send` は送信後に待たない |
| 同期メッセージ | `now` は受信側の `reply(value)` まで待つ |
| Future | `future` は即座にFutureハンドルを返す |
| Await | `await` はFutureの完了まで待つ |
| 返信スロット | `now` / `future` は内部のmsg_idとreply slotで相関 |
| sender | メッセージ送信元のアクター名を保持 |
| self | 現在のアクター自身 |
| become | アクターのクラス/メソッド表を差し替え、既存状態を保持 |

## 組み込み関数

### 基本I/O

| 関数 | 概要 |
| --- | --- |
| `print(x)` | 値を標準出力とWebログに出力 |
| `typeof(x)` | 実行時の型名を文字列で返す |
| `reply(x)` | `now` / `future` の呼び出し元へ値を返す |
| `wait(ms)` | ミリ秒単位でスリープ |

### 数学関数

| 関数 |
| --- |
| `sin(x)` |
| `cos(x)` |
| `tan(x)` |
| `asin(x)` |
| `acos(x)` |
| `atan(x)` |
| `sqrt(x)` |
| `exp(x)` |
| `log10(x)` |
| `abs(x)` |
| `floor(x)` |
| `ceil(x)` |
| `round(x)` |

### 配列

| 関数 | 概要 |
| --- | --- |
| `array_empty()` | 空配列を作る |
| `array_len(xs)` | 配列長を返す |
| `array_get(xs, i)` | 要素を読む |
| `array_set(xs, i, v)` | 要素を更新した新しい配列を返す |
| `array_push(xs, v)` | 末尾に追加した新しい配列を返す |

### SDL描画

| 関数 | 概要 |
| --- | --- |
| `sdl_init(w, h)` | SDLウィンドウを初期化 |
| `sdl_clear()` | 画面クリア |
| `sdl_present()` | 描画結果を表示 |
| `sdl_line(x1, y1, x2, y2)` | 線を描く |
| `sdl_erase_line(x1, y1, x2, y2)` | 線を背景色で消す |
| `sdl_line_c(x1, y1, x2, y2, r, g, b)` | 色付き線を描く |
| `sdl_poll_key()` | キー入力を非ブロッキング取得 |
| `sdl_mouse_x()` | マウスX座標 |
| `sdl_mouse_y()` | マウスY座標 |
| `sdl_mouse_down()` | 左ボタン押下状態 |

注意: `SDL_VIDEODRIVER=dummy` で実行するとウィンドウは出ません。CIやヘッドレス確認用です。

### Web/リモート連携

| 関数/構文 | 概要 |
| --- | --- |
| `web_listen(port)` | HTTP gatewayを起動 |
| `web_expose(path, actor)` | actorをWeb endpointとして公開 |
| `send remote("host:port", "actor").method(args);` | HTTP越しの非同期送信 |
| `now remote("host:port", "actor").method(args)` | HTTP越しの同期呼び出し |
| `future remote("host:port", "actor").method(args)` | HTTP越しのFuture呼び出し |

主なHTTP APIは `src/web_gateway.ml` にあり、JSON形式の `/api/json/send` と
`/api/json/call` を使います。

### AI呼び出し

| 関数 | 概要 |
| --- | --- |
| `ai_call(prompt)` | LLMへプロンプトを送る |
| `ai_call_with_system(system, prompt)` | system prompt付きでLLM呼び出し |
| `ai_call_retry(max_attempts, prompt)` | リトライ付きAI呼び出し |
| `ai_call_retry_with_system(max_attempts, system, prompt)` | system prompt付きリトライ |
| `ai_usage()` | 使用量文字列を返す |
| `ai_remaining()` | 残りトークン予算を返す。未設定なら `-1` |
| `ai_cost()` | 推定コストを返す |

関連環境変数:

| 環境変数 | 用途 |
| --- | --- |
| `ABCL_AI_PROVIDER` | `mock`, `gemini`, `anthropic`, `openai` など |
| `GEMINI_API_KEY` | Gemini API key |
| `ANTHROPIC_API_KEY` | Anthropic API key |
| `OPENAI_API_KEY` | OpenAI API key |
| `ABCL_AI_TOKEN_BUDGET` | 総トークン予算 |
| `ABCL_AI_MAX_CONCURRENT` | 同時AI呼び出し数 |
| `ABCL_AI_USAGE_FILE` | 使用量永続化ファイル |

### アクター管理/デバッグ

| 関数/コマンド | 概要 |
| --- | --- |
| `spawn(class, actor)` | 指定クラスのアクターを指定名で起動 |
| `actor_dump(actor)` | アクター型/メソッド情報を表示 |
| `actors` | REPLでアクター一覧を表示 |
| `list` / `vlist` | REPLでロード/実行中の情報を表示 |

## REPL/バッチ実行機能

OCaml版のREPL実行体は `src/abclrepl_thread` またはDuneビルド後の
`_build/default/src/repl_thread.exe` です。

| コマンド | 概要 |
| --- | --- |
| `help` | コマンド一覧 |
| `load file.abcl` | `.abcl` ファイルを読み込み、AST表示と型チェックを行う |
| `compile` | ロード済みプログラムを登録/起動 |
| `send obj.method(args)` | REPLから非同期メッセージ送信 |
| `ssend obj.method` | 引数なし簡易送信 |
| `ast name` | クラスまたはインスタンスのASTを表示 |
| `pprint name` | クラス定義を整形表示 |
| `script file.bat` | REPLコマンドをまとめて実行 |
| `clear` | 表示/バッファ系のクリア |
| `reset` | セッション状態をリセット |
| `exit` / `quit` | 終了 |

バッチ実行例:

```sh
cd /Users/yaskodama/local-genai-chatgpt-ga/aios-claude/abclc
eval $(opam env --switch=ocaml-5.1.1 --set-switch)
ocamlrun ../src/abclrepl_thread -f com04.bat
```

`com04.bat` のような `.bat` ファイルは、通常次の形式です。

```text
load LDD.abcl
compile
```

## 型推論/型関連

| 機能 | 説明 |
| --- | --- |
| HM風の型推論 | `src/infer.ml` と `src/typing_env.ml` で実装 |
| 算術型 | `int`, `float`、混在時はfloat昇格 |
| 比較型 | 数値比較、文字列の `==` / `!=` |
| `print` | 多相的に任意値を表示できる扱い |
| `reply` | 多相的に任意値を返せる扱い |
| 配列 | `array_*` に多相型を付与 |
| アクター型表示 | `actor_dump`, `typeof` で確認可能 |

制限:

- Python版の `method f(x: int) -> int` のような表面構文はOCaml版では未対応。
- Phase 11-16のサンプルは `abclc/PHASE11_16_CONTRACTS.md` に対応関係が整理されている。
- OCaml版のPhase名付きサンプルは、現在仕様の意図をOCaml版構文で近似したもの。

## トランスレータ/派生実行系

| 機能 | ファイル | 概要 |
| --- | --- | --- |
| C変換 | `src/c_translator.ml` | AIPL ASTからCランタイム風コードを生成 |
| Xinu向け変換 | `src/c_translator.ml` | Xinu向けの出力パスを含む |
| Python変換 | `src/c_translator.ml` | Pythonアクターコード生成パスを含む |
| Web gateway | `src/web_gateway.ml` | ブラウザ/HTTPからアクターへ送信 |
| Browser連携 | `src/browser-abcl/` | ブラウザ側AIPL実装/デモ |
| GUI IDE | `src/gui_ide.ml` | SDLベースのIDE |
| TUI IDE | `src/tui_ide.ml` | ターミナルUI |

## サンプル一覧

### 基本

| サンプル | 内容 |
| --- | --- |
| `abclc/Hello.abcl` | 生成、`init`、`send`、フィールド更新 |
| `abclc/counter.abcl` | カウンタ |
| `abclc/PingPong.abcl` | 2アクター間メッセージ |
| `abclc/become.abcl` | `become` による振る舞い変更 |
| `abclc/bbecome.abcl` | 状態を持つ `become` |

### 並行/同期

| サンプル | 内容 |
| --- | --- |
| `abclc/Phase11_TypedCounter.abcl` | `now` と `reply` を使う計算 |
| `abclc/Phase13_Channels.abcl` | チャンネル相当の同期サンプル |
| `abclc/bounded_buffer.abcl` | bounded buffer |
| `abclc/Philosophers5.abcl` | 食事する哲学者 |

### 描画

| サンプル | 内容 |
| --- | --- |
| `abclc/LineDrawer.abcl` | 線描画 |
| `abclc/Rotate4Lines.abcl` | 4本線の回転 |
| `abclc/Rotate4LinesGui.abcl` | GUI操作付き回転 |
| `abclc/Philosophers5Gui.abcl` | 哲学者GUI |
| `abclc/bounded_buffer_visual.abcl` | bounded buffer可視化 |

### AI/リモート

| サンプル | 内容 |
| --- | --- |
| `abclc/ai-samples/AIHello.abcl` | LLM呼び出し |
| `abclc/ai-samples/Budgeted.abcl` | AI予算/同時実行管理 |
| `abclc/ai-samples/CooperativeNowFuture.abcl` | 複数AI役割の協調 |
| `abclc/ai-samples/CooperativeNowFuture-jp.abcl` | 日本語版AI協調 |
| `abclc/ai-samples/CooperativeNowFuture-jp-remote.abcl` | リモートAI actor連携 |
| `abclc/ai-samples/RemoteCalcServer.abcl` | リモート計算サーバ |
| `abclc/ai-samples/RemoteCalcClient.abcl` | リモート計算クライアント |

## 代表的な実行コマンド

通常実行:

```sh
cd /Users/yaskodama/local-genai-chatgpt-ga/aios-claude/abclc
eval $(opam env --switch=ocaml-5.1.1 --set-switch)
ocamlrun ../src/abclrepl_thread -f run_pingpong.bat
```

描画なしのヘッドレス確認:

```sh
SDL_VIDEODRIVER=dummy SDL_RENDER_DRIVER=software \
  ocamlrun ../src/abclrepl_thread -f com04.bat
```

AIをmockで実行:

```sh
ABCL_AI_PROVIDER=mock \
  ocamlrun ../src/abclrepl_thread -f ai-samples/run_aihello.bat
```

## 現時点の主な制限

- `SDL_VIDEODRIVER=dummy` では実画面描画は表示されない。
- OCaml版はPython版より古い表面構文を使うため、型注釈付きメソッドや所有権構文はそのままでは読めない。
- `select` はAST/構文上に存在するが、サンプルと実装状況に依存するため、実運用前に対象サンプルで確認すること。
- リモート/AI機能は環境変数、API key、ネットワーク、`curl`/`jq` など外部コマンドに依存する。
- ビルド済み `src/abclrepl_thread` はOCaml runtimeのバージョンに依存するため、magic mismatchが出る場合は同じopam switchで再ビルドする。

