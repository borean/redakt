"""Markdown-to-themed-HTML renderer for QTextBrowser display.

Converts raw Markdown text into a fully styled HTML document that matches
the Factory AI neutral dark theme used throughout the application.
"""

from __future__ import annotations

import markdown


# ---------------------------------------------------------------------------
# Theme palette (neutral dark — matching Factory AI)
# ---------------------------------------------------------------------------
_BG_DARKEST = "#111111"
_BG_DARK = "#1a1a1a"
_BG_MID = "#252525"
_BG_LIGHT = "#303030"
_TEXT = "#d4d4d4"
_TEXT_DIM = "#808080"
_ACCENT = "#e78a4e"

_FONT_STACK = "'SF Mono', 'Fira Code', 'JetBrains Mono', Menlo, Consolas, monospace"

# ---------------------------------------------------------------------------
# CSS stylesheet embedded in every rendered document
# ---------------------------------------------------------------------------
_STYLE = f"""\
<style>
body {{
    font-family: {_FONT_STACK};
    font-size: 13px;
    color: {_TEXT};
    background: transparent;
    margin: 0;
    padding: 8px 12px;
    line-height: 1.6;
}}

h1, h2, h3, h4 {{
    color: {_TEXT};
    font-weight: 700;
    margin-top: 1.2em;
    margin-bottom: 0.5em;
    letter-spacing: 0.02em;
}}
h1 {{
    font-size: 1.5em;
    border-bottom: 1px solid {_BG_LIGHT};
    padding-bottom: 0.3em;
}}
h2 {{
    font-size: 1.3em;
    border-bottom: 1px solid {_BG_LIGHT};
    padding-bottom: 0.2em;
}}
h3 {{ font-size: 1.1em; }}
h4 {{ font-size: 1.0em; }}

p {{
    margin: 0.5em 0;
    line-height: 1.6;
}}

strong, b {{
    color: {_TEXT};
    font-weight: 700;
}}

em, i {{
    color: {_TEXT_DIM};
    font-style: italic;
}}

a {{
    color: {_ACCENT};
    text-decoration: none;
}}
a:hover {{
    text-decoration: underline;
}}

code {{
    background: {_BG_LIGHT};
    color: {_TEXT};
    padding: 2px 5px;
    border-radius: 3px;
    font-family: {_FONT_STACK};
    font-size: 0.92em;
}}

pre {{
    background: {_BG_MID};
    border: 1px solid {_BG_LIGHT};
    border-left: 3px solid {_BG_LIGHT};
    border-radius: 4px;
    padding: 10px 14px;
    margin: 0.7em 0;
    overflow-x: auto;
    line-height: 1.5;
}}
pre code {{
    background: transparent;
    color: {_TEXT};
    padding: 0;
    border-radius: 0;
    font-size: 0.9em;
}}

blockquote {{
    border-left: 3px solid {_BG_LIGHT};
    margin: 0.7em 0;
    padding: 5px 14px;
    color: {_TEXT_DIM};
    background: {_BG_DARKEST};
    border-radius: 0 3px 3px 0;
}}
blockquote p {{
    margin: 0.3em 0;
}}

ul {{
    margin: 0.5em 0;
    padding-left: 1.4em;
}}
ul li {{
    margin: 0.2em 0;
    line-height: 1.6;
    color: {_TEXT};
}}

ol {{
    margin: 0.5em 0;
    padding-left: 1.4em;
}}
ol li {{
    margin: 0.2em 0;
    line-height: 1.6;
}}

hr {{
    border: none;
    border-top: 1px solid {_BG_LIGHT};
    margin: 1em 0;
}}

table {{
    width: 100%;
    border-collapse: collapse;
    margin: 0.7em 0;
    font-size: 0.92em;
}}
th {{
    color: {_TEXT};
    font-weight: 700;
    text-align: left;
    padding: 6px 10px;
    border-bottom: 1px solid {_BG_LIGHT};
}}
td {{
    padding: 5px 10px;
    border-bottom: 1px solid {_BG_MID};
    color: {_TEXT};
}}
</style>
"""

# ---------------------------------------------------------------------------
# Markdown extensions
# ---------------------------------------------------------------------------
_MD_EXTENSIONS: list[str] = [
    "fenced_code",
    "tables",
    "nl2br",
    "sane_lists",
    "smarty",
]


def render_markdown(text: str) -> str:
    """Convert raw Markdown *text* into themed HTML suitable for QTextBrowser."""
    md = markdown.Markdown(
        extensions=_MD_EXTENSIONS,
        output_format="html",
    )
    body_html = md.convert(text)

    return (
        "<!DOCTYPE html>"
        "<html><head><meta charset='utf-8'>"
        f"{_STYLE}"
        "</head><body>"
        f"{body_html}"
        "</body></html>"
    )
