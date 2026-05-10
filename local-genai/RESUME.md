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

**Stage-6c Transformer (855K params, 4d-orth recipe + 10MB)** — **unified champion**

```
local-genai/out/transformer_stage6c_large.pt
  TinyTransformer depth=4, d_model=128, n_heads=4, ctx=256, bptt=256
  ffn_mult=4, RMSNorm, learned positional
  dropout 0.1, label_smoothing 0.05, weight_decay 0.05
  warmup 1500, cosine 終端 LR=1e-5 (min_lr_frac=0.005)
  TinyShakespeare+KJV-10MB 学習, 855,680 params
  best ppl 4.249 @ step 19500 (20000 step 走破; ほぼ収束)
  訓練時間 1494s (M2 MPS, ≈ 25 分)
```

**両ベンチで champion を奪取**:

| stage | params | trained on | **1MB tail** | **10MB tail** |
|---|---:|---|---:|---:|
| 5-RoPE | 165K | 1MB | 5.120 | 7.005 |
| 6b | 165K | 10MB | 5.289 | 4.725 |
| **6c** | **855K** | **10MB** | **4.765** | **4.249** |

容量 (855K) × データ (10MB) の **両軸を同時に**押すと、 専門特化の壁を
破って **両ベンチで同時に勝つ**単一モデルが出現した。 これは:
- 容量 855K だけでは効かない (4d-orth: 1MB tail 5.30, 10MB tail 7.32)
- データ 10MB だけでは効かない (6b: 1MB tail 5.29, 10MB tail 4.73 — 1MB
  tail で 5-RoPE に負ける = Shakespeare 特化が劣る)
- 容量 × データ 両方そろうと両方を制圧 (6c)

**Stage-6b Transformer (165K params, 軽量 champion)** — 165K で達成可能な
最良が 1MB tail 5.289 / 10MB tail 4.725:

```
local-genai/out/transformer_stage6b_rope.pt
  TinyTransformer depth=3, d_model=64, n_heads=4, ctx=256, bptt=256
  ffn_mult=4, RMSNorm, RoPE
  dropout 0.1, label_smoothing 0.05, weight_decay 0.05
  warmup 1500, cosine 終端 LR=1e-5 (min_lr_frac=0.005)
  TinyShakespeare+KJV-10MB 学習, 165,248 params
  best ppl 4.725 @ step 20000 (= 予算上限で更新中、未収束 — 延長で伸びる)
  訓練時間 ≈ 13 分 (M2 MPS)
```

**Stage-5-RoPE (165K params, 1MB 学習)** — 1MB tail (Shakespeare-only) で ppl **5.120** (= 1MB tail champion)

```
local-genai/out/transformer_stage5_rope.pt
  同アーキ, TinyShakespeare-1MB 学習
  best ppl 5.120 @ step 19500 (収束済)
  訓練時間 777s
```

歴代 (champion 推移):
- 1MB tail: 5.93 → 5.73 → 5.52 → 5.30 → 5.20 → **5.12** (Stage-5-RoPE)
- 10MB tail: 7.32 (1MB-trained 4f-extend; OOD) → **4.73** (Stage-6b; in-distribution)

**2 champion 併存の意味**: Stage-6b は同サイズ・同アーキでも 1MB tail だと
ppl 5.289 (5-RoPE の 5.120 より 0.17 劣る) — 容量が KJV ぶん分散したため
Shakespeare 特化では負ける。 専門特化 vs 汎用化のトレードオフ。

**学習可能 pos vs RoPE** (1MB tail):
- 4f-extend (181K, learned-pos): 5.200
- 5-RoPE (165K, RoPE): 5.120 — params -9% / ppl -1.5%
RoPE は data-saturated 領域でも勝つ→ byte-level char modeling では
absolute 位置よりも相対位置 invariance が本質。

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
    |       (181K)
5.3 |              ● Stage4e (383K) ● Stage4d-orth (855K)
5.2 |     ★ Stage4f-extend
    |       (181K)
    +---------------------------------------------------- params (log)
       100K   200K     400K     800K    1.6M
```
- **Stage-4f-extend (181K, ppl 5.20)** が絶対 champion かつ Pareto 左下を
  完全制圧。 4f-mini と同サイズで 20000 step + 深 LR 減衰のみで -0.32 ppl。
- **Stage-4g (383K, ppl 5.199)** は 4f-extend と統計的同点 (Δ=0.001)。
  容量 2x で改善ゼロ → **1MB コーパスは data-saturated** が確定。
  これ以上の ppl 改善は (a) アーキテクチャ刷新 (RoPE 等)、 (b) コーパス
  拡張 (10MB) のいずれかが必要 → 仮説 (a) を Stage-5-RoPE で検証 → 成功。
- **Stage-5-RoPE (165K, ppl 5.120)** は 4f-extend を **両方** で勝利:
  ppl -0.080 (-1.5%), params -9% (= 学習可能位置埋め込み 16K 撤去)。
  1MB が data-saturated でもアーキ刷新で更に下げられた事実は、 学習可能
  absolute pos が byte-level char modeling では最適でなかったことを示す。
  10MB 拡張時に RoPE は更に効く可能性が高い (Stage-6b で検証予定)。
- 学習スケジュールが ppl にもたらす効果は容量 2× や正則化変更と同等以上。
- LSTM 1MB (131K, ppl 6.17) は 0.97 ppl 差で完敗。 transformer が char-level
  1MB の **全帯域を制覇**。

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
| 4f-mini (1MB) | Tx d=64 d3 + 直交正則化 (同上) | 1MB | 181K | 5.52 | 5.52 |
| 4f-extend (1MB) | 4f-mini + 20000 step + min_lr_frac=0.005 | 1MB | 181K | 5.20 | 5.20 |
| 4g (1MB) | 4e + 20000 step + min_lr_frac=0.005 | 1MB | 383K | 5.20 | 5.20 |
| **5-RoPE (1MB)** | **4f-extend + RoPE** | **1MB** | **165K** | **5.12** | **5.12 (1MB tail champion)** |
| 6b (10MB) | 5-RoPE recipe + 10MB | 10MB | 165K | 4.73 | 4.73 (軽量 leader) |
| **6c (10MB)** | **4d-orth recipe + 10MB** | **10MB** | **855K** | **4.25** | **4.25 (unified champion: 1MB tail 4.77 / 10MB tail 4.25)** |

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

1. ~~**Stage-4f-mini / 4f-extend / 4g**~~ — 完了 (1MB は data-saturated 確認)
2. ~~**Stage-5-RoPE**~~ — 完了 (165K, ppl **5.12**, 絶対 champion)
3. **Stage-6 シリーズ (10MB 学習)**
   - ~~**6b**~~ — 完了 (165K, ppl 4.725 @ 10MB tail; 軽量 leader)
   - ~~**6c**~~ — 完了 (855K, ppl 4.249 @ 10MB tail; **unified champion**)
   - **6d**: 4d-orth + RoPE + 10MB (~840K, RoPE) — 6c に RoPE 追加で更に伸びるか
   - **6a**: 4f-extend recipe + 10MB (181K, learned pos) — RoPE 効果を 10MB で再検証
   - **6c-extend**: 6c を steps=40000 で延長 — 6c は step 19500 で best、 ほぼ収束だが微更新中
4. **Stage-7 シリーズ (Stage-6 を超える)**
   - **7-deeper**: depth=6 + d=128 → 1.5M params で 4.0 切り狙い
   - **7-bpe**: byte → BPE トークナイザに切替 (実効 ctx 4x)
   - **7-AIPL-revival**: 全 prior を AIPL .abcl に encode して進化計算へ
4. **Stage-AIPL-revival**: 全 prior (容量, 正則化 3 種, schedule, RoPE) を
   `.aice` に encode → AIPL evolution で人が見つけた Pareto を AI が更に
   押し下げられるか
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

## Stage-6c (unified champion, 両ベンチで champion) を回す手順

```sh
local-genai/.venv/bin/python local-genai/train_stage4.py \
  --corpus 10MB \
  --steps 20000 --eval-every 500 --warmup 1500 \
  --batch 24 --bptt 256 --ctx 256 \
  --depth 4 --d-model 128 --n-heads 4 \
  --lr 2e-3 --dropout 0.1 \
  --label-smoothing 0.05 --weight-decay 0.05 \
  --min-lr-frac 0.005 \
  --pos-encoding learned \
  --out-name transformer_stage6c_large.pt
# 約 25 分 (M2 MPS, 1494s), 855K params, best ppl 4.249 @ step 19500 (収束直前)
```

## Stage-6b (軽量 leader, 165K) を回す手順

```sh
local-genai/.venv/bin/python local-genai/train_stage4.py \
  --corpus 10MB \
  --steps 20000 --eval-every 500 --warmup 1500 \
  --batch 24 --bptt 256 --ctx 256 \
  --depth 3 --d-model 64 --n-heads 4 \
  --lr 2e-3 --dropout 0.1 \
  --label-smoothing 0.05 --weight-decay 0.05 \
  --min-lr-frac 0.005 \
  --pos-encoding rope \
  --out-name transformer_stage6b_rope.pt
# 約 13 分 (M2 MPS), 165K params, best ppl 4.725 @ step 20000 (未収束)
```

## Stage-5-RoPE (1MB tail champion) を回す手順

```sh
local-genai/.venv/bin/python local-genai/train_stage4.py \
  --steps 20000 --eval-every 500 --warmup 1500 \
  --batch 24 --bptt 256 --ctx 256 \
  --depth 3 --d-model 64 --n-heads 4 \
  --lr 2e-3 --dropout 0.1 \
  --label-smoothing 0.05 --weight-decay 0.05 \
  --min-lr-frac 0.005 \
  --pos-encoding rope \
  --out-name transformer_stage5_rope.pt
# 約 13 分 (M2 MPS, 777s), 165K params, best ppl 5.120 @ step 19500 (収束)
```

## Stage-4f-extend (歴史的: learned positional 上限)

```sh
local-genai/.venv/bin/python local-genai/train_stage4.py \
  --steps 20000 --eval-every 500 --warmup 1500 \
  --batch 24 --bptt 256 --ctx 256 \
  --depth 3 --d-model 64 --n-heads 4 \
  --lr 2e-3 --dropout 0.1 \
  --label-smoothing 0.05 --weight-decay 0.05 \
  --min-lr-frac 0.005 \
  --out-name transformer_stage4f_extend.pt
# 約 12 分 (M2 MPS, 697s), 181K params, best ppl 5.200 @ step 19000 (収束)
```

## Stage-4f-mini (歴史的: 10000 step 短縮版)

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
