#!/usr/bin/env python3
"""Run the full detection + auto-resolution pipeline against saved fixtures.

Reproduces findings 6 and 7 from KOKORO_PRONUNCIATIONS.md.

For each saved fixture (or hypothetical narration), this script:
  1. Tokenizes narration via pipeline.g2p()
  2. Filters tokens via inflection-aware base-form check against
     both misaki's lexicon and CMU dict
  3. Applies the all-caps acronym detection bypass
  4. For each remaining candidate, attempts compound split + IPA
     assembly via cmudict + ARPAbet→IPA mapping
  5. Reports (resolved, unresolved) candidates per fixture

Auto-resolution requires:
  - At least 2 split parts (single-part = real-word reinterpretation, rejected)
  - Each part ≥4 chars (rejects nonsense splits like Kokoro → koko + ro)
  - All parts in CMU dict

Run:
    python scripts/explore/pronunciations_detect_resolve.py

Requires: kokoro >= 0.9.4, cmudict installed (pip install cmudict).

This script is the prototype reference for what will become
src/instantdemo/pronunciations.py. The algorithm and decision
points here drive the implementation.
"""
from __future__ import annotations

import json
import re
import warnings
from pathlib import Path

warnings.filterwarnings("ignore")
import cmudict  # noqa: E402
from kokoro import KPipeline  # noqa: E402


CMU = cmudict.dict()
CMU_KEYS = set(CMU.keys())

FIXTURES = Path(__file__).resolve().parents[2] / "fixtures"
DEFAULT_SCENARIOS = [
    FIXTURES / "dress-rehearsal-claude-code-analytics-scroll-2026-05-14",
    FIXTURES / "evernote-non-technical-fixed-2026-05-14",
]

# Hypothetical "hard cases" narration — exercises detection of
# tokens that didn't happen to appear in real fixtures.
HARD_CASES_NARRATION = (
    "Kokoro powers the speech engine. Stagehand drives Playwright. "
    "ENEX files come from Evernote. API calls hit /api/notes. "
    "The instantdemo pipeline uses JSON for config. Misaki does G2P."
)


# --- Detection ---


def _clean(token_text: str) -> str:
    """Strip surrounding punctuation, lowercase."""
    return re.sub(r"[^\w\-']+", "", token_text).lower()


def _candidate_bases(word: str) -> list[str]:
    """Plausible base forms — misaki's lexicon often stores only roots."""
    bases = [word]
    for suf in ("'s", "'re", "'ve", "'ll", "'d", "'m", "n't"):
        if word.endswith(suf):
            bases.append(word[: -len(suf)])
    if word.endswith("es"):
        bases.append(word[:-2])
        bases.append(word[:-1])
    elif word.endswith("s"):
        bases.append(word[:-1])
    if word.endswith("ed"):
        bases.append(word[:-2])
        bases.append(word[:-1])
    if word.endswith("ing"):
        bases.append(word[:-3])
        bases.append(word[:-3] + "e")
    return bases


def _is_known(word: str, golds: dict) -> bool:
    return any(b in golds or b in CMU_KEYS for b in _candidate_bases(word))


def is_real_miss(token_text: str, golds: dict) -> bool:
    """A token needs investigation when Kokoro's default is likely wrong."""
    # All-caps acronyms always get flagged: Kokoro spells them out
    # letter-by-letter regardless of dictionary presence.
    if token_text.isupper() and 2 <= len(token_text) <= 6 and token_text.isalpha():
        return True

    word = _clean(token_text)
    if not word:
        return False
    if not word.replace("-", "").replace("'", "").isalpha():
        return False

    if _is_known(word, golds):
        return False

    # Hyphenated compounds where all parts are known → fallback handles it.
    if "-" in word:
        parts = [p for p in word.split("-") if p]
        if parts and all(_is_known(p, golds) for p in parts):
            return False

    return True


# --- Resolution ---


ARPA_IPA: dict[str, str] = {
    "AA": "ɑ", "AE": "æ", "AO": "ɔ", "AW": "aʊ", "AY": "aɪ",
    "B": "b", "CH": "tʃ", "D": "d", "DH": "ð",
    "EH": "ɛ", "EY": "eɪ", "F": "f", "G": "ɡ", "HH": "h",
    "IH": "ɪ", "IY": "i", "JH": "dʒ",
    "K": "k", "L": "l", "M": "m", "N": "n", "NG": "ŋ",
    "OW": "oʊ", "OY": "ɔɪ", "P": "p", "R": "ɹ",
    "S": "s", "SH": "ʃ", "T": "t", "TH": "θ",
    "UH": "ʊ", "UW": "u", "V": "v", "W": "w", "Y": "j",
    "Z": "z", "ZH": "ʒ",
}
ARPA_IPA_STRESS_CONDITIONAL: dict[str, dict[str, str]] = {
    "AH": {"0": "ə", "1": "ʌ", "2": "ʌ"},
    "ER": {"0": "ɚ", "1": "ɝ", "2": "ɝ"},
}


def _arpa_phoneme_to_ipa(arpa: str) -> tuple[str, str]:
    """Returns (ipa_glyph, stress_digit_or_empty)."""
    if arpa and arpa[-1].isdigit():
        stress = arpa[-1]
        base = arpa[:-1]
    else:
        stress = ""
        base = arpa
    if base in ARPA_IPA_STRESS_CONDITIONAL:
        return ARPA_IPA_STRESS_CONDITIONAL[base][stress or "0"], stress
    return ARPA_IPA.get(base, base), stress


def _arpa_list_to_ipa(phonemes: list[str]) -> str:
    """Assemble IPA from a list of ARPAbet phonemes.

    Stress marks placed immediately before the stressed vowel,
    matching the kokoro-say convention (rather than the strictly
    IPA convention of placing them at the syllable boundary).
    """
    out: list[str] = []
    for arpa in phonemes:
        ipa, stress = _arpa_phoneme_to_ipa(arpa)
        if stress == "1":
            out.append("ˈ" + ipa)
        elif stress == "2":
            out.append("ˌ" + ipa)
        else:
            out.append(ipa)
    return "".join(out)


def split_compound(word: str, min_part_len: int = 4) -> list[str] | None:
    """Longest-prefix recursive split against CMU dict.

    Returns a list of subwords (each in CMU dict) or None if no
    valid split exists. Single-part results returned as a one-item
    list — caller decides whether to accept.
    """
    word = word.lower()
    if not word:
        return []
    if word in CMU_KEYS:
        return [word]
    for n in range(len(word), min_part_len - 1, -1):
        prefix = word[:n]
        if prefix in CMU_KEYS:
            rest = word[n:]
            if not rest:
                return [prefix]
            if len(rest) >= min_part_len:
                sub = split_compound(rest, min_part_len)
                if sub is not None:
                    return [prefix] + sub
    return None


def try_resolve(word: str) -> tuple[str | None, list[str] | None]:
    """Attempt high-confidence auto-resolution.

    Returns (ipa_string, parts) on success, (None, None) on failure.
    Requires ≥2 parts each ≥4 chars (rejects acronym reinterpretations
    and nonsense splits).
    """
    parts = split_compound(word.lower(), min_part_len=4)
    if parts is None:
        return None, None
    if len(parts) < 2:
        # Single-part hit on CMU dict — likely a real-word reinterpretation
        # of an acronym. Reject.
        return None, parts
    ipa_segments = [_arpa_list_to_ipa(CMU[p][0]) for p in parts]
    return " ".join(ipa_segments), parts


# --- Main ---


def analyze(label: str, text: str, pipeline, golds: dict) -> None:
    print(f"=== {label} ===")
    _, tokens = pipeline.g2p(text)
    seen: set[str] = set()
    n_resolved = 0
    n_unresolved = 0
    for tok in tokens:
        word = _clean(tok.text)
        if not word or word in seen:
            continue
        if not is_real_miss(tok.text, golds):
            continue
        seen.add(word)
        ipa, parts = try_resolve(word)
        if ipa:
            n_resolved += 1
            status = f"RESOLVED → {parts}  IPA={ipa!r}"
        else:
            n_unresolved += 1
            if parts:
                status = f"UNRESOLVED (single-part split {parts} — likely acronym)"
            else:
                status = "UNRESOLVED (no compound split available)"
        print(f"  {tok.text!r:18s} default={tok.phonemes!r:30s}")
        print(f"      {status}")
    if not seen:
        print("  (no candidates)")
    print(f"  Summary: {n_resolved} resolved, {n_unresolved} unresolved")
    print()


def main() -> None:
    pipeline = KPipeline(lang_code="a")
    golds = pipeline.g2p.lexicon.golds
    print(f"Misaki lexicon: {len(golds):,}; CMU dict: {len(CMU_KEYS):,}\n")

    # Saved fixtures
    for fixture_dir in DEFAULT_SCENARIOS:
        script_path = fixture_dir / "demo-script.json"
        if not script_path.exists():
            print(f"!! missing {script_path}\n")
            continue
        data = json.loads(script_path.read_text())
        segments = data.get("segments") or []
        text = " ".join((s.get("narration") or "").strip() for s in segments)
        analyze(f"{fixture_dir.name} ({len(segments)} segments)", text, pipeline, golds)

    # Hypothetical hard cases
    analyze("Hypothetical hard-cases narration", HARD_CASES_NARRATION, pipeline, golds)


if __name__ == "__main__":
    main()
