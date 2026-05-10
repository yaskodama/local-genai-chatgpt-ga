# TrafficLightParadigmEvolutionJP_Auto 自動変換レポート

- dialect: `aice_evolution_v1`
- candidate_count: `3`
- reviewer_count: `3`
- final_archive: `ParallelOOPWinner`

## Stages

- order 1 `Assembly` branch `main` archive `AssemblyWinner`
  - parents: `none`
  - mutations: `none`
  - crossover: `none`
- order 2 `BASIC` branch `main` archive `BASICWinner`
  - parents: `AssemblyWinner`
  - mutations: `M1_Assembly_to_BASIC, M9_Add_Demo, M7_Integer_to_Symbolic_State optional`
  - crossover: `none`
- order 3 `C` branch `imperative_object_path` archive `CWinner`
  - parents: `BASICWinner`
  - mutations: `M2_BASIC_to_C, M7_Integer_to_Symbolic_State, M8_Implicit_Wrap_to_Explicit_Cases`
  - crossover: `C1_BASIC_to_C_from_AssemblyTraits optional`
- order 4 `JavaOOP` branch `imperative_object_path` archive `JavaOOPWinner`
  - parents: `CWinner`
  - mutations: `M3_C_to_Java_OOP, M9_Add_Demo`
  - crossover: `none`
- order 3 `Functional` branch `functional_object_path` archive `FunctionalWinner`
  - parents: `BASICWinner`
  - mutations: `M4_BASIC_to_Functional, M7_Integer_to_Symbolic_State, M8_Implicit_Wrap_to_Explicit_Cases`
  - crossover: `none`
- order 4 `FunctionalOOP` branch `functional_object_path` archive `FunctionalOOPWinner`
  - parents: `FunctionalWinner, BASICWinner`
  - mutations: `M5_Functional_to_FunctionalOOP, M9_Add_Demo`
  - crossover: `C2_Functional_to_FunctionalOOP_from_BASICDemo`
- order 5 `ParallelOOP` branch `join` archive `ParallelOOPWinner`
  - parents: `JavaOOPWinner, FunctionalOOPWinner`
  - mutations: `M6_Join_to_ParallelOOP, M10_Add_State_Owner, M9_Add_Demo`
  - crossover: `C3_JavaOOP_FunctionalOOP_to_ParallelOOP`
