# test_brand.py Spec

Source: `src/instantdemo/brand.py` + `server/routes/brand.py` (M6)
Test: `tests/test_brand.py`

## Methods not tested (and why)

| Method | Reason |
|---|---|
| `_logo_init_script` | A string template around base64; the live logo-record gate verifies the burned-in result visually |

## brand config

| ID | Scenario | Assertion | Risk if broken |
|----|----------|-----------|----------------|
| BR1 | No brand.json | load → None; load_or_default → all off (no logo, outro disabled) | Old projects suddenly grow watermarks/outros |
| BR2 | save/load round trip | Fields survive | Settings silently lost between sessions |
| BR3 | resolve_logo with a dangling path | None (degrades to no watermark) | Render crashes on a deleted logo file |

## routes

| ID | Scenario | Assertion | Risk if broken |
|----|----------|-----------|----------------|
| BR4 | POST logo: valid PNG | 200; file at .instantdemo/logo.png; state logo_exists true | Upload appears to work but the recorder finds nothing |
| BR5 | POST logo: wrong type / oversized / empty | 422 each, plain message | Garbage burned into every future film |
| BR6 | PUT outro settings | Persisted to brand.json; duration clamped by validation (2–10s) | An hour-long outro card |
| BR7 | DELETE logo | File gone; config logo None; state logo_exists false | "Remove" leaves the watermark in the next record |
