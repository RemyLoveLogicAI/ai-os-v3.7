# NATS Rehydration Experiment — Protocol Run
**Protocol Version:** 3.0  
**Experiment ID:** NATS-REHYDRATE-001  
**Date:** 2026-05-02  
**Operator:** remysr  
**Hypothesis:** Zo Super Server can fully rehydrate node-id, auth-token, and tool registry from NATS after complete local disk wipe — with zero manual intervention.

---

## Trigger / Context

**Hypothesis to prove:**  
Local disk is cache. NATS is truth. If `/srv/zo/data` is wiped completely, a Zo restart should restore full operational identity and capability from NATS streams alone.

**Why this matters:**  
- Proves the diskless-truth architecture is sound
- Enables ephemeral compute (containers, spot instances) without state loss
- Foundation for Orion Hub multi-node mesh (each node rehydrates from shared NATS)
- Proves kill -9 resilience at the architectural level, not just the service level

**Risk:**  
If rehydration fails, Zo will start in a "blank" state — new node-id, lost tool registry. This is recoverable from NATS backup but would prove the architecture has gaps.

---

## Mode

`Experiment` — Diskless-Truth Rehydration Test (Hypothesis Validation)

---

## Identity Phase

- **Agent:** zo-super-server (subject under test)
- **Operator:** remysr
- **Credentials:** NATS stream access (full read/write), shell access to /srv/zo
- **Context:** Zo hardening dispatch complete. SIGTERM handler writes state to NATS. This experiment validates that NATS write was complete and rehydration path works end-to-end.

---

## Guardrails / Constraints

```
HARD LIMITS:
✗ Delete ONLY /srv/zo/data — NOT /srv/zo/src, /srv/zo/config, /srv/zo/venv
✗ No changes to NATS streams during the experiment (read-only during test window)
✗ Do NOT wipe NATS if local wipe fails — preserve truth source

PRECONDITIONS (must be true before starting):
✓ Zo hardening dispatch PASSED
✓ NATS stream contains a recent state snapshot (verify before proceeding)
✓ /srv/zo/data backup created at /srv/zo/backups/pre-wipe-<timestamp>/
✓ supervisorctl stopped — manual start for controlled observation

ROLLBACK TRIGGERS:
→ Rehydration incomplete after 30s → immediate rollback from backup
→ NATS stream unreachable → abort, do NOT wipe local data
→ node-id mismatch after rehydration → flag as partial failure, document
```

---

## Goal

After deleting `/srv/zo/data` and restarting Zo Super Server, confirm that **node-id**, **auth-token**, and **tool registry** are fully restored from NATS with zero manual intervention in under 30 seconds.

---

## Success Criteria

- [ ] Pre-wipe: NATS stream contains valid state snapshot (verified with `nats sub`)
- [ ] Post-wipe: `/srv/zo/data` directory empty/absent
- [ ] Post-restart: Zo logs show "rehydrating from NATS" message
- [ ] Post-restart: node-id matches pre-wipe node-id exactly
- [ ] Post-restart: auth-token present and valid (Discord connection established)
- [ ] Post-restart: tool registry populated (same tools as pre-wipe)
- [ ] Time from restart to operational: < 30 seconds
- [ ] Zero manual intervention required

---

## Council Input / Debate

**Debate: When to publish state to NATS?**
- Option A: Publish on every state change (real-time sync)
- Option B: Publish on graceful shutdown only (SIGTERM handler)
- Option C: Publish on both + periodic heartbeat every 60s

**Consensus:** Option C. Periodic heartbeat ensures state is never stale by >60s even if SIGTERM is missed (kill -9 scenario). The 60s window is acceptable for recovery SLA.

**Debate: What to store in NATS?**
- Minimal: node-id + auth-token only
- Full: node-id + auth-token + tool registry + workspace config + conversation history
- Consensus: Full state minus conversation history (too large, not needed for recovery)

**Senate Approval:** ✅ APPROVED — Option C + Full state (no history)

---

## Plan

### Phase 0: Pre-Experiment Verification
```bash
# 0.1 — Confirm Zo is running and healthy
supervisorctl status zo
tail -n 20 /var/log/zo/zo.log

# 0.2 — Record pre-wipe state (node-id and auth-token)
# These values are your ground truth for comparison after rehydration
cat /srv/zo/data/identity.json
# Expected output example:
# {"node_id": "zo-abc123", "auth_token": "xoxb-...", "registered_at": "..."}

# 0.3 — Record pre-wipe tool registry
cat /srv/zo/data/tool_registry.json | python3 -m json.tool | head -40

# 0.4 — Verify NATS has current state
nats stream info ZO_STATE
nats sub zo.state.snapshot --count=1 > /tmp/pre_wipe_nats_state.json
echo "NATS state captured: $(wc -c < /tmp/pre_wipe_nats_state.json) bytes"

# 0.5 — Create local backup
mkdir -p /srv/zo/backups/pre-wipe-$(date +%Y%m%d-%H%M%S)/
cp -r /srv/zo/data/ /srv/zo/backups/pre-wipe-$(date +%Y%m%d-%H%M%S)/
echo "Backup created."
```
**CHECKPOINT:** Do NOT proceed until all 5 steps pass. NATS must have state. Backup must exist.

---

### Phase 1: Controlled Shutdown
```bash
# 1.1 — Graceful stop (SIGTERM → NATS flush)
supervisorctl stop zo
sleep 5

# 1.2 — Verify graceful shutdown logged
tail -n 10 /var/log/zo/zo.log | grep "shutdown\|NATS\|flush"
# Expected: "[ZO] State flushed to NATS — clean exit"

# 1.3 — Verify NATS has the latest state post-shutdown
nats sub zo.state.snapshot --count=1 > /tmp/post_shutdown_nats_state.json
diff /tmp/pre_wipe_nats_state.json /tmp/post_shutdown_nats_state.json
# If diff shows newer timestamp, shutdown flush worked ✓
```

---

### Phase 2: Local Data Wipe
```bash
# 2.1 — Delete ONLY the data directory
echo "Wiping /srv/zo/data..."
rm -rf /srv/zo/data
echo "Wipe complete. Verifying..."
ls /srv/zo/  # data/ should NOT appear
```

---

### Phase 3: Restart + Observe Rehydration
```bash
# 3.1 — Start with fresh data directory
supervisorctl start zo

# 3.2 — Watch rehydration in real-time
tail -f /var/log/zo/zo.log &
TAIL_PID=$!

# 3.3 — Wait up to 30 seconds for rehydration
sleep 30
kill $TAIL_PID

# 3.4 — Check for rehydration log lines
grep -E "rehydrat|recover|NATS|identity|node.id" /var/log/zo/zo.log | tail -20
```

---

### Phase 4: Post-Rehydration Verification
```bash
# 4.1 — Verify node-id matches pre-wipe
POST_NODE_ID=$(cat /srv/zo/data/identity.json | python3 -c "import sys,json; print(json.load(sys.stdin)['node_id'])")
PRE_NODE_ID="zo-abc123"  # Replace with actual pre-wipe value from Phase 0
echo "Pre-wipe: $PRE_NODE_ID"
echo "Post-rehydration: $POST_NODE_ID"
[ "$PRE_NODE_ID" = "$POST_NODE_ID" ] && echo "✅ node-id MATCH" || echo "❌ node-id MISMATCH"

# 4.2 — Verify auth-token present (don't print full token)
cat /srv/zo/data/identity.json | python3 -c "import sys,json; d=json.load(sys.stdin); print('auth_token present:', bool(d.get('auth_token')))"

# 4.3 — Verify tool registry restored
POST_TOOL_COUNT=$(cat /srv/zo/data/tool_registry.json | python3 -c "import sys,json; print(len(json.load(sys.stdin)['tools']))")
echo "Tools registered post-rehydration: $POST_TOOL_COUNT"

# 4.4 — Verify Discord connection (Zo responds to ping)
supervisorctl status zo
tail -n 5 /var/log/zo/zo.log | grep -i "discord\|connect\|ready"
```

---

## Outcome
*(Fill after execution)*

---

## Findings
*(Fill after execution — key questions to answer)*

- Did rehydration complete automatically? (Y/N)
- How long did rehydration take? (seconds)
- Was node-id preserved exactly?
- Was tool registry complete or partial?
- Any errors during rehydration?
- What would have failed without the NATS state?

---

## Evidence / Proof

Collect and attach:
- [ ] `cat /srv/zo/data/identity.json` output (pre-wipe)
- [ ] `nats sub zo.state.snapshot` output (pre-wipe)
- [ ] Terminal output of wipe commands
- [ ] Full log tail showing rehydration sequence
- [ ] node-id comparison output (MATCH/MISMATCH)
- [ ] Tool count before vs after
- [ ] Time measurement (start → operational)

---

## Artifacts Created

- [ ] `/tmp/pre_wipe_nats_state.json` — Pre-wipe NATS state capture
- [ ] `/tmp/post_shutdown_nats_state.json` — Post-shutdown NATS state capture
- [ ] `/srv/zo/backups/pre-wipe-<timestamp>/` — Local state backup
- [ ] This experiment log (signed off with evidence)

---

## Remediation

**If rehydration fails:**
```bash
# Restore from backup
cp -r /srv/zo/backups/pre-wipe-<timestamp>/data/ /srv/zo/data/
supervisorctl restart zo
supervisorctl status zo
```

**If NATS state is stale/incomplete:**
- Identify gap in state serialization
- Check what fields are missing from NATS payload
- Update state publisher to include missing fields
- Re-run experiment after fix

---

## Final Verification

- [ ] Pre-wipe NATS state captured: PASS / FAIL
- [ ] Local wipe completed: PASS / FAIL
- [ ] Rehydration from NATS: PASS / FAIL
- [ ] node-id preserved: PASS / FAIL
- [ ] auth-token present: PASS / FAIL
- [ ] Tool registry restored: PASS / FAIL
- [ ] Time < 30s: PASS / FAIL (actual: ___ seconds)

**Overall:** PASS ✅ / FAIL ❌ / PARTIAL ⚠️

---

## Learning / Update

*(Post-run: what protocol or architecture changes does this experiment trigger?)*

Key questions:
- Is 60s heartbeat interval the right SLA?
- Should workspace config be included in NATS state?
- Is NATS the right store, or should we add a backup (Redis, etcd)?

---

## Rollback

Restore from `/srv/zo/backups/pre-wipe-<timestamp>/data/`. Time to restore: <1 minute.

---

## Next Evolution

If experiment PASSES:
- [ ] Mark diskless-truth architecture as **PROVEN**
- [ ] Apply same pattern to Orion Hub nodes
- [ ] Document rehydration sequence in architecture ADR
- [ ] Enable ephemeral container deployments (no persistent volumes needed)
- [ ] Set up automated rehydration test in CI/CD pipeline

If experiment FAILS:
- [ ] Identify specific gaps in NATS state coverage
- [ ] Patch state publisher
- [ ] Re-run as `NATS-REHYDRATE-002`
