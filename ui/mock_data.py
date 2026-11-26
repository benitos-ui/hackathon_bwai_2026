"""Mock data for the Boutique X UI: Awa's dossier from the spec (section 3.4)."""

CHAT = [
    {"id": "m1", "time": "10:02", "author": "Awa",
     "text": "Bonjour, je veux 2 robes Ayoka, une en M et une en L, et 1 sérum vitamine C svp"},
    {"id": "m2", "time": "10:05", "author": "Vendeuse",
     "text": "Bonjour Awa, c'est noté. Livraison à Calavi ?"},
    {"id": "m3", "time": "10:06", "author": "Awa",
     "text": "Oui à Calavi, paiement à la livraison"},
    {"id": "m4", "time": "16:40", "author": "Livreur",
     "text": "Livré chez Awa. Elle a refusé la robe L (trop petite). "
             "1 robe M + 1 sérum livrés, payé en espèces."},
]

def _f(field, value, mid, text, start, end, conf,
       origin="conversation", status="extracted"):
    """Build one extracted field following the addendum v1.1 contract."""
    return {
        "field": field,
        "value": value,
        "source": {"message_id": mid, "text": text, "start": start, "end": end},
        "confidence": conf,
        "couleur": "vert" if conf >= 0.90 else "orange" if conf >= 0.60 else "rouge",  # mock only, the API will provide it
        "origin": origin,
        "status": status,
        "model_version": "baseline-1.0",
        "confirmed": False,  # UI-only state, not part of the API contract
    }


FIELDS = [
    _f("client", "CLI-0012 (Awa Dossou)", "m1", None, None, None, 0.96,
       origin="referentiel"),
    _f("product_1", "Robe wax Ayoka", "m1", "robes Ayoka", 19, 30, 0.97),
    _f("quantity_ordered", 2, "m1", "2", 17, 18, 0.98),
    _f("product_2", "Sérum vitamine C 30 ml", "m1", "sérum vitamine C", 59, 75, 0.94),
    _f("zone", "Abomey-Calavi", "m3", "Calavi", 6, 12, 0.88, status="needs_review"),
    _f("payment_mode", "À la livraison", "m3", "paiement à la livraison", 14, 37, 0.95),
    _f("delivered", "1 robe M + 1 sérum", "m4", "1 robe M + 1 sérum livrés", 55, 80, 0.91),
    _f("refusal", "Robe L, motif : taille", "m4", "refusé la robe L (trop petite)", 23, 53,
       0.86, status="needs_review"),
    _f("promo_code", None, None, None, None, None, 0.0, status="missing"),
]

ANOMALIES = [
    {"id": "A1", "type": "commande_vs_livre", "resolved": False, "resolution": "",
    "message": "2 robes commandées, 1 seule acceptée (la robe L a été refusée)."},
]

INVOICE_LINES = [
    {"label": "Robe wax Ayoka, taille M", "qty": 1, "unit": 15000, "amount": 15000},
    {"label": "Sérum vitamine C 30 ml", "qty": 1, "unit": 8000, "amount": 8000},
]

TOTALS = {
    "subtotal": 23000,
    "discount_label": "Remise fidélité 5 %",
    "discount": 1150,
    "base_after_discount": 21850,
    "delivery": 1500,
    "base_ht": 23350,
    "vat": 4203,
    "total_ttc": 27553,
}

USERS = {
    "vendeuse": "Vendeuse",
    "gerant": "Gérant",
    "auditeur": "Auditeur",
}

DOC_STATUS = "A_REVOIR"          # documentary status
FINANCIAL_STATUS = "NON_REGLEE"  # financial status, shown separately
INVOICE_NUMBER = None            # shown as "A attribuer" until validated

DELIVERY = [
    {"label": "Robe wax Ayoka, taille M", "ordered": 1, "delivered": 1,
     "accepted": 1, "refused": 0, "missing": 0, "reason": ""},
    {"label": "Robe wax Ayoka, taille L", "ordered": 1, "delivered": 1,
     "accepted": 0, "refused": 1, "missing": 0, "reason": "Taille trop petite"},
    {"label": "Sérum vitamine C 30 ml", "ordered": 1, "delivered": 1,
     "accepted": 1, "refused": 0, "missing": 0, "reason": ""},
]

BALANCE = {"total_ttc": 27553, "credits": 0, "paid": 0, "balance": 27553}