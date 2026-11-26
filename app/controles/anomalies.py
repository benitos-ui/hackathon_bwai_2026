from typing import Mapping

from app.calcul.references import load_rules


def detect_anomalies(
    dossier: Mapping,
    catalogue: Mapping,
    clients: Mapping,
    rules: Mapping | None = None,
) -> list[dict]:
    active_rules = rules if rules is not None else load_rules()
    tolerance_pct = int(active_rules.get("unusual_price_tolerance_percent", 10))
    anomalies: list[dict] = []

    client = dossier.get("client")
    if not client or client not in clients:
        anomalies.append({
            "code": "A_CLIENT_INCONNU",
            "severity": "bloquante",
            "description": "Client absent du référentiel ou identité incertaine.",
            "concerned_value": str(client) if client else None,
        })

    for amb in dossier.get("ambiguous_products", []):
        cands = ", ".join(c.get("ref", "") for c in amb.get("candidats", []))
        anomalies.append({
            "code": "A_PRODUIT_AMBIGU",
            "severity": "bloquante",
            "description": (
                f"Mention produit ambiguë « {amb.get('valeur_brute')} » "
                f"(candidats proches : {cands}). Sélection humaine requise."
            ),
            "concerned_value": amb.get("valeur_brute"),
        })

    seen_products = set()
    for line in dossier.get("lines", []):
        product_id = line.get("product_id")
        variant = line.get("variant")
        line_key = (product_id, variant)
        if product_id in seen_products and not variant:
            anomalies.append({
                "code": "A_DOUBLON",
                "severity": "bloquante",
                "description": f"Une même ligne produit ({product_id}) apparaît plusieurs fois.",
                "concerned_value": str(product_id),
            })
        elif line_key in seen_products:
            anomalies.append({
                "code": "A_DOUBLON",
                "severity": "bloquante",
                "description": f"Ligne produit/variante en doublon ({product_id} / {variant}).",
                "concerned_value": f"{product_id}:{variant}",
            })
        seen_products.add(product_id if not variant else line_key)

        if product_id not in catalogue:
            anomalies.append({
                "code": "A_PRODUIT_AMBIGU",
                "severity": "bloquante",
                "description": f"Produit absent du catalogue ou ambigu ({product_id}).",
                "concerned_value": str(product_id),
            })
        else:
            allowed_variants = catalogue[product_id].get("variants", [])
            if allowed_variants and allowed_variants != ["Unique"]:
                if variant and variant not in allowed_variants:
                    anomalies.append({
                        "code": "A_VARIANTE",
                        "severity": "bloquante",
                        "description": (
                            f"Variante « {variant} » indisponible pour {catalogue[product_id]['name']} "
                            f"(disponibles : {', '.join(allowed_variants)})."
                        ),
                        "concerned_value": str(variant),
                    })
                elif not variant and not line.get("variants_ordered"):
                    anomalies.append({
                        "code": "A_VARIANTE",
                        "severity": "bloquante",
                        "description": (
                            f"Taille/variante absente pour {catalogue[product_id]['name']} "
                            f"(disponibles : {', '.join(allowed_variants)})."
                        ),
                        "concerned_value": str(product_id),
                    })

        quantity = line.get("quantity_ordered")
        delivered = line.get("quantity_delivered")
        accepted = line.get("quantity_accepted")
        refused = line.get("quantity_refused", 0)
        missing = line.get("quantity_missing", 0)

        if (
            (quantity is not None and quantity < 0)
            or (delivered is not None and delivered < 0)
            or (accepted is not None and accepted < 0)
            or (refused is not None and refused < 0)
            or (missing is not None and missing < 0)
        ):
            anomalies.append({
                "code": "A_QUANTITE",
                "severity": "bloquante",
                "description": "Quantité négative ou contradictoire.",
                "concerned_value": str(product_id),
            })

        if accepted is not None and refused is not None and missing is not None:
            if delivered is not None and accepted + refused + missing != delivered:
                anomalies.append({
                    "code": "A_LIVRAISON",
                    "severity": "bloquante",
                    "description": (
                        f"Incohérence de livraison pour {line.get('description', product_id)} : "
                        f"acceptée ({accepted}) + refusée ({refused}) + manquante ({missing}) "
                        f"≠ livrée/expédiée ({delivered})."
                    ),
                    "concerned_value": str(product_id),
                })

        if quantity is not None and accepted is not None and quantity != accepted:
            reason = line.get("refusal_reason")
            suffix = f" (motif : {reason})" if reason else ""
            anomalies.append({
                "code": "A_LIVRAISON",
                "severity": "bloquante",
                "description": (
                    f"{line.get('description', product_id)} : {quantity} commandé(s), "
                    f"{accepted} accepté(s), {refused} refusé(s){suffix}."
                ),
                "concerned_value": str(product_id),
            })

        cited_price = line.get("cited_price_ht")
        if cited_price is not None and product_id in catalogue:
            official_price = catalogue[product_id]["price_ht"]
            if abs(cited_price - official_price) * 100 > official_price * tolerance_pct:
                anomalies.append({
                    "code": "A_PRIX",
                    "severity": "bloquante",
                    "description": (
                        f"Prix cité ({cited_price} FCFA) écarté de plus de {tolerance_pct} % "
                        f"du prix catalogue officiel ({official_price} FCFA) pour "
                        f"{catalogue[product_id]['name']}."
                    ),
                    "concerned_value": f"{cited_price} vs {official_price}",
                })

    if dossier.get("conversation_has_multiple_clients"):
        anomalies.append({
            "code": "A_CONVERSATION",
            "severity": "bloquante",
            "description": "Plusieurs clients ou commandes sont mélangés dans le fil.",
            "concerned_value": None,
        })

    if dossier.get("unsupported_media"):
        types = ", ".join(sorted({m.get("type_media", "media") for m in dossier["unsupported_media"]}))
        anomalies.append({
            "code": "A_MEDIA",
            "severity": "bloquante",
            "description": (
                f"Média(s) non pris en charge détecté(s) dans le fil ({types}). "
                "Vérification humaine requise."
            ),
            "concerned_value": types,
        })

    return anomalies
