# WebGodEye

A tiny restock watcher that runs on your PC. It checks stores on a schedule, shows a dashboard at
http://127.0.0.1:8765 and alerts you (Windows popup, phone via ntfy, Discord) when the product comes back.

## Start / stop
- **Start:** double-click `run.bat`. It runs in the background with no console window and opens the dashboard.
  Running it again restarts it, so use it after editing `watch.toml`.
- **Stop:** double-click `stop.bat`.
- **Runs at login:** a `WebGodEye` shortcut in your Startup folder (`Win+R` → `shell:startup`) starts it
  silently with `run.bat --no-browser`. Delete that shortcut to stop it starting with Windows.
- **Is it running?** The dashboard shows a Running / Offline / Stalled light, and the tab icon is a green or red dot.

First-time setup (already done on this PC):
```
python -m pip install -r requirements.txt
```

## Alerts
- **Phone:** install the **ntfy** app and subscribe to the topic shown at the bottom of the dashboard
  (also in `watch.toml` → `ntfy_topic`). Anyone who knows the topic name can read it, so keep it to yourself.
- **Discord:** in a channel you own, go to *Edit Channel → Integrations → Webhooks → New Webhook*, copy
  the URL and paste it into `discord_webhook` in `watch.toml`.
- **Test all channels:** `python -m godeye --test-notify`

You get one alert when something goes from sold out to in stock, not one every check.

## Watching a different product
Everything lives in **`watch.toml`**. Edit it, then double-click `run.bat` (it restarts the app).

1. Change `[target]`: `name`, and the `keywords` a product title must **all** contain.
   For the picture, run `python -m godeye --make-image <product image url>`. It cuts out a plain white
   background and saves `assets/target.png`. Or set `image` to any image URL.
2. Change the `url` of each `shopify_product` source to the new product pages.
3. The `shopify_search` sources pick up the new keywords automatically. Change `query` if you set one.

To add another Shopify store, add four lines:
```toml
[[source]]
name = "Some Store"
type = "shopify_product"          # or shopify_search with  store = "https://somestore.com"
url = "https://somestore.com/products/the-thing"
```
To find out whether a site runs on Shopify, open `<product url>.js` in your browser. If it shows JSON, it's Shopify.
For other sites use `type = "page_text"` (alerts when e.g. "Sold out" disappears from the page), or
`type = "link"` for a card that just links somewhere to check by hand. See the comments at the top of `watch.toml`.

## Handy commands
| Command | What it does |
|---|---|
| `python -m godeye --once` | Check every source once and print the results (no alerts) |
| `python -m godeye --test-notify` | Send a test alert to every channel |
| `python -m godeye --make-image URL` | Make the dashboard picture (transparent PNG) from a product photo |
| `python -m godeye` | Run in a console window, to watch the log live |

The log is in `data/godeye.log`. The last results are in `data/state.json`. Delete that file to reset.

## Adding a new kind of source (code)
Drop a file into `godeye/checkers/` that defines a function decorated with `@register("my_type")`. The function returns a
`Result` with a list of `Item`s, where `hot=True` means "this is what I'm waiting for". The scheduler handles
timing, backoff, the dashboard and alerts. Use `shopify_product.py` (about 25 lines) as the template.

## Notes
- Requests look like a normal Chrome browser and run every 10–30 minutes with random variation. If a store
  rate-limits (HTTP 429), that source backs off for up to 2 hours.
- TikTok was tried and dropped, because it won't show posts to automated browsers. Use a `link` card for social pages.
