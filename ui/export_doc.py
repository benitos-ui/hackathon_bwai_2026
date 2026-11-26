"""Pure presentation document exporters (PDF in-memory fallback + Word .doc) for Boutique X UI.

Strictly presentation-only: formats only the exact lines, totals, and metadata already
computed and returned by the FastAPI backend (zero business calculation).
"""
import html
import io

from ui.styles import fcfa


def render_pdf_bytes(
    number: str,
    doc_status: str,
    lines: list[dict],
    totals: dict,
    *,
    dossier_id: str = "",
    client_name: str = "",
    initiator: str = "",
    content_hash: str = "",
) -> bytes:
    """Render an A4 invoice PDF strictly in memory (BytesIO, zero temp-file lock on Windows)."""
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.units import mm
    from reportlab.pdfgen import canvas

    buf = io.BytesIO()
    pdf = canvas.Canvas(buf, pagesize=A4)
    w, h = A4

    st_upper = str(doc_status or "BROUILLON").upper()
    stamp = "ÉMISE" if st_upper == "EMISE" else ("VALIDÉE" if st_upper == "VALIDEE" else "BROUILLON")

    # Header bar
    pdf.setFillColor(colors.HexColor("#0F172A"))
    pdf.rect(0, h - 28 * mm, w, 28 * mm, stroke=0, fill=1)
    pdf.setFillColor(colors.white)
    pdf.setFont("Helvetica-Bold", 16)
    pdf.drawString(18 * mm, h - 13 * mm, "BOUTIQUE X — COTONOU")
    pdf.setFont("Helvetica", 9)
    pdf.drawString(18 * mm, h - 19 * mm, "Facturation assistée par IA · IFU non renseigné (prototype)")

    pdf.setFont("Helvetica-Bold", 12)
    pdf.drawRightString(w - 18 * mm, h - 13 * mm, f"{stamp} · {number}")
    pdf.setFont("Helvetica", 9)
    if dossier_id:
        pdf.drawRightString(w - 18 * mm, h - 19 * mm, f"Dossier : {dossier_id}")

    y = h - 40 * mm
    pdf.setFillColor(colors.HexColor("#0F172A"))
    pdf.setFont("Helvetica-Bold", 10)
    pdf.drawString(18 * mm, y, f"Client : {client_name or 'Non renseigné'}")
    if initiator:
        pdf.setFont("Helvetica", 9)
        pdf.drawRightString(w - 18 * mm, y, f"Initiateur : {initiator}")
    y -= 10 * mm

    # Table header
    pdf.setFillColor(colors.HexColor("#F1F5F9"))
    pdf.rect(18 * mm, y - 2 * mm, w - 36 * mm, 8 * mm, stroke=0, fill=1)
    pdf.setFillColor(colors.HexColor("#334155"))
    pdf.setFont("Helvetica-Bold", 9)
    pdf.drawString(20 * mm, y + 1 * mm, "Désignation")
    pdf.drawRightString(125 * mm, y + 1 * mm, "Qté")
    pdf.drawRightString(158 * mm, y + 1 * mm, "PU HT")
    pdf.drawRightString(w - 20 * mm, y + 1 * mm, "Montant HT")
    y -= 9 * mm

    pdf.setFont("Helvetica", 9.5)
    pdf.setFillColor(colors.HexColor("#0F172A"))
    for line in (lines or []):
        pdf.drawString(20 * mm, y, str(line.get("label", ""))[:58])
        pdf.drawRightString(125 * mm, y, str(line.get("qty", 0)))
        pdf.drawRightString(158 * mm, y, fcfa(line.get("unit", 0)).replace("\u00a0", " "))
        pdf.drawRightString(w - 20 * mm, y, fcfa(line.get("amount", 0)).replace("\u00a0", " "))
        pdf.setStrokeColor(colors.HexColor("#E2E8F0"))
        pdf.line(18 * mm, y - 2.5 * mm, w - 18 * mm, y - 2.5 * mm)
        y -= 7.5 * mm

    y -= 6 * mm
    tot_rows = [
        ("Sous-total articles HT", totals.get("subtotal", 0)),
        (totals.get("discount_label") or "Remise", -int(totals.get("discount", 0))),
        ("Base articles après remise", totals.get("base_after_discount", 0)),
        ("Frais de livraison HT", totals.get("delivery", 0)),
        ("Base HT totale", totals.get("base_ht", 0)),
        (f"TVA ({totals.get('vat_rate', 18)} %)", totals.get("vat", 0)),
    ]
    for lbl, amt in tot_rows:
        pdf.setFont("Helvetica", 9.5)
        pdf.drawString(110 * mm, y, str(lbl))
        amt_s = ("- " + fcfa(-amt) if amt < 0 else fcfa(amt)).replace("\u00a0", " ")
        pdf.drawRightString(w - 20 * mm, y, amt_s)
        y -= 6 * mm

    pdf.setStrokeColor(colors.HexColor("#0F172A"))
    pdf.setLineWidth(1.2)
    pdf.line(110 * mm, y + 2 * mm, w - 18 * mm, y + 2 * mm)
    y -= 4 * mm
    pdf.setFont("Helvetica-Bold", 11)
    pdf.drawString(110 * mm, y, "Total TTC")
    pdf.drawRightString(w - 20 * mm, y, fcfa(totals.get("total_ttc", 0)).replace("\u00a0", " "))

    # Footer
    pdf.setFont("Helvetica", 8)
    pdf.setFillColor(colors.HexColor("#64748B"))
    pdf.drawString(18 * mm, 18 * mm, "Document pédagogique — données fictives — paiements simulés")
    if content_hash:
        pdf.drawRightString(w - 18 * mm, 18 * mm, f"SHA-256 : {str(content_hash)[:28]}...")

    pdf.showPage()
    pdf.save()
    return buf.getvalue()


def render_word_bytes(
    number: str,
    doc_status: str,
    lines: list[dict],
    totals: dict,
    *,
    dossier_id: str = "",
    client_name: str = "",
    initiator: str = "",
    content_hash: str = "",
) -> bytes:
    """Render a clean Word-compatible (.doc) A4 invoice directly from API data."""
    st_upper = str(doc_status or "BROUILLON").upper()
    stamp = "ÉMISE" if st_upper == "EMISE" else ("VALIDÉE" if st_upper == "VALIDEE" else "BROUILLON")

    rows = []
    for l in (lines or []):
        rows.append(
            "<tr>"
            f"<td>{html.escape(str(l.get('label', '')))}</td>"
            f"<td style='text-align:right;'>{html.escape(str(l.get('qty', 0)))}</td>"
            f"<td style='text-align:right;'>{html.escape(fcfa(l.get('unit', 0)))}</td>"
            f"<td style='text-align:right;'><strong>{html.escape(fcfa(l.get('amount', 0)))}</strong></td>"
            "</tr>"
        )
    if not rows:
        rows.append("<tr><td colspan='4' style='text-align:center;color:#64748B;'>Aucune ligne facturable.</td></tr>")

    tot_rows = [
        ("Sous-total articles HT", totals.get("subtotal", 0)),
        (totals.get("discount_label") or "Remise", -int(totals.get("discount", 0))),
        ("Base articles après remise", totals.get("base_after_discount", 0)),
        ("Frais de livraison HT", totals.get("delivery", 0)),
        ("Base HT totale", totals.get("base_ht", 0)),
        (f"TVA ({totals.get('vat_rate', 18)} %)", totals.get("vat", 0)),
    ]
    tot_html = []
    for lbl, amt in tot_rows:
        amt_txt = ("− " + fcfa(-amt)) if amt < 0 else fcfa(amt)
        tot_html.append(
            f"<tr><td style='padding:4px 8px;'>{html.escape(str(lbl))}</td>"
            f"<td style='padding:4px 8px;text-align:right;'>{html.escape(amt_txt)}</td></tr>"
        )
    tot_html.append(
        f"<tr style='border-top:2px solid #0F172A;font-weight:bold;font-size:12pt;'>"
        f"<td style='padding:8px;'>Total TTC</td>"
        f"<td style='padding:8px;text-align:right;'>{html.escape(fcfa(totals.get('total_ttc', 0)))}</td></tr>"
    )

    hash_line = (
        f"<p style='font-family:Consolas,monospace;font-size:8.5pt;color:#14532D;'>Empreinte SHA-256 figée : {html.escape(str(content_hash))}</p>"
        if content_hash
        else "<p style='font-size:8.5pt;color:#64748B;'>Numéro définitif attribué uniquement à la validation par le gérant.</p>"
    )

    doc_html = (
        "<html xmlns:o='urn:schemas-microsoft-com:office:office' "
        "xmlns:w='urn:schemas-microsoft-com:office:word' "
        "xmlns='http://www.w3.org/TR/REC-html40'>"
        "<head><meta charset='utf-8'><title>Facture Boutique X</title>"
        "<style>"
        "@page { size: A4; margin: 1.8cm; }"
        "body { font-family: Calibri, Arial, sans-serif; color: #0F172A; font-size: 10.5pt; }"
        "table.lines { width: 100%; border-collapse: collapse; margin: 16px 0; }"
        "table.lines th { background: #F1F5F9; border-bottom: 2px solid #0F172A; padding: 8px; text-align: left; font-size: 9pt; text-transform: uppercase; }"
        "table.lines td { border-bottom: 1px solid #CBD5E1; padding: 8px; }"
        "table.totals { width: 52%; margin-left: auto; border-collapse: collapse; background: #F8FAFC; border: 1px solid #CBD5E1; }"
        "</style></head><body>"
        "<table style='width:100%;border-bottom:2px solid #0F172A;padding-bottom:10px;margin-bottom:14px;'><tr>"
        "<td><h1 style='margin:0;font-size:16pt;color:#0F172A;'>BOUTIQUE X — COTONOU</h1>"
        "<div style='font-size:9pt;color:#475569;'>Atelier IA de facturation · IFU non renseigné (prototype)</div></td>"
        f"<td style='text-align:right;'><div style='font-weight:bold;font-size:12pt;'>{html.escape(stamp)}</div>"
        f"<div style='font-family:Consolas,monospace;font-size:11pt;'>{html.escape(str(number))}</div></td>"
        "</tr></table>"
        f"<p><strong>Dossier :</strong> {html.escape(str(dossier_id or '-'))} &nbsp;|&nbsp; "
        f"<strong>Client :</strong> {html.escape(str(client_name or 'Non renseigné'))} &nbsp;|&nbsp; "
        f"<strong>Initiateur :</strong> {html.escape(str(initiator or '-'))}</p>"
        "<table class='lines'><thead><tr>"
        "<th>Désignation</th><th style='text-align:right;'>Qté livrée</th>"
        "<th style='text-align:right;'>PU HT</th><th style='text-align:right;'>Montant HT</th>"
        f"</tr></thead><tbody>{''.join(rows)}</tbody></table>"
        f"<table class='totals'>{''.join(tot_html)}</table>"
        "<hr style='border:none;border-top:1px dashed #94A3B8;margin-top:24px;'>"
        "<p style='font-size:8.5pt;color:#475569;'>Document pédagogique — données fictives — paiements simulés.</p>"
        f"{hash_line}</body></html>"
    )
    return ("\ufeff" + doc_html).encode("utf-8")
