#!/usr/bin/env python3
"""Phase 5 keystone — 6x6 cross-language conformance.

Generate 10k seeded inputs, have every implementation ENCODE them, then have
every implementation DECODE every encoder's output. All k*k pairs (36 with all
six present) must reproduce the original bytes exactly. Then confirm all decoders
return identical error codes over decode_errors.json (modulo the documented
decoder-dependent case, CAVEATS.md).

A language whose toolchain is missing or fails to build is SKIPPED with a notice,
never a silent pass; the matrix runs over whatever is present. Exit non-zero on
any disagreement.

Run: python3 conformance/run.py   (uses .venv python for the Python harness if
that is how it was launched).
"""

import json
import os
import random
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ENV = dict(os.environ)
ENV["PATH"] = "/opt/homebrew/opt/openjdk/bin:/opt/homebrew/opt/dotnet/bin:" + ENV.get("PATH", "")
ENV["DOTNET_CLI_TELEMETRY_OPTOUT"] = "1"
ENV["DOTNET_NOLOGO"] = "1"

RUST_BIN = os.path.join(ROOT, "rust", "target", "release", "harness")
GO_BIN = os.path.join(ROOT, "go", "ba64_harness")
CS_DLL = os.path.join(ROOT, "csharp", "bin", "Release", "net10.0", "ba64tests.dll")

# name -> {check, build, cmd(mode)->argv, cwd}
LANGS = {
    "python": {
        "check": [sys.executable, "--version"],
        "build": None,
        "cmd": lambda m: [sys.executable, "harness.py", m],
        "cwd": os.path.join(ROOT, "python"),
    },
    "typescript": {
        "check": ["node", "--version"],
        "build": None,
        "cmd": lambda m: ["node", "harness.ts", m],
        "cwd": os.path.join(ROOT, "js"),
    },
    "go": {
        "check": ["go", "version"],
        "build": (["go", "build", "-o", GO_BIN, "./harness"], os.path.join(ROOT, "go")),
        "cmd": lambda m: [GO_BIN, m],
        "cwd": os.path.join(ROOT, "go"),
    },
    "rust": {
        "check": ["cargo", "--version"],
        "build": (["cargo", "build", "--release", "--quiet", "--bin", "harness"], os.path.join(ROOT, "rust")),
        "cmd": lambda m: [RUST_BIN, m],
        "cwd": os.path.join(ROOT, "rust"),
    },
    "java": {
        "check": ["javac", "-version"],
        "build": (["javac", "Ba64.java", "Harness.java"], os.path.join(ROOT, "java")),
        "cmd": lambda m: ["java", "-cp", ".", "Harness", m],
        "cwd": os.path.join(ROOT, "java"),
    },
    "csharp": {
        "check": ["dotnet", "--version"],
        "build": (["dotnet", "build", "-c", "Release", "--nologo", "-v", "q", "ba64.csproj"], os.path.join(ROOT, "csharp")),
        "cmd": lambda m: ["dotnet", CS_DLL, m],
        "cwd": os.path.join(ROOT, "csharp"),
    },
}


def available(spec):
    try:
        subprocess.run(spec["check"], env=ENV, cwd=ROOT, capture_output=True, check=True)
        return True
    except Exception:
        return False


def build(name, spec):
    if not spec["build"]:
        return True
    argv, cwd = spec["build"]
    r = subprocess.run(argv, env=ENV, cwd=cwd, capture_output=True, text=True)
    if r.returncode != 0:
        print(f"  build failed for {name}:\n{r.stderr[-800:]}")
    return r.returncode == 0


def run_harness(spec, mode, items):
    if not items:
        return []
    payload = f"{len(items)}\n" + "\n".join(items)
    r = subprocess.run(spec["cmd"](mode), env=ENV, cwd=spec["cwd"],
                       input=payload, capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError(f"harness {mode} failed: {r.stderr[-500:]}")
    out = r.stdout.split("\n")
    if len(out) != len(items):
        raise RuntimeError(f"harness {mode} returned {len(out)} of {len(items)} lines")
    return out


def gen_inputs(n=10000):
    rng = random.Random(0x5150)
    out = []
    for i in range(n):
        k = i % 5
        if k == 0:
            out.append(bytes(rng.getrandbits(8) for _ in range(rng.randint(0, 48))))
        elif k == 1:
            out.append(rng.choice([b"ab ", b"log ", b'{"x":1} ']) * rng.randint(0, 40))
        elif k == 2:
            out.append(b"")
        elif k == 3:
            out.append(bytes([rng.randint(0, 255)]) * rng.randint(0, 30))
        else:
            out.append(bytes(rng.getrandbits(8) for _ in range(rng.randint(0, 4))))
    return [b.hex() for b in out]


def load_error_cases():
    cases = []
    with open(os.path.join(ROOT, "vectors", "decode_errors.json"), encoding="utf-8") as f:
        for c in json.load(f)["cases"]:
            cases.append((c["input"], [c["error"]] + c.get("error_alt", [])))
    return cases


def main():
    present = [n for n in LANGS if available(LANGS[n])]
    missing = [n for n in LANGS if n not in present]
    for n in missing:
        print(f"  {n:11s} SKIPPED (toolchain missing)")
    present = [n for n in present if build(n, LANGS[n])]

    print(f"\nPresent implementations: {', '.join(present)}")
    if len(present) < 2:
        print("need >=2 implementations for a cross-check")
        return 1

    inputs = gen_inputs()
    print(f"generated {len(inputs)} seeded inputs\n")

    # every implementation encodes the same inputs
    enc = {}
    for name in present:
        enc[name] = run_harness(LANGS[name], "encode", inputs)
        marker = sum(1 for e in enc[name] if e.startswith("="))
        print(f"  {name:11s} encoded {len(inputs)} inputs ({marker} compressed)")

    # every decoder decodes every encoder's output in one batch
    print(f"\n{len(present)}x{len(present)} = {len(present)**2} encoder/decoder pairs:")
    fail = 0
    for d in present:
        big = [item for e in present for item in enc[e]]
        dec = run_harness(LANGS[d], "decode", big)
        d_ok = True
        for idx, e in enumerate(present):
            chunk = dec[idx * len(inputs):(idx + 1) * len(inputs)]
            bad = sum(1 for got, want in zip(chunk, inputs) if got != want)
            if bad:
                fail = 1
                d_ok = False
                print(f"  enc={e:11s} dec={d:11s} {bad} MISMATCHES")
        if d_ok:
            print(f"  decoder {d:11s} agreed with all {len(present)} encoders")

    # all decoders return identical (accepted) error codes
    err_cases = load_error_cases()
    err_inputs = [c[0] for c in err_cases]
    accepted = [c[1] for c in err_cases]
    codes = {d: run_harness(LANGS[d], "decode", err_inputs) for d in present}
    err_fail = 0
    for i, acc in enumerate(accepted):
        for d in present:
            got = codes[d][i]
            if not got.startswith("!") or got[1:] not in acc:
                err_fail += 1
                print(f"  error mismatch: {err_inputs[i]!r} dec={d} got {got} want !{acc}")
    print(f"\nerror-code agreement over {len(err_cases)} cases: "
          f"{'OK' if err_fail == 0 else f'{err_fail} MISMATCHES'}")

    ok = fail == 0 and err_fail == 0
    print(f"\n{'PASS' if ok else 'FAIL'}: {len(present)}/{len(present)} decoders agree with "
          f"{len(present)} encoders over {len(inputs)} inputs "
          f"({len(present)**2} pairs).")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
