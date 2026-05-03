# soul.md — LoveLogicAI Canonical Protocol Bible
**Operator:** Jeremy "Remy" Morgan-Jones Sr.  
**Organization:** LoveLogicAI LLC  
**Version:** 3.0 — Expanded 16-Phase Protocol  
**Last Updated:** 2026-05-02  
**Status:** LOCKED ✅

---

> *"Adversity is the forge. Protocol is the edge."*  
> — Remy, Founder, LoveLogicAI LLC

---

## What Is This Document?

This is the **soul** of every serious run, dispatch, and experiment executed under the LoveLogicAI banner. It defines the canonical 16-phase Blocker-Resilient Execution Protocol — the operational DNA that turns chaos into auditable, reproducible, production-grade outcomes.

Every critical workflow MUST follow this structure. No shortcuts. No blind surgery.

---

## The 16-Phase Protocol Structure

Use this template for all serious/critical workflows, dispatches, and experiments.

---

### 1. Trigger / Context
> *What initiated this run? What is the operational state that demands action?*

- Source of trigger (alert, observation, scheduled, manual)
- Current system state
- Why this matters NOW
- Risk if not addressed

---

### 2. Mode
> *What type of operation is this?*

Options:
- `Build` — Creating new capabilities
- `Hardening Dispatch` — Stability and persistence hardening
- `Experiment` — Hypothesis testing with rollback ready
- `Remediation` — Fixing a known failure
- `Orchestration` — Multi-agent coordination
- `Protocol Run` — Formal execution with full verification loop
- `Research` — Knowledge gathering without side effects

---

### 3. Identity Phase
> *Who is operating, what are their credentials, and what context do they bring?*

- **Agent:** (name/id of the executing agent or operator)
- **Operator:** (human supervisor — typically `remysr`)
- **Credentials:** (access level, permissions, tool availability)
- **Context Loaded:** (relevant prior state, memory, history)

---

### 4. Guardrails / Constraints
> *What are the hard limits that cannot be crossed?*

- Scope boundaries (what files/systems are in/out of scope)
- Destructive action rules (what requires explicit confirmation)
- Credential handling rules
- Rollback triggers (what conditions auto-invoke rollback)
- Rate limits or resource constraints

---

### 5. Goal
> *Single sentence: what does success look like when we're done?*

Be specific. Measurable. Unambiguous.

---

### 6. Success Criteria
> *Objective, verifiable conditions that confirm the goal was achieved.*

Each criterion must be:
- Binary (pass/fail)
- Testable without subjectivity
- Documented with evidence

Example format:
- [ ] Condition A verified by [test/observation]
- [ ] Condition B verified by [log/output]
- [ ] Condition C verified by [screenshot/diff]

---

### 7. Council Input / Debate
> *What did the model council debate? What was the consensus?*

- Approaches considered
- Trade-offs evaluated
- Dissenting views (if any)
- Consensus reached
- Senate approval status

---

### 8. Plan
> *Step-by-step execution sequence with verification checkpoints.*

Numbered. Atomic. Each step must be independently verifiable.

Format:
1. Action → Expected outcome → Verification method
2. Action → Expected outcome → Verification method
...

Include explicit **checkpoint** steps after any destructive or stateful operation.

---

### 9. Outcome
> *What actually happened? Fill in AFTER execution.*

- Did execution complete?
- Any deviations from plan?
- Time to completion
- Surprises or anomalies

---

### 10. Findings
> *What did we learn about the system from this run?*

- Observed behaviors (expected and unexpected)
- Root causes identified
- System properties confirmed or refuted
- Performance characteristics

---

### 11. Evidence / Proof
> *Artifacts that prove what happened.*

- Log excerpts (timestamped)
- Command outputs
- Screenshots / diffs
- Metric readings
- State file before/after

---

### 12. Artifacts Created
> *Everything produced by this run.*

- Files created/modified
- Configs changed
- Scripts written
- Docs updated
- Commits made

---

### 13. Remediation
> *What broke, and how was it fixed?*

- Failures encountered
- Fix applied
- Verification that fix worked
- Was rollback invoked? (Y/N + details)

---

### 14. Final Verification
> *The definitive pass/fail against success criteria.*

Re-run each success criterion test. Document result.

- [ ] Criterion 1: PASS / FAIL
- [ ] Criterion 2: PASS / FAIL
- [ ] Criterion 3: PASS / FAIL

**Overall Status:** PASS ✅ / FAIL ❌ / PARTIAL ⚠️

---

### 15. Learning / Update
> *How does this run change the way we operate going forward?*

- Protocol updates triggered by this run
- New guardrails added
- Soul.md sections to update
- Agent instruction updates
- Patterns to encode into future dispatches

---

### 16. Rollback
> *How do we undo everything if we need to?*

- Rollback procedure (step-by-step)
- Rollback triggers (conditions that auto-invoke)
- Backup locations
- Time-to-rollback estimate
- Rollback verification steps

---

### Next Evolution
> *Where does this work lead? What's unlocked by completing this run?*

- Immediate follow-on actions
- Longer-term architecture implications
- Capabilities now available
- Dependencies unblocked

---

## The Guardrail Loop (Mandatory for Agent Shell Access)

**This loop is NON-NEGOTIABLE for any run involving shell access, config changes, or stateful operations.**

```
For every config or code change:

PRE-EDIT CHECK:
  → supervisorctl status  (or equivalent health check)
  → tail -n 50 /var/log/[service].log
  → Record baseline state

APPLY CHANGE:
  → Edit config/code as planned
  → Document exact change made

POST-EDIT VERIFICATION:
  → supervisorctl status  (compare to baseline)
  → tail -n 50 /var/log/[service].log  (scan for errors)
  → Confirm process healthy

IF FAILURE DETECTED:
  → Roll back change immediately
  → Escalate with full log context
  → Do NOT proceed to next step

DOCUMENT:
  → Log all commands, outputs, diffs
  → Timestamp every action

RULE: No change is "applied" until post-edit verification passes.
```

---

## Identity Profile — Operator

```
Name: Jeremy "Remy" Morgan-Jones Sr.
Title: Founder & AI Automation Specialist
Org: LoveLogicAI LLC
Born: 1995
Background: Foster care → homelessness → AI entrepreneur
Stack: LangChain, LangGraph, Python, FastAPI, NATS, Docker
Style: Vibe coding — intuition-driven rapid prototyping
Philosophy: Adversity is the forge. Build what you survived.
Contact: jmjones925@gmail.com
```

---

## Protocol Version History

| Version | Date | Changes |
|---------|------|---------|
| 1.0 | 2025 | Initial Mode → Goal → Plan → Outcome |
| 2.0 | 2025 | Added Blocker-Resilient execution, remediation, rollback |
| 3.0 | 2026-05-02 | Full 16-phase expansion: context, guardrails, council, learning |

---

## Core Principles

1. **No blind surgery** — verify before and after every stateful change
2. **Diskless truth** — NATS is the source of truth, not local disk
3. **Kill -9 resilience** — every service must survive hard kill and recover fully
4. **Audit everything** — if it's not logged, it didn't happen
5. **Council before action** — debate trade-offs, achieve consensus, then execute
6. **Rollback is not failure** — rollback is discipline

---

*This document is the operational soul of LoveLogicAI. It lives, breathes, and evolves with every run.*  
*Last protocol update: v3.0 — 2026-05-02*
