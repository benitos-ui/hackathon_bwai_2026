from typing import Iterable, Mapping


def detect_anomalies(
    dossier: Mapping,
    catalogue: Mapping,
    clients: Mapping,
) -> list[dict]:
    anomalies = []
    client = dossier.get("client")
    if client and client not in clients:
        anomalies.append({
            "code": "A_CLIENT_INCONNU",
            "severity": "bloquante",
            "description": "Client absent du référentiel ou identité incertaine.",
        })

    seen_products = set()
    for line in dossier.get("lines", []):
        product_id = line.get("product_id")
        if product_id in seen_products:
            anomalies.append({
                "code": "A_DOUBLON",
                "severity": "bloquante",
                "description": "Une même ligne produit apparaît plusieurs fois.",
            })
        seen_products.add(product_id)

        if product_id not in catalogue:
            anomalies.append({
                "code": "A_PRODUIT_AMBIGU",
                "severity": "bloquante",
                "description": "Produit absent du catalogue ou ambigu.",
            })

        quantity = line.get("quantity_ordered")
        delivered = line.get("quantity_delivered")
        accepted = line.get("quantity_accepted")
        refused = line.get("quantity_refused", 0)
        missing = line.get("quantity_missing", 0)
        if quantity is not None and quantity < 0:
            anomalies.append({
                "code": "A_QUANTITE",
                "severity": "bloquante",
                "description": "Quantité négative ou contradictoire.",
            })
        if accepted is not None and refused is not None and missing is not None:
            if delivered is not None and accepted + refused + missing != delivered:
                anomalies.append({
                    "code": "A_LIVRAISON",
                    "severity": "bloquante",
                    "description": "Acceptée + refusée + manquante doit égaler la quantité livrée.",
                })

        cited_price = line.get("cited_price_ht")
        if cited_price is not None and product_id in catalogue:
            official_price = catalogue[product_id]["price_ht"]
            if abs(cited_price - official_price) * 100 > official_price * 10:
                anomalies.append({
                    "code": "A_PRIX",
                    "severity": "bloquante",
                    "description": "Le prix cité diffère de plus de 10 % du prix catalogue.",
                })

    if dossier.get("conversation_has_multiple_clients"):
        anomalies.append({
            "code": "A_CONVERSATION",
            "severity": "bloquante",
            "description": "Plusieurs clients ou commandes sont mélangés dans le fil.",
        })

    return anomalies
