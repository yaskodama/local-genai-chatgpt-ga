# ABCL Runtime Run

Date: 2026-05-11

The generated evolution program ran successfully with the Python 3.13.2 AIPL
runtime:

```bash
cd aice-evolution-v2/examples
../../scripts/run_aipl_python313.sh LocalGenAIIndependentEvolutionJP.abcl --timeout 10 --idle-ms 120
```

Result:

- parsed successfully
- executed successfully
- wrote `out/LocalGenAIIndependentEvolutionJP.abcl_lineage.json`
- copied the run snapshot to `out/LocalGenAIIndependentEvolutionJP.abcl_runtime_lineage.json`
- lineage count: 52 individuals
- filled cells: 39
- best score: 0.77

Best genome:

```text
tokenizer_family=bytelevel_bpe|vocab_class=2048|context_class=ctx256_mixed_utf8|model_scale=depth6_d128_1p4M|japanese_support=ja_mixed_corpus|train_data_scale=30MB_mixed_en_ja|delivery_mode=train_eval_checkpoint|aipl_feedback=multilingual_axis
```

The next practical step is to build the `30MB_MIXED_EN_JA` corpus and train
the BPE2048 candidate described in `ga_training_next_step.md`.
