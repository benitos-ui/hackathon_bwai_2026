"""Reusable WhatsApp-like bubbles, shared by the Chat and Review pages."""
import html

import streamlit as st

_CSS = """
<style>
.bx-shell { overflow:hidden; border:1px solid #d1d7db; border-radius:12px;
  background:#efeae2; color:#111b21; }
.bx-header { display:flex; align-items:center; gap:11px; padding:11px 16px;
  background:#075e54; color:#fff; }
.bx-avatar { display:flex; align-items:center; justify-content:center;
  width:38px; height:38px; flex:none; border-radius:50%;
  background:#d9fdd3; color:#075e54; font-weight:700; font-size:1rem; }
.bx-header-title { font-weight:600; font-size:0.98rem; }
.bx-header-subtitle { color:rgba(255,255,255,0.78); font-size:0.76rem; margin-top:1px; }
.bx-chat { display:flex; flex-direction:column; gap:8px; padding:16px 18px;
  min-height:100px;
  background-color:#efeae2;
  background-image:radial-gradient(rgba(120,105,86,0.09) 0.7px, transparent 0.7px);
  background-size:12px 12px; }
.bx-row { display:flex; }
.bx-row.right { justify-content:flex-end; }
.bx-row.center { justify-content:center; }
.bx-bubble { max-width:min(78%, 620px); padding:7px 10px 5px;
  border-radius:9px; font-size:0.92rem; line-height:1.38;
  border:1px solid rgba(17,27,33,0.05);
  box-shadow:0 1px 1px rgba(17,27,33,0.12); overflow-wrap:anywhere; }
.bx-client, .bx-livreur { background:#fff; border-top-left-radius:2px; }
.bx-vendeuse { background:#d9fdd3; border-top-right-radius:2px; }
.bx-system { background:transparent; border:none; font-size:0.78rem;
  color:#54656f; font-style:italic; box-shadow:none; }
.bx-author { color:#008069; font-size:0.76rem; font-weight:600; margin-bottom:2px; }
.bx-meta { display:flex; justify-content:flex-end; gap:5px; align-items:center;
  color:#667781; font-size:0.68rem; line-height:1; margin-top:4px; }
.bx-ticks { color:#53bdeb; font-size:0.76rem; font-weight:700; }
.bx-bubble mark { background:rgba(255,200,0,0.55); color:#111b21;
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


def render_chat(
    messages,
    highlight=None,
    height=None,
    *,
    title=None,
    subtitle="Conversation simulée",
):
    """
    messages: list of dicts with id, time, author, text.
    highlight: None or dict {message_id, start, end} (offsets in that message text).
    height: optional pixel height, makes the thread scrollable.
    """
    parts = [_CSS, '<div class="bx-shell">']
    if title:
        initial = html.escape(title[:1].upper() or "C")
        parts.append(
            '<div class="bx-header">'
            f'<div class="bx-avatar">{initial}</div>'
            '<div><div class="bx-header-title">' + html.escape(title) + '</div>'
            '<div class="bx-header-subtitle">' + html.escape(subtitle) + '</div></div>'
            '</div>'
        )
    parts.append('<div class="bx-chat">')
    for m in messages:
        kind = _kind(m.get("author"))
        side = {"vendeuse": "right", "system": "center"}.get(kind, "left")
        start = end = None
        whole = False
        if highlight and highlight.get("message_id") == m.get("id"):
            start, end = highlight.get("start"), highlight.get("end")
            whole = start is None or end is None
        extra = " bx-hl" if whole else ""
        author = ""
        if kind != "system":
            author = '<div class="bx-author">' + html.escape(str(m.get("author", ""))) + '</div>'
        time_label = html.escape(str(m.get("time", "")))
        ticks = '<span class="bx-ticks">✓✓</span>' if kind == "vendeuse" else ""
        parts.append(
            f'<div class="bx-row {side}"><div class="bx-bubble bx-{kind}{extra}">'
            f'{author}{_body(m.get("text"), start, end)}'
            f'<div class="bx-meta">{time_label}{ticks}</div></div></div>'
        )
    parts.append("</div></div>")
    html_str = "".join(parts)  # single line, avoids markdown code-block parsing

    if height:
        with st.container(height=height):
            st.markdown(html_str, unsafe_allow_html=True)
    else:
        st.markdown(html_str, unsafe_allow_html=True)