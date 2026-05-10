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

**Stage-4e Transformer (1MB 学習, 4c サイズ + 4d-orth 正則化)** —
共通 1MB tail holdout 上で ppl **5.302** (Stage-4d-orth と統計的同点、 params 半減)

```
local-genai/out/transformer_stage4e.pt
  TinyTransformer depth=3, d_model=96, n_heads=4, ctx=256, bptt=256
  ffn_mult=4, RMSNorm, learned positional
  dropout 0.1, label_smoothing 0.05, weight_decay 0.05
  TinyShakespeare-1MB 学習, 383,040 params
  best ppl 5.302 @ step 10000 (= 走破直前; さらに延長で伸びる可能性)
  訓練時間 439s (M2 MPS, ≈ 7.3 分)
```

歴代 (1MB tail で評価):
- Stage-4 (1.87M, dropout 0.1): ppl 5.929 — overfit peak step 3500
- Stage-4b (855K, dropout 0.2): ppl 5.731 — capacity↓ + reg↑ で勝利
- Stage-4c (383K, depth=3, dropout 0.2): ppl 5.521 — さらなる縮小で更に勝利
- Stage-4d-orth (855K, dropout 0.1 + ls 0.05 + wd 0.05): ppl 5.304 — 直交正則化で大勝利
- **Stage-4e (383K, depth=3 + 直交正則化): ppl 5.302** — 4c のサイズと
  4d-orth の正則化を統合、 4d-orth と統計的同点を **半分の params** で達成。
  step 10000 でまだ下降中なので延長で更に伸びる可能性。
- 1MB 再学習 GRU `charrnn_1MB.pt` (131K): ppl 6.17
- 旧 winner `charrnn_winner.pt` (100KB 学習, 131K): 1MB tail 上で ppl 14.53 (OOD)

**Pareto 経路** (1MB tail ppl × params, 図示):
```
ppl
6.2 | ● R1_1MB(LSTM 131K)                        ● Stage4 (1.87M)
6.0 |
5.7 |                      ● Stage4b (855K)
5.5 |     ● Stage4f-mini   ● Stage4c (383K)
    |       (181K, 同点)
5.3 |              ★ Stage4e (383K) ● Stage4d-orth (855K)
    +---------------------------------------------------- params (log)
       100K   200K     400K     800K    1.6M
```
- Stage-4e (383K, ppl 5.30) が **絶対 ppl champion**
- Stage-4f-mini (181K, ppl 5.52) が **新 Pareto 点**: 4c と同 ppl を半分の params で。
  step 10000 で未収束 → 延長で 5.4 切れる可能性。
- LSTM 1MB (131K, ppl 6.17) はもはや transformer に完敗 (4f-mini 181K で
  -0.66 ppl, params も近い)。 params/ppl 効率は **transformer 領域に陥落**。

**3 種の正則化 (noise / target-dist / magnitude) を薄く重ねる戦略**は、
1MB scale で堅牢:
- dropout 単独 (4b, 855K): 5.73
- dropout 単独 縮小 (4c, 383K): 5.52
- 直交 3 種 (4d-orth, 855K): 5.30
- 直交 3 種 + 縮小 (4e, 383K): **5.30** ← 同じ ppl を半分の容量で

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
| 2c (1MB) | GRU tied (R1) | 1MB | 131K | 6.17 | 6.17 |
| 3 (試) | Transformer 1-block | 100KB | 247K | 14.96 | — |
| 3 (試) | Transformer 4-block | 100KB | 839K | 14.18 | 24.15 |
| 4 (1MB) | Tx d=192 d4 ctx=256 dropout 0.1 | 1MB | 1.87M | 5.93 | 5.93 |
| 4b (1MB) | Tx d=128 d4 ctx=256 dropout 0.2 | 1MB | 855K | 5.73 | 5.73 |
| 4c (1MB) | Tx d=96 d3 ctx=256 dropout 0.2 | 1MB | 383K | 5.52 | 5.52 |
| 4d-orth (1MB) | Tx d=128 d4 + dropout 0.1 + ls 0.05 + wd 0.05 | 1MB | 855K | 5.30 | 5.30 |
| **4e (1MB)** | **Tx d=96 d3 + dropout 0.1 + ls 0.05 + wd 0.05** | **1MB** | **383K** | **5.30** | **5.30 (champion)** |
| 4f-mini (1MB) | Tx d=64 d3 + 直交正則化 (同上) | 1MB | 181K | 5.52 | 5.52 (Pareto: 4c と同 ppl で半分) |

教訓:
- Stage-3 の transformer 敗北は ctx だけの問題ではなかった: BPTT < ctx
  にしていたため位置埋め込みが過学習し、コーパスも狭すぎた。
- BPTT == ctx (=256) + 1MB コーパスにすると 4-block transformer は
  step 3500 で ppl 5.93 にピークを打ち、その後 overfit。
- Stage-4b で d_model を 192→128 に縮小 + dropout を 0.1→0.2 に強化
  すると、params が半分以下 (855K) でありながら ppl 5.73 で Stage-4
  を 0.20 ppl 上回り、ピークも step 6500 まで遅延 (= 過学習体質が改善)。
  「正則化を効かせれば容量はむしろ減らせる」が確認できた。
- 同じ 1MB を見せた GRU (131K params) は ppl 6.17 で transformer に
  0.44 ppl 負け。params/ppl 効率では LSTM が依然強い (855K transformer
  と 131K GRU で 0.44 ppl 差)。
- 残課題: (a) Stage-4c で d_model=96 / depth=3 など更に縮小、
  (b) Stage-2 LSTM を 1MB で深く (hidden=192, 2-layer) 回す、
  (c) コーパスを 10MB に拡大して params を活かす空間を作る。

## 環境前提

- macOS arm64, M2 MPS available
- `/opt/homebrew/bin/python3.13` (lark, など普通のパッケージ入り)
- `local-genai/.venv/bin/python` (PyTorch 2.11.0, numpy 2.4.4)
- Java + tla2tools.jar (TLC 用、 `aipl_tlc.sh` が探す)
- spin 6.5.2 (`brew install spin` 済)

## 続行候補

1. ~~**Stage-4f-mini**~~ — 完了 (181K params, ppl 5.52, LSTM を圧倒)。
2. **Stage-4f-extend: 4f-mini を延長** (step 10000 で未収束)
   - 同設定で steps=20000 + cosine 終端 LR=1e-5 → 5.4 切り狙い
3. **Stage-4g-long: 4e を延長**
   - 同設定で steps=20000 + warmup=1500 + cosine 終端 LR=1e-5 で 5.0 切り狙い
3. **Stage-5-RoPE: 位置埋め込みを刷新**
   - 4e サイズ + RoPE で learned pos を排除 → 汎化向上を期待
4. **Stage-2c': LSTM を 1MB で深く回す**
   - hidden=192, 2-layer LSTM, steps=4000 で 6.17 を切れるか
5. **Stage-5-10MB: コーパスを 10MB に拡大**
   - 1.87M params を活かす空間を作る (現状 1MB は data-starved)。
6. **SemiAutoEvolve**: Ollama (gemma2:2b) で次世代 mutation を
   3 案起草 (`LocalGenAIScaledEvolutionJP.aice` の Stage 7 仕様あり)。

## Stage-4e (現 ppl champion) を回す手順

```sh
local-genai/.venv/bin/python local-genai/train_stage4.py \
  --steps 10000 --eval-every 500 --warmup 800 \
  --batch 24 --bptt 256 --ctx 256 \
  --depth 3 --d-model 96 --n-heads 4 \
  --lr 2e-3 --dropout 0.1 \
  --label-smoothing 0.05 --weight-decay 0.05 \
  --out-name transformer_stage4e.pt
# 約 7 分 (M2 MPS), best ppl 5.302 @ step 10000 (収束未達)
```

## Stage-4f-mini (Pareto 左下) を回す手順

```sh
local-genai/.venv/bin/python local-genai/train_stage4.py \
  --steps 10000 --eval-every 500 --warmup 800 \
  --batch 24 --bptt 256 --ctx 256 \
  --depth 3 --d-model 64 --n-heads 4 \
  --lr 2e-3 --dropout 0.1 \
  --label-smoothing 0.05 --weight-decay 0.05 \
  --out-name transformer_stage4f_mini.pt
# 約 6 分 (M2 MPS, 351s), 181K params, best ppl 5.523 @ step 10000 (未収束)
```

## Stage-4d-orth (歴史的: 直交正則化 855K)

```sh
local-genai/.venv/bin/python local-genai/train_stage4.py \
  --steps 10000 --eval-every 500 --warmup 800 \
  --batch 24 --bptt 256 --ctx 256 \
  --depth 4 --d-model 128 --n-heads 4 \
  --lr 2e-3 --dropout 0.1 \
  --label-smoothing 0.05 --weight-decay 0.05 \
  --out-name transformer_stage4d_orth.pt
# 約 12 分 (M2 MPS), best ppl 5.304 @ step 6500
```

## Stage-4c (歴史的: depth=3 縮小実験)

```sh
local-genai/.venv/bin/python local-genai/train_stage4.py \
  --steps 10000 --eval-every 500 --warmup 800 \
  --batch 24 --bptt 256 --ctx 256 \
  --depth 3 --d-model 96 --n-heads 4 \
  --lr 2e-3 --dropout 0.2 \
  --out-name transformer_stage4c.pt
# 約 8 分 (M2 MPS), best ppl 5.521 @ step 10000 (収束未達)
```

## Stage-4b (歴史的: dropout 単独正則化)

```sh
local-genai/.venv/bin/python local-genai/train_stage4.py \
  --steps 10000 --eval-every 500 --warmup 800 \
  --batch 24 --bptt 256 --ctx 256 \
  --depth 4 --d-model 128 --n-heads 4 \
  --lr 2e-3 --dropout 0.2 \
  --out-name transformer_stage4b.pt
# 約 12 分 (M2 MPS), best ppl 5.731 @ step 6500
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
