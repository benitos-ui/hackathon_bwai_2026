from typing import Iterable, Mapping


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
) -> dict:
    """
    Calculate a draft using integer FCFA values and catalogue prices.

    The quantity discount uses confirmed accepted units. Failed deliveries
    do not add delivery fees by default.
    """
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

    delivery_fees = {
        "Cotonou": 1000,
        "Abomey-Calavi": 1500,
        "Porto-Novo": 2000,
    }
    delivery_ht = 0 if delivery_failed else delivery_fees.get(zone, 0)

    applicable_discounts = []
    if faithful_customer:
        applicable_discounts.append(("fidélité", percentage(subtotal, 5)))
    if accepted_units >= 3:
        applicable_discounts.append(("quantité", percentage(subtotal, 10)))
    if first_order and promo_code == "BIENVENUE10":
        applicable_discounts.append(("BIENVENUE10", percentage(subtotal, 10)))

    discount_name = None
    discount_amount = 0
    if applicable_discounts:
        discount_name, discount_amount = max(
            applicable_discounts,
            key=lambda item: item[1],
        )

    article_base = subtotal - discount_amount
    base_ht = article_base + delivery_ht
    vat = percentage(base_ht, 18)
    total_ttc = base_ht + vat

    return {
        "lines": line_results,
        "subtotal_articles": subtotal,
        "discount_name": discount_name,
        "discount_amount": discount_amount,
        "articles_base": article_base,
        "delivery_zone": zone,
        "delivery_ht": delivery_ht,
        "base_ht": base_ht,
        "vat_rate": 18,
        "vat_amount": vat,
        "total_ttc": total_ttc,
    }
