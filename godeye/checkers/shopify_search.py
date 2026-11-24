"""Searches a whole Shopify store, so a re-listing under a new URL is still caught."""
from urllib.parse import quote_plus

from . import Result, matches_all, register, shopify_variant_items, stock_result
from ..fetch import get_json


@register("shopify_search")
def check(source: dict, target: dict) -> Result:
    store = source["store"].rstrip("/")
    keywords = [k.lower() for k in source.get("keywords") or target["keywords"]]  # per-store override
    query = source.get("query") or " ".join(keywords)
    data = get_json(f"{store}/search/suggest.json",
                    params={"q": query, "resources[type]": "product", "resources[limit]": 10})
    products = data.get("resources", {}).get("results", {}).get("products", [])
    link = f"{store}/search?q={quote_plus(query)}"

    items = []
    for p in products:
        if not matches_all(p.get("title", ""), keywords):
            continue
        page = store + (p.get("url") or "").split("?")[0]
        # Search results only say "some size is available", so read the product's sizes.
        items += shopify_variant_items(page, get_json(page + ".js"), source, target)

    if not items:
        return Result("not_listed", f"No listing matching {target['name']}", link)
    return stock_result(items, link)
