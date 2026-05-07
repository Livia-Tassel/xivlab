"""URL-slug helper.

Lower-cases, replaces any run of non-(ASCII alphanumeric or BMP CJK
ideograph) chars with a single ``-``, trims trailing/leading dashes,
caps at ``max_len``. CJK is preserved because the prompt hub is
bilingual — Chinese titles like "论文写作" should produce slugs that
read in both URL and breadcrumb UI.

Empty input or all-stripped input returns ``"prompt"`` rather than
"" so callers don't have to special-case it.
"""

import re

# Match runs of *unwanted* chars: anything that's NOT ASCII alphanumeric
# AND NOT a CJK Unified Ideograph (U+4E00..U+9FFF, the BMP block).
_NON_SLUG = re.compile(r"[^a-z0-9一-鿿]+")
_DASHES = re.compile(r"-+")


def slugify(text: str, max_len: int = 80) -> str:
    s = _NON_SLUG.sub("-", text.lower().strip())
    s = _DASHES.sub("-", s).strip("-")
    return s[:max_len] or "prompt"
