from copy import deepcopy
from pathlib import Path
import json
import tempfile
import unittest

from test_calendar import COUNTIES, NOW, fixture
from ukm_calendar.calendar import normalize
from ukm_calendar.publish import build
from ukm_calendar.registrations import public_entries, snapshot
from ukm_calendar.source import SourceError


class RegistrationsTests(unittest.TestCase):
    def sample(self):
        return [{"object_type": "innslag", "id": 123, "navn": "Eksempelband",
                 "beskrivelse": "<p>Vi spiller egen musikk.</p>",
                 "telefon": "ikke ta med", "bilde": "ikke ta med",
                 "personer": [{"id": 456, "navn": "Eksempeldeltaker",
                               "epost": "ikke ta med", "alder": "ikke ta med"}]}]

    def record(self):
        raw, page = fixture()
        event = normalize(raw, page, COUNTIES)
        return {"raw": raw, "page": page, "event": event,
                "registrations": public_entries(self.sample(), event["url"])}

    def test_only_requested_public_fields_are_exported(self):
        entry = public_entries(self.sample(), "https://www.ukm.no/arrangement/test")[0]
        self.assertEqual(set(entry), {"id", "navn", "beskrivelse", "deltakernavn"})
        self.assertEqual(entry["beskrivelse"], "Vi spiller egen musikk.")
        self.assertEqual(entry["deltakernavn"], ["Eksempeldeltaker"])
        self.assertNotIn("ikke ta med", json.dumps(entry))

    def test_empty_public_list_is_valid_but_errors_and_duplicates_fail(self):
        self.assertEqual(public_entries([], "https://www.ukm.no"), [])
        for invalid in ({"error": "serverfeil"}, [None], self.sample() * 2):
            with self.assertRaises(SourceError):
                public_entries(invalid, "https://www.ukm.no")

    def test_partial_fetch_does_not_look_like_zero_registrations(self):
        record = self.record()
        missing = deepcopy(record)
        missing.pop("registrations")
        with self.assertRaises(SourceError):
            snapshot([record, missing], NOW.isoformat())

    def test_registrations_are_saved_only_in_repository_data_and_fail_atomically(self):
        meta = {"search": {"hits": 1, "complete": True}}
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "generated"
            record = self.record()
            build(output, COUNTIES, [record], meta, NOW)
            export = json.loads((output / "data/paameldte.json").read_text())
            self.assertEqual(export["antall_innslag"], 1)
            self.assertEqual(export["arrangementer"][0]["innslag"][0]["navn"], "Eksempelband")
            self.assertNotIn("Eksempeldeltaker", (output / "data/latest.json").read_text())
            self.assertFalse((output / "site/paameldte.json").exists())
            for file in (output / "site").rglob("*"):
                if file.is_file():
                    self.assertNotIn("Eksempeldeltaker", file.read_text())
            before = (output / "data/paameldte.json").read_bytes()
            missing = deepcopy(record)
            missing.pop("registrations")
            with self.assertRaises(SourceError):
                build(output, COUNTIES, [record, missing], meta, NOW)
            self.assertEqual((output / "data/paameldte.json").read_bytes(), before)
            with self.assertRaises(SourceError):
                build(output, COUNTIES, [missing], meta, NOW)
            self.assertEqual((output / "data/paameldte.json").read_bytes(), before)
