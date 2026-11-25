from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.pdfgen import canvas


def generate_invoice_pdf(
    output_path: str | Path,
    calculation: dict,
    *,
    status: str,
    invoice_number: str = "À attribuer",
    dossier_reference: str = "",
    client: dict | None = None,
) -> Path:
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)

    pdf = canvas.Canvas(str(output), pagesize=A4)
    width, height = A4
    y = height - 18 * mm

    pdf.setFont("Helvetica-Bold", 18)
    pdf.drawString(18 * mm, y, f"{status.upper()} — Boutique X")
    y -= 10 * mm
    pdf.setFont("Helvetica", 10)
    pdf.drawString(18 * mm, y, f"Numéro: {invoice_number}")
    pdf.drawString(120 * mm, y, f"Dossier: {dossier_reference}")
    y -= 8 * mm
    pdf.drawString(18 * mm, y, "Adresse commerciale fictive — Cotonou")
    pdf.drawRightString(width - 18 * mm, y, "IFU: non renseigné — prototype")
    y -= 10 * mm

    client = client or {}
    pdf.setFont("Helvetica-Bold", 11)
    pdf.drawString(18 * mm, y, "Client")
    y -= 6 * mm
    pdf.setFont("Helvetica", 10)
    pdf.drawString(18 * mm, y, str(client.get("name", "Non renseigné")))
    pdf.drawString(100 * mm, y, str(client.get("phone", "Non renseigné")))
    y -= 6 * mm
    pdf.drawString(18 * mm, y, str(client.get("address", "Non renseignée")))
    y -= 10 * mm

    table_x = [18 * mm, 108 * mm, 132 * mm, 158 * mm]
    pdf.setFillColor(colors.HexColor("#1F4E78"))
    pdf.rect(18 * mm, y - 7 * mm, width - 36 * mm, 7 * mm, fill=1, stroke=0)
    pdf.setFillColor(colors.white)
    pdf.setFont("Helvetica-Bold", 9)
    pdf.drawString(table_x[0], y - 5 * mm, "Article")
    pdf.drawString(table_x[1], y - 5 * mm, "Qté")
    pdf.drawString(table_x[2], y - 5 * mm, "PU HT")
    pdf.drawString(table_x[3], y - 5 * mm, "Montant HT")
    pdf.setFillColor(colors.black)
    y -= 11 * mm

    pdf.setFont("Helvetica", 9)
    for line in calculation["lines"]:
        designation = line["description"]
        if line.get("variant"):
            designation += f" — {line['variant']}"
        pdf.drawString(table_x[0], y, designation[:45])
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

    y -= 8 * mm
    pdf.setFillColor(colors.grey)
    pdf.setFont("Helvetica", 8)
    pdf.drawString(18 * mm, y,
                   "Document pédagogique — données fictives — paiements simulés")
    pdf.save()
    return output
