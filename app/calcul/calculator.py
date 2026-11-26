from typing import Iterable, Mapping

from app.calcul.references import load_rules


def round_half_up(numerator: int, denominator: int) -> int:
    """Round an exact rational to the nearest integer, with halves upward."""
    if denominator <= 0:
        raise ValueError("The denominator must be positive")
    quotient, remainder = divmod(numerator, denominator)
    if remainder * 2 >= denominator:
        return quotient + 1
    return quotient


def percentage(amount: int, percentage_value: int) -> int:
    return round_half_up(amount * percentage_value, 100)


def calculate_invoice(
    lines: Iterable[Mapping],
    zone: str,
    *,
    faithful_customer: bool = False,
    first_order: bool = False,
    promo_code: str | None = None,
    delivery_failed: bool = False,
    rules: Mapping | None = None,
) -> dict:
    """
    Calculate a draft using integer FCFA values and external YAML rules.

    The quantity discount uses confirmed accepted units (decision D3).
    Failed deliveries do not add delivery fees by default (decision D5).
    """
    active_rules = rules if rules is not None else load_rules()
    discounts_cfg = active_rules.get("discounts", {})
    fidelity_pct = int(discounts_cfg.get("fidelity_percent", 5))
    quantity_pct = int(discounts_cfg.get("quantity_percent", 10))
    quantity_threshold = int(discounts_cfg.get("quantity_units_threshold", 3))
    welcome_code = str(discounts_cfg.get("welcome_code", "BIENVENUE10")).upper()
    welcome_pct = int(discounts_cfg.get("welcome_percent", 10))
    vat_rate = int(active_rules.get("tax_rate_percent", 18))
    delivery_fees = active_rules.get("delivery_fees_ht", {
        "Cotonou": 1000,
        "Abomey-Calavi": 1500,
        "Porto-Novo": 2000,
    })

    line_results = []
    subtotal = 0
    accepted_units = 0

    for line in lines:
        quantity = int(line["quantity_accepted"])
        unit_price = int(line["unit_price_ht"])
        if quantity < 0 or unit_price < 0:
            raise ValueError("Quantities and prices cannot be negative")
        amount = quantity * unit_price
        line_results.append({
            "product_id": line["product_id"],
            "description": line["description"],
            "variant": line.get("variant"),
            "quantity": quantity,
            "unit_price_ht": unit_price,
            "amount_ht": amount,
        })
        subtotal += amount
        accepted_units += quantity

    delivery_ht = 0 if (delivery_failed or accepted_units == 0) else int(delivery_fees.get(zone, 0))

    applicable_discounts = []
    if faithful_customer and subtotal > 0:
        applicable_discounts.append(("fidélité", percentage(subtotal, fidelity_pct), fidelity_pct))
    if accepted_units >= quantity_threshold and subtotal > 0:
        applicable_discounts.append(("quantité", percentage(subtotal, quantity_pct), quantity_pct))
    if first_order and promo_code and promo_code.strip().upper() == welcome_code and subtotal > 0:
        applicable_discounts.append((welcome_code, percentage(subtotal, welcome_pct), welcome_pct))

    discount_name = None
    discount_amount = 0
    discount_percent = 0
    if applicable_discounts:
        discount_name, discount_amount, discount_percent = max(
            applicable_discounts,
            key=lambda item: item[1],
        )

    article_base = subtotal - discount_amount
    base_ht = article_base + delivery_ht
    vat = percentage(base_ht, vat_rate)
    total_ttc = base_ht + vat

    return {
        "lines": line_results,
        "subtotal_articles": subtotal,
        "discount_name": discount_name,
        "discount_percent": discount_percent,
        "discount_amount": discount_amount,
        "articles_base": article_base,
        "delivery_zone": zone,
        "delivery_ht": delivery_ht,
        "base_ht": base_ht,
        "vat_rate": vat_rate,
        "vat_amount": vat,
        "total_ttc": total_ttc,
    }
