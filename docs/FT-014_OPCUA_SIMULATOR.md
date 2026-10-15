# FT-014 — Simulated OPC UA namespace adapter

FT-014 is an **in-process mock adapter**, not an OPC UA network server. It lets FactoryTwin exercise stable OPC-UA-style namespace mappings, typed variables and method semantics against the real deterministic simulator while keeping the project dependency-free and isolated from industrial networks.

## What is simulated

`factorytwin.opcua_sim.SimulatedOpcUaAdapter` builds NodeIds under namespace index 2, for example:

- `ns=2;s=FactoryTwin.Line.State`
- `ns=2;s=FactoryTwin.Production.Completed`
- `ns=2;s=FactoryTwin.Stations.Inspect.RemainingTicks`
- `ns=2;s=FactoryTwin.Faults.ActiveStations`
- `ns=2;s=FactoryTwin.Methods.Pause`
- `ns=2;s=FactoryTwin.Methods.AddFault`

Variables are typed metadata plus read-only values projected from a normal FactoryTwin snapshot. Reads and browse calls never advance simulation time. Control is represented through explicit method calls that delegate to the same validated `pause`, `resume`, fault, recovery and reset engine controls used by the local HTTP API.

## What is not implemented

There is no OPC UA binary/TCP encoding, endpoint URL, discovery service, session/channel negotiation, certificate trust store, user authentication, subscriptions, monitored items, information-model XML, companion specification, PubSub, historical access, or PLC connection. The adapter opens no socket at all. Tests explicitly fail if the adapter attempts to construct one.

Because there is no wire protocol, a standard OPC UA client such as UaExpert cannot connect to this module. A future wire-compatible simulator would require a separately reviewed OPC UA library and security/certificate model. It must still remain synthetic and isolated from production equipment unless a future phase is explicitly authorized.

## Namespace behavior

The node inventory is deterministic for a validated blueprint. Per-station nodes expose textual status, current synthetic workpiece ID, configured cycle ticks, remaining ticks and fault state. Line nodes expose simulation state/tick/time; production nodes expose good, scrap, rework and in-process counters. The active-fault array reflects FT-013's independent synthetic latches.

All variables are read-only. Invalid nodes, method IDs and arguments fail without mutating the simulation. Multi-fault methods preserve the whole-line interlock: this mock adapter does not create a protocol path that bypasses engine safety semantics.

## Why this boundary is useful

The adapter creates a tested contract between an eventual protocol transport and FactoryTwin's domain model without adding a network listener or third-party runtime dependency. Integration tests can therefore verify node naming, data types, read semantics, method/control mapping, custom-blueprint station nodes and fault behavior now, while wire security remains a separate future design concern.
