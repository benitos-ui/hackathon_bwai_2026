"""Reusable WhatsApp-like bubbles, shared by the Chat and Review pages."""
import html

import streamlit as st

_CSS = """
<style>
.bx-chat { display:flex; flex-direction:column; gap:6px; padding:4px 2px; }
.bx-row { display:flex; }
.bx-row.right { justify-content:flex-end; }
.bx-row.center { justify-content:center; }
.bx-bubble { max-width:78%; padding:7px 11px; border-radius:12px;
  font-size:0.92rem; line-height:1.35; border:1px solid rgba(128,128,128,0.25); }
.bx-client { background:rgba(128,128,128,0.12); border-top-left-radius:2px; }
.bx-vendeuse { background:rgba(37,211,102,0.18); border-top-right-radius:2px; }
.bx-livreur { background:rgba(80,140,255,0.16); border-top-left-radius:2px; }
.bx-system { background:transparent; border:none; font-size:0.78rem;
  opacity:0.65; font-style:italic; }
.bx-meta { font-size:0.72rem; opacity:0.65; margin-bottom:2px; }
.bx-bubble mark { background:rgba(255,200,0,0.55); color:inherit;
  padding:0 2px; border-radius:3px; }
.bx-bubble.bx-hl { outline:2px solid rgba(255,200,0,0.85); outline-offset:1px; }
</style>
"""


def _kind(author):
    """Map a raw author name to a bubble style."""
    a = (author or "").strip().lower()
    if not a:
        return "system"
    if a.startswith("vendeuse"):
        return "vendeuse"
    if a.startswith("livreur"):
        return "livreur"
    return "client"


def _body(text, start=None, end=None):
    """Escape the text and wrap the [start:end] span in <mark> if valid."""
    text = text or ""
    if start is not None and end is not None and 0 <= start < end <= len(text):
        out = (
            html.escape(text[:start])
            + "<mark>" + html.escape(text[start:end]) + "</mark>"
            + html.escape(text[end:])
        )
    else:
        out = html.escape(text)
    return out.replace("\n", "<br>")


def render_chat(messages, highlight=None, height=None):
    """
    messages: list of dicts with id, time, author, text.
    highlight: None or dict {message_id, start, end} (offsets in that message text).
    height: optional pixel height, makes the thread scrollable.
    """
    parts = [_CSS, '<div class="bx-chat">']
    for m in messages:
        kind = _kind(m.get("author"))
        side = {"vendeuse": "right", "system": "center"}.get(kind, "left")
        start = end = None
        whole = False
        if highlight and highlight.get("message_id") == m.get("id"):
            start, end = highlight.get("start"), highlight.get("end")
            whole = start is None or end is None
        extra = " bx-hl" if whole else ""
        meta = ""
        if kind != "system":
            meta = (
                '<div class="bx-meta">'
                + html.escape(str(m.get("author", "")))
                + " &middot; " + html.escape(str(m.get("time", "")))
                + "</div>"
            )
        parts.append(
            f'<div class="bx-row {side}"><div class="bx-bubble bx-{kind}{extra}">'
            f'{meta}{_body(m.get("text"), start, end)}</div></div>'
        )
    parts.append("</div>")
    html_str = "".join(parts)  # single line, avoids markdown code-block parsing

    if height:
        with st.container(height=height):
            st.markdown(html_str, unsafe_allow_html=True)
    else:
        st.markdown(html_str, unsafe_allow_html=True)