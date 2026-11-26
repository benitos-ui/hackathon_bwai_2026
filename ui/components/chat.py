"""Clean, legible WhatsApp bubbles with subtle confidence highlights (no noisy inline tags)."""
import html

import streamlit as st

_DOUBLE_TICK_SVG = (
    '<svg width="14" height="9" viewBox="0 0 18 11" fill="none" style="vertical-align:middle;">'
    '<path d="M1 5.8 4.4 9.2 11.4 1.5" stroke="#0284C7" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/>'
    '<path d="M6.2 5.8 9.6 9.2 16.6 1.5" stroke="#0284C7" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/>'
    '</svg>'
)

_CSS = """
<style>
.bx-shell {
  overflow: hidden;
  border: 1px solid #CBD5E1;
  border-radius: 14px;
  background: #EFEAE2;
  color: #0F172A;
  box-shadow: 0 4px 12px rgba(15, 23, 42, 0.05);
}
.bx-header {
  display: flex; align-items: center; justify-content: space-between; gap: 10px;
  padding: 11px 16px;
  background: #075E54;
  color: #FFFFFF;
}
.bx-header-left { display: flex; align-items: center; gap: 10px; }
.bx-avatar {
  display: flex; align-items: center; justify-content: center;
  width: 34px; height: 34px; border-radius: 50%; flex: none;
  background: #DCF8C6; color: #064E3B; font-weight: 700; font-size: 0.92rem;
}
.bx-header-title { font-weight: 700; font-size: 0.94rem; color: #FFFFFF; }
.bx-header-subtitle { color: rgba(255, 255, 255, 0.82); font-size: 0.74rem; }

.bx-chat {
  display: flex; flex-direction: column; gap: 9px;
  padding: 16px 18px; min-height: 110px;
  background-color: #EFEAE2;
  background-image: radial-gradient(rgba(120, 105, 86, 0.07) 0.7px, transparent 0.7px);
  background-size: 14px 14px;
}
.bx-row { display: flex; }
.bx-row.right { justify-content: flex-end; }
.bx-row.center { justify-content: center; }

.bx-bubble {
  max-width: min(82%, 620px);
  padding: 8px 12px 6px;
  border-radius: 10px;
  font-size: 0.9rem; line-height: 1.48;
  color: #0F172A;
  border: 1px solid rgba(15, 23, 42, 0.07);
  box-shadow: 0 1px 2px rgba(15, 23, 42, 0.08);
  overflow-wrap: anywhere;
}
.bx-client   { background: #FFFFFF; border-top-left-radius: 2px; }
.bx-vendeuse { background: #DCF8C6; border-top-right-radius: 2px; }
.bx-livreur  { background: #EFF6FF; border-top-left-radius: 2px; border-color: #BFDBFE; }
.bx-system   {
  background: rgba(255, 255, 255, 0.85);
  border: 1px solid #CBD5E1;
  border-radius: 999px; padding: 3px 12px; font-size: 0.76rem;
  color: #475569; font-style: italic; box-shadow: none;
}

.bx-author-row { display: flex; align-items: center; gap: 6px; margin-bottom: 3px; }
.bx-author { color: #065F46; font-size: 0.76rem; font-weight: 700; }
.bx-author.livreur { color: #1D4ED8; }
.bx-role-badge {
  font-size: 0.64rem; font-weight: 700; text-transform: uppercase;
  padding: 1px 6px; border-radius: 999px;
  background: #DBEAFE; color: #1E3A8A;
}

.bx-meta {
  display: flex; justify-content: flex-end; gap: 5px; align-items: center;
  color: #475569; font-size: 0.68rem; line-height: 1; margin-top: 5px;
  font-family: 'JetBrains Mono', monospace;
}

/* Clean pastel highlights without inline superscript clutter */
.bx-bubble mark {
  padding: 1px 4px;
  border-radius: 4px;
  font-weight: 600;
}
.bx-bubble mark.bx-mark-vert   { background: #BBF7D0; color: #14532D; border-bottom: 2px solid #16A34A; }
.bx-bubble mark.bx-mark-orange { background: #FDE68A; color: #78350F; border-bottom: 2px solid #D97706; }
.bx-bubble mark.bx-mark-rouge  { background: #FECACA; color: #7F1D1D; border-bottom: 2px solid #DC2626; }
.bx-bubble mark.bx-mark-active {
  outline: 2px solid #1D4ED8;
  outline-offset: 1px;
}
.bx-bubble.bx-hl {
  outline: 2px solid #1D4ED8;
  outline-offset: 2px;
}
</style>
"""


def _kind(author, role=None):
    r = (role or "").strip().lower()
    if r in ("vendeuse", "livreur", "client"):
        return r
    a = (author or "").strip().lower()
    if not a:
        return "system"
    if a.startswith("vendeuse") or a.startswith("boutique"):
        return "vendeuse"
    if a.startswith("livreur"):
        return "livreur"
    return "client"


def _render_body(text: str, spans: list[dict]) -> str:
    text = text or ""
    valid = [
        sp for sp in spans
        if sp.get("start") is not None
        and sp.get("end") is not None
        and 0 <= sp["start"] < sp["end"] <= len(text)
    ]
    if not valid:
        return html.escape(text).replace("\n", "<br>")

    valid.sort(key=lambda sp: (sp["start"], 0 if sp.get("active") else 1, -sp["end"]))
    out = []
    pos = 0
    for sp in valid:
        s, e = sp["start"], sp["end"]
        if s < pos:
            continue
        out.append(html.escape(text[pos:s]))
        couleur = sp.get("couleur") if sp.get("couleur") in ("vert", "orange", "rouge") else "orange"
        active_cls = " bx-mark-active" if sp.get("active") else ""
        title_attr = html.escape(str(sp.get("label") or ""))
        out.append(
            f'<mark class="bx-mark-{couleur}{active_cls}" title="{title_attr}">'
            f'{html.escape(text[s:e])}</mark>'
        )
        pos = e
    out.append(html.escape(text[pos:]))
    return "".join(out).replace("\n", "<br>")


def render_chat(
    messages,
    highlight=None,
    height=None,
    *,
    title=None,
    subtitle="WhatsApp local",
    all_highlights=None,
):
    """Render clean WhatsApp bubbles with subtle confidence-colored highlights."""
    by_msg: dict[str, list[dict]] = {}
    for sp in (all_highlights or []):
        mid = sp.get("message_id")
        if mid and sp.get("start") is not None and sp.get("end") is not None:
            is_active = bool(
                highlight
                and highlight.get("message_id") == mid
                and highlight.get("start") == sp.get("start")
                and highlight.get("end") == sp.get("end")
            )
            by_msg.setdefault(mid, []).append({**sp, "active": is_active})

    if highlight and highlight.get("message_id"):
        mid = highlight["message_id"]
        if highlight.get("start") is not None and highlight.get("end") is not None:
            existing = by_msg.setdefault(mid, [])
            if not any(
                x["start"] == highlight["start"] and x["end"] == highlight["end"]
                for x in existing
            ):
                existing.append({
                    "start": highlight["start"],
                    "end": highlight["end"],
                    "couleur": highlight.get("couleur", "orange"),
                    "label": highlight.get("label", ""),
                    "active": True,
                })

    parts = [_CSS, '<div class="bx-shell">']
    if title:
        initial = html.escape(title[:1].upper() or "B")
        parts.append(
            '<div class="bx-header">'
            '<div class="bx-header-left">'
            f'<div class="bx-avatar">{initial}</div>'
            f'<div><div class="bx-header-title">{html.escape(title)}</div>'
            f'<div class="bx-header-subtitle">{html.escape(subtitle)}</div></div></div>'
            '</div>'
        )

    parts.append('<div class="bx-chat">')
    if not messages:
        parts.append(
            '<div class="bx-row center"><div class="bx-bubble bx-system">'
            "Aucun message pour l'instant."
            "</div></div>"
        )
    for m in messages:
        kind = _kind(m.get("author"), m.get("role"))
        side = {"vendeuse": "right", "system": "center"}.get(kind, "left")
        mid = m.get("id")
        msg_spans = by_msg.get(mid, [])
        whole = bool(
            highlight
            and highlight.get("message_id") == mid
            and (highlight.get("start") is None or highlight.get("end") is None)
        )
        extra = " bx-hl" if whole else ""

        author_html = ""
        if kind != "system":
            badge = '<span class="bx-role-badge">Livreur</span>' if kind == "livreur" else ""
            cls_auth = "bx-author livreur" if kind == "livreur" else "bx-author"
            author_html = (
                f'<div class="bx-author-row"><span class="{cls_auth}">'
                f'{html.escape(str(m.get("author", "")))}</span>{badge}</div>'
            )

        time_label = html.escape(str(m.get("time", "")))
        ticks = _DOUBLE_TICK_SVG if kind == "vendeuse" else ""
        parts.append(
            f'<div class="bx-row {side}"><div class="bx-bubble bx-{kind}{extra}">'
            f'{author_html}{_render_body(m.get("text", ""), msg_spans)}'
            f'<div class="bx-meta">{time_label}{ticks}</div></div></div>'
        )
    parts.append("</div></div>")
    html_str = "".join(parts)

    if height:
        with st.container(height=height):
            st.markdown(html_str, unsafe_allow_html=True)
    else:
        st.markdown(html_str, unsafe_allow_html=True)
