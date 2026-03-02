"""Web tools — search the web and fetch URL content.

Provides two tools for the AI agent:
  web_search  — search the web via DuckDuckGo (no API key needed)
  fetch_url   — fetch and extract text content from a URL

Uses only Python standard library (urllib, html.parser, re).
No external dependencies required.
"""

import logging
import re
import socket
import urllib.error
import urllib.parse
import urllib.request
from html.parser import HTMLParser

log = logging.getLogger(__name__)

_USER_AGENT = "Forge/1.0 (AI Coding Assistant)"
_TIMEOUT = 10  # seconds


# ---------------------------------------------------------------------------
# HTML text extraction
# ---------------------------------------------------------------------------

class _TextExtractor(HTMLParser):
    """Extract visible text from HTML, stripping tags and scripts."""

    _SKIP_TAGS = frozenset([
        "script", "style", "noscript", "svg", "head", "meta", "link",
    ])

    def __init__(self):
        super().__init__()
        self._pieces: list[str] = []
        self._skip_depth = 0

    def handle_starttag(self, tag, attrs):
        if tag.lower() in self._SKIP_TAGS:
            self._skip_depth += 1
        # Insert whitespace for block-level elements
        if tag.lower() in ("p", "div", "br", "li", "h1", "h2", "h3",
                           "h4", "h5", "h6", "tr", "td", "th",
                           "blockquote", "pre", "hr", "section",
                           "article", "header", "footer", "nav"):
            self._pieces.append("\n")

    def handle_endtag(self, tag):
        if tag.lower() in self._SKIP_TAGS and self._skip_depth > 0:
            self._skip_depth -= 1

    def handle_data(self, data):
        if self._skip_depth == 0:
            self._pieces.append(data)

    def handle_entityref(self, name):
        if self._skip_depth == 0:
            from html import unescape
            self._pieces.append(unescape(f"&{name};"))

    def handle_charref(self, name):
        if self._skip_depth == 0:
            from html import unescape
            self._pieces.append(unescape(f"&#{name};"))

    def get_text(self) -> str:
        text = "".join(self._pieces)
        # Collapse runs of whitespace, preserve paragraph breaks
        text = re.sub(r"[ \t]+", " ", text)
        text = re.sub(r"\n{3,}", "\n\n", text)
        return text.strip()


def _extract_text(html: str) -> str:
    """Extract visible text from HTML content."""
    extractor = _TextExtractor()
    try:
        extractor.feed(html)
    except Exception:
        # If the parser chokes, fall back to regex stripping
        text = re.sub(r"<script[^>]*>.*?</script>", "", html,
                       flags=re.DOTALL | re.IGNORECASE)
        text = re.sub(r"<style[^>]*>.*?</style>", "", text,
                       flags=re.DOTALL | re.IGNORECASE)
        text = re.sub(r"<[^>]+>", " ", text)
        text = re.sub(r"\s+", " ", text)
        return text.strip()
    return extractor.get_text()


# ---------------------------------------------------------------------------
# DuckDuckGo search result parser
# ---------------------------------------------------------------------------

class _DuckDuckGoParser(HTMLParser):
    """Parse DuckDuckGo HTML search results page.

    Extracts result titles, URLs, and snippets from the HTML response
    returned by https://html.duckduckgo.com/html/.
    """

    def __init__(self):
        super().__init__()
        self.results: list[dict] = []
        self._in_result_link = False
        self._in_snippet = False
        self._current: dict = {}
        self._current_text: list[str] = []

    def handle_starttag(self, tag, attrs):
        attr_dict = dict(attrs)
        cls = attr_dict.get("class", "")

        # Result title link: <a class="result__a" href="...">
        if tag == "a" and "result__a" in cls:
            self._in_result_link = True
            self._current = {"title": "", "url": "", "snippet": ""}
            self._current_text = []
            # Extract the real URL from DuckDuckGo's redirect
            href = attr_dict.get("href", "")
            self._current["url"] = self._extract_url(href)

        # Snippet: <a class="result__snippet" ...> or
        # <td class="result__snippet"> etc.
        if "result__snippet" in cls:
            self._in_snippet = True
            self._current_text = []

    def handle_endtag(self, tag):
        if self._in_result_link and tag == "a":
            self._in_result_link = False
            self._current["title"] = " ".join(
                "".join(self._current_text).split()
            )
            self._current_text = []

        if self._in_snippet and tag in ("a", "td", "div", "span"):
            self._in_snippet = False
            self._current["snippet"] = " ".join(
                "".join(self._current_text).split()
            )
            self._current_text = []
            # Snippet marks the end of a result block
            if self._current.get("title") and self._current.get("url"):
                self.results.append(self._current)
                self._current = {}

    def handle_data(self, data):
        if self._in_result_link or self._in_snippet:
            self._current_text.append(data)

    def _extract_url(self, href: str) -> str:
        """Extract the actual URL from DuckDuckGo's redirect wrapper.

        DDG wraps result URLs like:
          //duckduckgo.com/l/?uddg=https%3A%2F%2Fexample.com&rut=...
        """
        if "uddg=" in href:
            parsed = urllib.parse.urlparse(href)
            params = urllib.parse.parse_qs(parsed.query)
            uddg = params.get("uddg", [None])[0]
            if uddg:
                return uddg
        # If it's a direct link, just clean it up
        if href.startswith("//"):
            return "https:" + href
        return href


# ---------------------------------------------------------------------------
# URL safety checks
# ---------------------------------------------------------------------------

def _is_private_ip_addr(ip: str) -> bool:
    """Check if an IP address string (IPv4 or IPv6) is private/loopback."""
    try:
        import ipaddress
        addr = ipaddress.ip_address(ip.strip("[]"))
        return (addr.is_private or addr.is_loopback or addr.is_link_local
                or addr.is_reserved or addr.is_unspecified)
    except (ValueError, AttributeError):
        pass
    return False


def _is_private_ip(hostname: str) -> bool:
    """Check if a hostname resolves to a private/loopback IP address."""
    # Well-known local names
    if hostname.lower() in ("localhost", "::1"):
        return True

    # Block .local, .internal, .localhost domains
    hn_lower = hostname.lower()
    if (hn_lower.endswith(".local") or hn_lower.endswith(".internal")
            or hn_lower.endswith(".localhost") or hn_lower.endswith(".home.arpa")):
        return True

    # If it looks like a bare IP address, check directly
    if _is_private_ip_addr(hostname):
        return True

    # Resolve hostname — check BOTH IPv4 and IPv6 results
    for family in (socket.AF_INET, socket.AF_INET6):
        try:
            addr_info = socket.getaddrinfo(hostname, None, family,
                                           socket.SOCK_STREAM)
            for _fam, _stype, _proto, _canonname, sockaddr in addr_info:
                if _is_private_ip_addr(sockaddr[0]):
                    return True
        except socket.gaierror:
            pass  # Can't resolve — let urllib handle the error

    return False


def _validate_url(url: str) -> tuple[bool, str]:
    """Validate a URL for safety. Returns (is_safe, error_message)."""
    try:
        parsed = urllib.parse.urlparse(url)
    except Exception:
        return False, "Invalid URL format."

    # Must have a scheme
    if not parsed.scheme:
        return False, "URL must include a scheme (e.g. https://)."

    # Block file:// and other dangerous schemes
    if parsed.scheme.lower() not in ("http", "https"):
        return False, f"Blocked URL scheme: {parsed.scheme}. Only http/https allowed."

    # Must have a hostname
    hostname = parsed.hostname
    if not hostname:
        return False, "URL has no hostname."

    # Block private/local IPs
    if _is_private_ip(hostname):
        return False, f"Blocked: {hostname} resolves to a private/local address."

    return True, ""


# ---------------------------------------------------------------------------
# Tool implementations
# ---------------------------------------------------------------------------

def web_search(query: str, num_results: int = 5) -> str:
    """Search the web using DuckDuckGo and return results.

    Args:
        query: The search query string.
        num_results: Maximum number of results to return (default 5).
    """
    if not query or not query.strip():
        return "Error: search query cannot be empty."

    num_results = max(1, min(num_results, 20))

    # Build the request to DuckDuckGo HTML search
    params = urllib.parse.urlencode({"q": query.strip()})
    url = f"https://html.duckduckgo.com/html/?{params}"

    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": _USER_AGENT,
            "Accept": "text/html",
            "Accept-Language": "en-US,en;q=0.9",
        },
        method="GET",
    )

    try:
        with urllib.request.urlopen(req, timeout=_TIMEOUT) as resp:
            # Read and decode the response
            raw = resp.read()
            charset = resp.headers.get_content_charset() or "utf-8"
            try:
                html = raw.decode(charset)
            except (UnicodeDecodeError, LookupError):
                html = raw.decode("utf-8", errors="replace")
    except urllib.error.HTTPError as e:
        return f"Error: DuckDuckGo returned HTTP {e.code}: {e.reason}"
    except urllib.error.URLError as e:
        reason = str(e.reason) if hasattr(e, "reason") else str(e)
        return f"Error: Could not connect to DuckDuckGo: {reason}"
    except TimeoutError:
        return "Error: Search request timed out after 10 seconds."
    except Exception as e:
        return f"Error: Search failed: {type(e).__name__}: {e}"

    # Parse the results
    parser = _DuckDuckGoParser()
    try:
        parser.feed(html)
    except Exception as e:
        return f"Error: Failed to parse search results: {e}"

    results = parser.results[:num_results]

    if not results:
        return f"No results found for: {query}"

    # Format the output
    lines = [f"Search results for: {query}", ""]
    for i, r in enumerate(results, 1):
        title = r.get("title", "(no title)")
        url_str = r.get("url", "")
        snippet = r.get("snippet", "(no snippet)")
        lines.append(f"{i}. {title}")
        lines.append(f"   URL: {url_str}")
        lines.append(f"   {snippet}")
        lines.append("")

    lines.append(f"({len(results)} result(s) shown)")
    return "\n".join(lines)


def fetch_url(url: str, max_chars: int = 5000) -> str:
    """Fetch a URL and return extracted text content.

    Args:
        url: The URL to fetch (must be http or https).
        max_chars: Maximum characters of text to return (default 5000).
    """
    if not url or not url.strip():
        return "Error: URL cannot be empty."

    url = url.strip()

    # Add scheme if missing
    if not url.startswith(("http://", "https://")):
        url = "https://" + url

    # Safety validation
    is_safe, error = _validate_url(url)
    if not is_safe:
        return f"Error: {error}"

    max_chars = max(100, min(max_chars, 50000))

    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": _USER_AGENT,
            "Accept": "text/html,application/xhtml+xml,text/plain,*/*",
            "Accept-Language": "en-US,en;q=0.9",
            "Accept-Encoding": "identity",  # No compression for simplicity
        },
        method="GET",
    )

    try:
        # Use a custom redirect handler that validates each hop
        class _SafeRedirectHandler(urllib.request.HTTPRedirectHandler):
            def redirect_request(self, req, fp, code, msg, headers, newurl):
                safe, err = _validate_url(newurl)
                if not safe:
                    raise urllib.error.URLError(
                        f"Redirect blocked: {err}")
                return super().redirect_request(
                    req, fp, code, msg, headers, newurl)

        opener = urllib.request.build_opener(_SafeRedirectHandler)
        with opener.open(req, timeout=_TIMEOUT) as resp:
            content_type = resp.headers.get("Content-Type", "")
            final_url = resp.url

            # Don't try to read binary content
            if any(ct in content_type.lower() for ct in (
                "image/", "audio/", "video/", "application/pdf",
                "application/zip", "application/octet-stream",
                "application/gzip",
            )):
                return (f"Error: URL points to binary content "
                        f"({content_type}), cannot extract text.")

            # Read with a size limit to avoid downloading huge pages
            # Read up to 1MB of raw HTML
            raw = resp.read(1_000_000)
            charset = resp.headers.get_content_charset() or "utf-8"
            try:
                text = raw.decode(charset)
            except (UnicodeDecodeError, LookupError):
                text = raw.decode("utf-8", errors="replace")

    except urllib.error.HTTPError as e:
        return f"Error: HTTP {e.code}: {e.reason} — {url}"
    except urllib.error.URLError as e:
        reason = str(e.reason) if hasattr(e, "reason") else str(e)
        return f"Error: Could not connect: {reason} — {url}"
    except TimeoutError:
        return f"Error: Request timed out after {_TIMEOUT} seconds — {url}"
    except Exception as e:
        return f"Error: Fetch failed: {type(e).__name__}: {e}"

    # Extract text based on content type
    if "text/html" in content_type or "xhtml" in content_type or not content_type:
        extracted = _extract_text(text)
    else:
        # Plain text or similar — just use as-is
        extracted = text

    # Apply character limit
    if len(extracted) > max_chars:
        extracted = extracted[:max_chars] + f"\n\n... (truncated at {max_chars} chars)"

    if not extracted.strip():
        return f"Fetched {url} but no text content was extracted."

    header = f"Content from: {final_url}\n{'=' * 60}\n"
    return header + extracted


# ---------------------------------------------------------------------------
# Tool registration
# ---------------------------------------------------------------------------

def register_web_tools(registry):
    """Register all web tools with the given ToolRegistry."""

    registry.register(
        "web_search", web_search,
        "Search the web using DuckDuckGo. Returns a list of results "
        "with titles, URLs, and snippets. No API key required. Use this "
        "to find documentation, look up errors, or research topics.",
        {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "The search query",
                },
                "num_results": {
                    "type": "integer",
                    "description": "Number of results to return (1-20)",
                    "default": 5,
                },
            },
            "required": ["query"],
        },
    )

    registry.register(
        "fetch_url", fetch_url,
        "Fetch a URL and extract its text content (HTML tags stripped). "
        "Use this to read documentation pages, blog posts, or API "
        "references found via web_search. Only http/https URLs are allowed. "
        "Private/local network addresses are blocked for safety.",
        {
            "type": "object",
            "properties": {
                "url": {
                    "type": "string",
                    "description": "URL to fetch (http or https)",
                },
                "max_chars": {
                    "type": "integer",
                    "description": "Maximum characters of text to return",
                    "default": 5000,
                },
            },
            "required": ["url"],
        },
    )
