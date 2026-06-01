#!/usr/bin/env python3
"""Reproduce findings 1-5 from KOKORO_PRONUNCIATIONS.md.

Probes Kokoro's lexicon mechanism to verify:
  1. Lexicon shape (size, key conventions, multi-word presence)
  2. Override precedence (do our entries beat CMU dict / fallbacks?)
  3. Multi-word keys with spaces (do they fire?)
  4. Case sensitivity + the all-caps mangling behavior
  5. The g2p() testing primitive

Run:
    python scripts/explore/kokoro_lexicon_research.py

Requires: kokoro >= 0.9.4 installed.

This script is exploratory / one-shot. The findings it produces
are captured in KOKORO_PRONUNCIATIONS.md "Empirical findings"
section. Keep this around so the findings stay reproducible.
"""
from __future__ import annotations

import warnings

warnings.filterwarnings("ignore")
from kokoro import KPipeline  # noqa: E402


def main() -> None:
    pipeline = KPipeline(lang_code="a")
    lex = pipeline.g2p.lexicon
    golds = lex.golds

    print("=== 1. Lexicon shape ===")
    print(f"type(golds): {type(golds).__name__}")
    print(f"len(golds): {len(golds):,}")
    sample_keys = list(golds.keys())[:10]
    print(f"sample keys: {sample_keys}")
    multi_word_in_default = [k for k in golds if " " in k][:5]
    print(f"keys with spaces (first 5): {multi_word_in_default}")
    print()

    print("=== 2. Single-word override precedence ===")
    # Use a distinctive marker no real G2P would produce.
    test_word = "api"
    prior = golds.get(test_word)
    print(f"golds[{test_word!r}] before override: {prior!r}")
    golds[test_word] = "ZZZ_OVERRIDE"
    out_str, _tokens = pipeline.g2p(f"the {test_word} works")
    print(f"g2p('the {test_word} works') -> {out_str!r}")
    if prior is None:
        del golds[test_word]
    else:
        golds[test_word] = prior
    print()

    print("=== 3. Multi-word key with space ===")
    multi_key = "instant demo"
    golds[multi_key] = "MMM_MULTIWORD"
    out_str, _tokens = pipeline.g2p("this is an instant demo of features")
    print(f"g2p('...instant demo...') -> {out_str!r}")
    del golds[multi_key]
    print()

    print("=== 4. Override survives over CMU dict ===")
    prior_hello = golds.get("hello")
    golds["hello"] = "QQQ_HELLO_OVERRIDE"
    out_str, _tokens = pipeline.g2p("hello world")
    print(f"g2p('hello world') -> {out_str!r}")
    if prior_hello is None:
        del golds["hello"]
    else:
        golds["hello"] = prior_hello
    print()

    print("=== 5. Case sensitivity probe ===")
    golds["instantdemo"] = "ZZZ_LOWERCASE_HIT"
    for text in [
        "instantdemo is great",
        "InstantDemo is great",
        "INSTANTDEMO is great",
    ]:
        _, tokens = pipeline.g2p(text)
        hits = [
            (t.text, t.phonemes) for t in tokens if "instantdemo" in t.text.lower()
        ]
        print(f"text: {text!r}")
        print(f"  hits: {hits}")
    del golds["instantdemo"]
    print()

    print("=== 6. The g2p() test primitive ===")
    out_str, tokens = pipeline.g2p("the quick brown fox")
    print(f"return type: {type(out_str).__name__}, list[{type(tokens[0]).__name__}]")
    print(f"combined: {out_str!r}")
    print(f"per-token: {[(t.text, t.phonemes) for t in tokens]}")


if __name__ == "__main__":
    main()
