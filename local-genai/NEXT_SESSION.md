# 次回セッション再起動メモ

## 再起動時に Claude に入力する文 (コピペ用)

```
local-genai/RESUME.md を読み込んで現状を把握して下さい。
現 champion は Stage-7-deeper-extend (1.22M params, 10MB tail ppl 4.038, 1MB tail ppl 4.231)。
直近で Stage-8-wider が失敗 (depth >> width 確定) したので、次は
Stage-8-deeper-plus (depth=8, d=128, RoPE, 10MB, 20000 step) か
chat.py を transformer 対応にしてデモを作るかを選びたい。
あなたが推奨する次の一手と理由を一言で教えて下さい。
```

## 現状サマリ (2026-05-11 時点)

### Champion (両ベンチで最強)

**Stage-7-deeper-extend** (`local-genai/out/transformer_stage7_deeper_extend.pt`)
- 1,217,920 params (d=128, depth=6, n_heads=4, RoPE)
- 10MB tail ppl: **4.038**
- 1MB  tail ppl: **4.231**
- 訓練: 40,000 step / 193 分 / M2 MPS

### 出発点 (Stage-4, 1MB 学習) からの累計改善

| 軸 | 出発 | 現在 | 改善 |
|---|---:|---:|---:|
| 1MB tail ppl | 5.929 | 4.231 | -29% |
| 10MB tail ppl (OOD→ID) | 7.318 (4d-orth OOD) | 4.038 | -45% |
| params (champion) | 1.87M | 1.22M | -35% |

### 5 つの discovery とその効果

| 軸 | 由来 stage | 単独効果 |
|---|---|---|
| 直交 3 種正則化 (dropout 0.1 + ls 0.05 + wd 0.05) | 4d-orth | 4b 比 -0.43 ppl |
| 深 cosine schedule (steps↑ + min_lr_frac↓) | 4f-extend | 4f-mini 比 -0.32 ppl |
| RoPE (rotary positional) | 5-RoPE | 4f-extend 比 -0.08 ppl |
| 10MB データ + 容量増 | 6c/6d | 5-RoPE 比 1MB tail -0.47 ppl |
| depth=4 → 6 | 7-deeper | 6d 比 -0.10 ppl |
| 訓練 20000 → 40000 step | 7-deeper-extend | 7-deeper 比 -0.31 ppl (1MB tail!) |

### Failed experiments (やってはダメと判明したもの)

- **width**: depth=4, d=192 (Stage-8-wider, 1.82M params) は depth=6, d=128 (1.22M) に負け。
  同 params 予算なら depth に投資。
- **1MB scale で容量増**: Stage-4 (1.87M) が Stage-4b (855K) より悪い。
  小データなら容量を絞って正則化を効かせるのが正解。

## 次の候補 (RESUME.md にも記載)

### A. アーキ深掘り
- **Stage-8-deeper-plus**: depth=8, d=128, RoPE, 10MB, 20000 step (≈ 1.6M params, ~75 分)
  - depth=6 で勝ったので depth=8 も効くか
- **Stage-8-BPE**: byte → BPE トークナイザに切替 (実効 ctx 4x, 大改修)
  - 数値的に最も伸び代がある
- **Stage-9-extend-7-deeper-extend**: 7-deeper-extend を steps=80000 で延長 (~6-7 時間)
  - diminishing returns 警戒だが、 still descending

### B. メタ実験
- **Stage-AIPL-revival**: 全 prior (容量, 直交正則化 3 種, schedule, RoPE, 深さ範囲) を
  `.aice` に encode → AIPL evolution で人が見つけた Pareto を AI が更に押し下げられるか
  (`aice-evolution-v2/examples/LocalGenAIScaledEvolutionJP.aice` の Stage 7 仕様あり)

### C. アプリ化 (本来の目標着地)
- **chat.py を transformer 対応に拡張**: 現状 stage-1 n-gram と stage-2 LSTM のみ
  - 最終 champion (Stage-7-deeper-extend) で実生成デモ
  - `generate_samples.py` のロジック (`local-genai/generate_samples.py`) を流用可能
  - 生成サンプル例は `local-genai/samples/samples_stage7_deeper_extend.md` 参照

## 重要ファイル一覧

| ファイル | 用途 |
|---|---|
| `local-genai/RESUME.md` | 詳細な進化履歴と現状 |
| `local-genai/NEXT_SESSION.md` | この再起動メモ |
| `local-genai/train_stage4.py` | 訓練ループ (Stage-4 〜 Stage-8 全て) |
| `local-genai/candidates/transformer_real.py` | TinyTransformer (RoPE 対応) |
| `local-genai/common.py` | コーパスロード + SHA-256 lock |
| `local-genai/fair_compare.py` | 全 checkpoint を共通 holdout で再評価 |
| `local-genai/build_10mb_corpus.py` | PG から 10MB コーパスを再生成 |
| `local-genai/generate_samples.py` | サンプル文書生成 |
| `local-genai/out/transformer_stage7_deeper_extend.pt` | 現 champion |
| `local-genai/corpus/tinyshake_10MB.txt` | 10MB コーパス (hash locked) |

## 環境前提

- macOS arm64 (M2 MPS available)
- `local-genai/.venv/bin/python` (PyTorch 2.11.0)
- `/opt/homebrew/bin/python3.13` (システム Python; AIPL/aice 用)

## 主要コマンド (再現用)

### Stage-7-deeper-extend (champion) を再生成

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
# ~193 分 (M2 MPS), best ppl 4.038 @ step 40000
```

### 全 checkpoint を再評価

```sh
cd local-genai && .venv/bin/python fair_compare.py              # 1MB tail
cd local-genai && .venv/bin/python fair_compare.py --corpus 10MB  # 10MB tail
```

### champion でサンプル生成

```sh
local-genai/.venv/bin/python local-genai/generate_samples.py
# → local-genai/samples/samples_stage7_deeper_extend.md
```

## git 状態

- branch: `main`
- origin: `https://github.com/yaskodama/aios-claude.git`
- 最新コミット: `fb1ce77 local-genai: Stage-8-wider — width=192 loses to depth=6`
