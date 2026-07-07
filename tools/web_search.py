import logging
import httpx

logger = logging.getLogger(__name__)

SCHEMA = {
    "name": "web_search",
    "description": "Search the web for current information on a topic.",
    "parameters": {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "The search query",
            }
        },
        "required": ["query"],
    },
}


def _search_duckduckgo(query):
    """Search via DuckDuckGo Instant Answer API (free, no key required)."""
    try:
        resp = httpx.get(
            "https://api.duckduckgo.com/",
            params={"q": query, "format": "json", "no_html": 1, "skip_disambig": 1},
            timeout=10,
        )
        data = resp.json()
        abstract = data.get("AbstractText")
        if abstract:
            source = data.get("AbstractSource", "")
            url = data.get("AbstractURL", "")
            result = abstract
            if source:
                result += f"\n(Source: {source})"
            if url:
                result += f"\n{url}"
            return result

        # Try related topics
        topics = data.get("RelatedTopics", [])
        snippets = []
        for t in topics:
            if isinstance(t, dict) and t.get("Text"):
                snippets.append(t["Text"])
                if len(snippets) >= 5:
                    break
        if snippets:
            return " | ".join(snippets)
        return None
    except Exception as e:
        logger.warning("DuckDuckGo search failed: %s", e)
        return None


def _search_google_html(query):
    """Crude Google fallback — parses organic result snippets from HTML.
    Slow and fragile; only used when DuckDuckGo returns nothing.
    """
    try:
        headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            )
        }
        resp = httpx.get(
            "https://www.google.com/search",
            params={"q": query, "hl": "en"},
            headers=headers,
            timeout=10,
        )
        from html.parser import HTMLParser

        class ResultParser(HTMLParser):
            def __init__(self):
                super().__init__()
                self.results = []
                self._capture = False
                self._depth = 0

            def handle_starttag(self, tag, attrs):
                attrs_dict = dict(attrs)
                if tag == "span" and attrs_dict.get("class") == "aCOpRe":
                    self._capture = True
                    self._depth += 1

            def handle_endtag(self, tag):
                if self._capture:
                    self._depth -= 1
                    if self._depth <= 0:
                        self._capture = False

            def handle_data(self, data):
                if self._capture and data.strip():
                    self.results.append(data.strip())

        parser = ResultParser()
        parser.feed(resp.text)
        if parser.results:
            return " | ".join(parser.results[:3])
        return None
    except Exception as e:
        logger.warning("Google HTML fallback failed: %s", e)
        return None


def run(query):
    """Free web search. Tries DuckDuckGo first, then falls back to scraping
    Google organic results. Returns a string of snippets.
    """
    result = _search_duckduckgo(query)
    if result:
        return result

    logger.info("DDG returned nothing, trying Google fallback for '%s'", query)
    result = _search_google_html(query)
    if result:
        return result

    return "No results found. Try rephrasing the query."
