# Surviving mutants — equivalence analysis

`mutmut run` on `ba64.py`. Every mutant that survives the suite is listed here
and shown to be **equivalent** (produces behaviour indistinguishable from the
original for all inputs), which is why no test kills it. Non-equivalent survivors
are not tolerated — each was closed with a boundary test (see
`tests/test_unit.py` "boundary hardening" and `tests/test_chaos.py`
`test_inflation_cap_bounds_memory`).

Run: `cd python && mutmut run` then `mutmut results`. Regenerate this analysis if
the codec changes.

## Equivalent survivors (9)

### Canonical-base64 strictness is enforced by the round-trip, not by `validate`
- `_b64_canonical_decode__mutmut_3` — `validate=True` → `validate=None`
- `_b64_canonical_decode__mutmut_5` — `validate=True` → argument removed
- `_b64_canonical_decode__mutmut_6` — `validate=True` → `validate=False`

`_b64_canonical_decode` decodes then re-encodes and compares to the input. Any
non-canonical string (non-alphabet character, whitespace, bad padding, non-zero
trailing bits) fails that comparison and raises `E_BASE64` regardless of the
`validate` flag. `validate=True` only changes *where* the rejection happens (an
exception inside `b64decode` vs. the re-encode mismatch), never *whether* it
happens or which code is raised. Kept for defence-in-depth and to match SPEC.md
Appendix B; behaviourally redundant.

### `"ascii"` and `"ASCII"` are the same codec
- `_b64_canonical_decode__mutmut_13`, `encode__mutmut_6`, `encode__mutmut_38`
  — `.decode("ascii")` → `.decode("ASCII")`

Python's codec lookup normalises the name; the two spellings resolve to one
codec. No input can distinguish them.

### DEFLATE level default is a SHOULD, not a MUST
- `encode__mutmut_1` — default `level=6` → `level=7`

SPEC.md §6.4–6.5: the DEFLATE level is the encoder's free choice and it *SHOULD*
default to 6. An encoder defaulting to 7 is fully conforming — output is still a
valid ba64 text that round-trips and obeys the floor rule. The `level` parameter
itself still works (a separate mutant that *drops* the parameter is killed by
`test_level_argument_actually_changes_output`). Since encoding is non-canonical,
no decode-side or invariant test can pin the exact default, and per the spec it
need not.

### The floor comparison can never see a tie
- `encode__mutmut_39` — `len(candidate) < len(plain)` → `<=`

`len(plain)` is a base64 length: always a multiple of 4. `len(candidate)` is
`1 + len("=" + base64(frame))` = `1 + 4k`, always ≡ 1 (mod 4). The two lengths
are in different residue classes mod 4, so `len(candidate) == len(plain)` is
**impossible**. The `<` vs `<=` boundary therefore governs an unreachable case;
the tie-breaking rule ("ties → plain", SPEC §6.2) is correct but vacuous.
(Verified empirically over 20k inputs; see the mod-4 note in the Phase-2 log.)

### A zero output-cap of 1 vs 2 is the same for `decoded_len == 0`
- `decode__mutmut_67` — `decoded_len or 1` → `decoded_len or 2`

The `or` only fires when `decoded_len == 0`. In that case the expected output is
zero bytes, so the length check `len(out) > decoded_len` is `len(out) > 0`: any
non-empty inflation fails as `E_LENGTH_MISMATCH` whether the cap was 1 or 2, and
an empty inflation (`len(out) == 0`) passes to the CRC check identically for both
caps. No frame distinguishes cap 1 from cap 2. (For `decoded_len > 0` the `or`
never evaluates its right operand, so the mutation is inert.)

## Note

Two mutations of `_leb128_encode` (`n >>= 7` → `n = 7`, and → `n <<= 7`) produce
infinite loops and are caught as **timeouts**, not silent survivors — the suite
detects them.
