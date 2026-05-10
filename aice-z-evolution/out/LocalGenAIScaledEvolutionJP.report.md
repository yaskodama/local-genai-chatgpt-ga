# LocalGenAIScaledEvolutionJP 自動変換レポート

- dialect: `aice_evolution_v1`
- candidate_count: `3`
- reviewer_count: `3`
- final_archive: `SemiAutoEvolveLocalLLMWinner`

## Stages

- order 1 `TinyBigram10KB_Inherited` branch `main` archive `TinyBigram10KBWinner`
  - parents: `none`
  - mutations: `none`
  - crossover: `none`
- order 2 `TinyCharRNN10KB_Inherited` branch `main` archive `TinyCharRNN10KBWinner`
  - parents: `TinyBigram10KBWinner`
  - mutations: `M1_NGram_to_CharRNN inherited`
  - crossover: `none`
- order 3 `MidCharRNN100KB` branch `main` archive `MidCharRNN100KBWinner`
  - parents: `TinyCharRNN10KBWinner`
  - mutations: `M1_Scale_Corpus_10x`
  - crossover: `none`
- order 4 `MidTransformer100KB` branch `main` archive `MidTransformer100KBWinner`
  - parents: `MidCharRNN100KBWinner`
  - mutations: `M2_Add_Transformer_Block, M3_Add_Dropout_For_Generalization, M4_RoPE_Plus_RMSNorm, M5_Add_KVCache_Inference`
  - crossover: `none`
- order 5 `BigTransformer1MB` branch `scale_path` archive `BigTransformer1MBWinner`
  - parents: `MidTransformer100KBWinner`
  - mutations: `M1_Scale_Corpus_10x, M2_Add_Transformer_Block`
  - crossover: `none`
- order 6 `DistilledMid1MB` branch `scale_path` archive `DistilledMid1MBWinner`
  - parents: `BigTransformer1MBWinner, MidTransformer100KBWinner`
  - mutations: `M6_Distill_From_Teacher, M5_Add_KVCache_Inference`
  - crossover: `C1_Distill_From_BigTransformer`
- order 7 `SemiAutoEvolveLocalLLM` branch `join` archive `SemiAutoEvolveLocalLLMWinner`
  - parents: `DistilledMid1MBWinner, BigTransformer1MBWinner`
  - mutations: `M7_Local_LLM_Proposes_Mutations`
  - crossover: `C2_LLMProposal_Plus_Reviewer_History`
