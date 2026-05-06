# AICE Z Evolution Translator

This directory is isolated from the existing project files. It adds an
extended `.aice` format and a standalone translator that emits `.abcl`.

Pipeline:

1. Read the initial natural-language specification from `.aice`.
2. Convert it into a lightweight Z-style schema.
3. Check it with two logical transformations:
   `predicate_normal_form` and `state_transition_model`.
4. Re-run three logical reviews and choose the best-scoring view.
5. If contradictions are found, repair by `logical_consensus` and carry the
   repaired specification to the next generation.
6. Run deterministic evolutionary selection over candidate genomes.
7. Emit an OCaml ABCL/c+ actor program for `src/repl_thread.ml` /
   `abclrepl_thread` that generates the target program and performs a final
   check against the Z specification and logical artifacts.

`target_language = ABCL;` is the default for the example. A concrete language
can be selected by writing, for example, `target_language = python;`.
`target_language = any;` is also accepted when the program language should be
left open, while the generated orchestration file remains OCaml ABCL/c+.

Run:

```sh
python3 aice-z-evolution/aice_z_translator.py \
  aice-z-evolution/examples/ReceptionWorkflowZEvolution.aice \
  -o aice-z-evolution/out
```

Generated files:

- `out/ReceptionWorkflowZEvolution.abcl`
- `out/ReceptionWorkflowZEvolution.report.md`
- `out/ReceptionWorkflowZEvolution.manifest.json`
