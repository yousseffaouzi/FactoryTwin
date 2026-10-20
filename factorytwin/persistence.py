"""Optional local SQLite durability for FactoryTwin simulation sessions."""
from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
import json
from pathlib import Path
import sqlite3
import uuid

from .blueprint import DEFAULT_BLUEPRINT, FactoryBlueprint
from .engine import CUSTOM_TRACE_SCHEMA, MAX_REPLAY_OPERATIONS, TRACE_SCHEMA
from .genealogy import QUALITY_TRACE_SCHEMA
from .quality import DEFAULT_QUALITY_SCENARIO, QualityScenario
from .runtime import RuntimeProductionLine as ProductionLine

SCHEMA_VERSION = 2
MAX_PERSISTENCE_READ = 1_000


class PersistenceError(RuntimeError):
    """Raised when durable state cannot be safely read or committed."""


def _json(data) -> str:
    return json.dumps(data, sort_keys=True, separators=(",", ":"))


def _parse_json(text: str, label: str):
    try:
        return json.loads(text)
    except (TypeError, json.JSONDecodeError) as exc:
        raise PersistenceError(f"invalid persisted {label}") from exc


class SQLiteStore:
    """Versioned local store; every public write is one SQLite transaction."""

    def __init__(self, path: str | Path):
        self.path = Path(path)
        if str(self.path) == ":memory:":
            raise ValueError("SQLite persistence requires a filesystem path")
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        try:
            connection = sqlite3.connect(self.path, timeout=5.0)
            connection.execute("PRAGMA foreign_keys = ON")
            connection.execute("PRAGMA busy_timeout = 5000")
            return connection
        except sqlite3.Error as exc:
            raise PersistenceError(f"unable to open SQLite database: {exc}") from exc

    @staticmethod
    def _tables(connection: sqlite3.Connection) -> set[str]:
        return {row[0] for row in connection.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")}

    def _initialize(self) -> None:
        connection = self._connect()
        try:
            connection.execute("PRAGMA journal_mode = WAL")
            connection.execute("PRAGMA synchronous = FULL")
            version = connection.execute("PRAGMA user_version").fetchone()[0]
            if version > SCHEMA_VERSION:
                raise PersistenceError(f"unsupported SQLite schema version {version}")
            if version == 0:
                if self._tables(connection):
                    raise PersistenceError("unversioned non-empty SQLite database")
                with connection:
                    self._create_v2(connection)
                    connection.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")
            elif version == 1:
                with connection:
                    self._migrate_v1_to_v2(connection)
                    connection.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")
            self._validate_schema(connection)
        except sqlite3.Error as exc:
            raise PersistenceError(f"unable to initialize SQLite schema: {exc}") from exc
        finally:
            connection.close()

    @staticmethod
    def _create_v2(connection: sqlite3.Connection) -> None:
        connection.executescript("""
            CREATE TABLE sessions (
                ordinal INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT NOT NULL UNIQUE,
                started_at_utc TEXT NOT NULL,
                trace_schema TEXT NOT NULL,
                blueprint_json TEXT NOT NULL,
                quality_scenario_json TEXT NOT NULL,
                closed INTEGER NOT NULL DEFAULT 0 CHECK (closed IN (0, 1))
            );
            CREATE TABLE operations (
                session_id TEXT NOT NULL,
                seq INTEGER NOT NULL CHECK (seq >= 1),
                tick INTEGER NOT NULL CHECK (tick >= 0),
                sim_time_ms INTEGER NOT NULL CHECK (sim_time_ms >= 0),
                operation_json TEXT NOT NULL,
                PRIMARY KEY (session_id, seq),
                FOREIGN KEY (session_id) REFERENCES sessions(session_id)
            );
            CREATE TABLE snapshots (
                session_id TEXT NOT NULL,
                op_seq INTEGER NOT NULL CHECK (op_seq >= 1),
                tick INTEGER NOT NULL CHECK (tick >= 0),
                sim_time_ms INTEGER NOT NULL CHECK (sim_time_ms >= 0),
                state_json TEXT NOT NULL,
                PRIMARY KEY (session_id, op_seq),
                FOREIGN KEY (session_id) REFERENCES sessions(session_id)
            );
            CREATE TABLE events (
                session_id TEXT NOT NULL,
                event_seq INTEGER NOT NULL CHECK (event_seq >= 1),
                tick INTEGER NOT NULL CHECK (tick >= 0),
                sim_time_ms INTEGER NOT NULL CHECK (sim_time_ms >= 0),
                event_json TEXT NOT NULL,
                PRIMARY KEY (session_id, event_seq),
                FOREIGN KEY (session_id) REFERENCES sessions(session_id)
            );
            CREATE INDEX idx_sessions_open ON sessions(closed, ordinal);
            CREATE INDEX idx_operations_tick ON operations(session_id, tick, seq);
            CREATE INDEX idx_snapshots_tick ON snapshots(session_id, tick, op_seq);
            CREATE INDEX idx_events_tick ON events(session_id, tick, event_seq);
        """)

    @staticmethod
    def _migrate_v1_to_v2(connection: sqlite3.Connection) -> None:
        required = {"sessions", "operations", "snapshots", "events"}
        tables = SQLiteStore._tables(connection)
        if not required.issubset(tables):
            raise PersistenceError("invalid SQLite v1 schema")
        columns = {row[1] for row in connection.execute("PRAGMA table_info(sessions)")}
        if "closed" not in columns:
            connection.execute(
                "ALTER TABLE sessions ADD COLUMN closed INTEGER NOT NULL DEFAULT 0 "
                "CHECK (closed IN (0, 1))")
        connection.executescript("""
            CREATE INDEX IF NOT EXISTS idx_sessions_open ON sessions(closed, ordinal);
            CREATE INDEX IF NOT EXISTS idx_operations_tick ON operations(session_id, tick, seq);
            CREATE INDEX IF NOT EXISTS idx_snapshots_tick ON snapshots(session_id, tick, op_seq);
            CREATE INDEX IF NOT EXISTS idx_events_tick ON events(session_id, tick, event_seq);
        """)

    @staticmethod
    def _validate_schema(connection: sqlite3.Connection) -> None:
        required = {"sessions", "operations", "snapshots", "events"}
        if not required.issubset(SQLiteStore._tables(connection)):
            raise PersistenceError("incomplete SQLite schema")
        columns = {row[1] for row in connection.execute("PRAGMA table_info(sessions)")}
        expected = {"ordinal", "session_id", "started_at_utc", "trace_schema",
                    "blueprint_json", "quality_scenario_json", "closed"}
        if not expected.issubset(columns):
            raise PersistenceError("invalid SQLite sessions schema")

    @staticmethod
    def new_session_id() -> str:
        return uuid.uuid4().hex

    def latest_open_session(self) -> dict | None:
        connection = self._connect()
        try:
            row = connection.execute(
                "SELECT session_id, trace_schema, blueprint_json, quality_scenario_json "
                "FROM sessions WHERE closed=0 ORDER BY ordinal DESC LIMIT 1").fetchone()
            if row is None:
                return None
            return {"session_id": row[0], "trace_schema": row[1],
                    "blueprint": _parse_json(row[2], "blueprint"),
                    "quality_scenario": _parse_json(row[3], "quality scenario")}
        except sqlite3.Error as exc:
            raise PersistenceError(f"unable to read persisted session: {exc}") from exc
        finally:
            connection.close()

    def create_session(self, session_id: str, line: ProductionLine) -> None:
        connection = self._connect()
        try:
            with connection:
                self._insert_session(connection, session_id, line)
        except sqlite3.Error as exc:
            raise PersistenceError(f"unable to create persisted session: {exc}") from exc
        finally:
            connection.close()

    @staticmethod
    def _insert_session(connection: sqlite3.Connection, session_id: str,
                        line: ProductionLine) -> None:
        schema = line.export_trace()["schema"]
        connection.execute(
            "INSERT INTO sessions(session_id, started_at_utc, trace_schema, blueprint_json, "
            "quality_scenario_json, closed) VALUES(?,?,?,?,?,0)",
            (session_id, datetime.now(timezone.utc).isoformat(), schema,
             _json(line.blueprint.to_dict()), _json(line.quality_scenario.to_dict())))

    @staticmethod
    def _write_operation(connection: sqlite3.Connection, session_id: str, operation: dict,
                         state: dict, events: list[dict]) -> None:
        seq = operation["seq"]
        connection.execute(
            "INSERT INTO operations(session_id, seq, tick, sim_time_ms, operation_json) "
            "VALUES(?,?,?,?,?)",
            (session_id, seq, operation["tick"], operation["sim_time_ms"], _json(operation)))
        connection.execute(
            "INSERT INTO snapshots(session_id, op_seq, tick, sim_time_ms, state_json) "
            "VALUES(?,?,?,?,?)",
            (session_id, seq, state["tick"], state["sim_time_ms"], _json(state)))
        for event in events:
            connection.execute(
                "INSERT INTO events(session_id, event_seq, tick, sim_time_ms, event_json) "
                "VALUES(?,?,?,?,?)",
                (session_id, event["seq"], event["tick"], event["sim_time_ms"], _json(event)))

    def persist_operation(self, session_id: str, operation: dict, state: dict,
                          events: list[dict]) -> None:
        connection = self._connect()
        try:
            with connection:
                self._write_operation(connection, session_id, operation, state, events)
        except sqlite3.Error as exc:
            raise PersistenceError(f"unable to persist simulation operation: {exc}") from exc
        finally:
            connection.close()

    def persist_reset(self, old_session_id: str, new_session_id: str, line: ProductionLine,
                      operation: dict, state: dict, events: list[dict]) -> None:
        connection = self._connect()
        try:
            with connection:
                changed = connection.execute(
                    "UPDATE sessions SET closed=1 WHERE session_id=? AND closed=0",
                    (old_session_id,)).rowcount
                if changed != 1:
                    raise sqlite3.IntegrityError("active session missing during reset")
                self._insert_session(connection, new_session_id, line)
                self._write_operation(connection, new_session_id, operation, state, events)
        except sqlite3.Error as exc:
            raise PersistenceError(f"unable to persist simulation reset: {exc}") from exc
        finally:
            connection.close()

    def recover(self, session: dict) -> ProductionLine:
        session_id = session["session_id"]
        connection = self._connect()
        try:
            operations_rows = connection.execute(
                "SELECT seq, operation_json FROM operations WHERE session_id=? ORDER BY seq",
                (session_id,)).fetchall()
            if len(operations_rows) > MAX_REPLAY_OPERATIONS:
                raise PersistenceError("persisted operation count exceeds replay limit")
            for expected, (seq, _) in enumerate(operations_rows, 1):
                if seq != expected:
                    raise PersistenceError("persisted operation sequence has a gap")
            if not operations_rows:
                blueprint = FactoryBlueprint.from_dict(session["blueprint"])
                quality = QualityScenario.from_dict(session["quality_scenario"])
                quality.validate_for_blueprint(blueprint)
                return ProductionLine(blueprint=blueprint, quality_scenario=quality)
            snapshot = connection.execute(
                "SELECT op_seq, state_json FROM snapshots WHERE session_id=? "
                "ORDER BY op_seq DESC LIMIT 1", (session_id,)).fetchone()
            if snapshot is None or snapshot[0] != len(operations_rows):
                raise PersistenceError("persisted snapshot does not match operation journal")
            operations = [_parse_json(text, "operation") for _, text in operations_rows]
            final_state = _parse_json(snapshot[1], "snapshot")
            event_count, min_seq, max_seq = connection.execute(
                "SELECT COUNT(*), MIN(event_seq), MAX(event_seq) FROM events WHERE session_id=?",
                (session_id,)).fetchone()
            expected_events = final_state.get("event_sequence")
            if (type(expected_events) is not int or
                    (expected_events == 0 and event_count != 0) or
                    (expected_events > 0 and
                     (event_count != expected_events or min_seq != 1 or max_seq != expected_events))):
                raise PersistenceError("persisted event journal is inconsistent")
            schema = session["trace_schema"]
            trace = {"schema": schema, "tick_duration_ms": 1000,
                     "operations": operations, "final_state": final_state}
            if schema in (CUSTOM_TRACE_SCHEMA, QUALITY_TRACE_SCHEMA):
                trace["blueprint"] = session["blueprint"]
            if schema == QUALITY_TRACE_SCHEMA:
                trace["quality_scenario"] = session["quality_scenario"]
            if schema not in (TRACE_SCHEMA, CUSTOM_TRACE_SCHEMA, QUALITY_TRACE_SCHEMA):
                raise PersistenceError("unknown persisted trace schema")
            try:
                return ProductionLine.replay(trace)
            except (ValueError, TypeError) as exc:
                raise PersistenceError(f"persisted replay validation failed: {exc}") from exc
        except sqlite3.Error as exc:
            raise PersistenceError(f"unable to recover persisted simulation: {exc}") from exc
        finally:
            connection.close()

    def list_snapshots(self, session_id: str, limit: int = 100) -> list[dict]:
        if type(limit) is not int or not 1 <= limit <= MAX_PERSISTENCE_READ:
            raise ValueError(f"limit must be 1..{MAX_PERSISTENCE_READ}")
        connection = self._connect()
        try:
            rows = connection.execute(
                "SELECT op_seq, tick, sim_time_ms, state_json FROM snapshots "
                "WHERE session_id=? ORDER BY op_seq DESC LIMIT ?", (session_id, limit)).fetchall()
            return [{"op_seq": row[0], "tick": row[1], "sim_time_ms": row[2],
                     "state": _parse_json(row[3], "snapshot")} for row in rows]
        except sqlite3.Error as exc:
            raise PersistenceError(f"unable to read persisted snapshots: {exc}") from exc
        finally:
            connection.close()


class PersistentProductionLine(ProductionLine):
    """ProductionLine that commits each accepted operation before exposing it."""

    @classmethod
    def open(cls, database_path: str | Path, blueprint: FactoryBlueprint | None = None,
             quality_scenario: QualityScenario | None = None):
        store = SQLiteStore(database_path)
        session = store.latest_open_session()
        if session is None:
            selected_blueprint = blueprint or DEFAULT_BLUEPRINT
            selected_quality = quality_scenario or DEFAULT_QUALITY_SCENARIO
            line = cls(blueprint=selected_blueprint, quality_scenario=selected_quality)
            session_id = store.new_session_id()
            store.create_session(session_id, line)
        else:
            persisted_blueprint = FactoryBlueprint.from_dict(session["blueprint"])
            persisted_quality = QualityScenario.from_dict(session["quality_scenario"])
            persisted_quality.validate_for_blueprint(persisted_blueprint)
            if blueprint is not None and blueprint != persisted_blueprint:
                raise PersistenceError("persisted session blueprint does not match requested blueprint")
            if quality_scenario is not None and quality_scenario != persisted_quality:
                raise PersistenceError("persisted quality scenario does not match requested scenario")
            recovered = store.recover(session)
            line = cls(blueprint=recovered.blueprint, quality_scenario=recovered.quality_scenario)
            line.__dict__.update(deepcopy(recovered.__dict__))
            session_id = session["session_id"]
        line._store = store
        line._session_id = session_id
        return line

    def _capture_runtime(self) -> dict:
        return deepcopy({key: value for key, value in self.__dict__.items()
                         if key not in {"_store", "_session_id"}})

    def _restore_runtime(self, before: dict, session_id: str) -> None:
        store = self._store
        self.__dict__.clear()
        self.__dict__.update(before)
        self._store = store
        self._session_id = session_id

    def _persisted_state(self) -> dict:
        return (self.quality_state_data() if self.quality_scenario.enabled
                else self.state_data())

    def step(self) -> dict:
        before = self._capture_runtime()
        session_id = self._session_id
        previous_event_sequence = self.event_sequence
        try:
            result = super().step()
            events = [deepcopy(event) for event in self.events
                      if event["seq"] > previous_event_sequence]
            self._store.persist_operation(session_id, deepcopy(self.operations[-1]),
                                          self._persisted_state(), events)
            return result
        except PersistenceError:
            self._restore_runtime(before, session_id)
            raise

    def control(self, action: str, station: str | None = None) -> None:
        before = self._capture_runtime()
        old_session_id = self._session_id
        previous_event_sequence = self.event_sequence
        store = self._store
        try:
            super().control(action, station)
            # Genealogy reset rebuilds __dict__, so reattach persistence handles.
            self._store = store
            self._session_id = old_session_id
            if action == "reset":
                new_session_id = store.new_session_id()
                events = deepcopy(self.events)
                store.persist_reset(old_session_id, new_session_id, self,
                                    deepcopy(self.operations[-1]), self._persisted_state(), events)
                self._session_id = new_session_id
            else:
                events = [deepcopy(event) for event in self.events
                          if event["seq"] > previous_event_sequence]
                store.persist_operation(old_session_id, deepcopy(self.operations[-1]),
                                        self._persisted_state(), events)
        except PersistenceError:
            self._store = store
            self._restore_runtime(before, old_session_id)
            raise
