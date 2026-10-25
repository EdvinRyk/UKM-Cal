"""Build an entire release before replacing the last successful snapshot."""
from __future__ import annotations

import html
import json
import os
import re
import tempfile
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, time
from pathlib import Path
from urllib.parse import quote, urljoin, urlparse

from .calendar import OSLO, is_test_county, make_calendar, normalize, revisions, short_name
from .source import Client, Document, SourceError, WEB, event_page, search_all, search_credentials


def read_json(path, default):
    return json.loads(path.read_text()) if path.exists() else default


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n")


def load(client, now, workers=4, progress=print):
    progress("Henter fylker, arrangementsoversikt og offentlig søk …")
    counties = client.api("alle_fylker")
    if not isinstance(counties, list) or not counties:
        raise SourceError("Fylkeslisten er tom eller ugyldig")
    counties = [c for c in counties if c.get("active") is True and c.get("fake") is False]
    if not counties or any(not re.fullmatch(r"[a-z0-9-]+", c.get("link", "")) for c in counties):
        raise SourceError("Ugyldige fylkeslenker")
    if len({c["link"] for c in counties}) != len(counties):
        raise SourceError("Dupliserte fylker")
    overview = client.text(WEB + "/arrangement")
    app, key = search_credentials(client, overview)
    hits, search_meta = search_all(client, app, key)
    upcoming = client.api("alle_kommende_arrangementer")
    if not isinstance(upcoming, list):
        raise SourceError("Ugyldig liste over kommende arrangementer")
    raw_by_path = {}
    for raw in upcoming:
        if not isinstance(raw, dict) or not raw.get("path"):
            raise SourceError("Ufullstendig arrangement i API-listen")
        raw_by_path[raw["path"]] = raw
    hit_by_path, paths = {}, set(raw_by_path)
    midnight = datetime.combine(now.astimezone(OSLO).date(), time(), OSLO)
    for hit in hits:
        path = hit.get("path")
        if not path:
            raise SourceError("Søkeresultat mangler path")
        hit_by_path[path] = hit
        timestamp = hit.get("endDate") or hit.get("startDate") or 0
        if timestamp:
            wall_time = datetime.fromtimestamp(timestamp / 1000, UTC).replace(tzinfo=None).replace(tzinfo=OSLO)
            if wall_time >= midnight:
                paths.add(path)
    # The national festival can be absent from Algolia. Follow explicit links
    # in the overview as well as the API list, without guessing event names/years.
    for node in Document(overview).nodes("a"):
        target = urlparse(urljoin(WEB, node.attrs.get("href", "")))
        match = re.fullmatch(r"/arrangement/([\w.-]+)/?", target.path)
        if target.netloc in ("www.ukm.no", "ukm.no") and match:
            path = match.group(1)
            if path not in hit_by_path:
                paths.add(path)
    progress(f"Komplett søkeliste: {len(hits)} arrangementer over {search_meta['pages']} sider. Kontrollerer {len(paths)} detaljsider …")

    def get(path):
        if not re.fullmatch(r"[\w.-]+", path):
            raise SourceError("Ugyldig arrangementspath")
        raw = raw_by_path.get(path)
        if raw is None:
            raw = client.api("single_arrangement", path=path)
        if not isinstance(raw, dict) or raw.get("path") != path or not raw.get("id"):
            raise SourceError("Detalj-API-et returnerte feil arrangement: " + path)
        if is_test_county(raw, counties):
            return None, {"id": raw["id"], "reason": "UKM markerer fylket som fake"}
        # Fetch all candidate pages, including extended festival layouts.
        page = event_page(client.text(WEB + "/arrangement/" + quote(path)), WEB + "/arrangement/" + path)
        normalized = normalize(raw, page, counties, hit_by_path.get(path))
        if datetime.fromisoformat(normalized["expires"]) <= now:
            return None, {"id": raw["id"], "reason": "avsluttet"}
        return {"raw": raw, "page": page, "event": normalized}, None

    records, skipped = [], []
    with ThreadPoolExecutor(max_workers=workers) as pool:
        for record, skip in pool.map(get, sorted(paths)):
            if record:
                records.append(record)
            if skip:
                skipped.append(skip)
    ids = [r["event"]["id"] for r in records]
    if len(ids) != len(set(ids)):
        raise SourceError("Samme arrangements-ID har flere aktive sider")
    records.sort(key=lambda r: (r["event"]["start"], r["event"]["id"]))
    checked = len(paths) - sum(s["reason"] == "UKM markerer fylket som fake" for s in skipped)
    return counties, records, {"search": search_meta, "upcoming_api_count": len(upcoming),
                               "checked_detail_pages": checked, "skipped": skipped}


STYLE = """
:root{color-scheme:dark;--ink:#edf5ef;--muted:#b1c4ba;--paper:#101b1a;--green:#a8dfbe;--card:#182725;--border:#344b43;--national:#22382b;--button-ink:#102c20;--accent-border:#6d9d7c;--preview:#3b321d}
*{box-sizing:border-box}body{margin:0;background:var(--paper);color:var(--ink);font:17px/1.55 system-ui,-apple-system,sans-serif}
main{max-width:1080px;margin:auto;padding:56px 24px}a{color:var(--green)}.eyebrow{font-size:13px;font-weight:750;letter-spacing:.15em;text-transform:uppercase}
h1{font-size:clamp(36px,6vw,64px);line-height:1.08;letter-spacing:-.045em;margin:16px 0 24px;max-width:800px}h2{font-size:24px;margin:0 0 10px}
.intro{max-width:750px;font-size:20px}.muted,small{color:var(--muted)}.status{margin:24px 0 40px;font-size:14px}.dot{color:var(--green)}
.how{border-left:4px solid var(--accent-border);padding:4px 22px;margin:32px 0 42px;max-width:820px}.how p{margin:8px 0}
.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(min(290px,100%),1fr));gap:16px}.card{background:var(--card);border:1px solid var(--border);border-radius:18px;padding:24px;display:flex;flex-direction:column;min-width:0}
.card.national{grid-column:1/-1;background:var(--national)}.count{margin:0 0 20px;color:var(--muted)}.actions{margin-top:auto;display:flex;gap:12px;align-items:center;flex-wrap:wrap}
.google{display:inline-block;background:var(--green);color:var(--button-ink);border-radius:9px;padding:10px 14px;text-decoration:none;font-size:14px;font-weight:650}
.copy{border:1px solid var(--accent-border);background:transparent;border-radius:9px;color:var(--ink);padding:9px 12px;font:inherit;font-size:14px;cursor:pointer}
.file{font-size:14px}.url{margin-top:16px;font-size:12px;overflow-wrap:anywhere;color:var(--muted)}footer{margin-top:44px;border-top:1px solid var(--border);padding-top:24px;font-size:14px}
a:focus-visible,button:focus-visible{outline:3px solid #e09f24;outline-offset:4px}.preview{padding:12px;background:var(--preview);border-radius:8px}
"""


def index_html(counties, events, generated_at, base_url):
    calendars = [("nasjonalt", "Nasjonale arrangementer")] + [(c["link"], short_name(c["navn"])) for c in counties]
    cards = []
    for slug, title in calendars:
        count = sum(slug in e["calendars"] for e in events)
        file = f"kalendere/{slug}.ics"
        url = base_url.rstrip("/") + "/" + file if base_url else ""
        google = "https://calendar.google.com/calendar/u/0/r?cid=" + quote(url, safe="") if url else "#"
        esc = html.escape
        cards.append(f'''<article class="card{' national' if slug == 'nasjonalt' else ''}">
<h2>{esc(title)}</h2><p class="count">{count} kommende og pågående arrangementer</p>
<div class="actions"><a class="google" data-google="{file}" href="{esc(google, quote=True)}" target="_blank" rel="noopener">Legg til i Google Kalender</a>
<button class="copy" type="button" data-copy="{file}">Kopier lenke</button>
<a class="file" href="{file}">iCal-fil</a></div>
<div class="url" data-url="{file}">{esc(url) if url else 'Abonnementslenken blir tilgjengelig ved publisering.'}</div></article>''')
    local = datetime.fromisoformat(generated_at).astimezone(OSLO).strftime("%d.%m.%Y kl. %H:%M")
    return f'''<!doctype html><html lang="nb" data-theme="dark"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="description" content="Abonner på UKM-arrangementer i ditt fylke eller på landsnivå. Daglig oppdaterte iCalendar-filer med full beskrivelse.">
<title>UKM i kalenderen din</title><style>{STYLE}</style></head><body><main>
<div class="eyebrow">Uavhengig kalenderoversikt · Data fra UKM</div>
<h1>Få UKM rett i kalenderen.</h1>
<p class="intro">Velg fylket ditt eller følg nasjonale arrangementer. Hver oppføring har tid, sted, hele arrangementsbeskrivelsen og relevante lenker.</p>
<p class="status"><span class="dot" aria-hidden="true">●</span> Kalenderfilene oppdateres daglig · Sist oppdatert {local} (norsk tid)</p>
<div class="how"><h2>Slik abonnerer du</h2><p>Bruk «Legg til i Google Kalender», eller kopier lenken og velg <strong>Andre kalendere → Fra nettadresse</strong> i Google Kalender på nett.</p>
<p class="muted">Google bestemmer når nye opplysninger hentes, så endringer kan vises senere enn tidspunktet ovenfor. Bruk abonnement for løpende oppdateringer; import av en nedlastet fil gir en engangskopi.</p>
<p class="muted">Fylkeskalenderne inneholder lokale og regionale arrangementer. Den nasjonale kalenderen inneholder bare arrangementer UKM har klassifisert på landsnivå.</p></div>
<p id="preview" class="preview" hidden>Dette er en lokal forhåndsvisning. Kalenderne må publiseres på en offentlig HTTPS-adresse før Google kan abonnere.</p>
<div class="grid">{''.join(cards)}</div><p id="feedback" role="status" aria-live="polite"></p>
<footer><p>Kilde: <a href="https://www.ukm.no/arrangement">UKMs offentlige arrangementssider</a>. Oversikten er en uavhengig tjeneste. Kontakt arrangøren via UKM for spørsmål om innholdet.</p>
<p>Bare kommende og pågående arrangementer tas med. Et tomt abonnement fylles automatisk når UKM publiserer aktuelle arrangementer. <a href="status.json">Oppdateringsstatus</a>.</p></footer>
</main><script>
const base = new URL('./', location.href);
const local = !['http:', 'https:'].includes(base.protocol) || ['localhost', '127.0.0.1', '[::1]'].includes(base.hostname);
const publicBase = {json.dumps(base_url.rstrip('/') + '/' if base_url else '')};
function feed(path) {{ return new URL(path, publicBase || base).href; }}
document.querySelectorAll('[data-url]').forEach(el => {{ if (!local || publicBase) el.textContent = feed(el.dataset.url); }});
document.querySelectorAll('[data-google]').forEach(el => {{
  if (local && !publicBase) {{ el.removeAttribute('href'); el.setAttribute('aria-disabled', 'true'); }}
  else el.href = 'https://calendar.google.com/calendar/u/0/r?cid=' + encodeURIComponent(feed(el.dataset.google));
}});
document.querySelectorAll('[data-copy]').forEach(el => el.addEventListener('click', async () => {{
  const out = document.querySelector('#feedback');
  if (local && !publicBase) {{ out.textContent = 'Publiser kalenderne først for å få abonnementslenker.'; return; }}
  try {{ await navigator.clipboard.writeText(feed(el.dataset.copy)); out.textContent = 'Kalenderlenken er kopiert.'; }}
  catch {{ out.textContent = 'Kopier denne lenken: ' + feed(el.dataset.copy); }}
}}));
document.querySelector('#preview').hidden = !local || !!publicBase;
</script></body></html>'''


def build(output, counties, records, metadata, now, base_url="", allow_empty=False):
    output = Path(output).absolute()
    if output.is_symlink() or output == output.parent or output.name in (".", ".."):
        raise SourceError("Ugyldig utmappe")
    if output.exists() and any(output.iterdir()) and not (output / "data/status.json").is_file():
        raise SourceError("Utmappe inneholder andre filer; velg en egen generert mappe")
    if base_url and (urlparse(base_url).scheme != "https" or not urlparse(base_url).netloc or urlparse(base_url).query or urlparse(base_url).fragment):
        raise SourceError("Publiseringsadressen må være en HTTPS-adresse uten query/fragment")
    events = [record["event"] for record in records]
    previous_snapshot = read_json(output / "data/latest.json", {"events": []})
    old_active = [e for e in previous_snapshot["events"] if datetime.fromisoformat(e["event"]["expires"]) > now]
    if not allow_empty and (not metadata["search"]["hits"] or (old_active and not events)):
        raise SourceError("Uventet tom kilde/kalender. Forrige versjon beholdes; kontroller UKM før --allow-empty brukes.")
    if not metadata["search"].get("complete"):
        raise SourceError("Ufullstendig kilde skal aldri publiseres")
    previous_state = read_json(output / "data/events-state.json", {})
    state = revisions(events, previous_state, now)
    stamp = now.astimezone(UTC).isoformat()
    names = {c["link"]: "UKM – " + short_name(c["navn"]) for c in counties}
    names["nasjonalt"] = "UKM – Nasjonale arrangementer"
    status = {"last_success": stamp, "event_count": len(events), "calendar_count": len(names),
              "calendars": {slug: sum(slug in e["calendars"] for e in events) for slug in names},
              "sources": metadata, "base_url": base_url or None}
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".ukm-release-", dir=output.parent) as temp:
        stage = Path(temp) / "release"
        site = stage / "site"
        (site / "kalendere").mkdir(parents=True)
        for slug, name in names.items():
            content = make_calendar(name, [e for e in events if slug in e["calendars"]], state)
            if not content.endswith(b"END:VCALENDAR\r\n") or any(len(line) > 75 for line in content.split(b"\r\n")):
                raise SourceError("Kalenderfilen besto ikke validering")
            (site / "kalendere" / (slug + ".ics")).write_bytes(content)
        (site / "index.html").write_text(index_html(counties, events, stamp, base_url))
        (site / ".nojekyll").touch()
        write_json(site / "status.json", status)
        write_json(stage / "data/status.json", status)
        write_json(stage / "data/events-state.json", state)
        write_json(stage / "data/latest.json", {"generated_at": stamp, "counties": counties, "events": records})
        # Only this final replacement mutates the last successful release.
        backup = Path(temp) / "previous"
        if output.exists():
            os.replace(output, backup)
        try:
            os.replace(stage, output)
        except BaseException:
            if backup.exists():
                os.replace(backup, output)
            raise
    return status


def update(output, base_url="", now=None, client=None, workers=4, allow_empty=False):
    now = now or datetime.now(UTC)
    counties, records, metadata = load(client or Client(), now, workers)
    return build(output, counties, records, metadata, now, base_url, allow_empty)
