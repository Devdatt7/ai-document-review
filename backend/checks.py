"""Deterministic regex checks: sensitive data (PII) and risky commitment wording.

These are HEURISTICS for the MVP. A match means "a human should look", not "this is
legally sensitive / legally risky". No LLM is used here, and raw PII values never leave
this file: find_pii() returns only masked text and positions.
"""

import re
from dataclasses import dataclass

from models import Claim, ConsequenceLevel, Evidence

C = ConsequenceLevel


def check_claim(claim: Claim, evidence: list[Evidence]) -> list[str]:
    raise NotImplementedError


# ---------- Sensitive data ----------

@dataclass
class SensitiveMatch:
    category: str  # e.g. "PAN"
    masked: str    # safe to show, same length as the original
    start: int     # position in the text (used for masking; not shown to the reviewer)
    end: int
    consequence: ConsequenceLevel
    label: str     # human name used in reasons


# (category, label, regex, capture group, consequence).
# ORDER MATTERS: more specific patterns come first, and a text span is only used once.
# Policy: identifiers that can enable identity/financial fraud are CRITICAL; the rest are HIGH.
PII_PATTERNS = [
    ("EMAIL", "email address", r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}", 0, C.HIGH),
    ("GSTIN", "GSTIN-like identifier", r"\b\d{2}[A-Z]{5}\d{4}[A-Z][1-9A-Z]Z[0-9A-Z]\b", 0, C.HIGH),
    ("PAN", "PAN (Indian tax ID)", r"\b[A-Z]{5}\d{4}[A-Z]\b", 0, C.CRITICAL),
    ("IFSC", "IFSC bank code", r"\b[A-Z]{4}0[A-Z0-9]{6}\b", 0, C.HIGH),
    # A bare 9-18 digit number is too common, so a bank account needs the word "account" / "a/c" before it.
    ("BANK_ACCOUNT", "bank account number",
     r"(?i:\b(?:account(?:\s*(?:no|number|num))?|a/c|acct)\b)[\s.:#-]*(\d{9,18})(?!\d)", 1, C.CRITICAL),
    ("AADHAAR", "Aadhaar-like number", r"(?<!\d)[2-9]\d{3}[ -]?\d{4}[ -]?\d{4}(?!\d)", 0, C.CRITICAL),
    ("PHONE", "phone number", r"(?<![\d@])(?:\+91[ -]?|0)?[6-9]\d{9}(?!\d)", 0, C.HIGH),
]


def mask_value(category: str, value: str) -> str:
    """Hide most of a value but keep its length. PAN 'ABCDE1234F' -> 'AB*****34F'."""
    if category == "EMAIL":
        name, domain = value.split("@", 1)
        return name[:1] + "*" * (len(name) - 1) + "@" + domain
    if category in ("PHONE", "AADHAAR", "BANK_ACCOUNT"):
        # Numbers: keep only the last 4 digits (separators stay as they are).
        digits_seen, out = 0, []
        total = sum(ch.isdigit() for ch in value)
        for ch in value:
            if ch.isdigit():
                digits_seen += 1
                out.append(ch if digits_seen > total - 4 else "*")
            else:
                out.append(ch)
        return "".join(out)
    return value[:2] + "*" * (len(value) - 5) + value[-3:]  # PAN, IFSC, GSTIN


def find_pii(text: str) -> list[SensitiveMatch]:
    """Find sensitive-looking values. Returns masked values only, in text order."""
    found: list[SensitiveMatch] = []
    for category, label, pattern, group, consequence in PII_PATTERNS:
        for m in re.finditer(pattern, text):
            start, end = m.span(group)
            if any(start < f.end and f.start < end for f in found):
                continue  # already claimed by a more specific pattern
            found.append(SensitiveMatch(category, mask_value(category, m.group(group)),
                                        start, end, consequence, label))
    return sorted(found, key=lambda f: f.start)


def mask_text(text: str) -> str:
    """Return `text` with every sensitive value masked. Used on anything sent back to the reviewer."""
    for match in sorted(find_pii(text), key=lambda m: m.start, reverse=True):
        text = text[:match.start] + match.masked + text[match.end:]  # masks keep the same length
    return text


def masked_line(text: str, match: SensitiveMatch, all_matches: list[SensitiveMatch]) -> str:
    """The line containing `match`, with every sensitive value on it masked (for the reviewer)."""
    line_start = text.rfind("\n", 0, match.start) + 1
    line_end = text.find("\n", match.end)
    line_end = len(text) if line_end == -1 else line_end
    line = text[line_start:line_end]
    # Replace from the end so earlier positions stay valid. Masks keep the same length.
    for other in sorted(all_matches, key=lambda f: f.start, reverse=True):
        if other.start >= line_start and other.end <= line_end:
            a, b = other.start - line_start, other.end - line_start
            line = line[:a] + other.masked + line[b:]
    return line.strip()[:200]


# ---------- Risky commitments ----------

@dataclass
class RiskyPhrase:
    phrase: str  # the words found in the text
    reason: str
    consequence: ConsequenceLevel


# (regex, reason, consequence). Policy: absolute guarantees and legal/liability wording are
# CRITICAL; money-related promises are HIGH. Negation ("not a guarantee") is NOT understood:
# every match is only a REVIEW FLAG.
RISKY_PATTERNS = [
    (r"\b100\s?%\s*(?:uptime|availability)\b", "Claim makes an explicit service guarantee.", C.CRITICAL),
    (r"\bzero downtime\b", "Claim makes an explicit service guarantee.", C.CRITICAL),
    (r"\bnever fails?\b", "Claim promises the service will never fail.", C.CRITICAL),
    (r"\bguarantee(?:s|d)?\b", "Claim makes an explicit guarantee.", C.CRITICAL),
    (r"\bindemnif\w*", "Claim creates a legal indemnity obligation.", C.CRITICAL),
    (r"\bunlimited liability\b", "Claim accepts unlimited liability.", C.CRITICAL),
    (r"\bliable for all (?:losses|damages)\b", "Claim accepts liability for all losses.", C.CRITICAL),
    (r"\blegally binding\b", "Claim creates a legally binding obligation.", C.CRITICAL),
    (r"\birrevocabl[ey]\b", "Claim makes an irrevocable commitment.", C.CRITICAL),
    (r"\bpenalt(?:y|ies)\b", "Claim mentions financial penalties.", C.HIGH),
    (r"\bcompensation\b", "Claim promises compensation.", C.HIGH),
    (r"\bno exceptions?\b", "Claim allows no exceptions.", C.HIGH),
    (r"\bfull (?:reimbursement|refund)\b", "Claim promises full repayment.", C.HIGH),
]

_LEVEL_ORDER = [C.LOW, C.MEDIUM, C.HIGH, C.CRITICAL]


def find_risky_phrases(text: str) -> list[RiskyPhrase]:
    """Find risky promise wording. Strongest first, then in text order."""
    hits = []
    for pattern, reason, consequence in RISKY_PATTERNS:
        for m in re.finditer(pattern, text, flags=re.I):
            hits.append((m.start(), RiskyPhrase(m.group(0), reason, consequence)))
    hits.sort(key=lambda h: (-_LEVEL_ORDER.index(h[1].consequence), h[0]))
    return [phrase for _, phrase in hits]
