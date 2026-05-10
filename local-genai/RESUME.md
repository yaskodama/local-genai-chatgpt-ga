# local-genai 再開メモ

このセッションで構築した「ローカル生成 AI 進化計算」の状態と、
別端末・後日の再開手順をまとめる。

## 直近のコミット

- `6fdd0a7` LocalGenAI evolved: AIPL .abcl run + lineage scoring + real Stage-3 training
- `512943d` LocalGenAIScaledEvolutionJP: v2 .ga.json + AIPL orchestrator
- `b6d6280` LocalGenAIScaledEvolutionJP.aice — corpus + params 同時進化版
- `74cec58` local-genai: stage 2 — real CharRNN training with PyTorch
- `1f53ce6` local-genai: chat.py — interactive REPL for stage-1 n-gram
- `ee6e952` local-genai: end-to-end 7-stage evolution loop

origin/main と同期済み (push 済み)。

## 作業ディレクトリ

- `local-genai/` — 実体 (corpus, candidates, evolve, chat, checkpoint)
- `aice-z-evolution/` — v1 .aice (stages/mutations 直線進化)
- `aice-evolution-v2/` — v2 .aice + .ga.json + AIPL .abcl (MAP-Elites)

## チャンピオン (現状最強モデル)

```
local-genai/out/charrnn_winner.pt
  R2 LSTM untied, hidden=128, 197K params
  TinyShakespeare-100KB 上で holdout ppl 5.23
  早期停止 (best snapshot retention)
```

## 起動手順

### 1. venv (一度だけ)

```sh
python3 -m venv local-genai/.venv
local-genai/.venv/bin/pip install torch numpy
```

### 2. 学習済みモデルと対話

```sh
local-genai/.venv/bin/python local-genai/chat.py --model charrnn -t 0.85 "your prompt"
```

stdlib のみで動く n-gram 版:

```sh
python3 local-genai/chat.py "your prompt"
```

### 3. 全 7 stage 推定スコアの再走 (~1 秒)

```sh
python3 local-genai/evolve.py
# → out/final_archive.json + out/stage_*.json
```

### 4. Stage 2 を実機学習し直す (~50 秒)

```sh
local-genai/.venv/bin/python local-genai/train_stage2.py --corpus 100KB --device cpu
# → out/charrnn_winner.pt + out/stage_CharRNN_real.json
```

オプション: `--corpus 10KB` で tiny_corpus.txt に戻す、 `--device mps` で MPS。

### 5. AIPL .abcl で MAP-Elites を回す

```sh
cd aice-evolution-v2/examples
mkdir -p out
AIPL_AI_PROVIDER=mock /opt/homebrew/bin/python3.13 \
  ../../src/python-aipl/aipl_main.py LocalGenAIScaledEvolutionJP.abcl
# → out/LocalGenAIScaledEvolutionJP.abcl_lineage.json (76 個体)
```

### 6. lineage を実スコアラで再採点

```sh
python3 local-genai/score_lineage.py
# → 上位候補と feasible 一覧を表示
# → out/lineage_top.json
```

### 7. AIPL が推した genome を実機学習

```sh
local-genai/.venv/bin/python local-genai/train_evolved.py --corpus 100KB
# → out/evolved_transformer.pt
```

## .aice → .abcl 再生成

v1 形式 (stages 直線):

```sh
python3 aice-z-evolution/aice_z_translator.py \
  aice-z-evolution/examples/LocalGenAIEvolutionJP.aice \
  -o aice-z-evolution/out
```

v2 形式 (MAP-Elites):

```sh
cd aice-evolution-v2 && /opt/homebrew/bin/python3.13 -m src.cli \
  examples/LocalGenAIScaledEvolutionJP.aice --no-run --abcl -o examples
```

## コーパス (SHA-256 ロック)

| ファイル | サイズ | SHA-256 |
|---|---:|---|
| `local-genai/corpus/tiny_corpus.txt` | 9,557 | `9614a5a4...48593e` |
| `local-genai/corpus/tinyshake_100KB.txt` | 100,000 | `caad989a...0f8839` |

## 進化の到達点 (実測)

| stage | model | corpus | params | holdout ppl |
|---|---|---:|---:|---:|
| 1 | bigram + Laplace | 9.5KB | 357 | 15.52 |
| 2 (10KB) | LSTM untied (R2) | 9.5KB | 198K | 4.48 |
| 2 (100KB) | LSTM untied (R2) | 100KB | 198K | **5.23 (champion)** |
| 3 (試) | Transformer 1-block | 100KB | 247K | 14.96 |
| 3 (試) | Transformer 4-block | 100KB | 839K | 14.18 |

教訓: byte-level / ctx=128 の固定窓 attention は LSTM の eval-time
無制限文脈に勝てない。 .aice の expected_holdout_ppl ルックアップは
楽観的すぎた。 改善には (a) ctx を伸ばす、 (b) コーパスを 1MB+ に
拡大、 (c) depth>=8 + より高度なレシピ、 が必要。

## 環境前提

- macOS arm64, M2 MPS available
- `/opt/homebrew/bin/python3.13` (lark, など普通のパッケージ入り)
- `local-genai/.venv/bin/python` (PyTorch 2.11.0, numpy 2.4.4)
- Java + tla2tools.jar (TLC 用、 `aipl_tlc.sh` が探す)
- spin 6.5.2 (`brew install spin` 済)

## 続行候補

1. **コーパス 1MB 化**: `/tmp/tinyshake.txt` (1.1MB) を `corpus/` に固定し、
   Stage 4-5 (depth=4-6 transformer) を実機学習。 ctx=256 + bf16 で 25 分以内。
2. **SemiAutoEvolve**: Ollama (gemma2:2b 等) をローカル起動し、
   過去 reviewer 採点と .aice 履歴を渡して次の mutation を 3 案起草させる。
   `aice-z-evolution/examples/LocalGenAIScaledEvolutionJP.aice` の Stage 7 仕様あり。
3. **Stage 2 を最終形と認め完了宣言**。

## デバッグ用クイックチェック

```sh
# venv が動くか
local-genai/.venv/bin/python -c "import torch; print(torch.__version__, torch.backends.mps.is_available())"

# corpus ハッシュ整合
shasum -a 256 local-genai/corpus/tiny_corpus.txt local-genai/corpus/tinyshake_100KB.txt

# checkpoint が読めるか
local-genai/.venv/bin/python -c "
import torch
ckpt = torch.load('local-genai/out/charrnn_winner.pt', weights_only=False, map_location='cpu')
print('name:', ckpt['name'], 'ppl:', ckpt['holdout_ppl'], 'params:', ckpt['params'])"

# AIPL .abcl が動くか (mock)
cd aice-evolution-v2/examples && mkdir -p out && \
  AIPL_AI_PROVIDER=mock python3 ../../src/python-aipl/aipl_main.py \
    LocalGenAIScaledEvolutionJP.abcl 2>&1 | tail -5
```

## 参照ドキュメント

- `local-genai/README.md` — local-genai 自体の概要
- `aice-z-evolution/examples/LocalGenAIEvolutionJP.aice` — 7 stage 仕様
- `aice-z-evolution/examples/LocalGenAIScaledEvolutionJP.aice` — corpus_size 同時進化
- `aice-evolution-v2/spec/ga_format.md` — .ga.json IR 仕様
