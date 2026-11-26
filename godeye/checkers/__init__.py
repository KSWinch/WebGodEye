"""Checker registry — the extension point.

To support a new kind of source, add a module in this folder with:

    from . import register, Result, Item

    @register("my_type")
    def check(source: dict, target: dict) -> Result:
        ...

then use `type = "my_type"` in watch.toml. Checkers never send alerts; they report items, and the
scheduler alerts when an item becomes "hot" (in stock / matching post) that wasn't hot last time.
"""
import importlib
import pkgutil
import re
from dataclasses import dataclass, field
from urllib.parse import urlsplit

REGISTRY: dict[str, "Checker"] = {}


@dataclass
class Item:
    id: str
    title: str
    hot: bool              # True = the thing we're waiting for (available / matching post)
    url: str = ""
    note: str = ""         # short extra text, e.g. "Sold out"
    buy_url: str = ""      # straight-to-checkout link, when the store supports one


@dataclass
class Result:
    status: str            # in_stock | out_of_stock | not_listed | match | no_match
    summary: str
    link: str = ""         # where a human should look
    items: list[Item] = field(default_factory=list)


@dataclass
class Checker:
    fn: callable
    # If True, the first successful run only records what already exists (no alert).
    # Used for social feeds so old posts don't fire alerts on first start.
    baseline_first_run: bool = False


def register(name: str, baseline_first_run: bool = False):
    def deco(fn):
        REGISTRY[name] = Checker(fn, baseline_first_run)
        return fn
    return deco


def matches_all(title: str, keywords: list[str]) -> bool:
    t = title.lower()
    return all(k in t for k in keywords)


def matches_any(text: str, keywords: list[str]) -> bool:
    t = text.lower()
    return any(k in t for k in keywords)


def _norm(text: str) -> str:
    return re.sub(r"\s+", "", text.lower())


def size_watched(label: str, source: dict, target: dict) -> bool:
    """True if `label` (e.g. "3.4 oz / 100 ml") is a size we alert on. No sizes configured = all sizes."""
    sizes = source.get("sizes") or target.get("alert_sizes") or []
    return not sizes or any(_norm(s) in _norm(label) for s in sizes)


def shopify_variant_items(page: str, product: dict, source: dict, target: dict) -> list[Item]:
    """Turn a Shopify product (.js JSON) into one Item per variant; hot = available AND a watched size."""
    items = []
    root = "{0.scheme}://{0.netloc}".format(urlsplit(page))
    for v in product.get("variants", []):
        vt = v.get("title") or "Default Title"
        label = product.get("title", "") if vt == "Default Title" else vt
        watched = size_watched(label, source, target)
        avail = bool(v.get("available"))
        note = ("In stock" if avail else "Sold out") + ("" if watched else " · not watched")
        items.append(Item(id=str(v["id"]), title=label, hot=avail and watched,
                          url=f"{page}?variant={v['id']}", note=note,
                          # Shopify cart permalink: puts 1 of this size in the cart and opens checkout.
                          buy_url=f"{root}/cart/{v['id']}:1"))
    return items


def stock_result(items: list[Item], link: str) -> Result:
    hot = [i for i in items if i.hot]
    if hot:
        return Result("in_stock", "In stock: " + ", ".join(i.title for i in hot), link, items)
    other = [i for i in items if i.note.startswith("In stock")]
    summary = (f"Watched size sold out · {', '.join(i.title for i in other)} in stock" if other
               else "Sold out")
    return Result("out_of_stock", summary, link, items)


def load_all():
    for mod in pkgutil.iter_modules(__path__):
        importlib.import_module(f"{__name__}.{mod.name}")
