"""Generic fallback for non-Shopify sites: watch for a piece of text appearing or disappearing.

    type = "page_text"
    url = "https://example.com/product"
    text = "Sold out"
    alert_when = "absent"          # "absent" (default) or "present"
    sanity_text = "Inferno"        # optional; page must contain this or the check counts as failed
                                   # (stops a blocked/blank page from looking like "Sold out is gone")
"""
from . import Item, Result, register
from ..fetch import FetchError, get


@register("page_text")
def check(source: dict, target: dict) -> Result:
    url = source["url"]
    html = get(url).text.lower()
    needle = source["text"].lower()
    sanity = [source["sanity_text"].lower()] if source.get("sanity_text") else target["keywords"]
    if not all(s in html for s in sanity):
        raise FetchError("Page didn't look like the product page (sanity text missing)")

    present = needle in html
    want_present = source.get("alert_when", "absent") == "present"
    hot = present == want_present
    note = f'"{source["text"]}" {"found" if present else "not found"} on page'
    return Result("in_stock" if hot else "out_of_stock", note, url,
                  [Item(id="page", title=target["name"], hot=hot, url=url, note=note)])
