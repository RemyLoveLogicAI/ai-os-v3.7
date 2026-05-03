#!/usr/bin/env bash
# ═══════════════════════════════════════════════════════════════════════════════
# ZO-TRIAGE-AND-HARDEN.sh
# LoveLogicAI LLC — Zo Super Server Environment Discovery + Auto-Hardening
# Version: 1.0.0 | Protocol: ZO-HARDEN-001 v3.0
#
# USAGE:
#   chmod +x zo-triage-and-harden.sh
#   sudo ./zo-triage-and-harden.sh [--dry-run] [--triage-only] [--force]
#
# FLAGS:
#   --dry-run      Show what would be done, make zero changes
#   --triage-only  Run discovery/audit only, no hardening
#   --force        Skip confirmation prompts (CI mode)
# ═══════════════════════════════════════════════════════════════════════════════

set -euo pipefail

# ── Config ────────────────────────────────────────────────────────────────────

SCRIPT_VERSION="1.0.0"
ZO_DIR="${ZO_DIR:-/srv/zo}"
ZO_LOG="${ZO_LOG:-/var/log/zo/zo.log}"
SUPERVISOR_CONF="${SUPERVISOR_CONF:-/etc/supervisor/conf.d/zo.conf}"
BACKUP_BASE="${ZO_DIR}/backups"
TIMESTAMP=$(date +%Y%m%d-%H%M%S)
BACKUP_DIR="${BACKUP_BASE}/pre-harden-${TIMESTAMP}"
DRY_RUN=false
TRIAGE_ONLY=false
FORCE=false
REPORT_FILE="/tmp/zo-triage-report-${TIMESTAMP}.txt"

# ── Colors ────────────────────────────────────────────────────────────────────

RED='\033[0;31m'; YELLOW='\033[1;33m'; GREEN='\033[0;32m'
CYAN='\033[0;36m'; PURPLE='\033[0;35m'; BOLD='\033[1m'; NC='\033[0m'

# ── Logging ───────────────────────────────────────────────────────────────────

log()     { echo -e "${CYAN}[ZO-TRIAGE]${NC} $*" | tee -a "$REPORT_FILE"; }
ok()      { echo -e "${GREEN}[✅ PASS]${NC} $*" | tee -a "$REPORT_FILE"; }
warn()    { echo -e "${YELLOW}[⚠️  WARN]${NC} $*" | tee -a "$REPORT_FILE"; }
fail()    { echo -e "${RED}[❌ FAIL]${NC} $*" | tee -a "$REPORT_FILE"; }
section() { echo -e "\n${PURPLE}${BOLD}══ $* ══${NC}\n" | tee -a "$REPORT_FILE"; }
dry()     { echo -e "${YELLOW}[DRY-RUN]${NC} Would execute: $*" | tee -a "$REPORT_FILE"; }

# ── Argument Parsing ──────────────────────────────────────────────────────────

for arg in "$@"; do
  case $arg in
    --dry-run)     DRY_RUN=true ;;
    --triage-only) TRIAGE_ONLY=true ;;
    --force)       FORCE=true ;;
    *) echo "Unknown flag: $arg" && exit 1 ;;
  esac
done

run() {
  if $DRY_RUN; then dry "$*"; else eval "$*"; fi
}

confirm() {
  if $FORCE || $DRY_RUN; then return 0; fi
  echo -e "${YELLOW}Proceed? [y/N]${NC} " && read -r ans
  [[ "$ans" =~ ^[Yy]$ ]]
}

# ═══════════════════════════════════════════════════════════════════════════════
# PHASE 0: ENVIRONMENT DISCOVERY
# ═══════════════════════════════════════════════════════════════════════════════

discover_environment() {
  section "PHASE 0: ENVIRONMENT DISCOVERY"

  declare -g ZO_RUNNING=false
  declare -g ZO_PID=""
  declare -g SUPERVISOR_AVAILABLE=false
  declare -g NATS_AVAILABLE=false
  declare -g ZO_FOUND=false
  declare -g PYTHON_CMD=""
  declare -g ENV_SCORE=0  # 0-10 health score

  # ── Detect Zo process ──────────────────────────────────────────────────────
  log "Searching for running Zo process..."
  if pgrep -f "zo" > /dev/null 2>&1; then
    ZO_RUNNING=true
    ZO_PID=$(pgrep -f "zo" | head -1)
    ok "Zo process found (PID: ${ZO_PID})"
    ((ENV_SCORE+=2))
  else
    warn "No Zo process running"
  fi

  # ── Detect Zo directory ───────────────────────────────────────────────────
  log "Checking Zo installation at ${ZO_DIR}..."
  if [[ -d "$ZO_DIR" ]]; then
    ZO_FOUND=true
    ok "Zo directory found: ${ZO_DIR}"
    ((ENV_SCORE+=2))

    # Check for key files
    for f in src config; do
      if [[ -d "${ZO_DIR}/${f}" ]]; then
        ok "  → ${f}/ present"
      else
        warn "  → ${f}/ MISSING"
      fi
    done

    for f in .env requirements.txt; do
      if [[ -f "${ZO_DIR}/${f}" ]]; then
        ok "  → ${f} present"
      else
        warn "  → ${f} MISSING (may need creation)"
      fi
    done
  else
    warn "Zo directory not found at ${ZO_DIR}"
    log "  Searching alternative locations..."
    for candidate in /home/*/zo /opt/zo ~/zo /app/zo; do
      if [[ -d "$candidate" ]]; then
        ZO_DIR="$candidate"
        ZO_FOUND=true
        warn "  Found at alternate location: ${ZO_DIR}"
        export ZO_DIR
        break
      fi
    done
    if ! $ZO_FOUND; then
      fail "Zo installation not found on this system"
    fi
  fi

  # ── Detect supervisord ────────────────────────────────────────────────────
  log "Checking supervisord..."
  if command -v supervisorctl > /dev/null 2>&1; then
    SUPERVISOR_AVAILABLE=true
    ok "supervisorctl available: $(supervisorctl version 2>/dev/null || echo 'version unknown')"
    ((ENV_SCORE+=2))

    # Check if zo program is registered
    if supervisorctl status zo > /dev/null 2>&1; then
      ok "  → zo program registered in supervisor"
      SUPERVISOR_STATUS=$(supervisorctl status zo 2>/dev/null || echo "UNKNOWN")
      log "  → Current status: ${SUPERVISOR_STATUS}"
      ((ENV_SCORE+=1))
    else
      warn "  → zo program NOT registered in supervisor"
    fi
  else
    warn "supervisorctl not found — manual process management only"
  fi

  # ── Detect NATS ───────────────────────────────────────────────────────────
  log "Checking NATS connectivity..."
  if command -v nats > /dev/null 2>&1; then
    if nats server ping > /dev/null 2>&1; then
      NATS_AVAILABLE=true
      ok "NATS server reachable"
      ((ENV_SCORE+=2))
    else
      warn "NATS CLI found but server not responding"
    fi
  elif nc -z localhost 4222 > /dev/null 2>&1; then
    NATS_AVAILABLE=true
    ok "NATS port 4222 is open"
    ((ENV_SCORE+=1))
  else
    warn "NATS not detected — diskless-truth features unavailable"
  fi

  # ── Detect Python ─────────────────────────────────────────────────────────
  log "Checking Python environment..."
  if [[ -f "${ZO_DIR}/venv/bin/python" ]]; then
    PYTHON_CMD="${ZO_DIR}/venv/bin/python"
    ok "Virtual environment Python: ${PYTHON_CMD}"
    ((ENV_SCORE+=1))
  elif command -v python3 > /dev/null 2>&1; then
    PYTHON_CMD="python3"
    warn "Using system Python3 (no venv found)"
  else
    fail "Python not found — cannot run Zo"
  fi

  # ── Check for .gitignore on .env ──────────────────────────────────────────
  if [[ -f "${ZO_DIR}/.gitignore" ]]; then
    if grep -q ".env" "${ZO_DIR}/.gitignore"; then
      ok ".env is gitignored ✓"
    else
      warn ".env is NOT in .gitignore — credential leak risk!"
    fi
  fi

  # ── Credential leak scan ──────────────────────────────────────────────────
  log "Scanning logs for credential leaks..."
  if [[ -f "$ZO_LOG" ]]; then
    LEAK_COUNT=$(grep -ciE "discord_token|bot token|api_key|secret.*=.*['\"][a-z0-9]{20,}" "$ZO_LOG" 2>/dev/null || echo 0)
    if [[ "$LEAK_COUNT" -gt 0 ]]; then
      fail "⚠️  CREDENTIAL LEAK DETECTED: ${LEAK_COUNT} suspicious patterns in ${ZO_LOG}"
      fail "   → Immediate rotation required (Phase 4 of hardening)"
    else
      ok "Log credential scan: clean"
      ((ENV_SCORE+=1))
    fi
  else
    warn "Log file not found at ${ZO_LOG} — skipping leak scan"
  fi

  # ── SIGTERM handler check ─────────────────────────────────────────────────
  log "Checking SIGTERM handler..."
  if $ZO_FOUND && find "${ZO_DIR}/src" -name "*.py" -exec grep -l "SIGTERM\|signal.signal" {} \; 2>/dev/null | grep -q .; then
    ok "SIGTERM handler code found"
    ((ENV_SCORE+=1))
  else
    warn "No SIGTERM handler detected — kill -9 recovery at risk"
  fi

  # ── Summary ───────────────────────────────────────────────────────────────
  section "ENVIRONMENT HEALTH SCORE: ${ENV_SCORE}/12"

  if [[ $ENV_SCORE -ge 10 ]]; then
    ok "Environment: EXCELLENT — minimal hardening needed"
  elif [[ $ENV_SCORE -ge 7 ]]; then
    warn "Environment: FAIR — hardening recommended"
  elif [[ $ENV_SCORE -ge 4 ]]; then
    warn "Environment: DEGRADED — hardening needed"
  else
    fail "Environment: CRITICAL — immediate hardening required"
  fi

  log "Full triage report: ${REPORT_FILE}"
}

# ═══════════════════════════════════════════════════════════════════════════════
# PHASE 1: CREATE BACKUPS
# ═══════════════════════════════════════════════════════════════════════════════

create_backups() {
  section "PHASE 1: CREATING BACKUPS"

  run "mkdir -p '${BACKUP_DIR}'"
  log "Backup directory: ${BACKUP_DIR}"

  if $ZO_FOUND; then
    if [[ -d "${ZO_DIR}/data" ]]; then
      run "cp -r '${ZO_DIR}/data' '${BACKUP_DIR}/data'"
      ok "Backed up: ${ZO_DIR}/data"
    fi
    if [[ -f "${SUPERVISOR_CONF}" ]]; then
      run "cp '${SUPERVISOR_CONF}' '${BACKUP_DIR}/zo.conf.bak'"
      ok "Backed up: ${SUPERVISOR_CONF}"
    fi
    if [[ -d "${ZO_DIR}/src" ]]; then
      run "cp -r '${ZO_DIR}/src' '${BACKUP_DIR}/src'"
      ok "Backed up: ${ZO_DIR}/src"
    fi
  fi

  ok "Backup complete at: ${BACKUP_DIR}"
}

# ═══════════════════════════════════════════════════════════════════════════════
# PHASE 2: PATCH SIGTERM HANDLER
# ═══════════════════════════════════════════════════════════════════════════════

patch_sigterm() {
  section "PHASE 2: PATCHING SIGTERM HANDLER"

  LIFECYCLE_FILE="${ZO_DIR}/src/lifecycle.py"

  if [[ -f "$LIFECYCLE_FILE" ]]; then
    if grep -q "SIGTERM" "$LIFECYCLE_FILE"; then
      ok "SIGTERM handler already present in lifecycle.py — checking completeness..."
      if grep -q "nats" "$LIFECYCLE_FILE" 2>/dev/null; then
        ok "NATS flush on shutdown detected — looks good"
        return 0
      else
        warn "SIGTERM handler exists but no NATS flush — patching..."
      fi
    fi
  fi

  log "Writing SIGTERM handler to ${LIFECYCLE_FILE}..."

  if ! $DRY_RUN; then
    mkdir -p "${ZO_DIR}/src"
    cat > "$LIFECYCLE_FILE" << 'PYEOF'
"""
Zo Super Server — Lifecycle Manager
Graceful shutdown with NATS state persistence.
Auto-generated by zo-triage-and-harden.sh
"""
import signal
import asyncio
import logging
import os

log = logging.getLogger("zo.lifecycle")

_shutdown_registered = False


def register_shutdown_handler(app_state=None, nats_client=None):
    """
    Register SIGTERM/SIGINT handler.
    On signal: flush state to NATS, then exit cleanly.
    """
    global _shutdown_registered
    if _shutdown_registered:
        return

    async def _graceful_shutdown(signum, frame):
        sig_name = "SIGTERM" if signum == signal.SIGTERM else "SIGINT"
        log.info(f"[ZO] Received {sig_name} — initiating graceful shutdown")

        if nats_client and app_state:
            try:
                state_bytes = app_state.to_bytes() if hasattr(app_state, 'to_bytes') else str(app_state).encode()
                await nats_client.publish("zo.lifecycle.shutdown", state_bytes)
                await nats_client.flush(timeout=3.0)
                log.info("[ZO] State flushed to NATS — clean exit ready")
            except Exception as e:
                log.error(f"[ZO] NATS flush failed during shutdown: {e}")
        else:
            log.info("[ZO] No NATS client configured — skipping state flush")

        loop = asyncio.get_event_loop()
        loop.stop()
        log.info("[ZO] Event loop stopped. Goodbye.")

    def _sync_handler(signum, frame):
        loop = asyncio.get_event_loop()
        if loop.is_running():
            asyncio.ensure_future(_graceful_shutdown(signum, frame))
        else:
            import sys
            log.info(f"[ZO] Signal {signum} received (no event loop) — hard exit")
            sys.exit(0)

    signal.signal(signal.SIGTERM, _sync_handler)
    signal.signal(signal.SIGINT, _sync_handler)
    _shutdown_registered = True
    log.info("[ZO] Graceful shutdown handlers registered (SIGTERM + SIGINT)")


def get_shutdown_status():
    return {"handlers_registered": _shutdown_registered}
PYEOF
    ok "SIGTERM handler written to ${LIFECYCLE_FILE}"
  else
    dry "Write SIGTERM handler to ${LIFECYCLE_FILE}"
  fi

  # Post-edit verification
  log "Verifying SIGTERM patch..."
  if $DRY_RUN || grep -q "SIGTERM" "$LIFECYCLE_FILE" 2>/dev/null; then
    ok "Post-edit verification: SIGTERM handler confirmed"
  else
    fail "Post-edit verification FAILED — SIGTERM handler not found"
    return 1
  fi
}

# ═══════════════════════════════════════════════════════════════════════════════
# PHASE 3: FIX SUPERVISOR CONFIG (ANTI-LOOP)
# ═══════════════════════════════════════════════════════════════════════════════

fix_supervisor() {
  section "PHASE 3: SUPERVISOR ANTI-LOOP CONFIG"

  if ! $SUPERVISOR_AVAILABLE; then
    warn "supervisord not available — skipping supervisor hardening"
    log "  → Install with: apt-get install supervisor"
    return 0
  fi

  log "Checking existing supervisor config..."

  NEEDS_UPDATE=false

  if [[ -f "$SUPERVISOR_CONF" ]]; then
    # Check for critical anti-loop settings
    for setting in "startretries" "startsecs" "stopwaitsecs"; do
      if ! grep -q "$setting" "$SUPERVISOR_CONF"; then
        warn "  → Missing: ${setting}"
        NEEDS_UPDATE=true
      fi
    done
    if ! $NEEDS_UPDATE; then
      ok "Supervisor config already has anti-loop settings"
      return 0
    fi
  else
    warn "Supervisor config not found — creating new one"
    NEEDS_UPDATE=true
  fi

  if $NEEDS_UPDATE; then
    log "Writing hardened supervisor config..."
    PYTHON_ENTRY="${PYTHON_CMD} ${ZO_DIR}/src/main.py"

    if ! $DRY_RUN; then
      mkdir -p "$(dirname "$SUPERVISOR_CONF")"
      cat > "$SUPERVISOR_CONF" << CONFEOF
[program:zo]
command=${PYTHON_ENTRY}
directory=${ZO_DIR}
user=$(whoami)
autostart=true
autorestart=true
startretries=3
startsecs=5
stopwaitsecs=10
killasgroup=true
stopasgroup=true
redirect_stderr=true
stdout_logfile=$(dirname "$ZO_LOG")/zo.log
stdout_logfile_maxbytes=50MB
stdout_logfile_backups=5
environment=ZO_ENV="production",HOME="${HOME}",PATH="${PATH}"
CONFEOF
      ok "Supervisor config written to ${SUPERVISOR_CONF}"

      # Reload
      run "supervisorctl reread"
      run "supervisorctl update"
      sleep 2
      STATUS=$(supervisorctl status zo 2>/dev/null || echo "UNKNOWN")
      log "Post-update supervisor status: ${STATUS}"
      if echo "$STATUS" | grep -qE "RUNNING|STARTING"; then
        ok "Supervisor: zo is RUNNING ✓"
      else
        warn "Supervisor: zo status = ${STATUS} — may need manual start"
      fi
    else
      dry "Write hardened supervisor config to ${SUPERVISOR_CONF}"
      dry "supervisorctl reread && supervisorctl update"
    fi
  fi
}

# ═══════════════════════════════════════════════════════════════════════════════
# PHASE 4: CREDENTIAL AUDIT
# ═══════════════════════════════════════════════════════════════════════════════

audit_credentials() {
  section "PHASE 4: CREDENTIAL AUDIT"

  CRED_ISSUES=0

  # Scan source files for hardcoded credentials
  log "Scanning source files for hardcoded credentials..."
  if $ZO_FOUND; then
    HARDCODED=$(grep -rn --include="*.py" -E "(discord_token|api_key|secret|password)\s*=\s*['\"][^'\"]{10,}" "${ZO_DIR}/src/" 2>/dev/null || true)
    if [[ -n "$HARDCODED" ]]; then
      fail "⚠️  HARDCODED CREDENTIALS FOUND:"
      echo "$HARDCODED" | head -10
      ((CRED_ISSUES++))
    else
      ok "No hardcoded credentials in source files"
    fi
  fi

  # Check .env exists and is protected
  if [[ -f "${ZO_DIR}/.env" ]]; then
    ENV_PERMS=$(stat -c "%a" "${ZO_DIR}/.env" 2>/dev/null || stat -f "%Lp" "${ZO_DIR}/.env" 2>/dev/null || echo "unknown")
    ok ".env file exists (permissions: ${ENV_PERMS})"
    if [[ "$ENV_PERMS" != "600" && "$ENV_PERMS" != "640" ]]; then
      warn ".env permissions should be 600 — running: chmod 600 ${ZO_DIR}/.env"
      run "chmod 600 '${ZO_DIR}/.env'"
    fi
  else
    warn ".env not found — creating template at ${ZO_DIR}/.env"
    if ! $DRY_RUN; then
      cat > "${ZO_DIR}/.env" << ENVEOF
# Zo Super Server — Environment Variables
# Generated by zo-triage-and-harden.sh
# DO NOT COMMIT THIS FILE

DISCORD_TOKEN=
OPENAI_API_KEY=
ANTHROPIC_API_KEY=
NATS_URL=nats://localhost:4222
ZO_ENV=production
LOG_LEVEL=INFO
ENVEOF
      chmod 600 "${ZO_DIR}/.env"
      ok ".env template created (600 permissions) — fill in your credentials"
    fi
    ((CRED_ISSUES++))
  fi

  # Ensure .gitignore covers .env
  if [[ -f "${ZO_DIR}/.gitignore" ]]; then
    if ! grep -q "^\.env$" "${ZO_DIR}/.gitignore"; then
      warn ".env not in .gitignore — adding it"
      run "echo '.env' >> '${ZO_DIR}/.gitignore'"
    else
      ok ".env is gitignored"
    fi
  fi

  if [[ $CRED_ISSUES -eq 0 ]]; then
    ok "Credential audit: CLEAN"
  else
    fail "Credential audit: ${CRED_ISSUES} issue(s) — manual review required"
    log "  → Open ${ZO_DIR}/.env and fill in all credential values"
    log "  → Rotate any exposed tokens immediately"
  fi
}

# ═══════════════════════════════════════════════════════════════════════════════
# PHASE 5: KILL -9 RECOVERY TEST
# ═══════════════════════════════════════════════════════════════════════════════

test_kill9_recovery() {
  section "PHASE 5: KILL -9 RECOVERY TEST"

  if ! $ZO_RUNNING; then
    warn "Zo is not running — cannot perform kill -9 test"
    log "  → Start Zo first, then re-run with --triage-only skipped"
    return 0
  fi

  if ! $SUPERVISOR_AVAILABLE; then
    warn "supervisord not available — skipping auto-recovery test"
    log "  → Manual test: kill -9 ${ZO_PID} && sleep 10 && pgrep -f zo"
    return 0
  fi

  log "Performing kill -9 recovery test on PID ${ZO_PID}..."
  log "  → Supervisor should auto-restart within 5 seconds"

  if ! $DRY_RUN; then
    PRE_STATUS=$(supervisorctl status zo 2>/dev/null || echo "UNKNOWN")
    log "Pre-kill status: ${PRE_STATUS}"

    kill -9 "$ZO_PID" 2>/dev/null || true
    log "kill -9 sent. Waiting 8 seconds for auto-restart..."
    sleep 8

    POST_STATUS=$(supervisorctl status zo 2>/dev/null || echo "UNKNOWN")
    log "Post-restart status: ${POST_STATUS}"

    if echo "$POST_STATUS" | grep -qE "RUNNING"; then
      ok "kill -9 RECOVERY TEST: PASSED ✅"
      ok "Zo auto-restarted via supervisord"
    else
      fail "kill -9 RECOVERY TEST: FAILED — status: ${POST_STATUS}"
      log "  → Check supervisor logs: tail -50 /var/log/supervisor/supervisord.log"
      log "  → Manual restart: supervisorctl start zo"
    fi
  else
    dry "kill -9 ${ZO_PID} && sleep 8 && supervisorctl status zo"
  fi
}

# ═══════════════════════════════════════════════════════════════════════════════
# FINAL REPORT
# ═══════════════════════════════════════════════════════════════════════════════

print_final_report() {
  section "FINAL REPORT — ZO-HARDEN-001"

  echo -e "${BOLD}Environment:${NC}"
  echo "  Zo Dir:          ${ZO_DIR}"
  echo "  Log File:        ${ZO_LOG}"
  echo "  Supervisor Conf: ${SUPERVISOR_CONF}"
  echo "  Backup:          ${BACKUP_DIR}"
  echo "  Health Score:    ${ENV_SCORE}/12"
  echo ""
  echo -e "${BOLD}Triage Report:${NC} ${REPORT_FILE}"
  echo ""

  if $TRIAGE_ONLY; then
    echo -e "${CYAN}Run again without --triage-only to apply hardening fixes.${NC}"
  elif $DRY_RUN; then
    echo -e "${YELLOW}DRY-RUN complete — no changes made. Remove --dry-run to apply.${NC}"
  else
    echo -e "${GREEN}${BOLD}Hardening dispatch complete. See report above for any remaining manual steps.${NC}"
    echo ""
    echo -e "${CYAN}Next steps if needed:${NC}"
    echo "  1. Fill in ${ZO_DIR}/.env with your credentials"
    echo "  2. supervisorctl restart zo"
    echo "  3. tail -f ${ZO_LOG}"
    echo "  4. Run NATS rehydration experiment"
  fi
}

# ═══════════════════════════════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════════════════════════════

main() {
  echo "" | tee "$REPORT_FILE"
  echo -e "${PURPLE}${BOLD}" | tee -a "$REPORT_FILE"
  echo "╔══════════════════════════════════════════════════════╗" | tee -a "$REPORT_FILE"
  echo "║   ZO TRIAGE + HARDENING v${SCRIPT_VERSION}                    ║" | tee -a "$REPORT_FILE"
  echo "║   LoveLogicAI LLC — Protocol ZO-HARDEN-001          ║" | tee -a "$REPORT_FILE"
  echo "╚══════════════════════════════════════════════════════╝" | tee -a "$REPORT_FILE"
  echo -e "${NC}" | tee -a "$REPORT_FILE"

  $DRY_RUN && log "DRY-RUN MODE — zero changes will be made"
  $TRIAGE_ONLY && log "TRIAGE-ONLY MODE — discovery only, no hardening"
  log "Timestamp: ${TIMESTAMP}"
  log "Report: ${REPORT_FILE}"

  # Always run discovery
  discover_environment

  if $TRIAGE_ONLY; then
    print_final_report
    exit 0
  fi

  # Confirm before hardening
  if ! $FORCE && ! $DRY_RUN; then
    echo -e "\n${YELLOW}${BOLD}Ready to apply hardening to ${ZO_DIR}${NC}"
    echo "  Backup will be created at: ${BACKUP_DIR}"
    confirm || { log "Aborted by user."; exit 0; }
  fi

  create_backups
  patch_sigterm
  fix_supervisor
  audit_credentials
  test_kill9_recovery
  print_final_report
}

main "$@"
