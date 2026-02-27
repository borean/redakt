"""Core redaction logic: find PII spans in text, render as highlighted/redacted HTML."""

import html as _html
from dataclasses import dataclass

from qwenkk.core.entities import PIIEntity

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


def find_entity_spans(text: str, entities: list[PIIEntity]) -> list[TextSpan]:
    """Find all occurrences of *entities* in *text*.

    Returns non-overlapping spans sorted by start position.
    Longer matches take priority (greedy).
    """
    sorted_entities = sorted(entities, key=lambda e: len(e.original), reverse=True)
    used: set[int] = set()
    spans: list[TextSpan] = []

    for entity in sorted_entities:
        start = 0
        while True:
            idx = text.find(entity.original, start)
            if idx == -1:
                break
            end_pos = idx + len(entity.original)
            # Check no overlap with already-claimed characters
            if not any(i in used for i in range(idx, end_pos)):
                spans.append(TextSpan(idx, end_pos, entity))
                used.update(range(idx, end_pos))
            start = idx + 1

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
            f"padding: 1px 5px; border-radius: 2px; font-weight: 600;\" "
            f'title="{_html.escape(cat_label)}: {_html.escape(span.entity.placeholder)}">'
            f"{_html.escape(span.entity.original)}</span>"
        )
        last = span.end
    parts.append(_html.escape(text[last:]))
    body = "".join(parts)
    return (
        '<pre style="white-space: pre-wrap; word-wrap: break-word; '
        "font-family: 'SF Mono', 'Fira Code', 'JetBrains Mono', Menlo, Consolas, monospace; "
        'margin: 0; line-height: 1.8; color: #d4d4d4; font-size: 12px;">'
        + body
        + "</pre>"
    )


def render_redacted_html(text: str, spans: list[TextSpan]) -> str:
    """Render text with solid bars replacing each PII entity (UI preview)."""
    parts: list[str] = []
    last = 0
    for span in spans:
        parts.append(_html.escape(text[last : span.start]))
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
        'margin: 0; line-height: 1.8; color: #d4d4d4; font-size: 12px;">'
        + body
        + "</pre>"
    )


def render_redacted_plain(text: str, spans: list[TextSpan]) -> str:
    """Plain-text redaction using unicode full-block characters."""
    parts: list[str] = []
    last = 0
    for span in spans:
        parts.append(text[last : span.start])
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
