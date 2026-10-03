"""Optional web search for dynamic mode. Off unless config enables it.

DuckDuckGo's HTML endpoint is the free default. If a Kagi API key is set, Kagi
is used instead; Kagi bills per request, separately from a subscription.

ponytail: DuckDuckGo HTML is scraped, so a markup change can break it. Swap in
a real API (Kagi, Brave) if that happens; the seam is this module.
"""

from __future__ import annotations

import html
import json
import os
import re
import urllib.parse
import urllib.request

from term_helper import render

DDG_URL = "https://html.duckduckgo.com/html/"
KAGI_URL = "https://kagi.com/api/v0/search"
UA = "Mozilla/5.0 (X11; Linux x86_64) term-helper"

RESULT_RE = re.compile(
    r'class="result__a"[^>]+href="(?P<url>[^"]+)"[^>]*>(?P<title>.*?)</a>', re.S
)
SNIPPET_RE = re.compile(r'class="result__snippet"[^>]*>(?P<snippet>.*?)</a>', re.S)
TAG_RE = re.compile(r"<[^>]+>")


def _clean(text: str) -> str:
    return html.unescape(TAG_RE.sub("", text)).strip()


def _unwrap(url: str) -> str:
    url = html.unescape(url)
    if "uddg=" in url:
        return urllib.parse.unquote(url.split("uddg=", 1)[1].split("&", 1)[0])
    return url


def parse_ddg(body: str, limit: int) -> list[str]:
    titles = RESULT_RE.findall(body)
    snippets = SNIPPET_RE.findall(body)
    out = []
    for i, (url, title) in enumerate(titles[:limit]):
        snippet = _clean(snippets[i]) if i < len(snippets) else ""
        out.append(f"- {_clean(title)}\n  {_unwrap(url)}\n  {snippet}")
    return out


def _ddg(query: str, limit: int) -> str:
    data = urllib.parse.urlencode({"q": query, "kl": "wt-wt"}).encode()
    request = urllib.request.Request(DDG_URL, data=data, headers={"User-Agent": UA})
    body = urllib.request.urlopen(request, timeout=15).read().decode("utf-8", "replace")
    return "\n".join(parse_ddg(body, limit))


def _kagi(query: str, limit: int, key: str) -> str:
    url = KAGI_URL + "?" + urllib.parse.urlencode({"q": query, "limit": limit})
    request = urllib.request.Request(
        url, headers={"Authorization": f"Bot {key}", "User-Agent": UA}
    )
    obj = json.load(urllib.request.urlopen(request, timeout=20))
    out = []
    for item in obj.get("data", []):
        if item.get("t") != 0:  # 0 = a web search result
            continue
        out.append(f"- {item.get('title', '')}\n  {item.get('url', '')}\n  "
                   f"{item.get('snippet', '')}")
    return "\n".join(out[:limit])


def run(cfg, query: str) -> str:
    """Run one web search. Returns text for the model, or a short error string."""
    limit = int(cfg.get("search_results", 5) or 5)
    key = os.environ.get("KAGI_API_KEY") or str(cfg.get("kagi_api_key", "") or "")
    try:
        if key:
            render.note(f"↗ web search (Kagi): {query}")
            return _kagi(query, limit, key)
        render.note(f"↗ web search (DuckDuckGo): {query}")
        return _ddg(query, limit)
    except Exception as exc:  # noqa: BLE001 - network, markup, quota, anything
        return f"<search failed: {exc}>"
