# Orion Hub — Mesh Architecture Design
**Organization:** LoveLogicAI LLC  
**Author:** Jeremy "Remy" Morgan-Jones Sr.  
**Version:** 1.0 — Initial Design  
**Date:** 2026-05-02  
**Status:** DESIGN PHASE — Ready for Implementation  
**Depends On:** Zo Super Server hardening complete (ZO-HARDEN-001 ✅)

---

> *"Orion is not a server. Orion is a gravity well — every node orbits it, every node can become it."*

---

## Executive Summary

Orion Hub is the coordination layer of the LoveLogicAI mesh. Where Zo Super Server is a single high-capability node, Orion Hub is the **connective tissue** — the message broker, consensus engine, and state synchronizer that allows multiple Zo-class nodes to operate as a coherent, self-healing swarm.

**Core properties:**
- **NATS-native** — all coordination flows through NATS JetStream
- **Diskless truth** — no node has persistent local state; NATS is the single source of truth
- **Kill -9 resilient** — any node can be hard-killed and a replacement spins up in <30 seconds, fully hydrated
- **Leaderless by default** — the mesh operates without a fixed leader; consensus emerges dynamically
- **Observable** — every state transition is a published NATS event; no hidden side effects

---

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────────┐
│                        ORION HUB MESH                           │
│                                                                 │
│   ┌─────────────┐    ┌─────────────┐    ┌─────────────┐        │
│   │  Zo Node 1  │    │  Zo Node 2  │    │  Zo Node N  │        │
│   │  (primary)  │    │  (replica)  │    │  (standby)  │        │
│   └──────┬──────┘    └──────┬──────┘    └──────┬──────┘        │
│          │                  │                  │                │
│          └──────────────────┼──────────────────┘                │
│                             │                                   │
│              ┌──────────────▼──────────────┐                   │
│              │      NATS JetStream          │                   │
│              │   (Distributed Truth Bus)    │                   │
│              │                             │                   │
│              │  Streams:                   │                   │
│              │  • zo.state.*               │                   │
│              │  • zo.events.*              │                   │
│              │  • orion.consensus.*        │                   │
│              │  • orion.registry.*         │                   │
│              │  • orion.heartbeat.*        │                   │
│              └──────────────┬──────────────┘                   │
│                             │                                   │
│         ┌───────────────────┼───────────────────┐             │
│         │                   │                   │             │
│  ┌──────▼──────┐   ┌────────▼──────┐   ┌───────▼──────┐     │
│  │  Consensus  │   │  Tool Router  │   │  Skill Sync  │     │
│  │   Engine    │   │  (load bal.)  │   │  (registry)  │     │
│  └─────────────┘   └───────────────┘   └──────────────┘     │
│                                                                 │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │                  Orion Control Plane                      │  │
│  │  • Node health monitoring (heartbeat every 10s)          │  │
│  │  • Automatic failover (<5s detection, <30s recovery)     │  │
│  │  • Skill marketplace synchronization                     │  │
│  │  • Distributed rate limiting                             │  │
│  └──────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────┘
```

---

## NATS Stream Topology

### Stream Definitions

```yaml
# orion-streams.yaml

streams:
  - name: ZO_STATE
    subjects: ["zo.state.>"]
    retention: limits
    max_age: 7d
    max_msgs_per_subject: 100
    storage: file
    replicas: 3
    description: "Per-node state snapshots for rehydration"

  - name: ZO_EVENTS
    subjects: ["zo.events.>"]
    retention: limits
    max_age: 24h
    storage: file
    replicas: 3
    description: "Audit log of all node lifecycle events"

  - name: ORION_CONSENSUS
    subjects: ["orion.consensus.>"]
    retention: limits
    max_age: 1h
    storage: memory
    replicas: 3
    description: "In-flight consensus rounds (short-lived)"

  - name: ORION_REGISTRY
    subjects: ["orion.registry.>"]
    retention: limits
    max_age: 30d
    max_msgs_per_subject: 1
    storage: file
    replicas: 3
    description: "Skill marketplace state — authoritative registry"

  - name: ORION_HEARTBEAT
    subjects: ["orion.heartbeat.>"]
    retention: limits
    max_age: 2m
    storage: memory
    replicas: 1
    description: "Live node health signals (ephemeral)"
```

### Subject Naming Convention

```
zo.state.{node_id}           — node state snapshot
zo.state.{node_id}.delta     — incremental state update
zo.events.{node_id}.{event}  — lifecycle event (startup, shutdown, error)

orion.consensus.{round_id}   — consensus proposal
orion.consensus.{round_id}.vote.{node_id} — node vote

orion.registry.skills        — current skill marketplace state
orion.registry.nodes         — active node registry

orion.heartbeat.{node_id}    — 10s heartbeat (last-value cache)
orion.control.{node_id}      — control plane commands to specific node
orion.broadcast              — broadcast to all nodes
```

---

## Node Identity & Registration

Every Zo node participating in the Orion mesh must have:

```python
# src/orion/node_identity.py

from dataclasses import dataclass, field
from typing import Optional
import uuid
import time

@dataclass
class NodeIdentity:
    node_id: str = field(default_factory=lambda: f"zo-{uuid.uuid4().hex[:8]}")
    node_type: str = "zo-worker"          # zo-worker | zo-primary | orion-hub
    capabilities: list[str] = field(default_factory=list)
    region: str = "us-east-1"
    version: str = "3.7.0"
    registered_at: float = field(default_factory=time.time)
    last_seen: float = field(default_factory=time.time)
    auth_token: Optional[str] = None      # Discord/service auth
    mesh_key: Optional[str] = None        # HMAC key for mesh auth

    def to_bytes(self) -> bytes:
        import json
        return json.dumps(self.__dict__).encode()

    @classmethod
    def from_bytes(cls, data: bytes) -> "NodeIdentity":
        import json
        return cls(**json.loads(data.decode()))
```

### Registration Flow

```
Node Startup:
  1. Check NATS for existing identity: GET orion.registry.nodes.{node_id}
  2. If found → rehydrate (diskless truth in action)
  3. If not found → generate new identity, publish to orion.registry.nodes.{node_id}
  4. Begin heartbeat loop: publish to orion.heartbeat.{node_id} every 10s
  5. Subscribe to orion.control.{node_id} (receive control plane commands)
  6. Subscribe to orion.broadcast (receive mesh-wide commands)
  7. Announce: publish zo.events.{node_id}.startup
```

---

## Consensus Engine

Orion uses a simplified **Raft-inspired** consensus for decisions that affect the whole mesh (skill updates, config changes, node promotions).

### When Consensus Is Required

| Decision | Consensus Required? | Threshold |
|----------|--------------------|-----------| 
| Skill marketplace update | Yes | Simple majority (>50%) |
| Node promotion to primary | Yes | Strong majority (>67%) |
| Emergency node eviction | Yes | Strong majority (>67%) |
| Individual tool invocation | No | Node handles locally |
| State snapshot | No | Node publishes directly |

### Consensus Protocol

```
PROPOSAL:
  → Proposer publishes to orion.consensus.{round_id}
  → Round contains: proposal_type, payload, proposer_id, timeout_ms

VOTING:
  → Each active node subscribes to orion.consensus.>
  → Evaluates proposal against local state + guardrails
  → Publishes vote to orion.consensus.{round_id}.vote.{node_id}
  → Vote payload: {vote: "yes"|"no"|"abstain", reason: "..."}

RESOLUTION:
  → Any node can tally votes once timeout expires
  → Result published to orion.consensus.{round_id}.result
  → All nodes apply or reject based on result

GUARDRAILS:
  → No consensus round can authorize destructive operations without operator override
  → Consensus results are immutable once published (append-only log)
  → Minimum 2 nodes required for any consensus round
```

---

## Tool Router (Load Balancing)

When a request comes into the mesh, Orion routes it to the best available node:

```python
# src/orion/tool_router.py

class OrionToolRouter:
    """
    Routes tool/LLM requests across the mesh.
    Strategy: lowest-latency node with the required capability.
    """

    async def route(
        self,
        tool_name: str,
        payload: dict,
        strategy: str = "lowest_latency"  # lowest_latency | round_robin | capability_match
    ) -> dict:

        # 1. Get active nodes with required capability
        capable_nodes = await self.find_capable_nodes(tool_name)

        if not capable_nodes:
            raise NoCapableNodeError(f"No node can handle: {tool_name}")

        # 2. Select node based on strategy
        target_node = self.select_node(capable_nodes, strategy)

        # 3. Route via NATS request/reply
        response = await self.nats.request(
            subject=f"orion.control.{target_node.node_id}",
            payload={"tool": tool_name, "input": payload},
            timeout=30.0
        )

        return response

    async def find_capable_nodes(self, tool_name: str) -> list[NodeStatus]:
        """Find nodes that have the required tool/skill loaded."""
        all_nodes = await self.get_active_nodes()
        return [n for n in all_nodes if tool_name in n.capabilities]

    def select_node(self, nodes: list, strategy: str) -> NodeStatus:
        if strategy == "lowest_latency":
            return min(nodes, key=lambda n: n.avg_latency_ms)
        elif strategy == "round_robin":
            return nodes[self._rr_counter % len(nodes)]
        elif strategy == "capability_match":
            return nodes[0]  # Already filtered by capability
        return nodes[0]
```

---

## Skill Marketplace Synchronization

The Skill Marketplace is distributed across the mesh — every node has a local cache, and NATS is the authoritative source:

```
SYNC PROTOCOL:
  1. When a skill is installed/updated on any node:
     → Publish to orion.registry.skills (KV-style last-value)
     → Include: skill_name, version, checksum, compatible_nodes

  2. All nodes subscribe to orion.registry.skills
     → On update: check local version vs published version
     → If outdated: trigger hot-swap via registry.hot_swap(skill_name)

  3. Skill discovery:
     → Any external client can query orion.registry.skills
     → Returns full marketplace state including all nodes' skill sets
     → "Install" a skill = publish to registry → all capable nodes auto-sync
```

---

## Failover & Self-Healing

```
FAILURE DETECTION:
  → Heartbeat timeout: if a node's heartbeat goes silent for 30s,
    the mesh marks it SUSPECTED
  → After 60s silence: node marked DEAD, mesh reconfigures

FAILOVER SEQUENCE (< 30s end-to-end):
  T+0s:   Heartbeat silence detected
  T+10s:  Node marked SUSPECTED, control plane notified
  T+20s:  Backup node begins hydrating from NATS state
  T+25s:  Backup node registers as replacement in orion.registry.nodes
  T+30s:  Traffic routes to new node, old node marked DEAD

SELF-HEALING:
  → Dead node slot stays open in the registry
  → When old node restarts (crash recovery), it rehydrates from NATS
  → Publishes zo.events.{node_id}.recovery
  → Rejoins mesh as a fresh worker (no leader promotion by default)
```

---

## Implementation Roadmap

### Phase 1 — Foundation (Now)
```
✅ Zo Super Server hardened (ZO-HARDEN-001)
✅ NATS rehydration proven (NATS-REHYDRATE-001)
⬜ orion/node_identity.py — Node identity + registration
⬜ orion/heartbeat.py — 10s heartbeat publisher/monitor
⬜ orion/nats_streams.py — Stream provisioning on startup
```

### Phase 2 — Coordination
```
⬜ orion/tool_router.py — Capability-aware request routing
⬜ orion/consensus.py — Simplified Raft consensus engine
⬜ orion/skill_sync.py — Distributed marketplace synchronization
⬜ orion/failover.py — Node failure detection + replacement
```

### Phase 3 — Observability
```
⬜ orion/dashboard.py — Real-time mesh state dashboard (FastAPI + WebSocket)
⬜ orion/audit_log.py — Immutable event log reader
⬜ orion/metrics.py — Prometheus-compatible metrics export
⬜ Grafana dashboard template for mesh visibility
```

### Phase 4 — Production Hardening
```
⬜ Mesh authentication (HMAC-signed NATS messages)
⬜ Multi-region NATS cluster (3+ nodes)
⬜ Chaos testing suite (random node kills, network partitions)
⬜ SLA monitoring: P99 latency < 100ms, failover < 30s
```

---

## Key Design Decisions (ADR)

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Coordination bus | NATS JetStream | Already used, proven, persistent, fast |
| Consensus algorithm | Raft-inspired (simplified) | Well-understood, good tooling, fits our scale |
| Leader election | Dynamic (no fixed leader) | Resilience > performance at current scale |
| State format | JSON (→ msgpack later) | Debuggable now, optimize when needed |
| Skill sync | Eventually consistent | Strong consistency not needed for skills |
| Auth | HMAC mesh key (Phase 4) | Defer until mesh is proven, add before prod |

---

## Files to Create

```
src/
├── orion/
│   ├── __init__.py
│   ├── node_identity.py       — Node ID + registration
│   ├── heartbeat.py           — 10s heartbeat loop
│   ├── nats_streams.py        — Stream provisioning
│   ├── tool_router.py         — Capability-aware routing
│   ├── consensus.py           — Voting + resolution
│   ├── skill_sync.py          — Marketplace sync
│   ├── failover.py            — Health monitoring + replacement
│   └── dashboard.py           — WS-based mesh visibility

protocols/
│   └── orion-hub-architecture.md  ← THIS DOCUMENT
│   └── orion-phase1-dispatch.md   ← Next protocol run
```

---

## Next Protocol Run

**Dispatch ID:** ORION-BUILD-001  
**Mode:** Build  
**Goal:** Implement Phase 1 of Orion Hub (node_identity + heartbeat + stream provisioning)  
**Prerequisite:** ZO-HARDEN-001 PASSED + NATS-REHYDRATE-001 PASSED  
**Estimated build time:** 2–3 hours  

*Ready to draft ORION-BUILD-001 dispatch on your command.*
