"""FT-009: optional transactional SQLite persistence and recovery."""
from contextlib import contextmanager
from copy import deepcopy
import json
from pathlib import Path
import sqlite3
import tempfile
import threading
import unittest
from unittest.mock import patch

from factorytwin.blueprint import FactoryBlueprint
from factorytwin.persistence import (
    MAX_PERSISTENCE_READ,
    PersistenceError,
    PersistentProductionLine,
    SCHEMA_VERSION,
    SQLiteStore,
)
from factorytwin.quality import QualityScenario
from factorytwin.sim import ProductionLine


def blueprint():
    return FactoryBlueprint.from_dict({
        "version": 1,
        "stations": [{"id": "Feed", "cycle_ticks": 1},
                     {"id": "Inspect", "cycle_ticks": 2},
                     {"id": "Pack", "cycle_ticks": 1}],
        "connections": [{"from": "Feed", "to": "Inspect"},
                        {"from": "Inspect", "to": "Pack"}],
    })


def quality():
    return QualityScenario.from_dict({
        "version": 1,
        "decisions": [
            {"workpiece_id": "WP-0001", "station": "Inspect", "attempt": 1,
             "outcome": "REWORK"},
            {"workpiece_id": "WP-0003", "station": "Inspect", "attempt": 1,
             "outcome": "SCRAP"},
        ],
    })


class SQLitePersistenceTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name) / "factorytwin.sqlite3"

    def tearDown(self):
        self.temp.cleanup()

    @contextmanager
    def connect(self):
        connection = sqlite3.connect(self.path)
        try:
            with connection:
                yield connection
        finally:
            connection.close()

    def test_fresh_database_persists_operation_snapshot_and_events(self):
        line = PersistentProductionLine.open(self.path)
        session_id = line._session_id
        line.step()
        line.step()
        line.control("pause")
        with self.connect() as connection:
            self.assertEqual(connection.execute("PRAGMA user_version").fetchone()[0], SCHEMA_VERSION)
            self.assertEqual(connection.execute(
                "SELECT COUNT(*) FROM operations WHERE session_id=?", (session_id,)).fetchone()[0], 3)
            self.assertEqual(connection.execute(
                "SELECT COUNT(*) FROM snapshots WHERE session_id=?", (session_id,)).fetchone()[0], 3)
            self.assertEqual(connection.execute(
                "SELECT COUNT(*) FROM events WHERE session_id=?", (session_id,)).fetchone()[0],
                line.event_sequence)

    def test_restart_recovers_exact_default_trace_and_continues(self):
        line = PersistentProductionLine.open(self.path)
        for _ in range(8):
            line.step()
        line.control("pause")
        line.step()
        line.control("resume")
        expected = json.loads(json.dumps(line.export_trace()))
        expected_continuation = ProductionLine.replay(expected)
        restored = PersistentProductionLine.open(self.path)
        self.assertEqual(restored.export_trace(), expected)
        expected_continuation.step()
        restored.step()
        self.assertEqual(restored.export_trace(), expected_continuation.export_trace())

    def test_custom_quality_trace_v3_recovers(self):
        line = PersistentProductionLine.open(self.path, blueprint=blueprint(),
                                             quality_scenario=quality())
        for _ in range(14):
            line.step()
        expected = json.loads(json.dumps(line.export_trace()))
        restored = PersistentProductionLine.open(self.path)
        self.assertEqual(restored.export_trace(), expected)
        self.assertEqual(restored.scrapped, line.scrapped)
        self.assertEqual(restored.rework_cycles, line.rework_cycles)
        restored.audit_genealogy()

    def test_reset_starts_new_session_without_deleting_old_history(self):
        line = PersistentProductionLine.open(self.path)
        for _ in range(5):
            line.step()
        old_session = line._session_id
        old_trace = deepcopy(line.export_trace())
        line.control("reset")
        new_session = line._session_id
        self.assertNotEqual(new_session, old_session)
        with self.connect() as connection:
            rows = connection.execute(
                "SELECT session_id, closed FROM sessions ORDER BY ordinal").fetchall()
            self.assertEqual(rows, [(old_session, 1), (new_session, 0)])
            self.assertEqual(connection.execute(
                "SELECT COUNT(*) FROM operations WHERE session_id=?", (old_session,)).fetchone()[0],
                len(old_trace["operations"]))
            self.assertEqual(connection.execute(
                "SELECT COUNT(*) FROM operations WHERE session_id=?", (new_session,)).fetchone()[0], 1)
        restored = PersistentProductionLine.open(self.path)
        self.assertEqual(restored.export_trace(), line.export_trace())

    def test_failed_step_write_restores_memory_exactly(self):
        line = PersistentProductionLine.open(self.path)
        line.step()
        before = deepcopy(line.export_trace())
        with patch.object(line._store, "persist_operation",
                          side_effect=PersistenceError("synthetic disk failure")):
            with self.assertRaisesRegex(PersistenceError, "synthetic disk failure"):
                line.step()
        self.assertEqual(line.export_trace(), before)

    def test_failed_control_write_restores_memory_exactly(self):
        line = PersistentProductionLine.open(self.path)
        before = deepcopy(line.export_trace())
        with patch.object(line._store, "persist_operation",
                          side_effect=PersistenceError("synthetic disk failure")):
            with self.assertRaises(PersistenceError):
                line.control("pause")
        self.assertEqual(line.export_trace(), before)
        self.assertTrue(line.running)

    def test_failed_reset_restores_old_session_and_memory(self):
        line = PersistentProductionLine.open(self.path)
        for _ in range(3):
            line.step()
        old_session = line._session_id
        before = deepcopy(line.export_trace())
        with patch.object(line._store, "persist_reset",
                          side_effect=PersistenceError("synthetic reset failure")):
            with self.assertRaises(PersistenceError):
                line.control("reset")
        self.assertEqual(line._session_id, old_session)
        self.assertEqual(line.export_trace(), before)

    def test_requested_configuration_must_match_open_session(self):
        PersistentProductionLine.open(self.path, blueprint=blueprint())
        other = FactoryBlueprint.from_dict({
            "version": 1,
            "stations": [{"id": "Only", "cycle_ticks": 1}],
            "connections": [],
        })
        with self.assertRaisesRegex(PersistenceError, "blueprint"):
            PersistentProductionLine.open(self.path, blueprint=other)
        with self.assertRaisesRegex(PersistenceError, "quality"):
            PersistentProductionLine.open(self.path, quality_scenario=quality())

    def test_unknown_schema_version_is_rejected(self):
        with self.connect() as connection:
            connection.execute("PRAGMA user_version = 999")
        with self.assertRaisesRegex(PersistenceError, "unsupported SQLite schema"):
            SQLiteStore(self.path)

    def test_unversioned_nonempty_database_is_rejected(self):
        with self.connect() as connection:
            connection.execute("CREATE TABLE unexpected(id INTEGER)")
        with self.assertRaisesRegex(PersistenceError, "unversioned non-empty"):
            SQLiteStore(self.path)

    def test_v1_schema_migrates_to_v2_without_data_loss(self):
        with self.connect() as connection:
            connection.executescript("""
                CREATE TABLE sessions (
                    ordinal INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id TEXT NOT NULL UNIQUE,
                    started_at_utc TEXT NOT NULL,
                    trace_schema TEXT NOT NULL,
                    blueprint_json TEXT NOT NULL,
                    quality_scenario_json TEXT NOT NULL
                );
                CREATE TABLE operations (
                    session_id TEXT NOT NULL, seq INTEGER NOT NULL, tick INTEGER NOT NULL,
                    sim_time_ms INTEGER NOT NULL, operation_json TEXT NOT NULL,
                    PRIMARY KEY(session_id, seq)
                );
                CREATE TABLE snapshots (
                    session_id TEXT NOT NULL, op_seq INTEGER NOT NULL, tick INTEGER NOT NULL,
                    sim_time_ms INTEGER NOT NULL, state_json TEXT NOT NULL,
                    PRIMARY KEY(session_id, op_seq)
                );
                CREATE TABLE events (
                    session_id TEXT NOT NULL, event_seq INTEGER NOT NULL, tick INTEGER NOT NULL,
                    sim_time_ms INTEGER NOT NULL, event_json TEXT NOT NULL,
                    PRIMARY KEY(session_id, event_seq)
                );
                INSERT INTO sessions(session_id, started_at_utc, trace_schema, blueprint_json,
                    quality_scenario_json) VALUES('legacy','2026-01-01T00:00:00+00:00',
                    'factorytwin.trace.v1',
                    '{"version":1,"stations":[{"id":"Feeder","cycle_ticks":1},{"id":"Conveyor","cycle_ticks":1},{"id":"Processing","cycle_ticks":1},{"id":"Packing","cycle_ticks":1}],"connections":[{"from":"Feeder","to":"Conveyor"},{"from":"Conveyor","to":"Processing"},{"from":"Processing","to":"Packing"}]}',
                    '{"version":1,"decisions":[]}');
                PRAGMA user_version = 1;
            """)
        store = SQLiteStore(self.path)
        session = store.latest_open_session()
        self.assertEqual(session["session_id"], "legacy")
        with self.connect() as connection:
            self.assertEqual(connection.execute("PRAGMA user_version").fetchone()[0], 2)
            columns = {row[1] for row in connection.execute("PRAGMA table_info(sessions)")}
            self.assertIn("closed", columns)
            self.assertEqual(connection.execute(
                "SELECT closed FROM sessions WHERE session_id='legacy'").fetchone()[0], 0)

    def test_missing_latest_snapshot_is_detected_on_recovery(self):
        line = PersistentProductionLine.open(self.path)
        line.step()
        line.step()
        session_id = line._session_id
        with self.connect() as connection:
            connection.execute("DELETE FROM snapshots WHERE session_id=? AND op_seq=2", (session_id,))
        with self.assertRaisesRegex(PersistenceError, "snapshot"):
            PersistentProductionLine.open(self.path)

    def test_event_journal_is_not_limited_by_ui_buffer(self):
        line = PersistentProductionLine.open(self.path)
        for _ in range(70):
            line.step()
        self.assertEqual(len(line.events), 40)
        with self.connect() as connection:
            count = connection.execute(
                "SELECT COUNT(*) FROM events WHERE session_id=?", (line._session_id,)).fetchone()[0]
        self.assertEqual(count, line.event_sequence)
        self.assertGreater(count, 40)
        restored = PersistentProductionLine.open(self.path)
        self.assertEqual(restored.export_trace(), line.export_trace())

    def test_snapshot_reads_are_bounded_and_concurrent_with_writes(self):
        line = PersistentProductionLine.open(self.path)
        errors = []
        done = threading.Event()

        def reader():
            try:
                while not done.is_set():
                    rows = line._store.list_snapshots(line._session_id, limit=5)
                    self.assertLessEqual(len(rows), 5)
            except Exception as exc:  # captured for assertion in the test thread
                errors.append(exc)

        thread = threading.Thread(target=reader)
        thread.start()
        try:
            for _ in range(30):
                line.step()
        finally:
            done.set()
            thread.join(timeout=5)
        self.assertFalse(thread.is_alive())
        self.assertEqual(errors, [])
        with self.assertRaises(ValueError):
            line._store.list_snapshots(line._session_id, limit=0)
        with self.assertRaises(ValueError):
            line._store.list_snapshots(line._session_id, limit=MAX_PERSISTENCE_READ + 1)


if __name__ == "__main__":
    unittest.main()
