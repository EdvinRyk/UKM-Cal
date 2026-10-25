"""Read-only clients for UKM's public API, search index and event pages."""
from __future__ import annotations

import json
import re
import time
from html.parser import HTMLParser
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, urlencode, urljoin, urlparse
from urllib.request import Request, urlopen

API = "https://api.ukm.no"
WEB = "https://www.ukm.no"
INDEX = "events_prod"


class SourceError(RuntimeError):
    pass


class Client:
    def __init__(self, attempts=3):
        self.attempts = attempts

    def text(self, url, headers=None):
        for attempt in range(self.attempts):
            try:
                request = Request(url, headers={
                    "User-Agent": "UKM-kalendere/1.0 (public iCalendar reader)",
                    **(headers or {}),
                })
                with urlopen(request, timeout=45) as response:
                    data = response.read(15_000_001)
                    if len(data) > 15_000_000:
                        raise SourceError("For stort svar fra " + url)
                    return data.decode("utf-8")
            except (HTTPError, URLError, TimeoutError, ConnectionError) as error:
                if isinstance(error, HTTPError) and error.code not in (429, 500, 502, 503, 504):
                    raise SourceError(f"HTTP {error.code}: {url}") from error
                if attempt == self.attempts - 1:
                    raise SourceError(f"Kunne ikke hente {url}: {error}") from error
                time.sleep(2 ** attempt)
        raise AssertionError("unreachable")

    def json(self, url, headers=None):
        try:
            return json.loads(self.text(url, headers))
        except (json.JSONDecodeError, UnicodeDecodeError) as error:
            raise SourceError("Ugyldig JSON fra " + url) from error

    def api(self, method, **params):
        return self.json(API + "/nettside:" + method + ("?" + urlencode(params) if params else ""))


class Node:
    def __init__(self, tag="root", attrs=()):
        self.tag, self.attrs, self.children = tag, dict(attrs), []

    def walk(self):
        yield self
        for child in self.children:
            if isinstance(child, Node):
                yield from child.walk()

    def plain(self):
        return "".join(c.plain() if isinstance(c, Node) else c for c in self.children)


class Document(HTMLParser):
    VOID = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "param", "source", "track", "wbr"}

    def __init__(self, html):
        super().__init__(convert_charrefs=True)
        self.root = Node()
        self.stack = [self.root]
        self.feed(html)

    def handle_starttag(self, tag, attrs):
        node = Node(tag, attrs)
        self.stack[-1].children.append(node)
        if tag not in self.VOID:
            self.stack.append(node)

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)
        if tag not in self.VOID:
            self.handle_endtag(tag)

    def handle_endtag(self, tag):
        for i in range(len(self.stack) - 1, 0, -1):
            if self.stack[i].tag == tag:
                del self.stack[i:]
                break

    def handle_data(self, data):
        self.stack[-1].children.append(data)

    def nodes(self, tag):
        return [node for node in self.root.walk() if node.tag == tag]


def clean(text):
    text = text.replace("\r\n", "\n").replace("\r", "\n").replace("\xa0", " ")
    text = re.sub(r"[ \t]+", " ", text)
    return re.sub(r"\n{3,}", "\n\n", "\n".join(line.strip() for line in text.splitlines())).strip()


def safe_url(value, base=WEB):
    if not value:
        return ""
    url = urljoin(base, value)
    if urlparse(url).scheme in ("http", "https", "mailto", "tel") and not any(ord(c) < 32 for c in url):
        return url
    return ""


def render_text(node, base=WEB, page=False):
    if isinstance(node, str):
        return node
    skip = {"script", "style", "svg", "head", "footer", "header", "button", "noscript", "template"}
    if page:
        skip |= {"nav"}
    if node.tag in skip or "hidden" in node.attrs or node.attrs.get("aria-hidden") == "true":
        return ""
    if node.tag == "br":
        return "\n"
    text = "".join(render_text(c, base, page) for c in node.children)
    if node.tag == "a":
        href = safe_url(node.attrs.get("href", ""), base)
        label = clean(text) or node.attrs.get("aria-label", "") or node.attrs.get("title", "")
        if href and not node.attrs.get("href", "").startswith("#"):
            text = label if href in label else f"{label} ({href})" if label else href
    if node.tag in ("iframe", "video", "audio"):
        href = safe_url(node.attrs.get("src", ""), base)
        text += "\n" + href if href else ""
    if node.tag == "img":
        href = safe_url(node.attrs.get("src", ""), base)
        if urlparse(href).path == "/_next/image":
            href = safe_url(parse_qs(urlparse(href).query).get("url", [href])[0], base)
        if href:
            text = f"\n{node.attrs.get('alt') or 'Bilde'}: {href}\n"
    if node.tag in ("div", "p", "section", "article", "li", "h1", "h2", "h3", "h4", "ul", "ol", "table", "tr"):
        text = "\n" + text + "\n"
    return text


def html_text(html, base=WEB):
    return clean(render_text(Document(html).root, base))


def event_page(html, url):
    """Extract only the public event body; never crawl linked news articles."""
    document = Document(html)
    mains = document.nodes("main")
    headings = document.nodes("h1")
    if not mains or not headings or "NEXT_HTTP_ERROR_FALLBACK;404" in html:
        raise SourceError("Arrangementssiden mangler innhold: " + url)
    main = mains[0]
    text = clean(render_text(main, url, page=True))
    # FAQ links concern UKM generally, not this particular event.
    text = re.sub(r"Ofte stilte spørsmål\s*Hva er UKM\?\s*\([^\n]*\)", "", text)
    text = text.replace("Hopp til hovedinnhold", "")
    # Desktop/mobile layouts repeat identical blocks. Keep one copy per paragraph.
    blocks, seen = [], set()
    for block in re.split(r"\n\s*\n", clean(text)):
        if block and block not in seen:
            blocks.append(block)
            seen.add(block)
    links = []
    for n in main.walk():
        if n.tag != "a":
            continue
        target = safe_url(n.attrs.get("href", ""), url)
        # Keep event navigation (program/media) as links, without its decorative UI.
        if target.startswith(url.rstrip("/") + "/"):
            label = clean(n.plain())
            if label:
                links.append(f"{label}: {target}")
    displayed_times = set()
    for n in main.walk():
        if n.tag == "p" and "leading-tight" in n.attrs.get("class", ""):
            displayed_times.update(re.findall(r"\b\d{1,2}:\d{2}\b", n.plain()))
    # UKM streams contact cards after </main>. Their publicly supplied client
    # props include the phone/email shown when a user opens the contact card.
    contacts, seen_contacts = [], set()
    decoder = json.JSONDecoder()
    for script in document.nodes("script"):
        for match in re.finditer(r'self\.__next_f\.push\((.*)\)\s*;?\s*$', script.plain(), re.S):
            try:
                frame = json.loads(match.group(1))
            except json.JSONDecodeError:
                continue
            if len(frame) < 2 or not isinstance(frame[1], str):
                continue
            payload = frame[1]
            for candidate in re.finditer(r'\{(?="(?:image|name)"\s*:)', payload):
                try:
                    value = decoder.raw_decode(payload[candidate.start():])[0]
                except json.JSONDecodeError:
                    continue
                if not isinstance(value, dict) or not value.get("name") or not (value.get("phone") or value.get("email")):
                    continue
                identity = (value["name"], value.get("phone"), value.get("email"))
                if identity in seen_contacts:
                    continue
                seen_contacts.add(identity)
                contact = [value["name"]]
                if value.get("description"):
                    contact.append(html_text(value["description"], url))
                if value.get("phone"):
                    contact.append("Telefon: " + value["phone"])
                if value.get("email"):
                    contact.append("E-post: " + value["email"])
                contacts.append("\n".join(contact))
    if contacts:
        blocks.append("Kontaktpersoner\n" + "\n\n".join(contacts))
    return {"title": clean(headings[0].plain()), "text": clean("\n\n".join(blocks + list(dict.fromkeys(links)))),
            "displayed_times": sorted(displayed_times)}


def search_credentials(client, html):
    """Discover the same public, read-only credentials UKM ships to browsers."""
    scripts = [n.attrs.get("src", "") for n in Document(html).nodes("script")]
    for src in scripts:
        if not src.startswith("/_next/static/"):
            continue
        js = client.text(urljoin(WEB, src))
        # Match the literal Algolia client constructor, not unrelated strings.
        match = re.search(r'\}\(\s*"([A-Z0-9]{10})"\s*,\s*"([a-f0-9]{32})"\s*\)', js)
        if match and "searchClient" in js and "algolia" in js.lower():
            return match.group(1), match.group(2)
    raise SourceError("Fant ikke UKMs offentlige søkeklient. Ingen kalenderfiler er endret.")


def search_all(client, app, key, page_size=100):
    hits, seen = [], set()
    page, expected, pages = 0, None, None
    headers = {"X-Algolia-Application-Id": app, "X-Algolia-API-Key": key, "Referer": WEB + "/"}
    while True:
        url = f"https://{app}-dsn.algolia.net/1/indexes/{INDEX}?" + urlencode({
            "query": "", "page": page, "hitsPerPage": page_size,
        })
        result = client.json(url, headers)
        if not isinstance(result, dict) or not all(k in result for k in ("hits", "nbHits", "nbPages", "page")):
            raise SourceError("Søkelisten har endret format")
        total, total_pages = result["nbHits"], result["nbPages"]
        if expected is None:
            expected, pages = total, total_pages
        if (total, total_pages) != (expected, pages) or result["page"] != page:
            raise SourceError("Søkelisten endret seg under uthenting; prøv igjen")
        if result.get("exhaustiveNbHits") is False:
            raise SourceError("Søket garanterer ikke en komplett resultatliste")
        for hit in result["hits"]:
            identity = str(hit["objectID"])
            if identity in seen:
                raise SourceError("Duplikat i søkepaginering")
            seen.add(identity)
            hits.append(hit)
        page += 1
        if page >= pages:
            break
        if not result["hits"] or page > 10000:
            raise SourceError("Ufullstendig søkepaginering")
    if len(hits) != expected:
        raise SourceError(f"Ufullstendig søkeliste: {len(hits)} av {expected}")
    return hits, {"index": INDEX, "hits": expected, "pages": pages, "complete": True}
