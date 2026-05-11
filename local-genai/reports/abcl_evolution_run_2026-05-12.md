# ABCL Evolution Run

Date: 2026-05-12

Command:

```bash
cd aice-evolution-v2/examples
../../scripts/run_aipl_python313.sh LocalGenAIIndependentEvolutionJP.abcl --timeout 20 --idle-ms 120
```

Artifacts:

- current lineage: `aice-evolution-v2/examples/out/LocalGenAIIndependentEvolutionJP.abcl_lineage.json`
- pre-run backup: `aice-evolution-v2/examples/out/LocalGenAIIndependentEvolutionJP.abcl_lineage.before_20260512_000841.json`
- run snapshot: `aice-evolution-v2/examples/out/LocalGenAIIndependentEvolutionJP.abcl_lineage.run_20260512_000859.json`

Result:

- status: completed
- JSON validation: passed
- individuals: 52
- filled cells: 41
- best score: 0.77
- best id: `I4`

Best genome:

```text
tokenizer_family=bytelevel_bpe|vocab_class=2048|context_class=ctx256_mixed_utf8|model_scale=depth6_d128_1p4M|japanese_support=ja_mixed_corpus|train_data_scale=30MB_mixed_en_ja|delivery_mode=train_eval_checkpoint|aipl_feedback=multilingual_axis
```

Top 5:

| rank | id | score | genome |
|---:|---|---:|---|
| 1 | `I4` | 0.77 | `tokenizer_family=bytelevel_bpe|vocab_class=2048|context_class=ctx256_mixed_utf8|model_scale=depth6_d128_1p4M|japanese_support=ja_mixed_corpus|train_data_scale=30MB_mixed_en_ja|delivery_mode=train_eval_checkpoint|aipl_feedback=multilingual_axis` |
| 2 | `I50` | 0.73 | `tokenizer_family=unigram|vocab_class=2048|context_class=ctx256_effective_midpoint|model_scale=stage9_bpe_extend|japanese_support=ja_mixed_corpus|train_data_scale=30MB_mixed_en_ja|delivery_mode=train_eval_checkpoint|aipl_feedback=multilingual_axis` |
| 3 | `I2` | 0.67 | `tokenizer_family=bytelevel_bpe|vocab_class=2048|context_class=ctx256_effective_3to4_bytes_per_token|model_scale=depth6_d128_1p4M|japanese_support=utf8_tokenizer_only|train_data_scale=10MB_en_baseline|delivery_mode=train_eval_checkpoint|aipl_feedback=vocab_axis` |
| 4 | `I44` | 0.66 | `tokenizer_family=bytelevel_bpe|vocab_class=4096|context_class=ctx256_effective_3to4_bytes_per_token|model_scale=depth6_d128_1p4M|japanese_support=utf8_tokenizer_only|train_data_scale=100MB_deduped|delivery_mode=train_eval_checkpoint|aipl_feedback=vocab_axis` |
| 5 | `I10` | 0.65 | `tokenizer_family=byte|vocab_class=4096|context_class=ctx256_current|model_scale=stage9_bpe_extend|japanese_support=ja_mixed_corpus|train_data_scale=100MB_deduped|delivery_mode=train_eval_checkpoint|aipl_feedback=productization` |

Interpretation:

The run again selected the same practical target that already produced the
best measured local model: BPE2048, mixed UTF-8 context, depth6/d_model128,
and 30 MB mixed English/Japanese data. The next improvement should focus on
replacing the current repeated Japanese smoke corpus with larger licensed
Japanese source text, then retraining this same genome.
