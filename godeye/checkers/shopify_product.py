"""Any Shopify product page: <url>.js returns per-variant `available` flags."""
from . import Result, register, shopify_variant_items, stock_result
from ..fetch import get_json


@register("shopify_product")
def check(source: dict, target: dict) -> Result:
    page = source["url"].split("?")[0].rstrip("/")
    items = shopify_variant_items(page, get_json(page + ".js"), source, target)
    if not items:
        return Result("not_listed", "Product has no variants", page)
    return stock_result(items, page)
