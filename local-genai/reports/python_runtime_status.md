# Python Runtime Status

Date: 2026-05-11

## Current Python

The active `python3` is already Homebrew Python 3.13.2:

```text
/opt/homebrew/bin/python3
Python 3.13.2
```

The AIPL virtual environment was created from the same Python:

```text
.venv-aipl/bin/python
Python 3.13.2
```

## AIPL Status

Python version is not the blocker. The AIPL parser dependency `lark` is now
available in `.venv-aipl`, and the generated ABCL evolution program runs
through the Python 3.13.2 wrapper.

Use this wrapper so AIPL always runs with the Python 3.13 venv:

```sh
scripts/run_aipl_python313.sh <program.abcl>
```

Verified:

```sh
scripts/run_aipl_python313.sh abclc/Hello.abcl --timeout 1
cd aice-evolution-v2/examples
../../scripts/run_aipl_python313.sh LocalGenAIIndependentEvolutionJP.abcl --timeout 10 --idle-ms 120
```

## Neural Training Blocker

For `local-genai` neural training, Python 3.13.2 is available but the active
environment lacks `torch` and `tokenizers`.

`train_stage8_bpe.py --help` now works without those packages, but actual BPE
transformer training stops with:

```text
need torch package: pip install torch
```

Install:

```sh
cd local-genai
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
```
