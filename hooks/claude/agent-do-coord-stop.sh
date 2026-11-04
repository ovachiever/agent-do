#!/bin/bash
# SessionEnd hook: retire this session's coord presence, then run the manna
# reconcile advisory for the next SessionStart to greet with.
# Advisory and silent — never blocks, never creates a board where none exists.

INPUT=$(cat 2>/dev/null || true)
CWD=$(echo "$INPUT" | jq -r '.cwd // ""' 2>/dev/null)
SESSION_ID=$(echo "$INPUT" | jq -r '.session_id // ""' 2>/dev/null)
[ -n "$CWD" ] || CWD="$PWD"
cd "$CWD" 2>/dev/null || exit 0

# Resolve agent-do (same chain as agent-do-session-start.sh, condensed).
AGENT_DO=""
if command -v agent-do &>/dev/null; then
    AGENT_DO="agent-do"
fi
if [ -z "$AGENT_DO" ] && [ -f "$HOME/.agent-do/install-path" ]; then
    REPO=$(cat "$HOME/.agent-do/install-path" 2>/dev/null)
    [ -n "$REPO" ] && [ -x "$REPO/agent-do" ] && AGENT_DO="$REPO/agent-do"
fi
if [ -z "$AGENT_DO" ]; then
    SCRIPT_REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." 2>/dev/null && pwd)"
    [ -n "$SCRIPT_REPO" ] && [ -x "$SCRIPT_REPO/agent-do" ] && AGENT_DO="$SCRIPT_REPO/agent-do"
fi
[ -n "$AGENT_DO" ] || exit 0

# Hard bound with process-group SIGKILL so a wedged agent-do spawn cannot
# hang session teardown or leave orphans holding pipes.
bounded_run() {
    perl -e '
        setpgrp(0, 0);
        $SIG{ALRM} = sub { kill KILL => -$$ };
        alarm shift(@ARGV);
        my $pid = fork();
        if (!$pid) { exec @ARGV or exit 127 }
        waitpid($pid, 0);
        exit($? >> 8);
    ' "$@"
}

# --- Coord retirement: only in projects that already use coord ---
GIT_DIR=$(git rev-parse --git-dir 2>/dev/null || true)
if [ -n "$GIT_DIR" ] && [ -d "$GIT_DIR/agent-do/coord" ]; then
    # Retire the same identity the session used (session-start pinned it via
    # AGENT_DO_COORD_SESSION in CLAUDE_ENV_FILE from the same session_id).
    [ -n "$SESSION_ID" ] && export AGENT_DO_COORD_SESSION="$SESSION_ID"
    bounded_run 5 "$AGENT_DO" coord stop --note "session ended" >/dev/null 2>&1
fi

# --- Manna reconcile advisory: only where a board already exists ---
# Writes .manna/drift.yaml for the next SessionStart's drift greeting. The
# exit code is deliberately discarded: reconcile is advisory and must never
# change this hook's exit 0. SessionEnd's registered timeout is 10s; coord
# stop (5s bound) + reconcile (4s bound) stays inside it.
if [ -d .manna ]; then
    # Same session anchor manna claims used during the session, so the drift
    # file's session field names who last reconciled.
    [ -n "$SESSION_ID" ] && export MANNA_SESSION_ID="$SESSION_ID"
    # --fix --only names the two repairs the tool itself calls safe (abandon
    # claims coord has positively verified dead or stopped, unblock resolved
    # blockers); judgment findings stay findings. The landed_open close is not
    # among them: a `Manna:` trailer proves a commit advanced an item, not that
    # the item is complete or accepted, and this hook runs as whichever session
    # happens to end, never as the claimant or the operator. Without --only the
    # full cure ran here and closed submitted-but-unaccepted items over their
    # claimants (mn-54fe40 on 2026-11-04; the review of ec30858, mn-880173).
    # A landed row stays a finding in drift.yaml with its next step; a hand
    # with authority (`manna done`, or an explicit `manna reconcile --fix`)
    # closes it.
    bounded_run 4 "$AGENT_DO" manna reconcile --fix --only dead_claim,blocker_desync --write-drift --json >/dev/null 2>&1
fi

exit 0
