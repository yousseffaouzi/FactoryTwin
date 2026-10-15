"""SQLite persistence extension for FT-013 multi-fault trace.v4 sessions."""
from __future__ import annotations

from copy import deepcopy
from pathlib import Path
import sqlite3

from .blueprint import DEFAULT_BLUEPRINT, FactoryBlueprint
from .faults import MULTI_FAULT_TRACE_SCHEMA
from .persistence import PersistenceError, PersistentProductionLine, SQLiteStore, _parse_json
from .quality import DEFAULT_QUALITY_SCENARIO, QualityScenario
from .sim import MAX_REPLAY_OPERATIONS, ProductionLine


class FaultSQLiteStore(SQLiteStore):
    """Adds trace.v4 recovery while preserving the FT-009 schema and migrations."""

    def persist_fault_operation(self, session_id: str, operation: dict, state: dict,
                                events: list[dict], trace_schema: str) -> None:
        connection = self._connect()
        try:
            with connection:
                changed = connection.execute(
                    "UPDATE sessions SET trace_schema=? WHERE session_id=? AND closed=0",
                    (trace_schema, session_id)).rowcount
                if changed != 1:
                    raise sqlite3.IntegrityError("active session missing during operation")
                self._write_operation(connection, session_id, operation, state, events)
        except sqlite3.Error as exc:
            raise PersistenceError(f"unable to persist simulation operation: {exc}") from exc
        finally:
            connection.close()

    def recover(self, session: dict) -> ProductionLine:
        if session["trace_schema"] != MULTI_FAULT_TRACE_SCHEMA:
            return super().recover(session)
        session_id = session["session_id"]
        connection = self._connect()
        try:
            rows = connection.execute(
                "SELECT seq, operation_json FROM operations WHERE session_id=? ORDER BY seq",
                (session_id,)).fetchall()
            if len(rows) > MAX_REPLAY_OPERATIONS:
                raise PersistenceError("persisted operation count exceeds replay limit")
            for expected, (seq, _) in enumerate(rows, 1):
                if seq != expected:
                    raise PersistenceError("persisted operation sequence has a gap")
            if not rows:
                raise PersistenceError("trace.v4 session cannot be empty")
            snapshot = connection.execute(
                "SELECT op_seq, state_json FROM snapshots WHERE session_id=? "
                "ORDER BY op_seq DESC LIMIT 1", (session_id,)).fetchone()
            if snapshot is None or snapshot[0] != len(rows):
                raise PersistenceError("persisted snapshot does not match operation journal")
            operations = [_parse_json(text, "operation") for _, text in rows]
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
            trace = {"schema": MULTI_FAULT_TRACE_SCHEMA, "tick_duration_ms": 1000,
                     "blueprint": session["blueprint"],
                     "quality_scenario": session["quality_scenario"],
                     "operations": operations, "final_state": final_state}
            try:
                return ProductionLine.replay(trace)
            except (ValueError, TypeError) as exc:
                raise PersistenceError(f"persisted replay validation failed: {exc}") from exc
        except sqlite3.Error as exc:
            raise PersistenceError(f"unable to recover persisted simulation: {exc}") from exc
        finally:
            connection.close()


class FaultPersistentProductionLine(PersistentProductionLine):
    """FT-009 durability with atomic trace-schema promotion for multi-fault sessions."""

    @classmethod
    def open(cls, database_path: str | Path, blueprint: FactoryBlueprint | None = None,
             quality_scenario: QualityScenario | None = None):
        store = FaultSQLiteStore(database_path)
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

    def _persisted_state(self) -> dict:
        if getattr(self, "_multi_fault_used", False):
            return self.multi_fault_state_data()
        return super()._persisted_state()

    def step(self) -> dict:
        before = self._capture_runtime()
        session_id = self._session_id
        previous_event_sequence = self.event_sequence
        try:
            # Skip PersistentProductionLine.step so the operation and any trace
            # schema promotion are committed in one transaction below.
            result = super(PersistentProductionLine, self).step()
            events = [deepcopy(event) for event in self.events
                      if event["seq"] > previous_event_sequence]
            schema = self.export_trace()["schema"]
            self._store.persist_fault_operation(session_id, deepcopy(self.operations[-1]),
                                                self._persisted_state(), events, schema)
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
            # Call the simulator layer directly, not the FT-009 persistence wrapper.
            super(PersistentProductionLine, self).control(action, station)
            self._store = store
            self._session_id = old_session_id
            if action == "reset":
                new_session_id = store.new_session_id()
                store.persist_reset(old_session_id, new_session_id, self,
                                    deepcopy(self.operations[-1]), self._persisted_state(),
                                    deepcopy(self.events))
                self._session_id = new_session_id
            else:
                events = [deepcopy(event) for event in self.events
                          if event["seq"] > previous_event_sequence]
                schema = self.export_trace()["schema"]
                store.persist_fault_operation(old_session_id, deepcopy(self.operations[-1]),
                                              self._persisted_state(), events, schema)
        except PersistenceError:
            self._store = store
            self._restore_runtime(before, old_session_id)
            raise
