"""A dashboard card that only links somewhere to check by hand (Instagram, a newsletter archive, …).

    type = "link"
    url = "https://www.instagram.com/officialmykonos/"
"""
from . import Result, register


@register("link")
def check(source: dict, target: dict) -> Result:
    return Result("manual", source.get("note", "Check manually"), source["url"])
