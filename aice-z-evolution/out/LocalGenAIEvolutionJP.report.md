# LocalGenAIEvolutionJP 自動変換レポート

- dialect: `aice_evolution_v1`
- candidate_count: `3`
- reviewer_count: `3`
- final_archive: `SemiAutoEvolveWinner`

## Stages

- order 1 `NGramFreq` branch `main` archive `NGramFreqWinner`
  - parents: `none`
  - mutations: `none`
  - crossover: `none`
- order 2 `CharRNN` branch `main` archive `CharRNNWinner`
  - parents: `NGramFreqWinner`
  - mutations: `M1_NGram_to_CharRNN`
  - crossover: `none`
- order 3 `TinyTransformer` branch `main` archive `TinyTransformerWinner`
  - parents: `CharRNNWinner`
  - mutations: `M2_CharRNN_to_TinyTransformer, M3_Add_Positional_Embedding, M4_Add_LayerNorm`
  - crossover: `C1_RNN_plus_Attention_to_Hybrid optional`
- order 4 `ImprovedMicroGPT` branch `improvement_path` archive `ImprovedMicroGPTWinner`
  - parents: `TinyTransformerWinner`
  - mutations: `M5_Add_Dropout, M6_Increase_Depth_and_Heads, M7_Add_KVCache_for_Inference`
  - crossover: `none`
- order 5 `DistilledMicro` branch `improvement_path` archive `DistilledMicroWinner`
  - parents: `ImprovedMicroGPTWinner`
  - mutations: `M8_Distill_from_Teacher`
  - crossover: `none`
- order 6 `PreferenceTuned` branch `alignment_path` archive `PreferenceTunedWinner`
  - parents: `DistilledMicroWinner`
  - mutations: `M9_Add_Preference_Tuning_DPO`
  - crossover: `C2_Distill_plus_DPO_to_Aligned`
- order 7 `SemiAutoEvolve` branch `join` archive `SemiAutoEvolveWinner`
  - parents: `PreferenceTunedWinner, ImprovedMicroGPTWinner`
  - mutations: `M10_Add_SelfProposed_Mutations`
  - crossover: `C3_Reviewer_Score_to_Mutation_Proposal`
