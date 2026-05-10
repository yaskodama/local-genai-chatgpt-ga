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

**Stage-4 Transformer (1MB 学習)** — 共通 1MB tail holdout 上で ppl **5.929**

```
local-genai/out/transformer_stage4.pt
  TinyTransformer depth=4, d_model=192, n_heads=6, ctx=256, bptt=256
  ffn_mult=4, RMSNorm, learned positional, dropout 0.1
  TinyShakespeare-1MB 学習, 1.87M params
  best ppl 5.929 @ step 3500 (10000 step 走破中、3500 で peak)
  早期停止 (best snapshot retention) で過学習区間を切り捨て
```

旧 champion `charrnn_winner.pt` (R1 GRU tied, 100KB 学習, 131K params) は
1MB tail 上では ppl 14.53 (out-of-distribution 評価のため)。
1MB で再学習した GRU (`charrnn_1MB.pt`) ですら ppl 6.17 で Stage-4 に劣る
(-0.24 ppl, ≈ 4%、ただし params は Stage-4 が 14×)。

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
| `local-genai/corpus/tinyshake_1MB.txt` | 1,115,394 | `86c4e6aa...c565ed` |

## 進化の到達点 (実測)

| stage | model | corpus | params | holdout ppl (own) | 1MB tail ppl (fair) |
|---|---|---:|---:|---:|---:|
| 1 | bigram + Laplace | 9.5KB | 357 | 15.52 | — |
| 2 (10KB) | LSTM untied (R2) | 9.5KB | 198K | 4.48 | — |
| 2 (100KB) | LSTM untied (R2) | 100KB | 198K | 5.23 | — |
| 2 (100KB) | GRU tied (R1) | 100KB | 131K | 5.68 | 14.53 |
| 2c (1MB) | GRU tied (R1) | 1MB | 131K | 6.17 | **6.17** |
| 3 (試) | Transformer 1-block | 100KB | 247K | 14.96 | — |
| 3 (試) | Transformer 4-block | 100KB | 839K | 14.18 | 24.15 |
| **4 (1MB)** | **Tx d=192 d4 ctx=256** | **1MB** | **1.87M** | **5.93** | **5.93 (champion)** |

教訓:
- Stage-3 の transformer 敗北は ctx だけの問題ではなかった: BPTT < ctx
  にしていたため位置埋め込みが過学習し、コーパスも狭すぎた。
- BPTT == ctx (=256) + 1MB コーパスにすると 4-block transformer は
  step 3500 で ppl 5.93 にピークを打ち、その後 overfit。 best-snapshot
  retention で確保。
- 同じ 1MB を見せた GRU (131K params) は ppl 6.17 で transformer に
  0.24 ppl 負け。ただし params は transformer が 14× なので、
  params/ppl 効率では LSTM の勝ち。
- 残課題: (a) Stage-4b で正則化強化 or 容量縮小して transformer を
  更に押し下げ、 (b) Stage-2 LSTM を 1MB で深く回す、 (c) コーパス
  を 10MB に拡大して params を活かす空間を作る。

## 環境前提

- macOS arm64, M2 MPS available
- `/opt/homebrew/bin/python3.13` (lark, など普通のパッケージ入り)
- `local-genai/.venv/bin/python` (PyTorch 2.11.0, numpy 2.4.4)
- Java + tla2tools.jar (TLC 用、 `aipl_tlc.sh` が探す)
- spin 6.5.2 (`brew install spin` 済)

## 続行候補

1. **Stage-4b: 正則化強化 / 容量縮小** (transformer の params 効率を改善)
   - d_model=128 depth=4 dropout=0.2 → ~830K params で 5.93 を破れるか
   - もしくは Stage-4 と同じサイズで dropout 0.2 + label smoothing 0.05
2. **Stage-2c': LSTM を 1MB で深く回す**
   - hidden=192, 2-layer LSTM, steps=4000 で 6.17 を切れるか確認
3. **コーパス 10MB 化**: 1.87M params を活かす空間を確保。1MB は
   3 epoch しか回せず params/data 比が崩れている。
4. **SemiAutoEvolve**: Ollama (gemma2:2b) で次世代 mutation を
   3 案起草 (`LocalGenAIScaledEvolutionJP.aice` の Stage 7 仕様あり)。
5. **fair_compare.py のスナップショット化**: 全候補を 1MB tail で
   再評価する benchmark をリリースゲートにする。

## Stage-4 を回す手順 (次回再現用)

```sh
local-genai/.venv/bin/python local-genai/train_stage4.py \
  --steps 10000 --eval-every 500 --warmup 800 \
  --batch 24 --bptt 256 --ctx 256 \
  --depth 4 --d-model 192 --n-heads 6 \
  --lr 2e-3 --dropout 0.1 \
  --out-name transformer_stage4.pt
# 約 19 分 (M2 MPS), best ppl ~5.93 @ step 3500
```

## fair_compare 再走

```sh
local-genai/.venv/bin/python local-genai/fair_compare.py
# 全 .pt を 1MB tail (55,770 bytes) で再評価し champion を決定
```

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
