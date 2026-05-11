# MeCab Segmentation

Japanese corpus building now defaults to MeCab segmentation:

```bash
cd local-genai
.venv/bin/python build_mixed_corpus.py --ja-segmenter mecab
```

Current local status:

- `mecab` command: not found on PATH
- Python module `MeCab`: installed and working
- Homebrew packages checked locally: no MeCab install found
- MeCab verification: `日本 語 の 区切り を 確認 し ます 。`

Supported MeCab paths:

1. `mecab` command on PATH, called as `mecab -Owakati`
2. Python module `MeCab` from `mecab-python3`, called with `MeCab.Tagger("-Owakati")`

If MeCab is not installed, the build command fails intentionally instead of
silently producing an unsegmented Japanese corpus.

Python-only install option:

```bash
cd local-genai
.venv/bin/pip install -r requirements-mecab.txt
```

After installation, verify:

```bash
cd local-genai
.venv/bin/python - <<'PY'
import MeCab
print(MeCab.Tagger("-Owakati").parse("日本語の区切りを確認します。"))
PY
```

Command-line install option on macOS:

```bash
brew install mecab mecab-ipadic
```

For a temporary unsegmented smoke corpus only:

```bash
cd local-genai
.venv/bin/python build_mixed_corpus.py --ja-segmenter none --allow-repeat
```

The manifest records the selected Japanese segmenter in
`corpus/tinyshake_ja_30MB.txt.manifest.json`.

Latest MeCab rebuild:

- corpus: `corpus/tinyshake_ja_30MB.txt`
- bytes: 30,000,000
- sha256: `7fa601e6d1871a54f491380866c082e40ba6c3c7ce1b38d8fd482a6feeffbc2b`
- segmenter: `mecab`
- Japanese source bytes after segmentation: 1,225
- audit quality flag: `smoke_only`

Dependency-free baseline on first 2 MB:

- N1 bigram: ppl 9.107, bpb 3.187
- N2 trigram with backoff: ppl 4.691, bpb 2.230
- N3 unigram: ppl 51.283, bpb 5.680

BPE2048 full training:

- checkpoint: `out/transformer_ga_bpe2048_ja30mb_mecab.pt`
- tokenizer: `out/tokenizer_ga_bpe2048_ja30mb_mecab.json`
- metrics: `out/stage_ga_bpe2048_ja30mb_mecab_real.json`
- steps: 20,000
- params: 1,447,296
- best bpb: 1.2335
- byte-equivalent perplexity: 2.351
- train time: 26,858.0 seconds

Comparison:

- existing byte-level champion: bpb 2.014
- previous unsegmented BPE2048 run: bpb 1.2338
- MeCab BPE2048 run: bpb 1.2335

Inference:

- chat model id: `ga_bpe2048_mecab`
- sample report: `samples/samples_ga_bpe2048_ja30mb_mecab.md`
