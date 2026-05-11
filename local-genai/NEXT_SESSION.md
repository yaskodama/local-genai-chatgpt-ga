# 次回セッション再起動メモ

## 再起動時に Claude に入力する文 (コピペ用)

```
local-genai/RESUME.md と local-genai/NEXT_SESSION.md を読み込んで現状を把握して下さい。
champion は二系統:
  - byte-level ppl champion = Stage-7-deeper-extend (1.22M params, 10MB tail ppl 4.038)
  - bits-per-byte champion = Stage-9-BPE-extend (1.32M params, bpb 1.911)
最近 Stage-9-BPE-extend で BPE は schedule 延長効果がほぼ飽和 (-0.004 bpb) と判明。
次の選択肢:
  (a) Stage-9-BPE-vocab2048 (vocab 1024 → 2048 で更に圧縮)
  (b) chat.py 拡張 (最終 champion で実生成デモ)
  (c) AIPL-revival (進化計算側に発見を還元)
あなたが推奨する次の一手と理由を一言で教えて下さい。
```

## 現状サマリ (2026-05-11 終了時点)

### 2 種類の champion 併存

| 指標 | champion | params | 値 |
|---|---|---:|---:|
| **byte-level ppl** (10MB tail) | Stage-7-deeper-extend | 1.22M | **4.038** |
| **byte-level ppl** (1MB tail) | Stage-7-deeper-extend | 1.22M | **4.231** |
| **bits-per-byte** (cross-tokenizer fair) | **Stage-9-BPE-extend** | **1.32M** | **bpb 1.911** (= ppl/byte 3.760) |

→ **Stage-9-BPE-extend が cross-tokenizer ベンチ (bpb) で最強**。
チェックポイント: `local-genai/out/transformer_stage9_bpe_extend.pt` +
`local-genai/out/tokenizer_stage9_bpe_extend.json`

### 6 つの discovery とその効果 (Stage 別)

| 軸 | 由来 stage | 効果 |
|---|---|---|
| 直交 3 種正則化 (dropout 0.1 + ls 0.05 + wd 0.05) | 4d-orth | -0.43 ppl |
| 深 cosine schedule (steps↑ + min_lr_frac↓) | 4f-extend | -0.32 ppl |
| RoPE (rotary positional) | 5-RoPE | -0.08 ppl + params -9% |
| 10MB データ + 容量増 | 6c/6d | 1MB tail -0.47 ppl |
| depth=4 → 6 | 7-deeper | -0.10 ppl |
| 訓練 20000 → 40000 step | 7-deeper-extend | -0.31 ppl (1MB tail!) |
| **BPE 1024-vocab トークナイザ** | 8-BPE | bpb -0.10 (-5%), 訓練 1/4 時間 |

### Failed / 飽和した experiments

- **width**: Stage-8-wider (d=192, depth=4, 1.82M) は depth=6 (1.22M) に負け
  → 同 params 予算なら depth >> width
- **depth=8**: Stage-8-deeper-plus (1.61M) は 7-deeper-extend (1.22M) と並ぶだけ
  → depth scaling は飽和 (depth=6 が optimum)
- **1MB scale で容量増**: Stage-4 (1.87M) が 4b (855K) より悪い
  → 小データなら容量を絞って正則化を効かせる
- **BPE schedule 延長**: 9-BPE-extend は 8-BPE 比 -0.004 bpb のみ
  → BPE は token 情報量が高く早く飽和。 vocab 拡張のほうが伸び代あり

## 次の候補

### A. **Stage-9-BPE-vocab2048** (BPE 軸の継続) — 推奨 1
- 同 recipe で vocab 1024 → 2048 に拡張 → ~3-4 bytes/token
- 各 prediction の情報量増→ bpb 1.8 切り狙い
- 時間: ~40-60 分 (token 数が更に減るため speedup あり)

### B. **chat.py 拡張** (アプリ化、本来の目標着地)
- 現状の chat.py は stage-1 n-gram のみ対応
- byte-level transformer + BPE transformer の両方で対話デモ
- `generate_samples.py` のロジック流用可能
- 時間: ~30 分

### C. **AIPL-revival** (メタ実験)
- 全 prior を AIPL .aice schema に encode し直し
- `design_estimator.py` の table 更新 (現状 prior が 1MB 時代のまま)
- 人間が発見した Pareto を AIPL が更に押し下げられるか
- 時間: 実装 ~1 時間 + AIPL evolution + 上位候補訓練

## 重要ファイル一覧

| ファイル | 用途 |
|---|---|
| `local-genai/RESUME.md` | 詳細な進化履歴と現状 |
| `local-genai/NEXT_SESSION.md` | この再起動メモ |
| `local-genai/train_stage4.py` | byte-level 訓練 (Stage-4 〜 Stage-8 全て) |
| `local-genai/train_stage8_bpe.py` | BPE 訓練 (Stage-8/9-BPE) |
| `local-genai/candidates/transformer_real.py` | TinyTransformer (RoPE 対応) |
| `local-genai/common.py` | コーパスロード + SHA-256 lock |
| `local-genai/fair_compare.py` | 全 checkpoint を共通 holdout で再評価 (1MB / 10MB) |
| `local-genai/build_10mb_corpus.py` | PG から 10MB コーパスを再生成 |
| `local-genai/generate_samples.py` | サンプル文書生成 (byte-level) |
| `local-genai/out/transformer_stage7_deeper_extend.pt` | byte-level ppl champion |
| `local-genai/out/transformer_stage9_bpe_extend.pt` | bpb champion |
| `local-genai/out/tokenizer_stage9_bpe_extend.json` | bpb champion の BPE tokenizer |
| `local-genai/corpus/tinyshake_10MB.txt` | 10MB コーパス (hash locked) |
| `local-genai/samples/samples_stage7_deeper_extend.md` | byte-level champion の生成サンプル |

## 環境前提

- macOS arm64 (M2 MPS available)
- `local-genai/.venv/bin/python` (PyTorch 2.11.0)
- `/opt/homebrew/bin/python3.13` (システム Python; AIPL/aice 用)
- `tokenizers==0.23.1` (Stage-8/9-BPE で必要、 .venv に install 済)

## 主要コマンド (再現用)

### byte-level ppl champion (Stage-7-deeper-extend) を再生成

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
# ~193 分 (M2 MPS), best ppl 4.038
```

### bpb champion (Stage-9-BPE-extend) を再生成

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
# ~112 分 (M2 MPS), best bpb 1.911 @ step 32000
```

### 全 checkpoint を再評価

```sh
cd local-genai && .venv/bin/python fair_compare.py              # 1MB tail
cd local-genai && .venv/bin/python fair_compare.py --corpus 10MB  # 10MB tail
```

### byte-level champion でサンプル生成

```sh
local-genai/.venv/bin/python local-genai/generate_samples.py
# → local-genai/samples/samples_stage7_deeper_extend.md
```

## git 状態

- branch: `main`
- origin: `https://github.com/yaskodama/aios-claude.git`
- 最新コミット: `f7cf721 local-genai: Stage-9-BPE-extend — 40000 steps give only -0.004 bpb`

## ppl / bpb 推移 (Stage-4 → Stage-9)

```
1MB tail ppl:        5.93 → 5.73 → 5.52 → 5.30 → 5.20 → 5.12 → 4.77 → 4.65 → 4.54 → 4.23  (-29%)
10MB tail ppl:        —  →  —  →  —  → 7.32 → 4.73 → 4.25 → 4.19 → 4.06 → 4.04
                                            (OOD)                            (in-distribution)
10MB tail bpb:        —  →  —  →  —  →  —  →  —  →  —  →  —  →  —  → 2.01 → 1.92 → 1.91
                                                              (byte→BPE 切替)
```
