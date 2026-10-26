"""Allowlisted exports of publicly registered UKM entries, for GitHub only."""
from __future__ import annotations

from .source import API, SourceError, clean, html_text


def public_entries(value, event_url):
    """Discard all API fields except entry identity, names and description."""
    if not isinstance(value, list):
        raise SourceError("Ugyldig offentlig liste over påmeldte innslag")
    entries, seen = [], set()
    for entry in value:
        if not isinstance(entry, dict) or entry.get("object_type") != "innslag":
            raise SourceError("Ugyldig innslag i påmeldingslisten")
        identity, name = entry.get("id"), entry.get("navn")
        description = entry.get("beskrivelse") or ""
        if (not str(identity).isdigit() or int(identity) <= 0
                or not isinstance(name, str) or not clean(name)
                or not isinstance(description, str)):
            raise SourceError("Påmeldt innslag mangler gyldig ID, navn eller beskrivelse")
        identity = str(identity)
        if identity in seen:
            raise SourceError("Duplisert innslag i offentlig påmeldingsliste")
        seen.add(identity)
        people = entry.get("personer") or []
        if not isinstance(people, list):
            raise SourceError("Ugyldig navneliste på et påmeldt innslag")
        names = []
        for person in people:
            if not isinstance(person, dict) or not isinstance(person.get("navn"), str) or not clean(person["navn"]):
                raise SourceError("Ugyldig offentlig deltakernavn")
            names.append(clean(person["navn"]))
        entries.append({"id": identity, "navn": clean(name),
                        "beskrivelse": html_text(description, event_url), "deltakernavn": names})
    return sorted(entries, key=lambda entry: (entry["navn"].casefold(), entry["id"]))


def snapshot(records, stamp):
    """An empty list is a successful fetch; absent data is never counted as zero."""
    availability = ["registrations" in record for record in records]
    if availability and not any(availability):
        return None  # Older offline build callers without registration data.
    if not all(availability):
        raise SourceError("Ufullstendig påmeldingsuthenting. Forrige utgivelse beholdes.")
    events = []
    for record in records:
        event, entries = record["event"], record["registrations"]
        events.append({"arrangement_id": event["id"], "navn": event["title"],
                       "arrangement_url": event["url"],
                       "kilde": API + "/nettside:arrangement_innslag?arrangement_id=" + event["id"],
                       "antall_innslag": len(entries), "innslag": entries})
    return {"oppdatert": stamp, "omfang": "Kommende og pågående arrangementer i kalenderen",
            "merknad": "Offentlig påmeldte innslag og publiserte deltakernavn. Ikke en fullstendig liste over alle deltakere eller aktivitetspåmeldinger.",
            "antall_arrangementer": len(events),
            "antall_innslag": sum(event["antall_innslag"] for event in events),
            "antall_deltakernavn_i_innslag": sum(len(entry["deltakernavn"]) for event in events for entry in event["innslag"]),
            "arrangementer": events}
