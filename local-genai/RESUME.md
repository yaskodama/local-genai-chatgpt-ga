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

**Stage-9-BPE-extend (1.32M params, depth=6, RoPE + 10MB + 1024-vocab BPE, 40000 step)** — **bits-per-byte champion**

```
local-genai/out/transformer_stage9_bpe_extend.pt + tokenizer_stage9_bpe_extend.json
  TinyTransformer depth=6, d_model=128, n_heads=4, ctx=256, bptt=256
  ffn_mult=4, RMSNorm, RoPE
  dropout 0.1, label_smoothing 0.05, weight_decay 0.05
  warmup 1500, cosine 終端 LR=1e-5 (min_lr_frac=0.005)
  BPE 1024-vocab (2.04 bytes/token on holdout)
  TinyShakespeare+KJV-10MB 学習, 1,316,224 params
  best bpb 1.911 @ step 32000 (40000 step 走破; step 32000 で peak)
  ppl/byte 換算 ≈ 3.760
  訓練時間 6700s (M2 MPS, ≈ 112 分)
```

**Stage-8-BPE (1.32M params, depth=6, RoPE + 10MB + 1024-vocab BPE)** — bpb 1.915 (20K step)

```
local-genai/out/transformer_stage8_bpe.pt + tokenizer_stage8_bpe.json
  TinyTransformer depth=6, d_model=128, n_heads=4, ctx=256, bptt=256
  ffn_mult=4, RMSNorm, RoPE
  dropout 0.1, label_smoothing 0.05, weight_decay 0.05
  warmup 1500, cosine 終端 LR=1e-5 (min_lr_frac=0.005)
  BPE 1024-vocab (2.04 bytes/token on holdout)
  TinyShakespeare+KJV-10MB 学習, 1,316,224 params
  best bpb 1.915 @ step 19500 (20000 step 走破; まだ微更新中で未収束)
  ppl/byte 換算 ≈ 3.771 (byte-level の 4.038 比 -6.6%)
  訓練時間 3269s (M2 MPS, ≈ 54.5 分)
```

**Cross-tokenizer 比較 (bits-per-byte = 唯一の fair 指標)**:

| stage | params | tokenizer | bpb | ppl/byte | 訓練時間 |
|---|---:|---|---:|---:|---:|
| 7-deeper-extend | 1.22M | byte | 2.014 | 4.038 | 193 min |
| 8-BPE | 1.32M | BPE-1024 | 1.915 | 3.771 | 54.5 min |
| **9-BPE-extend** | **1.32M** | **BPE-1024** | **1.911** | **3.760** | **112 min** |

延長効果は微小 (-0.004 bpb): BPE は token あたり情報量が高く、 byte-level
のような長 schedule での「終盤微調整」の余地が少ない。 step 32000 で peak
後、 残り 8000 step で更新なし → 完全収束。

BPE は同 step 数で **byte-level の 1/4 時間** で同等以上の bpb を達成。
理由: 10MB byte → 5MB tokens で trainset 半分 + より大きな語彙単位を学習
すると bytes-per-prediction が 2x になり、 transformer の限界文脈長
(bptt=256) が実効 ~520 bytes に伸びる。

**Stage-7-deeper-extend (1.22M params, depth=6, RoPE + 10MB, 40000 step)** — **byte-level (ppl) champion**

```
local-genai/out/transformer_stage7_deeper_extend.pt
  TinyTransformer depth=6, d_model=128, n_heads=4, ctx=256, bptt=256
  ffn_mult=4, RMSNorm, RoPE
  dropout 0.1, label_smoothing 0.05, weight_decay 0.05
  warmup 1500, cosine 終端 LR=1e-5 (min_lr_frac=0.005)
  TinyShakespeare+KJV-10MB 学習, 1,217,920 params (= 7-deeper と同じ)
  best ppl 4.038 @ step 40000 (40000 step 走破; まだ微更新中)
  訓練時間 11558s (M2 MPS, ≈ 193 分 = 3.2 時間)
```

**Stage-7-deeper-extend が両ベンチで最強の単一モデル**:

| stage | params | trained on | **1MB tail** | **10MB tail** | 時間 |
|---|---:|---|---:|---:|---:|
| 7-deeper | 1.22M | 10MB | 4.543 | 4.064 | 58 分 |
| **7-deeper-extend** | **1.22M** | **10MB** | **4.231** | **4.038** | **193 分** |

驚きの結果: 訓練長 2x で:
- 10MB tail (in-distribution): -0.026 ppl (-0.6%) — 限界に近い改善
- 1MB tail (out-of-distribution = Shakespeare-only): **-0.31 ppl (-7%)** — 大改善

→ 長 LR 減衰は in-distribution の最適化よりも、 **混合分布の中の難所
(Shakespeare の Early Modern English) を最終局面で仕上げる**効果が大きい。
40000 step 全体を通して、 step 30000 以降の低 LR 局面で 1MB tail ppl が
4.55 → 4.23 に急降下した可能性がある (詳細な記録は train ログにあり)。

**両ベンチで最強の単一モデル**:

| stage | params | trained on | **1MB tail** | **10MB tail** | 時間 |
|---|---:|---|---:|---:|---:|
| 5-RoPE | 165K | 1MB | 5.120 | 7.005 | 13 分 |
| 6b | 165K | 10MB | 5.289 | 4.725 | 13 分 |
| 6c | 855K | 10MB | 4.765 | 4.249 | 25 分 |
| 6d | 823K | 10MB | 4.646 | 4.191 | 28.5 分 |
| **7-deeper** | **1.22M** | **10MB** | **4.543** | **4.064** | **57.9 分** |

**5 つの発見の統合 + 訓練延長**:
1. 直交 3 種正則化 (Stage-4d-orth)
2. 深 cosine schedule (Stage-4f-extend)
3. RoPE (Stage-5-RoPE)
4. 10MB データ + 大容量 (Stage-6c, 6d)
5. **深さ depth=4 → 6** (Stage-7-deeper)
6. **訓練 20000 → 40000 step** (Stage-7-deeper-extend)

**重要: width は効かない**:
- Stage-8-wider (depth=4, d=192, 1.82M params, 50 分訓練): ppl 4.232 @ 10MB / 5.206 @ 1MB
- Stage-7-deeper (depth=6, d=128, 1.22M params, 58 分訓練): ppl 4.064 @ 10MB / 4.543 @ 1MB
- → 同程度 params 予算なら **depth に投資すべき**。 width=192 は depth=6
  + 訓練延長を上回れない。 head_dim を 32 → 48 にしても表現力増加には
  繋がらず、 FFN の二次的拡大は data 不足で活きない。

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
| 6c (10MB) | 4d-orth recipe + 10MB | 10MB | 855K | 4.25 | 4.25 (1MB tail 4.77 / 10MB tail 4.25) |
| 6d (10MB) | 4d-orth + RoPE + 10MB | 10MB | 823K | 4.19 | 4.19 (1MB tail 4.65 / 10MB tail 4.19) |
| 7-deeper (10MB) | 6d + depth 4→6 | 10MB | 1.22M | 4.06 | 4.06 (1MB tail 4.54 / 10MB tail 4.06) |
| **7-deeper-extend (10MB)** | **7-deeper + steps=40000** | **10MB** | **1.22M** | **4.04** | **4.04 (ultimate champion: 1MB tail 4.23 / 10MB tail 4.04)** |
| 8-wider (10MB) | depth=4, d=192 (width 試行) | 10MB | 1.82M | 4.23 | 4.23 (1MB tail 5.21 / 10MB tail 4.23 — params +50% で 7-deeper に負け) |
| 8-deeper-plus (10MB) | depth=8, d=128 RoPE 20K step | 10MB | 1.61M | 4.04 | 4.04 (1MB tail 4.36 / 10MB tail 4.04 — 7-deeper-extend と並ぶが超えず) |
| 8-BPE (10MB) | 7-deeper recipe + BPE-1024 vocab | 10MB | 1.32M | bpb 1.92 | bpb 1.915 (= ppl/byte 3.77) |
| **9-BPE-extend (10MB)** | **8-BPE + steps 20K→40K** | **10MB** | **1.32M** | **bpb 1.911** | **bpb 1.911 (= ppl/byte 3.76; bpb champion)** |

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
3. **Stage-6 シリーズ (10MB 学習)** — 完了
   - ~~6b~~ (165K, ppl 4.725 軽量 leader)
   - ~~6c~~ (855K, ppl 4.249)
   - ~~**6d**~~ — 完了 (823K, ppl **4.191** @ 10MB / **4.646** @ 1MB; **ultimate champion**)
   - 6a: 4f-extend recipe + 10MB は未実行 (RoPE 効果 165K 上で再確認用)
4. **Stage-7 シリーズ (Stage-6d を超える)**
   - ~~7-deeper~~ — 完了 (1.22M, 1MB 4.54 / 10MB 4.06)
   - ~~**7-deeper-extend**~~ — 完了 (1.22M, 1MB **4.23** / 10MB **4.04**; **ultimate champion**)
5. **Stage-8 シリーズ (4.0 切り探索)**
   - ~~8-wider~~ — 失敗 (1.82M, ppl 4.23/5.21; depth >> width 確定)
   - ~~8-deeper-plus~~ — 完了 (1.61M, depth=8 20K step, ppl 4.04/4.36;
     7-deeper-extend に並ぶが超えず — **depth scaling は減衰局面**)
   - **判明**: 訓練長 (40K step) > 深さ (depth=8)。 同 ppl を達成する
     のに depth=8 (1.61M, 81 分) より depth=6 + 延長 (1.22M, 193 分)
     のほうが省 params。
6. **Stage-9 / Plan-β (BPE 確立後)**
   - ~~**8-bpe**~~ — 完了 (1.32M, BPE-1024, bpb 1.915)
   - ~~**9-bpe-extend**~~ — 完了 (1.32M, BPE-1024, 40K step, bpb **1.911**;
     **bpb champion**、延長効果は微小)
   - **9-bpe-vocab-2048**: vocab を 1024 → 2048 で更に圧縮 (~4-5 bytes/token)
   - **chat.py 拡張**: 最終 champion (byte + BPE) で実生成デモ
   - **8-AIPL-revival**: 全 prior を AIPL .abcl に encode して進化計算へ
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

## Stage-9-BPE-extend (現 bpb champion, 40K step) を回す手順

```sh
local-genai/.venv/bin/python local-genai/train_stage8_bpe.py \
  --corpus 10MB --vocab-size 1024 \
  --steps 40000 --eval-every 1000 --warmup 1500 \
  --batch 24 --bptt 256 --ctx 256 \
  --depth 6 --d-model 128 --n-heads 4 \
  --lr 2e-3 --dropout 0.1 \
  --label-smoothing 0.05 --weight-decay 0.05 \
  --min-lr-frac 0.005 \
  --pos-encoding rope \
  --out-name transformer_stage9_bpe_extend.pt \
  --tokenizer-name tokenizer_stage9_bpe_extend.json
# 約 112 分 (M2 MPS, 6700s), 1.32M params,
# best bpb 1.911 @ step 32000 (= ppl/byte 3.76) — 完全収束
```

## Stage-8-BPE (歴史的, 20K step) を回す手順

```sh
local-genai/.venv/bin/python local-genai/train_stage8_bpe.py \
  --corpus 10MB --vocab-size 1024 \
  --steps 20000 --eval-every 500 --warmup 1500 \
  --batch 24 --bptt 256 --ctx 256 \
  --depth 6 --d-model 128 --n-heads 4 \
  --lr 2e-3 --dropout 0.1 \
  --label-smoothing 0.05 --weight-decay 0.05 \
  --min-lr-frac 0.005 \
  --pos-encoding rope \
  --out-name transformer_stage8_bpe.pt \
  --tokenizer-name tokenizer_stage8_bpe.json
# 約 54 分 (M2 MPS, 3269s), 1.32M params,
# best bpb 1.915 @ step 19500 — 未収束
```

## Stage-7-deeper-extend (byte-level ppl champion, 両ベンチで champion) を回す手順

```sh
local-genai/.venv/bin/python local-genai/train_stage4.py \
  --corpus 10MB \
  --steps 40000 --eval-every 1000 --warmup 1500 \
  --batch 24 --bptt 256 --ctx 256 \
  --depth 6 --d-model 128 --n-heads 4 \
  --lr 2e-3 --dropout 0.1 \
  --label-smoothing 0.05 --weight-decay 0.05 \
  --min-lr-frac 0.005 \
  --pos-encoding rope \
  --out-name transformer_stage7_deeper_extend.pt
# 約 193 分 (M2 MPS, 11558s), 1.22M params,
# best ppl 4.038 @ step 40000 (10MB tail), 4.231 (1MB tail) — 未収束
```

## Stage-7-deeper (歴史的: 20000 step 版) を回す手順

```sh
local-genai/.venv/bin/python local-genai/train_stage4.py \
  --corpus 10MB \
  --steps 20000 --eval-every 500 --warmup 1500 \
  --batch 24 --bptt 256 --ctx 256 \
  --depth 6 --d-model 128 --n-heads 4 \
  --lr 2e-3 --dropout 0.1 \
  --label-smoothing 0.05 --weight-decay 0.05 \
  --min-lr-frac 0.005 \
  --pos-encoding rope \
  --out-name transformer_stage7_deeper.pt
# 約 58 分 (M2 MPS, 3472s), 1.22M params,
# best ppl 4.064 @ step 19500 (10MB tail), 4.543 (1MB tail) — 未収束
```

## Stage-6d (10MB, RoPE, depth=4) を回す手順

```sh
local-genai/.venv/bin/python local-genai/train_stage4.py \
  --corpus 10MB \
  --steps 20000 --eval-every 500 --warmup 1500 \
  --batch 24 --bptt 256 --ctx 256 \
  --depth 4 --d-model 128 --n-heads 4 \
  --lr 2e-3 --dropout 0.1 \
  --label-smoothing 0.05 --weight-decay 0.05 \
  --min-lr-frac 0.005 \
  --pos-encoding rope \
  --out-name transformer_stage6d_large_rope.pt
# 約 28.5 分 (M2 MPS, 1708s), 823K params,
# best ppl 4.191 @ step 19500 (10MB tail), 4.646 (1MB tail) — 収束直前
```

## Stage-6c (10MB, learned-pos, 6d より前) を回す手順

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
