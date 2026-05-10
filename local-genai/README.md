# local-genai

ローカル MacBook (M2, MPS) のみで動く byte 単位生成 AI を、
`aice-z-evolution/examples/LocalGenAIEvolutionJP.aice` の 7 世代設計に
従って実際に走らせる進化ループ。

## 構成

```
local-genai/
├── corpus/
│   └── tiny_corpus.txt          # 9.5KB の決定的英文 (SHA-256 ロック)
├── candidates/
│   ├── ngram_real.py            # stage 1 — 実機 numpy n-gram
│   └── design_estimator.py      # stages 2–7 — genome → ppl/params/time
├── common.py                    # corpus loader + ppl ヘルパ
├── reviewers.py                 # 3 reviewer (Quality / Efficiency / Reproducibility)
├── stages.py                    # 7 stage × 3 candidate の genome 定義
├── evolve.py                    # メインループ
└── out/
    ├── stage_<Name>.json        # 各世代の全候補と勝者
    └── final_archive.json       # 全世代のまとめ
```

## 実行

```sh
python3 local-genai/evolve.py
```

依存は標準ライブラリのみ。 PyTorch がない環境でも動くように、

- **stage 1 NGramFreq** だけは実機学習 (numpy なし、 stdlib のみ) で
  本物の bigram/trigram/unigram を訓練し、 holdout perplexity を測る。
- **stages 2–7** (CharRNN / TinyTransformer / ImprovedMicroGPT /
  DistilledMicro / PreferenceTuned / SemiAutoEvolve) は genome から
  param 数・ppl・学習時間・推論スループットを **設計推定式** で計算する。
  式は `aice-z-evolution/examples/LocalGenAIEvolutionJP.aice` の
  `expected_delta` 群と整合。

各候補は 3 reviewer で 0–34 点で採点し、 normalized_total
(`Quality/12 + Efficiency/12 + Reproducibility/10`) で勝者を決める。

## 結果サマリ (決定的、 seed=42)

| stage | winner | style | est ppl | params |
|---|---|---|---|---|
| NGramFreq | N1 | char_bigram_laplace | 15.52 (実測) | 357 (実観測) |
| CharRNN | R1 | single_layer_GRU_tied | 6.55 | 90,112 |
| TinyTransformer | T1 | depth1_h4_d128_rope_rmsnorm | 5.08 | 229,632 |
| ImprovedMicroGPT | G2 | depth8_h4_d160_drop005_kvcache | 3.80 | 2,501,120 |
| DistilledMicro | DI1 | soft_label_T2_alpha05 | 3.50 | 1,271,040 |
| PreferenceTuned | PT3 | three_axis_separate_lora | 3.69 | 1,271,040 |
| SemiAutoEvolve | SE1 | model_drafts_three_mutations | 3.63 | 1,271,040 |

ppl は世代を追って単調に下がり (15.5 → 6.5 → 5.1 → 3.8 → 3.5)、
DistilledMicro 以降は params を半分に絞っても品質を保つ。
PreferenceTuned は ppl がわずかに戻る (DPO の代償) が、 reviewer 整合性
スコアと推論スループット (`kv_cache_plus_int8`) で勝つ。

## 設計上の注意

- corpus は `9614a5a4d3f6474f004c982e8a2e89f8bdbda367fe55edc6d9d52d72cc48593e`
  でロックされており、 `common.load_corpus()` が起動時に検証する。
- 出力は決定的: 同じソースから常に同じ `final_archive.json` が出る。
- 実機 PyTorch 学習を組み込みたい場合は、
  `candidates/charrnn_real.py` などを足し、 `stages.py` の
  `real_train` フラグを `True` にして evolve.py に分岐を追加するだけ。
