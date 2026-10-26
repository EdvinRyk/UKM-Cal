"""Independent checks against the actual generated release, offline."""
from datetime import datetime
import json
from pathlib import Path
import unittest

try:
    from icalendar import Calendar
except ImportError:
    Calendar = None

ROOT = Path(__file__).resolve().parents[1]


class ReleaseTests(unittest.TestCase):
    @unittest.skipUnless((ROOT / "generated/data/paameldte.json").exists(), "Ingen påmeldingseksport ennå")
    def test_registration_export_is_complete_and_limited_to_requested_fields(self):
        root = ROOT / "generated"
        export = json.loads((root / "data/paameldte.json").read_text())
        snapshot = json.loads((root / "data/latest.json").read_text())
        self.assertEqual({e["arrangement_id"] for e in export["arrangementer"]},
                         {r["event"]["id"] for r in snapshot["events"]})
        self.assertEqual(export["antall_arrangementer"], len(export["arrangementer"]))
        self.assertEqual(export["antall_innslag"], sum(len(e["innslag"]) for e in export["arrangementer"]))
        occurrences = 0
        for event in export["arrangementer"]:
            self.assertEqual(event["antall_innslag"], len(event["innslag"]))
            self.assertEqual(len(event["innslag"]), len({e["id"] for e in event["innslag"]}))
            for entry in event["innslag"]:
                self.assertEqual(set(entry), {"id", "navn", "beskrivelse", "deltakernavn"})
                self.assertIsInstance(entry["beskrivelse"], str)
                self.assertTrue(all(isinstance(n, str) and n.strip() for n in entry["deltakernavn"]))
                occurrences += len(entry["deltakernavn"])
        self.assertEqual(export["antall_deltakernavn_i_innslag"], occurrences)
        self.assertTrue(all("registrations" not in r for r in snapshot["events"]))
        self.assertFalse((root / "site/paameldte.json").exists())
        self.assertFalse((root / "site/data/paameldte.json").exists())

    @unittest.skipUnless(Calendar and (ROOT / "generated/data/status.json").exists(), "Ingen utgivelse eller .[test] mangler")
    def test_all_published_files_match_snapshot(self):
        root = ROOT / "generated"
        status = json.loads((root / "data/status.json").read_text())
        snapshot = json.loads((root / "data/latest.json").read_text())
        expected = {r["event"]["uid"]: r["event"] for r in snapshot["events"]}
        expected.update({e["uid"]: e for e in snapshot.get("deadline_events", [])})
        found = set()
        files = list((root / "site/kalendere").glob("*.ics"))
        self.assertEqual(len(files), status["calendar_count"])
        for path in files:
            content = path.read_bytes()
            self.assertNotIn(b"\n", content.replace(b"\r\n", b""))
            parsed = Calendar.from_ical(content)
            self.assertEqual(parsed.errors, [])
            events = parsed.walk("VEVENT")
            self.assertEqual(len(events), status["calendars"][path.stem])
            self.assertEqual(len(events), len({str(e["UID"]) for e in events}))
            for event in events:
                uid = str(event["UID"])
                expected_event = expected[uid]
                self.assertEqual(event.errors, [])
                self.assertIn(path.stem, expected_event["calendars"])
                self.assertEqual(str(event["DESCRIPTION"]), expected_event["description"])
                self.assertEqual(str(event["SUMMARY"]), expected_event["title"])
                self.assertGreater(datetime.fromisoformat(expected_event["expires"]), datetime.fromisoformat(status["last_success"]))
                found.add(uid)
        self.assertEqual(found, set(expected))
