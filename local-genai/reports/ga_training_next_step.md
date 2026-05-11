# GA Training Next Step

The latest ABCL-equivalent evolution run selected this practical target:

- tokenizer: byte-level BPE
- vocab: 2048
- context: 256 mixed UTF-8 tokens
- model: depth 6, d_model 128
- data: 30 MB mixed English/Japanese

`local-genai` can now load a sidecar-hashed mixed corpus as
`30MB_MIXED_EN_JA`.

Current status: `torch` and `tokenizers` are installed in `local-genai/.venv`,
the evolved BPE2048 model has been trained, and inference works. The remaining
quality blocker is corpus quality: the current Japanese side is a repeated
smoke seed, not final training data.

## Build Corpus

Install runtime dependencies first:

```bash
cd local-genai
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
```

Place Japanese UTF-8 text files in:

```bash
local-genai/corpus/ja_sources/
```

Then run:

```bash
cd local-genai
.venv/bin/python build_mixed_corpus.py --ja-segmenter mecab
```

For a smoke test with limited local text, repeat available sources:

```bash
cd local-genai
.venv/bin/python build_mixed_corpus.py --ja-segmenter mecab --allow-repeat
```

## Train GA Elite Candidate

```bash
cd local-genai
.venv/bin/python train_stage8_bpe.py \
  --corpus 30MB_MIXED_EN_JA \
  --vocab-size 2048 \
  --ctx 256 \
  --bptt 256 \
  --depth 6 \
  --d-model 128 \
  --steps 20000 \
  --out-name transformer_ga_bpe2048_ja30mb.pt \
  --tokenizer-name tokenizer_ga_bpe2048_ja30mb.json
```

This is the recommended continuation because it converts the evolved genome
from a strategy artifact into a trainable experiment.

## Dependency-Free Baseline

Before PyTorch dependencies are available, verify the mixed corpus with a real
n-gram measurement:

```bash
cd local-genai
python train_ngram_baseline.py --corpus 30MB_MIXED_EN_JA --limit-bytes 2000000
```

Latest smoke result on the generated 30 MB mixed corpus, evaluated on the
first 2 MB:

- N1 bigram: ppl 8.795, bpb 3.137
- N2 trigram with backoff: ppl 4.559, bpb 2.189
- N3 unigram: ppl 61.392, bpb 5.940

Metrics were written to `out/stage_ngram_baseline_mixed.json`.

The generated corpus currently uses `--allow-repeat` with a small Japanese
seed file, so it proves the pipeline but should be replaced with real licensed
Japanese text before judging model quality.

Audit the current corpus:

```bash
cd local-genai
.venv/bin/python audit_mixed_corpus.py
```

Latest audit:

- report: `reports/mixed_corpus_audit.json`
- quality flag: `smoke_only`
- Japanese source bytes: 1,225 after MeCab segmentation
- Japanese character ratio in generated corpus: 0.114
- repeated 4 KB chunk ratio: 0.144
- recommendation: replace the Japanese seed with larger licensed Japanese
  text, segment with MeCab, and rebuild without `--allow-repeat`

## BPE2048 Training Pilots

After installing `torch` and `tokenizers`, the evolved BPE2048 candidate was
trained on CPU because MPS was not available in the active runtime.

Smoke run:

- checkpoint: `out/transformer_ga_bpe2048_ja30mb_smoke.pt`
- metrics: `out/stage_ga_bpe2048_ja30mb_smoke_real.json`
- steps: 20
- best bpb: 9.648

Pilot run:

- checkpoint: `out/transformer_ga_bpe2048_ja30mb_pilot200.pt`
- metrics: `out/stage_ga_bpe2048_ja30mb_pilot200_real.json`
- steps: 200
- best bpb: 3.254

Longer pilot:

- checkpoint: `out/transformer_ga_bpe2048_ja30mb_pilot1000.pt`
- metrics: `out/stage_ga_bpe2048_ja30mb_pilot1000_real.json`
- steps: 1000
- best bpb: 2.437
- best step: 1000

Full evolved run:

- checkpoint: `out/transformer_ga_bpe2048_ja30mb.pt`
- tokenizer: `out/tokenizer_ga_bpe2048_ja30mb.json`
- metrics: `out/stage_ga_bpe2048_ja30mb_real.json`
- steps: 20000
- best bpb: 1.234
- best step: 20000
- byte-equivalent perplexity: 2.352
- params: 1,447,296
- train time: 5460.99 seconds

Final comparison:

- existing byte-level champion: bpb 2.014
- evolved BPE2048 full run: bpb 1.234
- improvement: 0.780 bpb better

The ABCL/GA-selected genome has produced a better measured model than the
previous byte-level champion on this generated mixed corpus.

MeCab-segmented full run:

- checkpoint: `out/transformer_ga_bpe2048_ja30mb_mecab.pt`
- tokenizer: `out/tokenizer_ga_bpe2048_ja30mb_mecab.json`
- metrics: `out/stage_ga_bpe2048_ja30mb_mecab_real.json`
- steps: 20000
- best bpb: 1.2335
- byte-equivalent perplexity: 2.351
- sample report: `samples/samples_ga_bpe2048_ja30mb_mecab.md`

## Inference

Use the evolved model in one-shot mode:

```bash
cd local-genai
.venv/bin/python chat.py --model ga_bpe2048 "こんにちは。今日は"
```

Generate the fixed sample report:

```bash
cd local-genai
.venv/bin/python generate_bpe_samples.py
```

Verified one-shot prompts:

```text
こんにちは。今日は、depth 6、d_model 128 です。
To be, or not to be,
Or else I know not what. Well, that have no wife
```

Sample report:

- `samples/samples_ga_bpe2048_ja30mb.md`
