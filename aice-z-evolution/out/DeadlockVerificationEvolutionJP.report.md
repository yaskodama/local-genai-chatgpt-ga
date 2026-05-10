# DeadlockVerificationEvolutionJP 自動変換レポート

- dialect: `aice_evolution_v1`
- candidate_count: `3`
- reviewer_count: `3`
- final_archive: `ProvenAndCheckedWinner`

## Stages

- order 1 `PrintDebug` branch `main` archive `PrintDebugWinner`
  - parents: `none`
  - mutations: `none`
  - crossover: `none`
- order 2 `Assertion` branch `main` archive `AssertionWinner`
  - parents: `PrintDebugWinner`
  - mutations: `M1_Print_to_Assert`
  - crossover: `none`
- order 3 `RandomFuzz` branch `main` archive `RandomFuzzWinner`
  - parents: `AssertionWinner`
  - mutations: `M2_Assert_to_Fuzz`
  - crossover: `none`
- order 4 `BoundedModelCheck` branch `main` archive `BoundedModelCheckWinner`
  - parents: `RandomFuzzWinner`
  - mutations: `M3_Fuzz_to_Bounded, M8_Add_LTL_Property, M9_Add_Counter_Example_Trace`
  - crossover: `none`
- order 5 `PromelaSPIN` branch `exhaustive_external_path` archive `PromelaSPINWinner`
  - parents: `BoundedModelCheckWinner`
  - mutations: `M4_Bounded_to_Promela, M8_Add_LTL_Property`
  - crossover: `none`
- order 5 `TLAPlusTLC` branch `exhaustive_external_path` archive `TLAPlusTLCWinner`
  - parents: `BoundedModelCheckWinner`
  - mutations: `M5_Bounded_to_TLA, M8_Add_LTL_Property`
  - crossover: `none`
- order 6 `OrderedAcquisition` branch `structural_fix_path` archive `OrderedAcquisitionWinner`
  - parents: `BoundedModelCheckWinner`
  - mutations: `M6_Symptom_to_Resource_Hierarchy`
  - crossover: `C2_Bounded_to_OrderedFix_via_CounterExample`
- order 7 `TypedLinear` branch `structural_fix_path` archive `TypedLinearWinner`
  - parents: `OrderedAcquisitionWinner, BoundedModelCheckWinner`
  - mutations: `M7_Untyped_to_Linear_Channel`
  - crossover: `C3_OrderedConvention_to_TypedLinear`
- order 8 `ProvenAndChecked` branch `join` archive `ProvenAndCheckedWinner`
  - parents: `TypedLinearWinner, PromelaSPINWinner, TLAPlusTLCWinner`
  - mutations: `M10_Combine_Typed_and_Checked`
  - crossover: `C1_SPIN_TLA_to_BackendAbstraction`
