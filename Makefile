.PHONY: vectors conformance verify clean py-test py-cov py-slow py-mutation py-gate cross matrix

# Python interpreter for the reference impl's tests. Uses the local .venv if
# present (created in Phase 2), else the system python3.
PY := $(shell [ -x .venv/bin/python ] && echo .venv/bin/python || echo python3)

# Regenerate the conformance corpus + SHA256SUMS (deterministic, fixed seed).
vectors:
	python3 generator/gen_vectors.py

# Drive every committed vector through the reference codec (Phase 1 exit gate).
conformance:
	python3 conformance/run_reference.py

# CI gate: the committed corpus must exactly match a fresh generator run AND
# pass against the reference codec. Back up the committed files, regenerate over
# them, and diff — so a hand-edited vector OR a stale generator is caught.
verify:
	@rm -rf vectors/.backup && mkdir -p vectors/.backup
	@cp vectors/*.json vectors/SHA256SUMS vectors/.backup/ 2>/dev/null || true
	python3 generator/gen_vectors.py
	@# bombs.json and differential.json embed raw zlib DEFLATE output, which is
	@# byte-reproducible only within one zlib build; exclude them (and the derived
	@# SHA256SUMS) from the drift check. They are still regenerated and semantically
	@# re-verified against the reference by run_reference.py below.
	@if ! diff -rq vectors/.backup vectors --exclude=.backup \
			--exclude=bombs.json --exclude=differential.json --exclude=SHA256SUMS >/dev/null; then \
		echo "vectors/ out of date or hand-edited — regenerated output differs from committed;"; \
		echo "run 'make vectors' and commit the result."; \
		rm -rf vectors/.backup; exit 1; \
	fi
	@rm -rf vectors/.backup
	python3 conformance/run_reference.py

# --- Python reference (Phase 2) ---------------------------------------------

# Fast suite (unit, property, conformance, differential, chaos, CLI).
py-test:
	cd python && $(abspath $(PY)) -m pytest

# Heavy IT/perf suite (10 MiB roundtrips, 40 MiB CLI streams).
py-slow:
	cd python && $(abspath $(PY)) -m pytest -m slow

# 100% branch-coverage gate on the codec file (non-negotiable).
py-cov:
	cd python && $(abspath $(PY)) -m coverage run --branch -m pytest
	cd python && $(abspath $(PY)) -m coverage report --include='*/ba64.py' --fail-under=100 -m

# Mutation gate: >=95% killed; survivors must be documented equivalents (MUTANTS.md).
py-mutation:
	cd python && $(abspath $(PY)) -m mutmut run

# Phase 2 CI gate.
py-gate: py-cov py-slow

# --- Phase 5: cross-language conformance ------------------------------------

# Every implementation runs the shared corpus (per-language conformance).
cross:
	bash conformance/run_all.sh

# 6x6 encoder/decoder matrix over 10k seeded inputs (the keystone).
matrix:
	$(abspath $(PY)) conformance/run.py

clean:
	rm -f vectors/*.json vectors/SHA256SUMS
	rm -rf python/mutants python/.mutmut-cache python/.coverage
