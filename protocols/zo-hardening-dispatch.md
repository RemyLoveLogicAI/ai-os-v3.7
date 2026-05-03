# Zo Super Server — Persistence Hardening Dispatch
**Protocol Version:** 3.0  
**Dispatch ID:** ZO-HARDEN-001  
**Date:** 2026-05-02  
**Operator:** remysr  
**Status:** READY TO RUN

---

## Trigger / Context

Zo control-plane instability observed:
- **SIGTERMs** not handled gracefully → partial state writes on shutdown
- **Fatal loops** — service restarts into broken state, loops indefinitely
- **Discord secret leaks** — credentials appearing in logs or config dumps
- **Orion Hub rollout blocked** — cannot extend mesh to Orion until Zo foundation is rock-solid

This dispatch hardens Zo Super Server to production-grade persistence before Orion Hub integration begins.

---

## Mode

`Hardening Dispatch` — Persistence & Stability

---

## Identity Phase

- **Agent:** zo-hardening-agent
- **Operator:** remysr
- **Credentials:** shell access, supervisorctl, log tail permissions
- **Scope:** /srv/zo (all subdirectories)
- **Context:** Zo Super Server running on NATS-first architecture. Local disk is cache, not truth.

---

## Guardrails / Constraints

```
HARD LIMITS:
✗ No destructive actions outside /srv/zo
✗ No credential exfiltration (Discord tokens, API keys never in logs)
✗ No changes to NATS streams without explicit operator approval
✗ No multi-step changes without checkpoint between each step

MANDATORY PATTERNS:
✓ Pre/post verification loop on EVERY config change (see Guardrail Loop)
✓ supervisorctl status + log tail after EVERY restart
✓ Rollback plan documented BEFORE each change is applied
✓ All credentials must use environment variables, never hardcoded

AUTO-ROLLBACK TRIGGERS:
→ Fatal loop detected (3 restarts in <60s)
→ NATS connection loss lasting >10s
→ Credential found in stdout/stderr log
```

---

## Goal

Achieve **rock-solid persistence**: 100% state recovery after `kill -9`, restart in <5 seconds, zero partial writes, no fatal loops, Discord secrets fully secured and rotated.

---

## Success Criteria

- [ ] `kill -9 $(pidof zo-server)` → Full state recovery from NATS within 5s
- [ ] No fatal loop on restart (3 consecutive clean starts)
- [ ] SIGTERM handled: graceful shutdown writes final state to NATS before exit
- [ ] Discord secrets NOT present in any log file (grep clean)
- [ ] Supervisorctl shows `RUNNING` status continuously for 60+ seconds post-hardening
- [ ] NATS stream contains valid node-id and auth-token after disk wipe test

---

## Council Input / Debate

**Approaches Considered:**
1. Patch SIGTERM handler in-place (fast, minimal disruption)
2. Rebuild supervisor config from scratch (clean, but risky mid-operation)
3. Layered approach: patch → verify → rotate → verify (chosen)

**Trade-offs:**
- Option 1 alone doesn't address fatal loop root cause
- Option 2 risks config drift introduction
- Option 3 is slower but each step is independently verifiable

**Consensus:** Layered approach. Mandatory verification loop between each layer.  
**Senate Approval:** ✅ APPROVED — mandatory guardrail loop enforced

---

## Plan

### Phase 1: Audit
```bash
# Step 1.1 — Baseline health check
supervisorctl status
echo "---BASELINE---"

# Step 1.2 — Check current SIGTERM handler
grep -n "SIGTERM\|signal\|atexit\|shutdown" /srv/zo/src/*.py

# Step 1.3 — Check supervisor config
cat /etc/supervisor/conf.d/zo.conf

# Step 1.4 — Tail recent logs for error patterns
tail -n 100 /var/log/zo/zo.log | grep -E "ERROR|FATAL|SIGTERM|restart"

# Step 1.5 — Scan logs for credential leaks
grep -iE "discord|token|secret|password|api_key" /var/log/zo/zo.log
```
**Checkpoint:** Document baseline. No proceed until audit complete.

---

### Phase 2: Patch SIGTERM Handler
```python
# /srv/zo/src/lifecycle.py — Add/update graceful shutdown

import signal
import asyncio
import logging

log = logging.getLogger("zo.lifecycle")

def register_shutdown_handler(app_state, nats_client):
    """Register SIGTERM/SIGINT handler that writes state to NATS before exit."""
    
    async def _graceful_shutdown(signum, frame):
        log.info(f"[ZO] Received signal {signum} — initiating graceful shutdown")
        try:
            await nats_client.publish(
                "zo.lifecycle.shutdown",
                app_state.to_bytes()
            )
            await nats_client.flush(timeout=3.0)
            log.info("[ZO] State flushed to NATS — clean exit")
        except Exception as e:
            log.error(f"[ZO] Shutdown flush failed: {e}")
        finally:
            asyncio.get_event_loop().stop()
    
    signal.signal(signal.SIGTERM, lambda s, f: asyncio.ensure_future(_graceful_shutdown(s, f)))
    signal.signal(signal.SIGINT,  lambda s, f: asyncio.ensure_future(_graceful_shutdown(s, f)))
    log.info("[ZO] Shutdown handlers registered")
```

**Post-Edit Verification:**
```bash
supervisorctl restart zo
sleep 3
supervisorctl status
tail -n 20 /var/log/zo/zo.log
```

---

### Phase 3: Fix Fatal Loop
```ini
# /etc/supervisor/conf.d/zo.conf — Anti-loop config

[program:zo]
command=/srv/zo/venv/bin/python /srv/zo/src/main.py
directory=/srv/zo
autostart=true
autorestart=true
startretries=3              ; Max 3 retries before FATAL state
startsecs=5                 ; Must run 5s before considered "started"
stopwaitsecs=10             ; Wait 10s for graceful shutdown
killasgroup=true
stopasgroup=true
redirect_stderr=true
stdout_logfile=/var/log/zo/zo.log
stdout_logfile_maxbytes=50MB
stdout_logfile_backups=5
environment=ZO_ENV="production"
```

**Post-Edit Verification:**
```bash
supervisorctl reread
supervisorctl update
supervisorctl status zo
# Confirm: no FATAL state, startretries not exhausted
```

---

### Phase 4: Rotate Discord Secrets
```bash
# Step 4.1 — Remove any hardcoded credentials
grep -rn "DISCORD_TOKEN\|discord_token\|Bot " /srv/zo/src/ --include="*.py"

# Step 4.2 — Verify .env file exists and is not committed
ls -la /srv/zo/.env
cat /srv/zo/.gitignore | grep .env

# Step 4.3 — Rotate: update .env with new token
# !! OPERATOR ACTION REQUIRED — paste new token here !!
# nano /srv/zo/.env
# DISCORD_TOKEN=<new_rotated_token>

# Step 4.4 — Verify env loads correctly
grep -n "os.getenv\|os.environ" /srv/zo/src/config.py

# Step 4.5 — Confirm token NOT in logs after restart
supervisorctl restart zo
sleep 5
grep -i "discord\|token\|Bot " /var/log/zo/zo.log
# Expected: zero matches
```

---

### Phase 5: kill -9 Recovery Test
```bash
# Step 5.1 — Record current NATS state
nats sub zo.state.snapshot --count=1

# Step 5.2 — Hard kill
kill -9 $(pidof python)  # or pidof zo-server

# Step 5.3 — Supervisor auto-restart (should happen within 5s)
sleep 6
supervisorctl status zo

# Step 5.4 — Verify state recovered from NATS
tail -n 30 /var/log/zo/zo.log | grep "rehydrat\|recover\|NATS"

# Step 5.5 — Confirm node-id and auth-token present
grep -E "node.id|auth.token|identity" /var/log/zo/zo.log | tail -5
```

---

## Outcome
*(Fill after execution)*

---

## Findings
*(Fill after execution)*

---

## Evidence / Proof

Collect and attach:
- [ ] `supervisorctl status` output (before + after)
- [ ] Log excerpts showing SIGTERM handling
- [ ] Log grep showing ZERO credential leaks
- [ ] kill -9 test output
- [ ] NATS event trace showing state flush on shutdown

---

## Artifacts Created

- [ ] `/srv/zo/src/lifecycle.py` — Updated shutdown handler
- [ ] `/etc/supervisor/conf.d/zo.conf` — Updated anti-loop config
- [ ] `/srv/zo/.env` — Rotated Discord secret
- [ ] This runbook (signed off with evidence)

---

## Remediation

*(Document any failures and fixes applied here after execution)*

---

## Final Verification

- [ ] `kill -9` test: full state recovery observed ✓/✗
- [ ] No fatal loops: 3 consecutive clean starts ✓/✗
- [ ] SIGTERM handled: graceful shutdown logged ✓/✗
- [ ] Discord secrets: log grep clean ✓/✗
- [ ] Supervisor RUNNING: 60s sustained ✓/✗

**Overall:** PASS ✅ / FAIL ❌ / PARTIAL ⚠️

---

## Learning / Update

*(Post-run: document what changes to soul.md or agent instructions this run triggers)*

---

## Rollback

```bash
# Restore previous supervisor config
cp /etc/supervisor/conf.d/zo.conf.bak /etc/supervisor/conf.d/zo.conf
supervisorctl reread && supervisorctl update

# Restore previous lifecycle.py
cp /srv/zo/src/lifecycle.py.bak /srv/zo/src/lifecycle.py
supervisorctl restart zo

# Verify rollback
supervisorctl status zo
tail -n 20 /var/log/zo/zo.log
```

**Estimated time to rollback:** <2 minutes  
**Backup location:** `/srv/zo/backups/pre-harden-<timestamp>/`

---

## Next Evolution

Once this dispatch passes final verification:
- [ ] Extend hardening to **Orion Hub** (same SIGTERM + supervisor pattern)
- [ ] Implement **NATS health heartbeat** (publish every 30s, alert on silence)
- [ ] Add **supervisord web UI** for real-time status visibility
- [ ] Set up **log aggregation** (Loki or similar) for cross-service correlation
- [ ] Draft `orion-hardening-dispatch.md` using this runbook as template
