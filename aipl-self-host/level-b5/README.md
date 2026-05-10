# Level B-5 — Phase 15 Owned (pub field visibility) in AIPL

Pure-AIPL extension of Level B-4 that adds class declarations with
per-field `is_pub` flags and enforces external-access rules:

- External `obj.field` **read** of a non-`pub` field → flagged.
- External `obj.field = expr` **write** to any field of an actor →
  always flagged (must go through a method).

## AST extensions vs B-4

```
Field         {name, type, is_pub}      // is_pub = 1 / 0
ClassDecl     {name, fields: [Field], methods: [FnDecl]}
New           {tag:"New", cls_name, args}
FieldAccess   {tag:"FieldAccess", obj, field}
FieldAssign   {tag:"FieldAssign", obj, field, expr}
```

Program shape:

```
{classes: [ClassDecl], fns: [FnDecl], main: [stmt]}
```

## What the checker enforces

| Rule                                                 | Sample                  |
| ---                                                  | ---                     |
| `New cls(args)` -> `actor(cls)` type binding         | `SampleOwnedClean`      |
| `pub` field read OK from outside                     | `SampleOwnedClean`      |
| Private field read external -> `private field` issue | `SamplePrivateRead`     |
| External write -> always issue (pub or private)      | `SampleExternalWrite`   |
| Self-consistency + owned violation                   | `SampleSelfConsistency` |

The walker reads a separate `classes` registry alongside `fns` (both
registered at `tc_check_program` entry).  `actor_class_name(ty)`
extracts `C` from `"actor(C)"`, and `cls_field(classes, cls, name)`
fetches the field decl for visibility checks.

## Phase monotonicity

| Invariant                    | B-5 status                                       |
| ---                          | ---                                              |
| `tenv` shape                 | unchanged                                        |
| tail-first lookup            | unchanged                                        |
| per-call fresh tenv          | unchanged                                        |
| `tc_compatible` lattice      | unchanged at the surface (linearity strip first) |
| Phase 12 effect tracking     | unchanged                                        |
| Phase 13 channel rules       | unchanged                                        |
| Phase 14 linear / moved      | unchanged                                        |

The walker signature gains one extra param `classes` threaded through
every internal call — a sibling-orthogonal addition.  No B-4
behaviour was modified; B-5 simply ignores `classes` when no class
decls are present, which is exactly the case for B-1…B-4 samples.

## Run

```sh
cd aipl-self-host/level-b5
bash run.sh   samples/SampleOwnedClean.abcl
bash run.sh   samples/SamplePrivateRead.abcl
bash run.sh   samples/SampleExternalWrite.abcl
bash run.sh   samples/SampleSelfConsistency.abcl

bash smoke.sh
```

## Verification (smoke.sh)

```
PASS  SampleOwnedClean.abcl            issues=0
PASS  SamplePrivateRead.abcl           issues=1
PASS  SampleExternalWrite.abcl         issues=2
PASS  SampleSelfConsistency.abcl       issues=2
Level B-5 owned samples: 4 pass / 0 fail
```

Diagnostic strings:

```
private field `acct.balance` of actor(BankAccount) — annotate with `pub`
  or call a method instead

external write to `acct.holder` on actor(BankAccount) is not allowed
  — use a method (Phase 15: symbol_owned)
```

## Out of scope (deferred)

- **Methods within a class can read/write their own fields freely** —
  B-5 doesn't model in-class method bodies separately yet (the host
  Python typeck does this via "self." vs bare-Var resolution).
  Method bodies in our `ClassDecl.methods` are walked as if they
  were top-level functions, so they don't get a special "in-class
  context" treatment.  All four samples avoid in-class field access
  patterns by keeping `methods: []`.
- **become C()** retargeting an actor's class isn't tracked.
- **Records inside actor fields**: an actor field of record type
  isn't recursively guarded; FieldAssign on the inner record would
  go through the record path, not the actor path.

## Bootstrap progress

| Level | Phase | Self-host responsibility                      | smoke |
| ---   | ---   | ---                                            | ---   |
| A     | —     | metacircular eval                              | 4/4   |
| B-1   | 11    | typed annotations / arity / unions / promotion | 6/6   |
| B-2   | 12    | + capability effects (`!{fs,ai,net,mut}`)      | 4/4   |
| B-3   | 13    | + channel element types                        | 5/5   |
| B-4   | 14    | + linear / use-after-move                      | 4/4   |
| **B-5** | **15** | **+ owned (pub field visibility)**         | **4/4** |
| C     | 16+   | parser, scheduler, mailbox, futures, I/O       | —     |

All five Phase 9 prediction axes are now self-hostable in AIPL.
