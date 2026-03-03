"""Core redaction logic: find PII spans in text, render as highlighted/redacted HTML."""

import html as _html
import re as _re
import unicodedata as _ud
from dataclasses import dataclass

from redakt.core.entities import PIIEntity

# Category → color for UI highlighting (muted neutral dark palette)
CATEGORY_COLORS: dict[str, str] = {
    "name": "#d46b6b",      # muted red
    "date": "#d4884e",      # muted orange
    "id": "#d4a04e",        # muted amber
    "address": "#6bbd6b",   # muted green
    "phone": "#5ba8b5",     # muted teal
    "email": "#7aabdb",     # muted blue
    "institution": "#9b8ec4", # muted purple
    "age": "#c47a8e",       # muted pink
}

CATEGORY_LABELS_TR: dict[str, str] = {
    "name": "Ad/Soyad",
    "date": "Tarih",
    "id": "Kimlik No",
    "address": "Adres",
    "phone": "Telefon",
    "email": "E-posta",
    "institution": "Kurum",
    "age": "Yas",
}


@dataclass
class TextSpan:
    """A region of text that corresponds to a PII entity."""

    start: int
    end: int
    entity: PIIEntity


def _normalize_ws(s: str) -> str:
    """Collapse all whitespace/NBSP runs into single spaces and strip."""
    return _re.sub(r"[\s\u00a0\u200b]+", " ", _ud.normalize("NFC", s)).strip()


def find_entity_spans(text: str, entities: list[PIIEntity]) -> list[TextSpan]:
    """Find all occurrences of *entities* in *text*.

    Returns non-overlapping spans sorted by start position.
    Longer matches take priority (greedy).

    Uses a 3-tier matching strategy:
    1. Exact substring match (fast path)
    2. Normalized match (whitespace/unicode normalization)
    3. Fuzzy match via rapidfuzz (handles OCR errors, minor LLM variations)
    """
    sorted_entities = sorted(entities, key=lambda e: len(e.original), reverse=True)
    used: set[int] = set()
    spans: list[TextSpan] = []

    # Pre-compute normalized text for tier-2 matching
    text_norm = _normalize_ws(text)

    # Build a mapping from normalized-text positions back to original positions.
    # This lets us find the original start/end after matching on normalized text.
    norm_to_orig: list[int] = []
    ni = 0
    for oi, ch in enumerate(text):
        nch = _normalize_ws(text[oi : oi + 1])
        if nch:
            norm_to_orig.append(oi)
            ni += 1
        elif norm_to_orig and _re.match(r"[\s\u00a0\u200b]", ch):
            # Whitespace that was collapsed — don't advance norm index,
            # but if the normalized text has a space at this position, map it
            if ni < len(text_norm) and text_norm[ni] == " ":
                norm_to_orig.append(oi)
                ni += 1
    # Pad to full length
    while len(norm_to_orig) < len(text_norm):
        norm_to_orig.append(len(text) - 1)

    def _try_exact(entity_text: str) -> list[tuple[int, int]]:
        """Tier 1: exact substring match."""
        hits = []
        start = 0
        while True:
            idx = text.find(entity_text, start)
            if idx == -1:
                break
            hits.append((idx, idx + len(entity_text)))
            start = idx + 1
        return hits

    def _try_normalized(entity_text: str) -> list[tuple[int, int]]:
        """Tier 2: whitespace/unicode-normalized match."""
        needle = _normalize_ws(entity_text)
        if not needle or needle == entity_text:
            return []  # Same as exact — already tried
        hits = []
        start = 0
        while True:
            idx = text_norm.find(needle, start)
            if idx == -1:
                break
            # Map back to original text positions
            orig_start = norm_to_orig[idx] if idx < len(norm_to_orig) else 0
            end_norm = idx + len(needle) - 1
            orig_end = (norm_to_orig[end_norm] + 1) if end_norm < len(norm_to_orig) else len(text)
            hits.append((orig_start, orig_end))
            start = idx + 1
        return hits

    def _try_fuzzy(entity_text: str) -> list[tuple[int, int]]:
        """Tier 3: fuzzy substring match using rapidfuzz."""
        try:
            from rapidfuzz.fuzz import partial_ratio
            from rapidfuzz.process import extractBests
        except ImportError:
            return []

        if len(entity_text) < 3:
            return []  # Too short for reliable fuzzy matching

        # Sliding window: check windows of similar size to entity text
        window = len(entity_text)
        best_score = 0
        best_pos = -1
        best_len = window

        for wsize in (window, window - 1, window + 1, window + 2):
            if wsize < 3:
                continue
            for i in range(0, len(text) - wsize + 1, max(1, wsize // 4)):
                candidate = text[i : i + wsize]
                score = partial_ratio(entity_text, candidate)
                if score > best_score:
                    best_score = score
                    best_pos = i
                    best_len = wsize

        if best_score >= 88 and best_pos >= 0:
            return [(best_pos, best_pos + best_len)]
        return []

    for entity in sorted_entities:
        # Try all three tiers in order
        hits = _try_exact(entity.original)
        if not hits:
            hits = _try_normalized(entity.original)
        if not hits:
            hits = _try_fuzzy(entity.original)

        for idx, end_pos in hits:
            if not any(i in used for i in range(idx, end_pos)):
                spans.append(TextSpan(idx, end_pos, entity))
                used.update(range(idx, end_pos))

    spans.sort(key=lambda s: s.start)
    return spans


# ── HTML rendering ───────────────────────────────────────────────────────


def render_highlighted_html(text: str, spans: list[TextSpan]) -> str:
    """Render text with colored highlight badges around each PII entity."""
    parts: list[str] = []
    last = 0
    for i, span in enumerate(spans):
        # Normal text before this span
        parts.append(_html.escape(text[last : span.start]))
        color = CATEGORY_COLORS.get(span.entity.category, "#808080")
        cat_label = CATEGORY_LABELS_TR.get(span.entity.category, span.entity.category)
        parts.append(
            f'<a name="e{i}"></a>'
            f'<span style="background-color: {color}22; color: {color}; '
            f"border: 1px solid {color}66; "
            f"padding: 0 3px; border-radius: 2px; font-weight: 600;\" "
            f'title="{_html.escape(cat_label)}: {_html.escape(span.entity.placeholder)}">'
            f"{_html.escape(span.entity.original)}</span>"
        )
        last = span.end
    parts.append(_html.escape(text[last:]))
    body = "".join(parts)
    return (
        '<pre style="white-space: pre-wrap; word-wrap: break-word; '
        "font-family: 'SF Mono', 'Fira Code', 'JetBrains Mono', Menlo, Consolas, monospace; "
        'margin: 0; line-height: 1.85; color: #d4d4d4; font-size: 12px;">'
        + body
        + "</pre>"
    )


def render_redacted_html(text: str, spans: list[TextSpan], age_mode: bool = False) -> str:
    """Render text with solid bars replacing each PII entity (UI preview).

    When *age_mode* is True, age-converted dates show their placeholder text
    instead of block bars.
    """
    parts: list[str] = []
    last = 0
    for span in spans:
        parts.append(_html.escape(text[last : span.start]))
        ph = span.entity.placeholder
        if age_mode and span.entity.category == "date" and not ph.startswith("["):
            # Age-converted date → show styled age text
            parts.append(
                f'<span style="color: #d4884e; font-weight: 600;">'
                f'{_html.escape(ph)}</span>'
            )
        else:
            bar_len = max(len(span.entity.original), 3)
            # Neutral bar on dark background
            parts.append(
                f'<span style="background-color: #808080; color: #808080; '
                f'border-radius: 1px; letter-spacing: -0.5px;">'
                f'{"█" * bar_len}</span>'
            )
        last = span.end
    parts.append(_html.escape(text[last:]))
    body = "".join(parts)
    return (
        '<pre style="white-space: pre-wrap; word-wrap: break-word; '
        "font-family: 'SF Mono', 'Fira Code', 'JetBrains Mono', Menlo, Consolas, monospace; "
        'margin: 0; line-height: 1.85; color: #d4d4d4; font-size: 12px;">'
        + body
        + "</pre>"
    )


def render_redacted_plain(text: str, spans: list[TextSpan], age_mode: bool = False) -> str:
    """Plain-text redaction using unicode full-block characters.

    When *age_mode* is True, date entities whose placeholder is an age string
    (e.g. "12 yaş 3 ay", "at age 12.3 yrs") are rendered with their
    placeholder text instead of blocks.  All other entities use blocks.
    """
    parts: list[str] = []
    last = 0
    for span in spans:
        parts.append(text[last : span.start])
        ph = span.entity.placeholder
        if age_mode and span.entity.category == "date" and not ph.startswith("["):
            # Age-converted date → show the age placeholder
            parts.append(ph)
        else:
            parts.append("\u2588" * len(span.entity.original))
        last = span.end
    parts.append(text[last:])
    return "".join(parts)


def render_placeholder_text(text: str, spans: list[TextSpan]) -> str:
    """Replace PII with [PLACEHOLDER] tags (e.g. [AD_1], [KIMLIK_1])."""
    parts: list[str] = []
    last = 0
    for span in spans:
        parts.append(text[last : span.start])
        parts.append(span.entity.placeholder)
        last = span.end
    parts.append(text[last:])
    return "".join(parts)
