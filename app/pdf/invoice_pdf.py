from pathlib import Path

try:
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.units import mm
    from reportlab.pdfgen import canvas
    HAS_REPORTLAB = True
except ImportError:  # pragma: no cover - fallback when reportlab is not installed
    HAS_REPORTLAB = False


def _pdf_escape(text: str) -> str:
    ascii_text = (
        str(text)
        .replace("\u2014", "-")
        .replace("\u2013", "-")
        .replace("\u2212", "-")
        .replace("\u00a0", " ")
        .encode("latin-1", "replace")
        .decode("latin-1")
    )
    return ascii_text.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


def _write_minimal_pdf(output: Path, lines: list[str]) -> Path:
    """Generate a valid single-page A4 PDF without external dependencies."""
    content_cmds = ["BT", "/F1 11 Tf", "50 790 Td", "15 TL"]
    for idx, line in enumerate(lines):
        escaped = _pdf_escape(line)
        if idx == 0:
            content_cmds.append(f"({escaped}) Tj")
        else:
            content_cmds.append(f"T* ({escaped}) Tj")
    content_cmds.append("ET")
    stream = "\n".join(content_cmds).encode("latin-1")

    objects = [
        b"1 0 obj << /Type /Catalog /Pages 2 0 R >> endobj\n",
        b"2 0 obj << /Type /Pages /Kids [3 0 R] /Count 1 >> endobj\n",
        b"3 0 obj << /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] /Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >> endobj\n",
        f"4 0 obj << /Length {len(stream)} >> stream\n".encode("ascii") + stream + b"\nendstream endobj\n",
        b"5 0 obj << /Type /Font /Subtype /Type1 /BaseFont /Helvetica >> endobj\n",
    ]

    buf = bytearray(b"%PDF-1.4\n")
    offsets = [0]
    for obj in objects:
        offsets.append(len(buf))
        buf.extend(obj)
    xref_pos = len(buf)
    buf.extend(f"xref\n0 {len(offsets)}\n".encode("ascii"))
    buf.extend(b"0000000000 65535 f \n")
    for off in offsets[1:]:
        buf.extend(f"{off:010d} 00000 n \n".encode("ascii"))
    buf.extend(
        f"trailer << /Size {len(offsets)} /Root 1 0 R >>\nstartxref\n{xref_pos}\n%%EOF\n".encode("ascii")
    )
    output.write_bytes(bytes(buf))
    return output


def _fmt_fcfa(amount: int) -> str:
    return f"{int(amount):,}".replace(",", " ") + " FCFA"


def generate_invoice_pdf(
    output_path: str | Path,
    calculation: dict,
    *,
    status: str,
    invoice_number: str = "À attribuer",
    dossier_reference: str = "",
    client: dict | None = None,
    vendor: dict | None = None,
    payments_summary: dict | None = None,
    issued_at: str | None = None,
) -> Path:
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    client = client or {}
    vendor = vendor or {}
    vendor_name = vendor.get("name", "Boutique X")
    vendor_address = vendor.get("address", "Adresse commerciale fictive — Cotonou")
    vendor_phone = vendor.get("phone", "+229 01 00 00 00 00 (fictif)")
    vendor_ifu = vendor.get("ifu", "non renseigné — prototype")
    footer = vendor.get("footer", "Document pédagogique — données fictives — paiements simulés")

    if not HAS_REPORTLAB:
        text_lines = [
            f"{status.upper()} - {vendor_name}",
            f"Numero : {invoice_number} | Dossier : {dossier_reference}"
            + (f" | Date : {issued_at[:10]}" if issued_at else ""),
            f"Vendeur : {vendor_name} - {vendor_address} - Tel: {vendor_phone} - IFU: {vendor_ifu}",
            f"Client : {client.get('name', 'Non renseigne')} | Tel: {client.get('phone', 'Non renseigne')} | Zone: {client.get('zone', client.get('address', 'Non renseignee'))}",
            "-" * 72,
            "Lignes facturees (quantites livrees et acceptees) :",
        ]
        for line in calculation.get("lines", []):
            desc = line["description"]
            if line.get("variant"):
                desc += f" ({line['variant']})"
            text_lines.append(
                f"  - {desc} | Qte: {line['quantity']} | PU HT: {_fmt_fcfa(line['unit_price_ht'])} | Montant HT: {_fmt_fcfa(line['amount_ht'])}"
            )
        text_lines.append("-" * 72)
        text_lines.append(f"Sous-total articles HT : {_fmt_fcfa(calculation['subtotal_articles'])}")
        text_lines.append(
            f"Remise ({calculation.get('discount_name') or 'aucune'}) : -{_fmt_fcfa(calculation['discount_amount'])}"
        )
        text_lines.append(f"Base articles apres remise : {_fmt_fcfa(calculation['articles_base'])}")
        text_lines.append(f"Frais de livraison HT ({calculation.get('delivery_zone', '')}) : {_fmt_fcfa(calculation['delivery_ht'])}")
        text_lines.append(f"Base HT : {_fmt_fcfa(calculation['base_ht'])}")
        text_lines.append(f"TVA ({calculation['vat_rate']} %) : {_fmt_fcfa(calculation['vat_amount'])}")
        text_lines.append(f"TOTAL TTC : {_fmt_fcfa(calculation['total_ttc'])}")
        if payments_summary:
            text_lines.append("-" * 72)
            text_lines.append(
                f"Cumul regle : {_fmt_fcfa(payments_summary.get('paid', 0))} | "
                f"Avoirs : {_fmt_fcfa(payments_summary.get('credits', 0))} | "
                f"Solde : {_fmt_fcfa(payments_summary.get('balance', calculation['total_ttc']))} | "
                f"Statut financier : {payments_summary.get('financial_status', 'NON_REGLEE')}"
            )
        text_lines.append("-" * 72)
        text_lines.append(footer)
        return _write_minimal_pdf(output, text_lines)

    pdf = canvas.Canvas(str(output), pagesize=A4)
    width, height = A4
    y = height - 18 * mm

    pdf.setFont("Helvetica-Bold", 18)
    pdf.drawString(18 * mm, y, f"{status.upper()} — {vendor_name}")
    y -= 10 * mm
    pdf.setFont("Helvetica", 10)
    pdf.drawString(18 * mm, y, f"Numéro : {invoice_number}")
    pdf.drawString(115 * mm, y, f"Dossier : {dossier_reference}")
    y -= 6 * mm
    if issued_at:
        pdf.drawString(18 * mm, y, f"Date d'émission : {issued_at[:10]}")
        y -= 6 * mm
    pdf.drawString(18 * mm, y, f"{vendor_address} — {vendor_phone}")
    pdf.drawRightString(width - 18 * mm, y, f"IFU : {vendor_ifu}")
    y -= 10 * mm

    pdf.setFont("Helvetica-Bold", 11)
    pdf.drawString(18 * mm, y, "Client")
    y -= 6 * mm
    pdf.setFont("Helvetica", 10)
    pdf.drawString(18 * mm, y, str(client.get("name", "Non renseigné")))
    pdf.drawString(100 * mm, y, str(client.get("phone", "Non renseigné")))
    y -= 6 * mm
    pdf.drawString(18 * mm, y, str(client.get("address") or client.get("zone") or "Non renseignée"))
    y -= 10 * mm

    table_x = [18 * mm, 108 * mm, 132 * mm, 158 * mm]

    def _draw_table_header(pos_y: float) -> float:
        pdf.setFillColor(colors.HexColor("#1F4E78"))
        pdf.rect(18 * mm, pos_y - 7 * mm, width - 36 * mm, 7 * mm, fill=1, stroke=0)
        pdf.setFillColor(colors.white)
        pdf.setFont("Helvetica-Bold", 9)
        pdf.drawString(table_x[0], pos_y - 5 * mm, "Article")
        pdf.drawString(table_x[1], pos_y - 5 * mm, "Qté")
        pdf.drawString(table_x[2], pos_y - 5 * mm, "PU HT")
        pdf.drawString(table_x[3], pos_y - 5 * mm, "Montant HT")
        pdf.setFillColor(colors.black)
        return pos_y - 11 * mm

    y = _draw_table_header(y)
    pdf.setFont("Helvetica", 9)
    for line in calculation.get("lines", []):
        if y < 40 * mm:
            pdf.showPage()
            y = height - 20 * mm
            y = _draw_table_header(y)
            pdf.setFont("Helvetica", 9)
        designation = line["description"]
        if line.get("variant"):
            designation += f" — {line['variant']}"
        pdf.drawString(table_x[0], y, designation[:48])
        pdf.drawRightString(table_x[1] + 12 * mm, y, str(line["quantity"]))
        pdf.drawRightString(table_x[2] + 18 * mm, y, f"{line['unit_price_ht']:,.0f}".replace(",", " "))
        pdf.drawRightString(table_x[3] + 28 * mm, y, f"{line['amount_ht']:,.0f}".replace(",", " "))
        y -= 7 * mm

    y -= 5 * mm
    summaries = [
        ("Sous-total articles HT", calculation["subtotal_articles"]),
        (f"Remise {calculation['discount_name'] or 'aucune'}", -calculation["discount_amount"]),
        ("Base articles après remise", calculation["articles_base"]),
        ("Frais de livraison HT", calculation["delivery_ht"]),
        ("Base HT", calculation["base_ht"]),
        (f"TVA {calculation['vat_rate']} %", calculation["vat_amount"]),
        ("TOTAL TTC", calculation["total_ttc"]),
    ]
    pdf.setFont("Helvetica", 10)
    for label, amount in summaries:
        pdf.drawString(100 * mm, y, label)
        pdf.drawRightString(width - 18 * mm, y, f"{amount:,.0f} FCFA".replace(",", " "))
        y -= 7 * mm

    if payments_summary:
        y -= 4 * mm
        pdf.setFont("Helvetica", 9)
        pdf.drawString(
            18 * mm,
            y,
            f"Règlements confirmés : {_fmt_fcfa(payments_summary.get('paid', 0))} | "
            f"Avoirs : {_fmt_fcfa(payments_summary.get('credits', 0))} | "
            f"Solde : {_fmt_fcfa(payments_summary.get('balance', calculation['total_ttc']))}",
        )
        y -= 6 * mm

    y -= 6 * mm
    pdf.setFillColor(colors.grey)
    pdf.setFont("Helvetica", 8)
    pdf.drawString(18 * mm, y, footer)
    pdf.save()
    return output


def generate_credit_pdf(
    output_path: str | Path,
    credit: dict,
    invoice: dict,
) -> Path:
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "AVOIR — Boutique X",
        f"Numéro d'avoir : {credit.get('number') or credit.get('id')}",
        f"Facture liée : {invoice.get('number')} (ID: {invoice.get('id')})",
        f"Date : {str(credit.get('created_at', ''))[:10]} | Créé par : {credit.get('created_by', '')}",
        f"Motif : {credit.get('reason', '')}",
        "-" * 72,
        f"Montant avoir TTC : -{_fmt_fcfa(credit.get('amount', 0))}",
        "-" * 72,
        "Document pédagogique — données fictives — paiements simulés",
    ]
    if not HAS_REPORTLAB:
        return _write_minimal_pdf(output, lines)

    pdf = canvas.Canvas(str(output), pagesize=A4)
    _, height = A4
    y = height - 20 * mm
    pdf.setFont("Helvetica-Bold", 16)
    pdf.drawString(18 * mm, y, lines[0])
    y -= 10 * mm
    pdf.setFont("Helvetica", 10)
    for line in lines[1:-1]:
        pdf.drawString(18 * mm, y, line)
        y -= 7 * mm
    pdf.setFillColor(colors.grey)
    pdf.setFont("Helvetica", 8)
    pdf.drawString(18 * mm, y - 5 * mm, lines[-1])
    pdf.save()
    return output
