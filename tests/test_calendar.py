from copy import deepcopy
from datetime import UTC, date, datetime, timedelta
import json
from pathlib import Path
import tempfile
import unittest

from ukm_calendar.calendar import (OSLO, backstage_deadline, cancelled, county_memberships, is_test_county,
                                   make_calendar, normalize, revisions, source_date)
from ukm_calendar.publish import build
from ukm_calendar.source import SourceError, event_page, search_all

try:
    from icalendar import Calendar
except ImportError:
    Calendar = None

FIXTURES = Path(__file__).parent / "fixtures"
COUNTIES = [
    {"id": 46, "link": "vestland", "navn": "Vestland"},
    {"id": 3, "link": "oslo", "navn": "Oslo"},
    {"id": 33, "link": "buskerud", "navn": "Buskerud"},
]
NOW = datetime(2026, 10, 25, 10, tzinfo=UTC)


def fixture(name="local"):
    raw = json.loads((FIXTURES / f"{name}-api.json").read_text())
    page = event_page((FIXTURES / f"{name}-page.html").read_text(), "https://www.ukm.no/arrangement/" + raw["path"])
    return raw, page


def event(name="local"):
    raw, page = fixture(name)
    return normalize(raw, page, COUNTIES)


class SourceTests(unittest.TestCase):
    def test_all_pages_including_next_year(self):
        pages = [
            {"page": 0, "nbPages": 2, "nbHits": 3, "hits": [{"objectID": "1"}, {"objectID": "2"}]},
            {"page": 1, "nbPages": 2, "nbHits": 3, "hits": [{"objectID": "3", "name": "Festival 2027"}]},
        ]
        class Client:
            def json(self, url, headers):
                self.last_url = url
                return pages.pop(0)
        client = Client()
        hits, meta = search_all(client, "ABCDEFGHIJ", "read-only", 2)
        self.assertEqual([h["objectID"] for h in hits], ["1", "2", "3"])
        self.assertTrue(meta["complete"])
        self.assertIn("page=1", client.last_url)

    def test_incomplete_or_changing_search_fails(self):
        class Client:
            def json(self, *_):
                return {"page": 0, "nbPages": 1, "nbHits": 2, "hits": [{"objectID": "1"}]}
        with self.assertRaises(SourceError):
            search_all(Client(), "ABCDEFGHIJ", "public")

    def test_duplicate_search_pages_fail(self):
        class Client:
            n = -1
            def json(self, *_):
                self.n += 1
                return {"page": self.n, "nbPages": 2, "nbHits": 2, "hits": [{"objectID": "1"}]}
        with self.assertRaises(SourceError):
            search_all(Client(), "ABCDEFGHIJ", "public")

    def test_real_local_and_festival_layouts(self):
        for name in ("local", "regional", "national"):
            raw, page = fixture(name)
            self.assertIn(raw["navn"], page["text"])
            self.assertTrue(page["displayed_times"])
            self.assertNotIn("Hopp til hovedinnhold", page["text"])
            self.assertNotIn("Ofte stilte spørsmål", page["text"])
        self.assertIn("pop-art-portrett", event()["description"])
        self.assertIn("/program", event("regional")["description"])

    def test_streamed_contact_cards_and_media_links(self):
        props = {"image": "", "name": "Kontakt (UKM)", "phone": "12345678", "email": "kontakt@example.org"}
        frame = json.dumps([1, "2:[" + json.dumps(props) + "]"])
        html = '<main><h1>UKM</h1><p>Hele teksten</p><iframe src="https://example.org/video"></iframe></main>'
        html += '<script>self.__next_f.push(' + frame + ')</script><footer>Unrelated</footer>'
        page = event_page(html, "https://www.ukm.no/arrangement/test")
        self.assertIn("kontakt@example.org", page["text"])
        self.assertIn("12345678", page["text"])
        self.assertIn("https://example.org/video", page["text"])
        self.assertNotIn("Unrelated", page["text"])

    def test_not_found_page_fails(self):
        with self.assertRaises(SourceError):
            event_page('<main><h2>404</h2></main>', 'https://www.ukm.no/arrangement/missing')


class CalendarTests(unittest.TestCase):
    def test_real_clock_is_16_oslo_not_17(self):
        value = event()
        start = datetime.fromisoformat(value["start"])
        self.assertEqual(start.hour, 16)
        self.assertEqual(start.utcoffset(), timedelta(hours=1))

    def test_summer_clock_and_national_classification(self):
        value = event("national")
        start = datetime.fromisoformat(value["start"])
        self.assertEqual(start.hour, 17)
        self.assertEqual(start.utcoffset(), timedelta(hours=2))
        self.assertEqual(value["calendars"], ["nasjonalt"])
        self.assertEqual(event("regional")["calendars"], ["oslo"])

    def test_cross_county_membership_and_legacy_county_name(self):
        raw, _ = fixture()
        raw["kommuner"].append({"navn": "Teststed", "fylke_id": 33, "fylke_navn": "Buskerud"})
        raw["fylke"]["id"] = 999
        self.assertEqual(county_memberships(raw, COUNTIES), ["buskerud", "vestland"])

    def test_unknown_county_and_level_fail(self):
        raw, _ = fixture()
        raw["kommuner"] = []
        raw["fylke"] = {"id": 999, "navn": "Ukjent"}
        with self.assertRaises(SourceError):
            county_memberships(raw, COUNTIES)
        raw["type"] = "unknown"
        with self.assertRaises(SourceError):
            county_memberships(raw, COUNTIES)

    def test_test_counties_excluded_but_national_fake_allowed(self):
        raw, _ = fixture()
        raw["fylke"] = {"id": 21, "fake": True}
        self.assertTrue(is_test_county(raw, COUNTIES))
        raw["type"] = "land"
        self.assertFalse(is_test_county(raw, COUNTIES))

    def test_date_only_has_exclusive_end(self):
        raw, page = fixture()
        raw["start_date"]["date"] = "2027-04-01"
        raw["stop_date"]["date"] = "2027-04-03"
        page["displayed_times"] = []
        value = normalize(raw, page, COUNTIES)
        self.assertTrue(value["all_day"])
        self.assertEqual(value["start"], "2027-04-01")
        self.assertEqual(value["end"], "2027-04-04")

    def test_missing_end_does_not_invent_duration(self):
        raw, page = fixture()
        raw.pop("stop_date")
        raw["stop"] = 0
        self.assertIsNone(normalize(raw, page, COUNTIES)["end"])

    def test_wrong_visible_clock_fails(self):
        raw, page = fixture()
        page["displayed_times"] = ["17:00", "21:00"]
        with self.assertRaises(SourceError):
            normalize(raw, page, COUNTIES)

    def test_dst_ambiguity_is_not_guessed(self):
        for day in ("2027-03-28", "2027-10-31"):
            with self.assertRaises(SourceError):
                source_date({"start_date": {"date": day + " 02:30:00"}}, "start")

    def test_cancellation_requires_explicit_evidence(self):
        self.assertFalse(cancelled({"navn": "UKM"}, "Arrangementet er ikke avlyst"))
        self.assertTrue(cancelled({"navn": "AVLYST: UKM"}, ""))
        self.assertTrue(cancelled({"avlyst": True}, ""))
        self.assertTrue(cancelled({}, "Arrangementet er avlyst."))

    def test_unchanged_revisions_and_reappearing_event(self):
        value = event()
        first = revisions([value], {}, NOW)
        second = revisions([value], first, NOW + timedelta(days=1))
        self.assertEqual(first, second)
        self.assertEqual(revisions([], first, NOW), first)
        value["description"] += "\nNy informasjon"
        updated = revisions([value], second, NOW + timedelta(days=2))
        self.assertEqual(updated[value["id"]]["sequence"], 1)
        self.assertEqual(updated[value["id"]]["created"], first[value["id"]]["created"])

    @unittest.skipUnless(Calendar, "Installer .[test] for uavhengig iCalendar-kontroll")
    def test_utf8_folding_escape_long_text_and_utc_roundtrip(self):
        value = event()
        value["description"] += '\n' + 'Æøå, semikolon; og \\ skråstrek. ' * 600
        value["description"] += '\nBEGIN:VEVENT\nSUMMARY:Dette er tekst'
        state = revisions([value], {}, NOW)
        content = make_calendar("UKM – Vestland", [value], state)
        self.assertTrue(all(len(line) <= 75 for line in content.split(b"\r\n")))
        parsed = Calendar.from_ical(content)
        events = parsed.walk("VEVENT")
        self.assertEqual(len(events), 1)
        self.assertEqual(str(events[0]["DESCRIPTION"]), value["description"])
        self.assertEqual(events[0].decoded("DTSTART").astimezone(OSLO).hour, 16)

    @unittest.skipUnless(Calendar, "Installer .[test]")
    def test_multiday_all_day_and_cancellation_roundtrip(self):
        raw, page = fixture()
        raw["start_date"]["date"], raw["stop_date"]["date"] = "2027-04-01", "2027-04-03"
        raw["avlyst"], page["displayed_times"] = True, []
        value = normalize(raw, page, COUNTIES)
        parsed = Calendar.from_ical(make_calendar("Test", [value], revisions([value], {}, NOW))).walk("VEVENT")[0]
        self.assertEqual(parsed.decoded("DTSTART"), date(2027, 4, 1))
        self.assertEqual(parsed.decoded("DTEND"), date(2027, 4, 4))
        self.assertEqual(str(parsed["STATUS"]), "CANCELLED")


class BackstageDeadlineTests(unittest.TestCase):
    def record(self, deadline="2026-10-26 23:59:00.000000"):
        raw, page = fixture()
        raw["paameldingsfrist_2_date"]["date"] = deadline
        return {"raw": raw, "page": page, "event": normalize(raw, page, COUNTIES)}

    def test_distinct_deadline_links_to_parent_and_keeps_description(self):
        record = self.record()
        parent = record["event"]
        value = backstage_deadline(record["raw"], parent)
        self.assertNotEqual(value["uid"], parent["uid"])
        self.assertEqual(value["parent_uid"], parent["uid"])
        self.assertEqual(value["title"], "Påmeldingsfrist bak scenen – " + parent["title"])
        self.assertEqual(value["calendars"], parent["calendars"])
        self.assertEqual(value["expires"], parent["expires"])
        self.assertEqual(value["url"], parent["url"])
        self.assertIn(parent["description"], value["description"])
        self.assertEqual(datetime.fromisoformat(value["start"]).hour, 23)
        self.assertIsNone(value["end"])

    def test_missing_and_unused_late_deadlines_are_not_invented(self):
        record = self.record("2027-01-01 23:59:00")
        self.assertIsNone(backstage_deadline(record["raw"], record["event"]))
        record["raw"].pop("paameldingsfrist_2_date")
        record["raw"]["paameldingsfrist_2"] = 0
        self.assertIsNone(backstage_deadline(record["raw"], record["event"]))

    def test_past_deadline_and_cancellation_follow_active_parent(self):
        record = self.record("2026-10-20 23:59:00")
        record["event"]["status"] = "CANCELLED"
        value = backstage_deadline(record["raw"], record["event"])
        self.assertLess(datetime.fromisoformat(value["start"]), NOW)
        self.assertGreater(datetime.fromisoformat(value["expires"]), NOW)
        self.assertEqual(value["status"], "CANCELLED")

    @unittest.skipUnless(Calendar, "Installer .[test]")
    def test_winter_summer_and_date_only_deadlines_roundtrip(self):
        for deadline, expected_offset in (("2026-10-26 23:59:00", 1), ("2026-10-24 23:59:00", 2)):
            record = self.record(deadline)
            value = backstage_deadline(record["raw"], record["event"])
            content = make_calendar("Test", [value], revisions([value], {}, NOW))
            parsed = Calendar.from_ical(content).walk("VEVENT")[0]
            local = parsed.decoded("DTSTART").astimezone(OSLO)
            self.assertEqual(local.strftime("%Y-%m-%d %H:%M:%S"), deadline)
            self.assertEqual(local.utcoffset(), timedelta(hours=expected_offset))
            self.assertEqual(str(parsed["RELATED-TO"]), record["event"]["uid"])
            self.assertEqual(parsed["RELATED-TO"].params["RELTYPE"], "PARENT")
        record = self.record("2026-10-26")
        value = backstage_deadline(record["raw"], record["event"])
        parsed = Calendar.from_ical(make_calendar("Test", [value], revisions([value], {}, NOW))).walk("VEVENT")[0]
        self.assertEqual(parsed.decoded("DTSTART"), date(2026, 10, 26))
        self.assertEqual(parsed.decoded("DTEND"), date(2026, 10, 27))

    @unittest.skipUnless(Calendar, "Installer .[test]")
    def test_feed_updates_deadline_without_duplicates_and_removes_missing_deadline(self):
        meta = {"search": {"hits": 1, "complete": True}}
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "generated"
            first = self.record()
            status = build(output, COUNTIES, [first], meta, NOW)
            self.assertEqual(status["event_count"], 1)
            self.assertEqual(status["deadline_count"], 1)
            self.assertEqual(status["calendars"]["vestland"], 2)
            path = output / "site/kalendere/vestland.ics"
            original = Calendar.from_ical(path.read_bytes()).walk("VEVENT")
            original_uids = {str(e["UID"]) for e in original}
            changed = self.record("2026-10-27 12:00:00")
            build(output, COUNTIES, [changed], meta, NOW + timedelta(hours=1))
            updated = Calendar.from_ical(path.read_bytes()).walk("VEVENT")
            self.assertEqual({str(e["UID"]) for e in updated}, original_uids)
            deadline = next(e for e in updated if "RELATED-TO" in e)
            self.assertEqual(int(deadline["SEQUENCE"]), 1)
            self.assertEqual(deadline.decoded("DTSTART").astimezone(OSLO).hour, 12)
            self.assertIn("1 påmeldingsfrist bak scenen", (output / "site/index.html").read_text())
            changed["raw"].pop("paameldingsfrist_2_date")
            changed["raw"]["paameldingsfrist_2"] = 0
            build(output, COUNTIES, [changed], meta, NOW + timedelta(hours=2))
            remaining = Calendar.from_ical(path.read_bytes()).walk("VEVENT")
            self.assertEqual(len(remaining), 1)
            self.assertEqual(str(remaining[0]["UID"]), first["event"]["uid"])


class AtomicBuildTests(unittest.TestCase):
    def records(self):
        raw, page = fixture()
        return [{"raw": raw, "page": page, "event": normalize(raw, page, COUNTIES)}]

    def test_failed_or_empty_build_preserves_previous_files(self):
        meta = {"search": {"hits": 1, "complete": True}}
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "generated"
            build(output, COUNTIES, self.records(), meta, NOW)
            before = {str(p.relative_to(output)): p.read_bytes() for p in output.rglob("*") if p.is_file()}
            for broken in ({"search": {"hits": 0, "complete": True}}, {"search": {"hits": 1, "complete": False}}):
                with self.assertRaises(SourceError):
                    build(output, COUNTIES, [], broken, NOW)
                after = {str(p.relative_to(output)): p.read_bytes() for p in output.rglob("*") if p.is_file()}
                self.assertEqual(before, after)

    @unittest.skipUnless(Calendar, "Installer .[test]")
    def test_removal_and_changed_description_do_not_duplicate_uid(self):
        meta = {"search": {"hits": 2, "complete": True}}
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "generated"
            records = self.records()
            extra = deepcopy(records[0])
            extra["event"]["id"], extra["event"]["uid"] = "999", "ukm-arrangement-999@ukm-kalendere"
            build(output, COUNTIES, records + [extra], meta, NOW)
            records[0]["event"]["description"] += "\nOppdatert tekst"
            build(output, COUNTIES, records, meta, NOW + timedelta(hours=1))
            parsed = Calendar.from_ical((output / "site/kalendere/vestland.ics").read_bytes()).walk("VEVENT")
            self.assertEqual(len(parsed), 1)
            self.assertEqual(str(parsed[0]["UID"]), records[0]["event"]["uid"])
            self.assertEqual(int(parsed[0]["SEQUENCE"]), 1)
            self.assertIn("Oppdatert tekst", str(parsed[0]["DESCRIPTION"]))

    def test_build_does_not_replace_unrelated_folder(self):
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp)
            (output / "valuable.txt").write_text("behold")
            with self.assertRaises(SourceError):
                build(output, COUNTIES, self.records(), {"search": {"hits": 1, "complete": True}}, NOW)
            self.assertEqual((output / "valuable.txt").read_text(), "behold")
