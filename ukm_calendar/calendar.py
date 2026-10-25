"""Normalize UKM wall-clock dates and serialize RFC 5545 calendars."""
from __future__ import annotations

import hashlib
import json
import re
from datetime import UTC, date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from .source import SourceError, clean, html_text, safe_url, WEB

OSLO = ZoneInfo("Europe/Oslo")


def utc_stamp(value):
    return value.astimezone(UTC).strftime("%Y%m%dT%H%M%SZ")


def source_date(raw, key):
    """UKM labels Norwegian wall time as UTC. Match the website, not that label.

    Verified against public winter/summer pages. Do not convert the API's
    numeric epoch to Oslo: that would add an incorrect one/two hours.
    """
    structured = raw.get(key + "_date")
    value = structured.get("date") if isinstance(structured, dict) else None
    if value:
        try:
            parsed = datetime.fromisoformat(value)
            naive = parsed.replace(tzinfo=None)
        except ValueError as error:
            raise SourceError(f"Ugyldig {key}-dato for {raw.get('id')}") from error
    else:
        epoch = raw.get(key)
        if not epoch:
            return None
        try:
            epoch = float(epoch)
            naive = datetime.fromtimestamp(epoch / 1000 if epoch > 100_000_000_000 else epoch, UTC).replace(tzinfo=None)
        except (ValueError, TypeError, OverflowError) as error:
            raise SourceError("Ugyldig tidsstempel") from error
    local = naive.replace(tzinfo=OSLO)
    # Fail visibly on nonexistent times at the spring DST transition.
    if local.astimezone(UTC).astimezone(OSLO).replace(tzinfo=None) != naive:
        raise SourceError(f"Klokkeslettet finnes ikke i norsk tid: {naive}")
    if local.fold == 0 and local.utcoffset() != local.replace(fold=1).utcoffset():
        raise SourceError(f"Tvetydig klokkeslett ved overgang til vintertid: {naive}")
    return local


def short_name(name):
    return name.split(" - ")[0].strip()


def county_memberships(raw, counties, hit=None):
    if raw.get("type") == "land":
        return ["nasjonalt"]
    if raw.get("type") not in ("kommune", "fylke"):
        raise SourceError(f"Ukjent arrangementsnivå: {raw.get('type')}")
    by_id = {str(c["id"]): c["link"] for c in counties}
    by_name = {short_name(c["navn"]).casefold(): c["link"] for c in counties}
    memberships = set()

    def add(identity, name):
        slug = by_id.get(str(identity)) or by_name.get(short_name(name or "").casefold())
        if slug:
            memberships.add(slug)

    county = raw.get("fylke") or {}
    add(county.get("id"), county.get("navn"))
    for municipality in raw.get("kommuner") or []:
        add(municipality.get("fylke_id"), municipality.get("fylke_navn"))
    for location in (hit or {}).get("locations", []):
        add(None, location.split(" > ")[0])
    if not memberships:
        raise SourceError(f"Ingen reelle fylker for arrangement {raw.get('id')}")
    return sorted(memberships)


def is_test_county(raw, counties):
    county = raw.get("fylke") or {}
    return raw.get("type") != "land" and county.get("fake") is True and not any(
        str(county.get("id")) == str(c["id"]) for c in counties)


def cancelled(raw, page_text):
    for key in ("avlyst", "cancelled", "canceled", "isCancelled"):
        if raw.get(key) in (True, 1, "true", "1"):
            return True
    if str(raw.get("status", "")).casefold() in ("cancelled", "canceled", "avlyst"):
        return True
    if re.match(r"^\s*(?:avlyst|cancelled)\s*[:–—-]", raw.get("navn", ""), re.I):
        return True
    return bool(re.search(r"(?im)^\s*(?:arrangementet er avlyst[.!]?|avlyst)\s*$", page_text))


def normalize(raw, page, counties, hit=None):
    identity = str(raw["id"])
    path = raw.get("path", "")
    if not identity.isdigit() or not path or "/" in path or not re.fullmatch(r"[\w.-]+", path):
        raise SourceError("Ugyldig arrangementsidentitet eller path")
    start, end = source_date(raw, "start"), source_date(raw, "stop")
    if start is None:
        raise SourceError(f"Arrangement {identity} mangler startdato")
    if end and end < start:
        raise SourceError(f"Arrangement {identity} slutter før det starter")
    shown = set(page.get("displayed_times", []))
    for value in (start, end):
        if value and shown and value.strftime("%H:%M") not in shown:
            raise SourceError(f"Datoene stemmer ikke med synlig klokkeslett for {identity}")
    date_only = len(str((raw.get("start_date") or {}).get("date", ""))) == 10
    all_day = raw.get("all_day") is True or date_only or (
        not shown and start.time() == time() and (not end or end.time() == time()))
    if all_day:
        start_value = start.date()
        # UKM stop is the final day, whereas iCalendar DTEND is exclusive.
        end_value = (end.date() if end else start_value) + timedelta(days=1)
        starts, ends = start_value.isoformat(), end_value.isoformat()
        expires = datetime.combine(end_value, time(), OSLO)
    else:
        starts, ends = start.isoformat(), end.isoformat() if end and end > start else None
        expires = end if end and end > start else datetime.combine(start.date() + timedelta(days=1), time(), OSLO)
    url = WEB + "/arrangement/" + path
    description = page["text"]
    api_description = html_text(raw.get("beskrivelse") or "", url)
    def simplify(value):
        value = re.sub(r"\s*\((?:https?|mailto|tel):[^)]+\)", "", value)
        return re.sub(r"\s+", " ", value).strip()
    if api_description and simplify(api_description) not in simplify(description):
        description += "\n\n" + api_description
    extras = []
    for link in raw.get("paamelding_lenker") or []:
        target = safe_url(link.get("lenke", ""), url)
        if target and target not in description:
            label = next((c.get("navn", "") for c in raw.get("kommuner", []) if c.get("id") == link.get("id")), "")
            extras.append(f"Påmelding{(' – ' + label) if label else ''}: {target}")
    for number, label in ((1, "delta"), (2, "bidra bak scenen")):
        deadline = source_date(raw, f"paameldingsfrist_{number}")
        if deadline and deadline <= (end or start):
            extras.append(f"Påmeldingsfrist – {label}: {deadline:%d.%m.%Y kl. %H:%M}")
    banner = raw.get("bannerImage") or (hit or {}).get("bannerImage")
    if isinstance(banner, dict):
        banner = banner.get("UKM_banner_image_large") or banner.get("UKM_banner_image")
    if isinstance(banner, str) and banner and banner not in description:
        target = safe_url(banner, url)
        if target:
            extras.append("Arrangementsbilde: " + target)
    if url not in description:
        extras.append("Arrangementsside: " + url)
    description = clean(description + "\n\n" + "\n".join(dict.fromkeys(extras)))
    municipality_names = list(dict.fromkeys(c["navn"] for c in raw.get("kommuner", []) if c.get("navn")))
    venue = clean(raw.get("sted") or "")
    location = ", ".join([venue] + [name for name in municipality_names if name.casefold() not in venue.casefold()])
    return {"id": identity, "uid": f"ukm-arrangement-{identity}@ukm-kalendere", "title": raw["navn"],
            "url": url, "location": location, "description": description,
            "start": starts, "end": ends, "all_day": all_day, "expires": expires.isoformat(),
            "calendars": county_memberships(raw, counties, hit),
            "status": "CANCELLED" if cancelled(raw, page["text"]) else "CONFIRMED"}


def revisions(events, previous, now):
    """Keep revision metadata even for removed events, so reappearing IDs stay stable."""
    state = dict(previous)
    stamp = utc_stamp(now)
    for event in events:
        fingerprint = hashlib.sha256(json.dumps(event, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
        old = state.get(event["id"], {})
        changed = old.get("fingerprint") != fingerprint
        state[event["id"]] = {
            "fingerprint": fingerprint,
            "sequence": old.get("sequence", -1) + 1 if changed else old["sequence"],
            "modified": stamp if changed else old["modified"],
            "created": old.get("created", stamp),
        }
    return state


def escape(value):
    return str(value).replace("\\", "\\\\").replace("\r\n", "\n").replace("\r", "\n").replace("\n", "\\n").replace(";", "\\;").replace(",", "\\,")


def fold_line(line):
    """RFC 5545 lines are at most 75 octets, without splitting UTF-8 codepoints."""
    parts, part, size = [], "", 0
    for char in line:
        width = len(char.encode("utf-8"))
        if size + width > 75:
            parts.append(part)
            part, size = " ", 1
        part += char
        size += width
    parts.append(part)
    return "\r\n".join(parts)


def make_calendar(name, events, state):
    lines = ["BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//UKM-kalendere//NO", "CALSCALE:GREGORIAN",
             "METHOD:PUBLISH", "X-WR-CALNAME:" + escape(name), "X-WR-TIMEZONE:Europe/Oslo",
             "REFRESH-INTERVAL;VALUE=DURATION:P1D", "X-PUBLISHED-TTL:P1D"]
    for event in sorted(events, key=lambda e: (e["start"], e["id"])):
        revision = state[event["id"]]
        lines += ["BEGIN:VEVENT", "UID:" + event["uid"], "DTSTAMP:" + revision["modified"],
                  "CREATED:" + revision["created"], "LAST-MODIFIED:" + revision["modified"],
                  "SEQUENCE:" + str(revision["sequence"])]
        if event["all_day"]:
            lines += ["DTSTART;VALUE=DATE:" + date.fromisoformat(event["start"]).strftime("%Y%m%d"),
                      "DTEND;VALUE=DATE:" + date.fromisoformat(event["end"]).strftime("%Y%m%d")]
        else:
            lines.append("DTSTART:" + utc_stamp(datetime.fromisoformat(event["start"])))
            if event["end"]:
                lines.append("DTEND:" + utc_stamp(datetime.fromisoformat(event["end"])))
        lines += ["SUMMARY:" + escape(event["title"]), "DESCRIPTION:" + escape(event["description"]),
                  "LOCATION:" + escape(event["location"]), "URL:" + event["url"],
                  "STATUS:" + event["status"], "TRANSP:TRANSPARENT", "END:VEVENT"]
    lines.append("END:VCALENDAR")
    return ("\r\n".join(fold_line(line) for line in lines) + "\r\n").encode("utf-8")
