"""pkmncards.com provider."""

from __future__ import annotations

import json
import logging
import re
from urllib.parse import quote_plus, urljoin, urlsplit, urlunsplit

import httpx
from bs4 import BeautifulSoup, Tag

from ptcg_art_scraper.models import CardAsset, CardRef, FetchedImage
from ptcg_art_scraper.net.http import RateLimiter, fetch_bytes, fetch_text
from ptcg_art_scraper.providers.base import BaseProvider

logger = logging.getLogger(__name__)

BASE_URL = "https://pkmncards.com"
_IMAGE_PATH_RE = re.compile(r"\.(?:png|jpe?g|webp)$", re.IGNORECASE)


def _normalize_label(value: str) -> str:
    """Normalize metadata labels for resilient matching."""
    return re.sub(r"[^a-z0-9]+", "", value.lower())


def _extract_card_number(raw: str) -> str:
    """Extract the printed card number from a raw number string."""
    cleaned = raw.strip().lstrip("#")
    if not cleaned:
        return ""
    m = re.search(r"(\d+[a-z]?)", cleaned, flags=re.IGNORECASE)
    if m:
        return m.group(1)
    if "/" in cleaned:
        return cleaned.split("/", 1)[0].strip()
    return cleaned


def _set_slug_from_url(url: str) -> str:
    """Extract set slug from ``/set/{slug}/`` URLs."""
    normalized = _normalize_url(url)
    parsed = urlsplit(normalized)
    parts = [p for p in parsed.path.split("/") if p]
    if len(parts) >= 2 and parts[-2] == "set":
        return parts[-1]
    return ""


def _slug_from_card_url(url: str) -> str:
    """Extract the card slug from a pkmncards card URL."""
    parsed = urlsplit(url)
    parts = [p for p in parsed.path.split("/") if p]
    if len(parts) >= 2 and parts[-2] == "card":
        return parts[-1]
    return ""


def _slug_to_card_url(slug: str) -> str:
    """Build a canonical card-page URL from a card slug."""
    return _normalize_url(f"{BASE_URL}/card/{slug}/")


def _card_url_from_image_url(url: str) -> str | None:
    """Best-effort conversion from image URL to card-page URL."""
    normalized = _normalize_url(url)
    parsed = urlsplit(normalized)
    if "/wp-content/uploads/" not in parsed.path:
        return None
    if not _IMAGE_PATH_RE.search(parsed.path):
        return None

    filename = parsed.path.rsplit("/", 1)[-1]
    stem = re.sub(r"\.(?:png|jpe?g|webp)$", "", filename, flags=re.IGNORECASE)
    stem = re.sub(r"-\d+x\d+$", "", stem)  # remove WP thumbnail suffixes
    stem = stem.replace("_", "-").strip("-").lower()
    if not stem:
        return None
    m_locale = re.match(
        r"en-us-(?P<set>[a-z0-9]+)-(?P<num>\d+[a-z]?)-(?P<name>.+)$",
        stem,
    )
    if m_locale:
        guessed_slug = (
            f"{m_locale.group('name').strip('-')}-"
            f"{m_locale.group('set')}-{m_locale.group('num')}"
        ).strip("-")
        if guessed_slug:
            return _slug_to_card_url(guessed_slug)
    if not re.search(r"-\d+[a-z]?$", stem):
        # Most card slugs end in the printed number; skip uncertain conversions.
        return None
    return _slug_to_card_url(stem)


def _coerce_card_page_url(url: str, *, base_url: str = BASE_URL) -> str | None:
    """Return a card-page URL from a raw search href (or ``None``)."""
    normalized = _normalize_url(url, base_url=base_url)
    parsed = urlsplit(normalized)
    if "/card/" in parsed.path:
        slug = _slug_from_card_url(normalized)
        if slug:
            return _slug_to_card_url(slug)
        return normalized
    return _card_url_from_image_url(normalized)


def _set_code_and_number_from_slug(slug: str) -> tuple[str, str]:
    """Infer set code and number from a card slug."""
    cleaned = slug.strip().lower()
    m = re.search(r"-([a-z0-9]+)-(\d+[a-z]?)$", cleaned)
    if m:
        return m.group(1), m.group(2)
    return "", ""


def _set_info_from_title(title: str) -> tuple[str, str, str, str]:
    """Extract card name, set name, set code and number from page title."""
    cleaned = " ".join(title.split())
    cleaned = re.sub(r"\s*\|\s*pkmncards(?:\.com)?\s*$", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\s*-\s*pkmncards(?:\.com)?\s*$", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\s*[‹<\u2039]\s*pkmncards(?:\.com)?\s*$", "", cleaned, flags=re.IGNORECASE)
    if not cleaned:
        return "", "", "", ""

    # e.g. "Aggron · Ruby & Sapphire (RS) #1"
    m = re.search(
        r"^(?P<name>.+?)\s*(?:·|Â·)\s*(?P<set>.+?)\s*(?:\((?P<code>[^)]+)\))?\s*#(?P<num>[A-Za-z0-9-]+)$",
        cleaned,
    )
    if m:
        card_name = m.group("name").strip()
        set_name = m.group("set").strip()
        set_code = (m.group("code") or "").strip().lower()
        number = m.group("num").strip()
        return card_name, set_name, set_code, number

    # e.g. "Charizard ex - 100/197"
    m2 = re.search(
        r"^(?P<name>.+?)\s*(?:–|-|â€“)\s*(?P<num>\d+)\s*/\s*\d+$",
        cleaned,
    )
    if m2:
        # Keep the original title text as name for compatibility.
        return cleaned, "", "", m2.group("num").strip()
    return cleaned, "", "", ""


def _guess_name_from_slug(
    slug: str,
    *,
    set_slug: str = "",
    set_code: str = "",
    number: str = "",
) -> str:
    """Best-effort conversion of a card slug to a readable card name."""
    working = slug.strip().lower()
    if not working:
        return ""

    if set_code and number:
        suffix = f"-{set_code}-{number.lower()}"
        if working.endswith(suffix):
            working = working[: -len(suffix)]
    if set_slug:
        normalized_set = set_slug.strip().strip("/").lower()
        suffix = f"-{normalized_set}"
        if working.endswith(suffix):
            working = working[: -len(suffix)]

    working = working.strip("-")
    if not working:
        return ""
    return " ".join(part.capitalize() for part in working.split("-") if part)


def _encode_ref_metadata(meta: dict[str, str]) -> str:
    """Serialize non-empty metadata hints into ``CardRef.card_id``."""
    cleaned: dict[str, str] = {}
    for key, value in meta.items():
        val = str(value).strip()
        if val:
            cleaned[key] = val
    if not cleaned:
        return ""
    return json.dumps(cleaned, separators=(",", ":"), ensure_ascii=False)


def _parse_search_rows(
    html: str,
    *,
    base_url: str = BASE_URL,
) -> list[tuple[str, dict[str, str]]]:
    """Extract card URL + metadata hints from full-display search rows."""
    soup = BeautifulSoup(html, "html.parser")
    out: list[tuple[str, dict[str, str]]] = []
    seen: set[str] = set()

    row_selectors = (
        ".entry-content .entry-inner table tbody tr",
        ".entry-content table tbody tr",
        "table tbody tr",
    )
    rows: list[Tag] = []
    for selector in row_selectors:
        rows = list(soup.select(selector))
        if rows:
            break

    for row in rows:
        link = row.select_one(
            "a.card-image-otherwise-text, a.card-image-link, "
            "a[href*='/card/'], a[href*='/wp-content/uploads/']"
        )
        if link is None:
            continue

        href = str(link.get("href", ""))
        if not href:
            continue
        card_url = _coerce_card_page_url(href, base_url=base_url)
        if not card_url or card_url in seen:
            continue

        slug = _slug_from_card_url(card_url)
        set_code, slug_number = _set_code_and_number_from_slug(slug)

        set_name = ""
        set_slug = ""
        set_link = row.select_one("a[href*='/set/']")
        if set_link is not None:
            set_name = set_link.get_text(" ", strip=True)
            set_slug = _set_slug_from_url(str(set_link.get("href", "")))

        card_link = row.select_one("a[href*='/card/']")
        name = card_link.get_text(" ", strip=True) if card_link is not None else ""

        number = ""
        cells = row.find_all("td", recursive=False)
        if len(cells) >= 4:
            number = _extract_card_number(cells[3].get_text(" ", strip=True))
        if not number:
            number = slug_number

        if not name:
            name = _guess_name_from_slug(
                slug, set_slug=set_slug, set_code=set_code, number=number
            )

        image_url = ""
        img = row.select_one("img")
        if img is not None:
            src = str(img.get("src", ""))
            if src:
                image_url = _normalize_url(src, base_url=base_url)

        meta = {
            "name": name,
            "set_name": set_name,
            "set_code": set_code,
            "number": number,
            "image_url": image_url,
        }
        out.append((card_url, meta))
        seen.add(card_url)

    # Current search layout uses <article> cards instead of table rows.
    for article in soup.select("article.type-pkmn_card.entry"):
        card_anchor = article.select_one("h2.card-title a[href*='/card/'], a[href*='/card/']")
        if card_anchor is None:
            continue
        href = str(card_anchor.get("href", "")).strip()
        if not href:
            continue
        card_url = _coerce_card_page_url(href, base_url=base_url)
        if not card_url or card_url in seen:
            continue

        title_text = _text_of_any(
            article,
            ("h2.card-title a span", "h2.card-title a", "h2.card-title", "h1.card-title"),
        )
        title_name, _title_set_name, title_set_code, title_number = _set_info_from_title(title_text)

        release_meta = article.select_one(".release-meta")
        set_name = ""
        set_code = title_set_code
        number = title_number
        if release_meta is not None:
            set_name = _text_of_any(
                release_meta,
                ("span[title='Set'] a", "span[title='Set']"),
            )
            set_code = _text_of(release_meta, "span[title='Set Abbreviation']") or set_code
            number = _extract_card_number(
                _text_of_any(release_meta, (".number a", ".number"))
            ) or number

        if not number:
            slug = _slug_from_card_url(card_url)
            _, slug_number = _set_code_and_number_from_slug(slug)
            number = slug_number

        name = title_name or title_text
        image_url = ""
        image_link = article.select_one("a.card-image-link[href*='/wp-content/uploads/']")
        if image_link is not None:
            image_url = _normalize_url(str(image_link.get("href", "")), base_url=base_url)

        meta = {
            "name": _collapse_ws(name),
            "set_name": set_name,
            "set_code": set_code,
            "number": number,
            "image_url": image_url,
        }
        out.append((card_url, meta))
        seen.add(card_url)

    return out


def _parse_search_results(html: str) -> list[str]:
    """Extract card-page URLs from a pkmncards.com search-results page."""
    soup = BeautifulSoup(html, "html.parser")
    urls: list[str] = []
    seen: set[str] = set()

    selectors = (
        "a.card-image-otherwise-text",
        "a.card-image-link",
        "a[href*='/card/']",
        "a[href*='/wp-content/uploads/']",
    )
    for selector in selectors:
        for a_tag in soup.select(selector):
            href = a_tag.get("href")
            if not href:
                continue
            card_url = _coerce_card_page_url(str(href), base_url=BASE_URL)
            if card_url and card_url not in seen:
                seen.add(card_url)
                urls.append(card_url)

    if not urls:
        # Fallback: look for entry links inside card list items
        for a_tag in soup.select(".entry-title a, article a"):
            href = a_tag.get("href")
            if not href:
                continue
            card_url = _coerce_card_page_url(str(href), base_url=BASE_URL)
            if card_url and card_url not in seen:
                seen.add(card_url)
                urls.append(card_url)
    return urls


def _normalize_url(url: str, *, base_url: str = BASE_URL) -> str:
    """Return an absolute URL without fragment."""
    abs_url = urljoin(base_url, url)
    parsed = urlsplit(abs_url)
    return urlunsplit(
        (parsed.scheme, parsed.netloc, parsed.path, parsed.query, "")
    )


def _next_page_url(html: str, *, current_url: str = "") -> str | None:
    """Return the next-page URL from pagination, or *None*."""
    soup = BeautifulSoup(html, "html.parser")
    selectors = (
        "a.next.page-numbers",
        "a.nextpostslink",
        ".nav-links a.next",
        "a[rel='next']",
        "link[rel='next']",
    )
    for selector in selectors:
        nxt = soup.select_one(selector)
        if nxt is None:
            continue
        href = nxt.get("href")
        if href:
            return _normalize_url(str(href), base_url=current_url or BASE_URL)

    # Fallback for alternate pagination markup.
    for a_tag in soup.select("a[href]"):
        href = a_tag.get("href")
        if not href:
            continue
        label = a_tag.get_text(" ", strip=True).lower()
        classes = " ".join(a_tag.get("class", []))
        rel = " ".join(a_tag.get("rel", []))
        aria = str(a_tag.get("aria-label", "")).lower()
        marker = f"{classes} {rel} {aria}".lower()
        if (
            "next" in marker
            or label.startswith("next")
            or label.startswith("older")
            or label in {">>", "»"}
        ):
            return _normalize_url(str(href), base_url=current_url or BASE_URL)
    return None


def _text_of(soup: BeautifulSoup | Tag, selector: str) -> str:
    """Return stripped text of the first element matching *selector*, or ''."""
    el = soup.select_one(selector)
    return el.get_text(strip=True) if el else ""


def _text_of_any(soup: BeautifulSoup | Tag, selectors: tuple[str, ...]) -> str:
    """Return the first non-empty value across multiple CSS selectors."""
    for selector in selectors:
        value = _text_of(soup, selector)
        if value:
            return value
    return ""


def _abbr_title_of(soup: BeautifulSoup | Tag, selector: str = "abbr[title]") -> str:
    """Return the title attribute of the first matching <abbr>, if any."""
    el = soup.select_one(selector)
    if el is None:
        return ""
    return str(el.get("title", "")).strip()


def _collapse_ws(value: str) -> str:
    """Collapse runs of whitespace to a single space."""
    return " ".join(value.split())


def _first_named_span_text(paragraph: Tag) -> str:
    """Return the first meaningful <span> text in a paragraph."""
    for span in paragraph.find_all("span"):
        classes = set(span.get("class", []))
        if "vh" in classes:
            continue
        if span.find_parent("abbr") is not None:
            continue
        text = _collapse_ws(span.get_text(" ", strip=True))
        if text:
            return text
    return ""


def _extract_info_field(rows: list[Tag], label: str) -> str:
    """Search table rows / info divs for a labelled value."""
    target = _normalize_label(label)
    for row in rows:
        # Common structure: <tr><th>Label</th><td>Value</td></tr>
        th = row.find("th")
        td = row.find("td")
        if th and td:
            header = _normalize_label(th.get_text(" ", strip=True))
            if target in header:
                value = td.get_text(" ", strip=True)
                if value:
                    return value

        # Alternate structure: <dt>Label</dt><dd>Value</dd>
        dt = row.find("dt")
        dd = row.find("dd")
        if dt and dd:
            header = _normalize_label(dt.get_text(" ", strip=True))
            if target in header:
                value = dd.get_text(" ", strip=True)
                if value:
                    return value

        # Fallback for two-cell rows without headers.
        cells = row.find_all("td", recursive=False)
        if len(cells) >= 2:
            header = _normalize_label(cells[0].get_text(" ", strip=True))
            if target in header:
                value = cells[1].get_text(" ", strip=True)
                if value:
                    return value

        # Fallback for plain "Label: Value" text rows.
        text = row.get_text(" ", strip=True)
        if ":" in text:
            lhs, rhs = text.split(":", 1)
            if target in _normalize_label(lhs):
                value = rhs.strip()
                if value:
                    return value
    return ""


def _classify_basic_type(raw_type: str, name: str) -> str:
    """Determine basicType as 'Pokemon', 'Trainer', or 'Energy'."""
    combined = f"{raw_type} {name}".lower()
    if "energy" in combined:
        return "Energy"
    trainer_keywords = ("trainer", "supporter", "item", "stadium", "tool")
    for kw in trainer_keywords:
        if kw in combined:
            return "Trainer"
    return "Pokemon"


def _parse_attacks(soup: BeautifulSoup | Tag) -> list[dict]:
    """Extract attack info from the card page."""
    attacks: list[dict] = []
    for section in soup.select(".pokemon-attack, .card-attack, .attack"):
        name = _text_of(section, ".attack-name, .name")
        damage = _text_of(section, ".attack-damage, .damage")
        text = _text_of(section, ".attack-text, .text")
        cost_els = section.select(".attack-cost img, .cost img, .energy-icon")
        cost = [str(el.get("alt", el.get("title", ""))) for el in cost_els]
        if name:
            attacks.append({"name": name, "damage": damage, "text": text, "cost": cost})
    if attacks:
        return attacks

    # Current pkmncards layout uses paragraph-based attack rows.
    for paragraph in soup.select(".card-tabs .tab.text .text p"):
        raw_text = _collapse_ws(paragraph.get_text(" ", strip=True))
        if "→" not in raw_text:
            continue

        name = _first_named_span_text(paragraph)
        if not name:
            continue

        # Attack energy symbols carry their type in the <abbr title="..."> elements.
        cost = [
            str(el.get("title", "")).strip()
            for el in paragraph.select("abbr[title]")
            if str(el.get("title", "")).strip()
        ]

        after_name = raw_text.split(name, 1)[1].strip() if name in raw_text else raw_text
        if after_name.startswith(":"):
            after_name = after_name[1:].strip()

        damage = ""
        text = after_name
        m = re.match(r"(?P<dmg>\d{1,4}[+×x\-]?)\s*(?P<rest>.*)$", after_name)
        if m:
            damage = m.group("dmg")
            text = m.group("rest").strip()

        attacks.append({"name": name, "damage": damage, "text": text, "cost": cost})
    return attacks


def _parse_abilities(soup: BeautifulSoup | Tag) -> list[dict]:
    """Extract ability/poke-power/poke-body info."""
    abilities: list[dict] = []
    for section in soup.select(".pokemon-ability, .card-ability, .ability"):
        name = _text_of(section, ".ability-name, .name")
        kind = _text_of(section, ".ability-type, .type")
        text = _text_of(section, ".ability-text, .text")
        if name:
            abilities.append({"name": name, "type": kind, "text": text})
    if abilities:
        return abilities

    prefixes = {
        "ability": "Ability",
        "poké-power": "Poké-Power",
        "poke-power": "Poké-Power",
        "pokémon power": "Pokemon Power",
        "pokemon power": "Pokemon Power",
        "poké-body": "Poké-Body",
        "poke-body": "Poké-Body",
        "ancient trait": "Ancient Trait",
    }

    for paragraph in soup.select(".card-tabs .tab.text .text p"):
        raw_text = _collapse_ws(paragraph.get_text(" ", strip=True))
        if not raw_text or "→" in raw_text:
            continue

        lowered = raw_text.lower()
        ability_type = ""
        for prefix, normalized in prefixes.items():
            if lowered.startswith(prefix):
                ability_type = normalized
                break
        if not ability_type:
            continue

        name = _first_named_span_text(paragraph)
        text = raw_text
        if name and name in text:
            text = text.split(name, 1)[1].lstrip(" :")
        else:
            tail = re.sub("^[^\u21d2\u21e2:]+(?:\u21d2|\u21e2|:)\\s*", "", text).strip()
            if tail:
                # Many ability rows are plain text: "Ability ⇒ Name Once during your turn..."
                keyword_index = -1
                for marker in (
                    " Once ",
                    " During ",
                    " If ",
                    " When ",
                    " While ",
                    " As long as ",
                    " Your ",
                    " You may ",
                    " Each ",
                    " Prevent ",
                    " Search ",
                    " Flip ",
                    " Choose ",
                    " Attach ",
                ):
                    idx = tail.find(marker)
                    if idx > 0 and (keyword_index < 0 or idx < keyword_index):
                        keyword_index = idx
                if keyword_index > 0:
                    name = tail[:keyword_index].strip(" :")
                    text = tail[keyword_index:].strip()
                else:
                    text = tail
            else:
                text = ""
        abilities.append({"name": name, "type": ability_type, "text": text})
    return abilities


def _parse_weakness_resistance(
    rows: list[Tag], label: str, *, soup: BeautifulSoup | Tag | None = None
) -> dict[str, str]:
    """Return {type, value} for weakness or resistance."""
    if soup is not None:
        cls = "weak" if label.lower().startswith("weak") else "resist"
        section = soup.select_one(f".weak-resist-retreat .{cls}")
        if section is not None:
            section_text = _collapse_ws(section.get_text(" ", strip=True))
            if "n/a" in section_text.lower():
                return {}
            type_name = _abbr_title_of(section, "abbr[title]")
            value = _text_of(section, "span[title*='Modifier']")
            if type_name:
                return {"type": type_name, "value": value.strip()}

    raw = _extract_info_field(rows, label)
    if not raw:
        return {}
    # Common patterns: "Fire ×2", "Grass -30"
    m = re.match(r"([A-Za-z]+)\s*([×x+\-]\s*\d+)?", raw)
    if m:
        return {"type": m.group(1), "value": (m.group(2) or "").strip()}
    return {"type": raw, "value": ""}


def parse_card_page(html: str, page_url: str = "") -> CardAsset:
    """Parse a pkmncards.com card detail page into a :class:`CardAsset`."""
    soup = BeautifulSoup(html, "html.parser")

    # --- image URL ---
    image_url = ""
    img_tag = soup.select_one("div.entry-content img")
    if img_tag is None:
        img_tag = soup.select_one("img.card-image")
    if img_tag is None:
        img_tag = soup.select_one("article img")
    if img_tag:
        image_url = str(img_tag.get("src", ""))
    if not image_url:
        og_image = soup.select_one("meta[property='og:image']")
        if og_image is not None:
            image_url = str(og_image.get("content", ""))

    # --- name ---
    name = ""
    title_el = (
        soup.select_one("h1.card-title")
        or soup.select_one("h1.entry-title")
        or soup.select_one("h2.entry-title")
        or soup.select_one("h1")
    )
    if title_el:
        name = title_el.get_text(strip=True)
    if not name:
        og_title = soup.select_one("meta[property='og:title']")
        if og_title is not None:
            name = str(og_title.get("content", "")).strip()
    if not name and soup.title is not None:
        name = soup.title.get_text(strip=True)
    title_name, title_set_name, title_set_code, title_number = _set_info_from_title(name)
    if title_name:
        name = title_name

    card_name = _text_of_any(
        soup,
        (
            ".name-hp-color .name a",
            ".name-hp-color .name",
        ),
    )
    if card_name:
        name = card_name

    # --- Collect info rows once ---
    info_rows: list[Tag] = list(
        soup.select(
            "table tr, .card-tab-otherwise-text div, .entry-content tr, "
            ".entry-content li, .entry-content p"
        )
    )

    # --- set / number from breadcrumbs or page text ---
    release_meta = soup.select_one(".release-meta")
    release_set_name = ""
    release_set_code = ""
    release_number = ""
    release_rarity = ""
    if release_meta is not None:
        release_set_name = _text_of_any(
            release_meta,
            ("span[title='Set'] a", "span[title='Set']"),
        )
        release_set_code = _text_of(release_meta, "span[title='Set Abbreviation']")
        release_number = _text_of_any(
            release_meta,
            (".number a", ".number"),
        )
        release_rarity = _text_of_any(
            release_meta,
            (".rarity a", ".rarity"),
        )

    set_name = release_set_name or _extract_info_field(info_rows, "set") or title_set_name
    number = _extract_card_number(release_number or _extract_info_field(info_rows, "number"))
    if not number and title_number:
        number = _extract_card_number(title_number)

    # Try parsing name like "Charizard ex - 100/197"
    if not number and name:
        m = re.search(r"(\d+)\s*/\s*\d+", name)
        if m:
            number = m.group(1)

    # Attempt set code/number fallback from URL segments (e.g. /card/{slug}/)
    set_code = release_set_code or title_set_code
    if page_url:
        slug = _slug_from_card_url(page_url)
        slug_set_code, slug_number = _set_code_and_number_from_slug(slug)
        if not set_code:
            set_code = slug_set_code
        if not number and slug_number:
            number = slug_number

    if not set_name and set_code:
        # Keep template grouping stable even with partial metadata.
        set_name = set_code

    # --- Rich metadata ---
    type_meta = soup.select_one(".type-evolves-is")
    raw_type = ""
    specific_type = ""
    evolves_from = ""
    if type_meta is not None:
        raw_type = _text_of_any(type_meta, (".type a", ".type"))
        specific_type = _text_of_any(
            type_meta,
            (".stage a", ".stage", ".sub-type a", ".sub-type"),
        )
        specific_type = re.sub(r"^[()\s]+|[()\s]+$", "", specific_type)
        evolves_from = _text_of_any(
            type_meta,
            (".evolves a:last-child", ".evolves a", ".evolves"),
        )
    if not raw_type:
        raw_type = _extract_info_field(info_rows, "type")
    if not specific_type:
        specific_type = _extract_info_field(info_rows, "stage") or _extract_info_field(
            info_rows, "sub"
        )
    basic_type = _classify_basic_type(raw_type or specific_type, name)

    if not evolves_from:
        evolves_from = _extract_info_field(info_rows, "evolves from")

    hp_raw = _text_of_any(soup, (".name-hp-color .hp a", ".name-hp-color .hp")) or _extract_info_field(
        info_rows, "hp"
    )
    hp = 0
    if hp_raw:
        hp_match = re.search(r"\d+", hp_raw)
        if hp_match:
            hp = int(hp_match.group())

    color = _abbr_title_of(soup, ".name-hp-color .color abbr[title]") or _text_of_any(
        soup,
        (".name-hp-color .color a", ".name-hp-color .color"),
    ) or _extract_info_field(info_rows, "color") or _extract_info_field(info_rows, "type")

    rarity = release_rarity or _extract_info_field(info_rows, "rarity")
    artist = _text_of_any(soup, (".illus a", ".illus")) or _extract_info_field(info_rows, "artist")
    artist = re.sub(r"^illus\.\s*", "", artist, flags=re.IGNORECASE)

    retreat_raw = _text_of_any(
        soup,
        (
            ".weak-resist-retreat .retreat a abbr",
            ".weak-resist-retreat .retreat abbr",
            ".weak-resist-retreat .retreat a",
            ".weak-resist-retreat .retreat",
        ),
    ) or _extract_info_field(info_rows, "retreat")
    retreat_cost = 0
    if retreat_raw:
        rc_match = re.search(r"\d+", retreat_raw)
        if rc_match:
            retreat_cost = int(rc_match.group())

    attacks = _parse_attacks(soup)
    abilities = _parse_abilities(soup)
    weaknesses = _parse_weakness_resistance(info_rows, "weakness", soup=soup)
    resistances = _parse_weakness_resistance(info_rows, "resistance", soup=soup)

    return CardAsset(
        name=name,
        set_name=set_name,
        set_code=set_code,
        number=number,
        rarity=rarity,
        artist=artist,
        image_url=image_url,
        source_page_url=page_url,
        provider="pkmncards",
        basic_type=basic_type,
        specific_type=specific_type,
        evolves_from=evolves_from,
        hp=hp,
        color=color,
        attacks=attacks,
        abilities=abilities,
        weaknesses=weaknesses,
        resistances=resistances,
        retreat_cost=retreat_cost,
    )


class PkmnCardsProvider(BaseProvider):
    """Scraper for pkmncards.com."""

    name = "pkmncards"

    def get_image_url(self, set_code: str, card_number: str) -> str | None:
        del set_code, card_number
        logger.info(
            "%s failed deterministically: card URLs require search/discovery and cannot be constructed",
            self.name,
        )
        return None

    async def search(
        self,
        client: httpx.AsyncClient,
        query: str,
        *,
        set_filter: str = "",
        limit: int = 0,
        rate_limiter: RateLimiter | None = None,
    ) -> list[CardRef]:
        refs: list[CardRef] = []
        seen_refs: set[str] = set()
        seen_pages: set[str] = set()
        search_url = f"{BASE_URL}/?s={quote_plus(query)}&display=full"
        if set_filter:
            joiner = "&" if "?" in search_url else "?"
            search_url += f"{joiner}set={quote_plus(set_filter)}"

        page_url: str | None = search_url
        while page_url:
            normalized_page = _normalize_url(page_url)
            if normalized_page in seen_pages:
                break
            seen_pages.add(normalized_page)

            html = await fetch_text(client, normalized_page, rate_limiter=rate_limiter)
            row_entries = _parse_search_rows(html, base_url=normalized_page)
            for card_url, meta in row_entries:
                normalized_ref = _normalize_url(card_url, base_url=normalized_page)
                if normalized_ref in seen_refs:
                    continue
                seen_refs.add(normalized_ref)
                refs.append(
                    CardRef(
                        provider=self.name,
                        url=normalized_ref,
                        card_id=_encode_ref_metadata(meta),
                    )
                )
                if 0 < limit <= len(refs):
                    return refs

            card_urls = _parse_search_results(html)
            for u in card_urls:
                normalized_ref = _normalize_url(u, base_url=normalized_page)
                if normalized_ref in seen_refs:
                    continue
                seen_refs.add(normalized_ref)
                refs.append(CardRef(provider=self.name, url=normalized_ref))
                if 0 < limit <= len(refs):
                    return refs
            page_url = _next_page_url(html, current_url=normalized_page)
        return refs

    async def resolve(
        self,
        client: httpx.AsyncClient,
        ref: CardRef,
        *,
        rate_limiter: RateLimiter | None = None,
    ) -> CardAsset:
        page_url = _coerce_card_page_url(ref.url) or _normalize_url(ref.url)
        html = await fetch_text(client, page_url, rate_limiter=rate_limiter)
        asset = parse_card_page(html, page_url=page_url)
        if not asset.image_url:
            # If metadata page fails to expose the image, preserve original source.
            if _IMAGE_PATH_RE.search(urlsplit(ref.url).path):
                asset.image_url = _normalize_url(ref.url)
        return asset

    async def fetch_image(
        self,
        client: httpx.AsyncClient,
        asset: CardAsset,
        *,
        rate_limiter: RateLimiter | None = None,
    ) -> FetchedImage:
        if not asset.image_url:
            raise ValueError(f"No image URL for card {asset.name!r}")
        data = await fetch_bytes(client, asset.image_url, rate_limiter=rate_limiter)
        ext = asset.image_url.rsplit(".", 1)[-1].lower()
        mime = f"image/{'jpeg' if ext in ('jpg', 'jpeg') else ext}"
        return FetchedImage(data=data, mime_type=mime, source_url=asset.image_url)
