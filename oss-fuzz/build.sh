#!/bin/bash -eu
# OSS-Fuzz build script for the ba64 Python harnesses.

cd "$SRC/ba64"

# The codec is importable as a top-level module.
export PYTHONPATH="$SRC/ba64/python"

for harness in fuzz_decode fuzz_roundtrip; do
  compile_python_fuzzer "python/fuzz/${harness}.py"
done

# Seed corpus, shared across languages, built from the committed vectors.
python3 python/fuzz/seed_corpus.py "$SRC/corpus"
( cd "$SRC/corpus" && zip -q -r "$OUT/fuzz_decode_seed_corpus.zip" . )
cp "$OUT/fuzz_decode_seed_corpus.zip" "$OUT/fuzz_roundtrip_seed_corpus.zip"
