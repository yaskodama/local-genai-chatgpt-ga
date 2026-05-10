# Level C — Parser + Eval Pipeline (full self-host of an AIPL subset)

The bootstrap's most ambitious step: **AIPL parses AIPL**.  Source
text → token array → AST records → Level A's evaluator runs them.
The host Python AIPL is now reduced to a literal interpreter for a
handful of `function` declarations; everything else (lexing, AST
construction, evaluation logic) lives in pure AIPL.

## Components

```
lexer.abcl    — character predicates, scanning helpers, `tokenize(src)`.
parser.abcl   — recursive-descent parser; `parse_program(tokens) -> {funcs, main}`.
eval.abcl     — Level A's evaluator carried over (env / binop / If / While).
run.sh        — concats lexer + parser + eval + sample, runs through host AIPL.
samples/      — full-pipeline programs.
out/          — captured output.
```

## Supported AIPL subset (parsable by parser.abcl)

```
program  := stmt*
stmt     := var_decl | assign | print | if | while | block | call_stmt
var_decl := "var" IDENT "=" expr ";"
assign   := IDENT "=" expr ";"
print    := "print" "(" expr ")" ";"
if       := "if" "(" expr ")" stmt ("else" stmt)?
while    := "while" "(" expr ")" "do" stmt
block    := "{" stmt* "}"
call_stmt:= IDENT "(" args? ")" ";"
expr     := add_expr (rel_op add_expr)?
add_expr := mul_expr (add_op mul_expr)*
mul_expr := unary    (mul_op unary)*
unary    := "-" unary | primary
primary  := INT | STR | IDENT ("(" args? ")")? | "(" expr ")"
```

Operators: `+ - * /  ==  != < > <= >=`.  Comments: `// to EOL`.

## What's not yet here

- **function decls** in the parsed source (the parser ingests
  top-level statements only; function calls in user code resolve to
  Call AST nodes which `eval.abcl` does not dispatch).
- **classes / records / tuples / arrays** — out of scope for the
  Level C demo, but achievable by extending the same pattern.
- **AIPL scheduler** (mailboxes, futures) — see "Self-host scope"
  below.

## Run

```sh
cd aipl-self-host/level-c
bash run.sh   samples/SampleLexer.abcl
bash run.sh   samples/SamplePipeline.abcl
bash run.sh   samples/SampleWhile.abcl

bash smoke.sh
```

## Verification (smoke.sh)

```
PASS  SampleLexer.abcl               found 'token count = 26'
PASS  SamplePipeline.abcl            found '13'
PASS  SampleWhile.abcl               found '10'
Level C samples: 3 pass / 0 fail
```

## Self-host scope (what stays on the host)

The original `.aice` spec for Level C asked for parser + scheduler +
mailbox + future + I/O bridges + a 20-line bootstrap loader.  This
implementation realises:

| layer        | location |
| ---          | ---      |
| **lexer**    | AIPL (lexer.abcl)            |
| **parser**   | AIPL (parser.abcl)           |
| **AST**      | AIPL records (constructed by parser.abcl) |
| **evaluator**| AIPL (eval.abcl)             |
| typeck         | AIPL (Level B-1…B-5)        |
| effect/linear/owned checks | AIPL (Level B-2…B-5) |
| actor scheduler        | host (Python — running the AIPL `function`s themselves) |
| mailbox / future       | host                           |
| I/O builtins           | host                           |
| bootstrap loader       | host (`run.sh` + Python AIPL `aipl_main.py`) |

The remaining "host" rows are the inherent layer-0 we discussed at
the start of this self-host — `eval(ast,env)` runs on top of host
AIPL `function`s, which in turn run inside Python's actor runtime.
A truly host-free AIPL would need to also write the actor scheduler
and the message queue in AIPL, with a tiny boot loop in C/Python
that just steps the scheduler.  That's a sensible Level C-2 target
later.

## Pipeline diagram

```
     source string                                      AIPL
          │   "var x = 3; var y = x*x+4; print(y);"    function
          ↓
   lexer.abcl::tokenize    → [{kind,val,pos}, ...]
          ↓
   parser.abcl::parse_program  → {funcs:[], main:[ast,...]}
          ↓
   eval.abcl::run_program       → prints values
```

Each box is pure-AIPL.  The diagram itself fits inside one host
process running `aipl_main.py`.

## Bootstrap progress

| Level | Phase | Self-host responsibility                       | smoke |
| ---   | ---   | ---                                            | ---   |
| A     | —     | metacircular eval                              | 4/4   |
| B-1   | 11    | typed annotations / arity / unions / promotion | 6/6   |
| B-2   | 12    | + capability effects                           | 4/4   |
| B-3   | 13    | + channel element types                        | 5/5   |
| B-4   | 14    | + linear / use-after-move                      | 4/4   |
| B-5   | 15    | + owned (pub field visibility)                 | 4/4   |
| **C** | **16+** | **lexer + parser + eval pipeline**            | **3/3** |

All Phase 9 axes are now self-checked, and the source-to-execution
front end is in pure AIPL.  The remaining gap is the actor
scheduler / mailbox / I/O which logically belongs to a future
"Level C-2".
