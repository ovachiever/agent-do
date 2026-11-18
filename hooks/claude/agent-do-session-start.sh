#!/bin/bash
# SessionStart hook: Add agent-do to PATH, inject tooling reminder,
# load always-active skills, detect frontend projects
#
# Auto-detects agent-do location (no hardcoded paths):
#   1. `which agent-do` (already in PATH)
#   2. ~/.local/bin/agent-do symlink (install.sh creates this)
#   3. ~/.agent-do/install-path breadcrumb file

INPUT=$(cat)
CWD=$(echo "$INPUT" | jq -r '.cwd // ""')

# --- Resolve agent-do location ---
AGENT_DO_DIR=""

# 1. Already in PATH?
if command -v agent-do &>/dev/null; then
    RESOLVED=$(readlink "$(command -v agent-do)" 2>/dev/null || command -v agent-do)
    AGENT_DO_DIR="$(cd "$(dirname "$RESOLVED")" 2>/dev/null && pwd)"
fi

# 2. Check ~/.local/bin symlink
if [ -z "$AGENT_DO_DIR" ] && [ -L "$HOME/.local/bin/agent-do" ]; then
    RESOLVED=$(readlink "$HOME/.local/bin/agent-do" 2>/dev/null)
    if [ -n "$RESOLVED" ] && [ -x "$RESOLVED" ]; then
        AGENT_DO_DIR="$(cd "$(dirname "$RESOLVED")" 2>/dev/null && pwd)"
    fi
fi

# 3. Check breadcrumb file
if [ -z "$AGENT_DO_DIR" ] && [ -f "$HOME/.agent-do/install-path" ]; then
    BREADCRUMB=$(cat "$HOME/.agent-do/install-path" 2>/dev/null)
    if [ -n "$BREADCRUMB" ] && [ -x "$BREADCRUMB/agent-do" ]; then
        AGENT_DO_DIR="$BREADCRUMB"
    fi
fi

# 4. Script-relative fallback: this hook lives at <repo>/hooks/claude/, so a
#    bare checkout (fresh contributor, CI) resolves its own dispatcher without
#    any install artifacts.
if [ -z "$AGENT_DO_DIR" ]; then
    SCRIPT_REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." 2>/dev/null && pwd)"
    if [ -n "$SCRIPT_REPO" ] && [ -x "$SCRIPT_REPO/agent-do" ]; then
        AGENT_DO_DIR="$SCRIPT_REPO"
    fi
fi

# --- Add to PATH if found ---
if [ -n "$AGENT_DO_DIR" ] && [ -n "$CLAUDE_ENV_FILE" ]; then
    echo "export PATH=\"$AGENT_DO_DIR:\$PATH\"" >> "$CLAUDE_ENV_FILE"
fi

# --- Pin coord + stable host identity to this Claude session ---
# Every Bash call then derives the same coord agent identity, and the
# SessionEnd hook can retire exactly that identity via the same session_id.
# Manna derives its private proof from the stable host id under a machine-local
# key, so separate shell invocations and process restarts recover one owner.
SESSION_ID=$(echo "$INPUT" | jq -r '.session_id // ""')
if [ -n "$SESSION_ID" ] && [ -z "${AGENT_DO_COORD_SESSION:-}" ] && [ -n "$CLAUDE_ENV_FILE" ]; then
    echo "export AGENT_DO_COORD_SESSION=\"$SESSION_ID\"" >> "$CLAUDE_ENV_FILE"
fi
# Manna ownership rides a machine-key derived identity: manna-core derives
# the proof from CLAUDE_SESSION_ID under ~/.agent-do/manna/session-identity.key,
# so a restarted process re-derives the same proof and keeps lifecycle
# authority over its claims (mn-ba8db6). A random MANNA_SESSION_TOKEN died
# with the process and wedged mid-work claims. Explicit MANNA_SESSION_ID +
# MANNA_SESSION_TOKEN pins (scripted lanes) still take priority when present.
if [ -n "$SESSION_ID" ] && [ -n "$CLAUDE_ENV_FILE" ] && [ -z "${MANNA_SESSION_TOKEN:-}" ]; then
    if [ -n "${MANNA_SESSION_ID:-}" ]; then
        # Neutralize a stale half-pinned pair; manna treats empty as unset
        # and falls through to the derived identity.
        echo 'export MANNA_SESSION_ID=""' >> "$CLAUDE_ENV_FILE"
    fi
    if [ -z "${CLAUDE_SESSION_ID:-}" ]; then
        echo "export CLAUDE_SESSION_ID=\"$SESSION_ID\"" >> "$CLAUDE_ENV_FILE"
    fi
fi

run_native_bootstrap_prompt() {
    local ask_prompt="$1"
    local project_root="$2"
    local response
    # A person answered the dialog. Only then may a failure open a second,
    # blocking dialog: an auto-response is a script (tests, CI, headless
    # lanes), and a modal dialog there waits forever on nobody.
    local answered_by_person=0
    # With many sessions open, an unlabeled dialog is unanswerable: the title
    # names the repo, and the body always ends with its full path.
    local dialog_label
    dialog_label="$(basename "$project_root")"
    case "$ask_prompt" in
        *"$project_root"*) ;;
        *) ask_prompt="$ask_prompt

Project: $project_root" ;;
    esac

    case "${AGENT_DO_BOOTSTRAP_AUTO_RESPONSE:-}" in
        bootstrap)
            response="Bootstrap"
            ;;
        not_now)
            response="Not now"
            ;;
        *)
            if ! command -v osascript >/dev/null 2>&1; then
                return 2
            fi

            response=$(osascript <<EOF 2>/dev/null || true
display dialog "$(printf '%s' "$ask_prompt" | sed 's/\\/\\\\/g; s/"/\\"/g')" with title "agent-do Bootstrap — $(printf '%s' "$dialog_label" | sed 's/\\/\\\\/g; s/"/\\"/g')" buttons {"Not now", "Bootstrap"} default button "Bootstrap"
button returned of result
EOF
)
            answered_by_person=1
            ;;
    esac

    if [[ "$response" == "Bootstrap" ]]; then
        # Capture output to a log; emit a macOS notification with status; on
        # failure also fire a follow-up dialog with the option to view the log.
        # The session-start hook fires once per session, so it's fine to grab
        # the user's attention briefly when something actually needs them.
        local log_dir log_file run_exit project_label
        log_dir="${HOME}/.agent-do/logs"
        mkdir -p "$log_dir" 2>/dev/null || true
        log_file="$log_dir/bootstrap-$(date +%Y%m%d-%H%M%S)-$$.log"
        project_label="$(basename "$project_root")"

        (
            cd "$project_root"
            echo "agent-do bootstrap --yes" > "$log_file"
            echo "project: $project_root" >> "$log_file"
            echo "started: $(date '+%Y-%m-%d %H:%M:%S')" >> "$log_file"
            echo "---" >> "$log_file"
            "$AGENT_DO_DIR/agent-do" bootstrap --yes >> "$log_file" 2>&1
        )
        run_exit=$?

        if command -v osascript >/dev/null 2>&1; then
            if [[ "$run_exit" -eq 0 ]]; then
                osascript -e "display notification \"Bootstrap completed for $project_label. Log: $log_file\" with title \"agent-do Bootstrap\" sound name \"Glass\"" 2>/dev/null || true
            else
                osascript -e "display notification \"Bootstrap FAILED for $project_label (exit $run_exit). Log: $log_file\" with title \"agent-do Bootstrap\" sound name \"Basso\"" 2>/dev/null || true
                echo "[agent-do bootstrap] FAILED for $project_label (exit $run_exit). Log: $log_file" >&2
            fi
            if [[ "$run_exit" -ne 0 && "$answered_by_person" -eq 1 ]]; then
                # The person who clicked Bootstrap is at the screen: offer the log.
                local choice
                choice=$(osascript <<DLG 2>/dev/null || true
display dialog "agent-do bootstrap failed (exit $run_exit) for $project_label.

Log: $log_file" with title "agent-do Bootstrap failed" buttons {"Dismiss", "Open log"} default button "Open log"
button returned of result
DLG
)
                if [[ "$choice" == "Open log" ]] && command -v open >/dev/null 2>&1; then
                    open "$log_file" 2>/dev/null || true
                fi
            fi
        else
            # Non-macOS / no osascript: echo status to stderr so it lands in
            # whatever the host shell shows.
            if [[ "$run_exit" -eq 0 ]]; then
                echo "[agent-do bootstrap] completed for $project_label. Log: $log_file" >&2
            else
                echo "[agent-do bootstrap] FAILED for $project_label (exit $run_exit). Log: $log_file" >&2
            fi
        fi
    fi

    return 0
}

append_bootstrap_prompt() {
    local bootstrap_json needs_bootstrap ask_prompt project_root commands prompt_mode legacy_board legacy_notice

    [ -n "$AGENT_DO_DIR" ] || return 0
    [ -n "$CWD" ] || return 0
    [ -x "$AGENT_DO_DIR/agent-do" ] || return 0

    bootstrap_json=$(bounded_run 3 "$AGENT_DO_DIR/agent-do" bootstrap --recommend --json --cwd "$CWD" 2>/dev/null || true)
    [ -n "$bootstrap_json" ] || return 0

    needs_bootstrap=$(echo "$bootstrap_json" | jq -r 'if .needs_bootstrap then "true" else "false" end' 2>/dev/null || echo "false")
    [ "$needs_bootstrap" = "true" ] || return 0

    ask_prompt=$(echo "$bootstrap_json" | jq -r '.ask_prompt // ""' 2>/dev/null || true)
    project_root=$(echo "$bootstrap_json" | jq -r '.project_root // ""' 2>/dev/null || true)
    commands=$(echo "$bootstrap_json" | jq -r '.commands[]?' 2>/dev/null || true)
    legacy_board=$(echo "$bootstrap_json" | jq -r 'if .legacy_board then "true" else "false" end' 2>/dev/null || echo "false")
    legacy_notice=""
    if [ "$legacy_board" = "true" ]; then
        legacy_notice="legacy board: run agent-do manna migrate"
    fi

    prompt_mode="${AGENT_DO_BOOTSTRAP_PROMPT_MODE:-}"
    if [ -z "$prompt_mode" ]; then
        if [ "$(uname -s)" = "Darwin" ] && command -v osascript >/dev/null 2>&1; then
            prompt_mode="native"
        else
            prompt_mode="context"
        fi
    fi

    case "$prompt_mode" in
        native)
            run_native_bootstrap_prompt "$ask_prompt" "$project_root" && return 0
            ;;
        disabled)
            return 0
            ;;
    esac

    CONTEXT="$CONTEXT

---

## Bootstrap Opportunity

This project has pending agent-do bootstrap work.

$legacy_notice

At the start of your first reply in this session, ask exactly one short yes/no question:
\"$ask_prompt\"

If the user says yes, run:
\`agent-do bootstrap --yes\`

Run it from:
\`$project_root\`

Planned bootstrap:
\`\`\`
$commands
\`\`\`

    If the user says no, continue normally and do not ask again in this session."
}

# There is no project-tooling section here, and its absence is deliberate.
# `agent-do suggest --project` needs ~10.5s against a real repo and this hook
# could only afford 3, so it was killed on every session and the block it fed
# never once rendered: the cost was paid, the text never arrived. What it would
# have said reaches the session by three other roads anyway — CLAUDE.md's
# task-to-tool routing table, the PreToolUse nudge at the moment a raw command
# is typed, and zpc's project profile — and each of those is either free or
# paid for elsewhere. `agent-do suggest --project` remains on demand, where a
# ten-second answer is something the caller chose to wait for.

# Run a command with a hard wall-clock bound, SIGKILLing its entire process
# group on expiry so orphaned grandchildren cannot hold pipes open.
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

append_coord_context() {
    local touch_json interrupts_json active_count focus_goal active_block interrupt_count interrupt_block
    local coord_scratch
    local -a coord_cmd

    [ -n "$AGENT_DO_DIR" ] || return 0
    [ -n "$CWD" ] || return 0
    [ -x "$AGENT_DO_DIR/agent-do" ] || return 0

    # Straight at the tool rather than through the dispatcher. `agent-do <tool>`
    # spends most of a second before the tool itself starts — a registry parse
    # to resolve declared credentials, then a telemetry write — and coord
    # declares no credentials to resolve (`agent-do creds required coord`: none).
    # Measured here: 1,126ms dispatched against 300ms direct. The dispatched
    # form stays as the fallback, for an install whose resolved agent-do has no
    # tools/ beside it.
    if [ -x "$AGENT_DO_DIR/tools/agent-coord" ]; then
        coord_cmd=("$AGENT_DO_DIR/tools/agent-coord")
    else
        coord_cmd=("$AGENT_DO_DIR/agent-do" coord)
    fi

    # Two reads, taken at the same time, because no single verb answers both
    # questions and minting one is not this hook's call. `touch` renews the
    # presence lease and is the only read carrying peer_counts, which is where
    # the dead/stopped/stale tail comes from; `interrupts --mark-seen` is the
    # only read that consumes what it shows. `coord status` carries both shapes
    # and substitutes for neither: it marks nothing seen and drops peer_counts.
    # So the two stay two and overlap, for one call's wall clock instead of two,
    # each still under the same 2s bound it had alone. Overlapping is safe:
    # coord takes its own flock around every read-modify-write, and both spawns
    # resolve one identity, anchored to the runtime process rather than to
    # either spawn's pid.
    #
    # bounded_run kills the whole process group on timeout, both children with
    # it: a wedged coord must degrade to "no coord context", never hold the
    # hook's budget open.
    coord_scratch=$(mktemp -d "${TMPDIR:-/tmp}/agent-do-session-coord.XXXXXX" 2>/dev/null) || return 0
    # The same anchor this hook pinned into CLAUDE_ENV_FILE for the shell:
    # the hook process itself never sees that file, so without the pin coord
    # would read as a second identity and the shell's acknowledgments would
    # not quiet what this hook shows (mn-812cd9).
    if [ -n "$SESSION_ID" ] && [ -z "${AGENT_DO_COORD_SESSION:-}" ]; then
        export AGENT_DO_COORD_SESSION="$SESSION_ID"
    fi
    bounded_run 2 bash -c '
        cd "$1" || exit 0
        scratch="$2"
        shift 2
        "$@" touch --json > "$scratch/touch.json" 2>/dev/null &
        "$@" interrupts --json --mark-seen --limit 5 > "$scratch/interrupts.json" 2>/dev/null &
        wait
    ' agent-do-session-coord "$CWD" "$coord_scratch" "${coord_cmd[@]}" >/dev/null 2>&1 || true

    [ -s "$coord_scratch/touch.json" ] && touch_json=$(<"$coord_scratch/touch.json")
    [ -s "$coord_scratch/interrupts.json" ] && interrupts_json=$(<"$coord_scratch/interrupts.json")
    rm -rf "$coord_scratch" 2>/dev/null

    [ -n "$touch_json" ] || return 0

    # jq rather than python3 for every parse below: the same answer for ~10ms
    # instead of ~190ms, which is what an interpreter costs to start here. The
    # counters keep a numeric guard because a parse failure now yields an empty
    # string where python yielded a fallback integer, and `[ "" -gt 0 ]` is an
    # error message, not a comparison.
    active_count=$(echo "$touch_json" | jq -r '.active_peers | length' 2>/dev/null || echo "0")
    case "$active_count" in
        ''|*[!0-9]*) active_count=0 ;;
    esac
    focus_goal=$(echo "$touch_json" | jq -r '.focus.goal? // ""' 2>/dev/null || true)

    interrupt_count=$(echo "$interrupts_json" | jq -r '.interrupts | length' 2>/dev/null || echo "0")
    case "$interrupt_count" in
        ''|*[!0-9]*) interrupt_count=0 ;;
    esac

    if [ "$interrupt_count" -gt 0 ]; then
        interrupt_block=$(echo "$interrupts_json" | jq -r '
            .interrupts[]?
            | "- " + (if .new then "[new] " else "" end)
              + (.kind | tostring) + ": " + (.summary | tostring)
        ' 2>/dev/null || true)

        [ -n "$interrupt_block" ] || return 0

        CONTEXT="$CONTEXT

---

## Coord Interrupts

Relevant coordination interrupts are active in this repo:
$interrupt_block

Use:
\`agent-do coord status\`
\`agent-do coord interrupts\`
\`agent-do coord focus show\`
A drop keeps returning until you acknowledge it (\`agent-do coord drop ack <drp-id>\`, you only)
or its owner/recipient resolves it (\`agent-do coord drop resolve <drp-id> --reason ...\`, everyone).
"
        return 0
    fi

    [ "$active_count" -gt 0 ] || return 0
    [ -z "$focus_goal" ] || return 0

    # Writers first, then everyone else, each group in the order coord gave
    # them: a partition rather than a sort, so nothing depends on whether jq's
    # sort happens to be stable.
    active_block=$(echo "$touch_json" | jq -r '
        (([.active_peers[]? | select((.mode // "writer") == "writer")]
          + [.active_peers[]? | select((.mode // "writer") != "writer")])[]
         | ([(if (.mode // "writer") == "read-only"
              then ((.role // "auditor") | tostring) + ", read-only" else empty end),
             (if .phase then "phase:" + (.phase | tostring) else empty end),
             (if .age then (.age | tostring) else empty end)]) as $details
         | "- " + ((.alias // .agent_id) | tostring)
           + (if ($details | length) > 0 then " (" + ($details | join(", ")) + ")" else "" end)
           + (if (.focus.goal? // null) then " goal: " + (.focus.goal | tostring) else "" end)),
        ((((.peer_counts.dead? // 0) + (.peer_counts.stopped? // 0) + (.peer_counts.stale? // 0)) as $hidden
          | if $hidden > 0
            then "- (\($hidden) dead/stopped/stale sessions on the board, not shown)"
            else empty end))
    ' 2>/dev/null || true)

    [ -n "$active_block" ] || return 0

    CONTEXT="$CONTEXT

---

## Coord Focus Reminder

Other active peers exist in this repo, and you have not declared focus yet.

Active peers:
$active_block

Set focus before overlapping work starts:
\`agent-do coord focus set \"<goal>\" --path <path> [--path <path> ...]\`
\`agent-do coord peers\`
\`agent-do coord claim <path>\`
\`agent-do coord interrupts\`
"
}

append_manna_board() {
    local board_json board_block drift_file drift_block

    [ -n "$AGENT_DO_DIR" ] || return 0
    [ -n "$CWD" ] || return 0
    [ -x "$AGENT_DO_DIR/agent-do" ] || return 0
    # Board presence gates everything below: repos without .manna/ take none
    # of this path, so the emitted envelope stays byte-identical to today.
    [ -d "$CWD/.manna" ] || return 0

    board_json=$(cd "$CWD" && bounded_run 2 "$AGENT_DO_DIR/agent-do" manna context --max-tokens 1500 --json 2>/dev/null || true)
    if [ -n "$board_json" ]; then
        board_block=$(echo "$board_json" | jq -r '.context // ""' 2>/dev/null || true)
        if [ -n "$board_block" ]; then
            CONTEXT="$CONTEXT

---

## Manna Board

$board_block

Work the board: \`agent-do manna claim <id>\` before starting, \`agent-do manna done <id>\` when verified.
Human view: \`agent-do manna serve\` prints this board's URL (http://127.0.0.1:<port>/<project>); hand it over whenever the board is asked for."
        fi
    fi

    # Drift greeting: the SessionEnd reconcile advisory writes .manna/drift.yaml;
    # read-if-exists, so a hand-written file greets before that ever ships.
    drift_file="$CWD/.manna/drift.yaml"
    [ -f "$drift_file" ] || return 0
    grep -q '^findings:' "$drift_file" 2>/dev/null || return 0
    grep -Eq '^[[:space:]]*-[[:space:]]+kind:' "$drift_file" 2>/dev/null || return 0

    drift_block=$(sed -n '1,30p' "$drift_file" 2>/dev/null)
    [ -n "$drift_block" ] || return 0

    CONTEXT="$CONTEXT

---

## Board drift (unresolved from last session)

\`\`\`yaml
$drift_block
\`\`\`

Reconcile the board against reality before claiming new work, then remove \`.manna/drift.yaml\` once resolved."
}

# Every project gets a store, without the hook ever writing a tracked file.
# Two limits make that true. A git worktree is the unit of "project", so a bare
# directory never gets one. And `zpc init` does more than create the store: it
# appends to .gitignore and writes (or appends to) the repo's agent instruction
# file, which is not something a silent session-start hook may do to a repo it
# does not own. So auto-init rides a store-only mode and stays home without it.
# The git worktree containing $CWD, for auto-init to know where a store
# belongs. Asked of git rather than walked, because placement wants git's own
# answer — GIT_DIR, linked worktrees and all. The store walk does not use this:
# it carries its own ceiling from zpc_worktree_root, matching the rule zpc
# resolves by, and the two must not be allowed to drift into each other.
CWD_TOPLEVEL=""
zpc_resolve_toplevel() {
    [ -n "$CWD" ] || return 0
    CWD_TOPLEVEL=$(cd "$CWD" 2>/dev/null && bounded_run 3 git rev-parse --show-toplevel 2>/dev/null) || CWD_TOPLEVEL=""
    [ -n "$CWD_TOPLEVEL" ] && [ -d "$CWD_TOPLEVEL" ] || CWD_TOPLEVEL=""
}

zpc_autoinit() {
    local toplevel dir init_help

    [ "${AGENT_DO_ZPC_AUTOINIT:-1}" != "0" ] || return 0
    [ -n "$CWD" ] || return 0
    [ -n "$AGENT_DO_DIR" ] || return 0
    [ -x "$AGENT_DO_DIR/agent-do" ] || return 0

    toplevel="$CWD_TOPLEVEL"
    [ -n "$toplevel" ] || return 0

    # zpc resolves a store by walking up from cwd, so a store anywhere between
    # cwd and the toplevel means this project already has one.
    dir="$CWD"
    while [ -n "$dir" ] && [ "$dir" != "/" ]; do
        [ -d "$dir/.zpc" ] && return 0
        [ "$dir" = "$toplevel" ] && break
        dir=$(dirname "$dir")
    done
    [ -d "$toplevel/.zpc" ] && return 0

    # A bound worktree already has memory — someone else's directory holds it.
    # Creating a store here would shadow that binding on the very next session
    # and put this tree back on the path where its lessons die with it.
    zpc_binding_for "$toplevel" >/dev/null 2>&1 && return 0

    # init's argument loop swallows flags it does not know, so asking an older
    # zpc for --store-only gets a full invasive init that reports success. The
    # gate has to be positive: no such flag in the help text, no auto-init.
    init_help=$(bounded_run 3 "$AGENT_DO_DIR/agent-do" zpc init --help 2>/dev/null || true)
    case "$init_help" in
        *--store-only*) ;;
        *) return 0 ;;
    esac

    (cd "$toplevel" && bounded_run 3 "$AGENT_DO_DIR/agent-do" zpc init --store-only) >/dev/null 2>&1 || return 0
}

# Owning uid of a path. Mode `link` reads the name itself; `target` (the
# default) follows symlinks, so a .zpc pointing somewhere else is judged by what
# it actually resolves to. Prints nothing when it cannot tell, and every caller
# treats "cannot tell" as "do not trust". GNU stat reads -f as --file-system and
# answers with something that is not a uid at all, so the answer has to look
# like one before it counts.
_path_uid() {
    local uid
    if [ "${2:-target}" = "link" ]; then
        uid=$(stat -f %u "$1" 2>/dev/null) || uid=$(stat -c %u "$1" 2>/dev/null) || return 1
    else
        uid=$(stat -L -f %u "$1" 2>/dev/null) || uid=$(stat -L -c %u "$1" 2>/dev/null) || return 1
    fi
    case "$uid" in
        ''|*[!0-9]*) return 1 ;;
    esac
    printf '%s' "$uid"
}

# A store is ours only when we own both the name and what it resolves to: a
# link owned by somebody else can be re-aimed whenever they like, and a link we
# own can still land in a directory we do not. zpc applies the identical pair
# (tools/agent-zpc/lib/common.sh:_zpc_store_is_ours).
_zpc_store_is_ours() {
    local uid
    uid=$(_path_uid "$1" link) || return 1
    [ "$uid" = "$EUID" ] || return 1
    uid=$(_path_uid "$1" target) || return 1
    [ "$uid" = "$EUID" ]
}

# The store a directory is bound to, or nothing. `agent-git worktree add` binds
# every linked worktree it creates, because .zpc/ is gitignored and an unbound
# worktree would record its lessons into a store that dies with
# `worktree remove`.
#
# The binding lives in this user's config, never in the repository, and that
# location is the whole security property: a pointer file inside the tree would
# let repository content decide where this hook reads memory from and where the
# session writes it, and this hook injects what it finds as the project's
# recorded truth without anyone asking. A clone cannot write $AGENT_DO_HOME.
# Trust rules identical to zpc's (tools/agent-zpc/lib/common.sh:_zpc_binding_for).
zpc_binding_for() {
    local key="${1%/}" bindings worktree store
    [ -n "$key" ] || return 1
    bindings="${AGENT_DO_HOME:-$HOME/.agent-do}/zpc/worktree-bindings.tsv"
    [ -f "$bindings" ] || return 1
    _zpc_store_is_ours "$bindings" || return 1

    while IFS="$(printf '\t')" read -r worktree store || [ -n "$worktree" ]; do
        case "$worktree" in
            ''|'#'*) continue ;;
        esac
        [ "${worktree%/}" = "$key" ] || continue
        store="${store%$'\r'}"
        store="${store%/}"
        case "$store" in
            /*/.zpc) ;;
            *) return 1 ;;
        esac
        [ -d "$store" ] || return 1
        _zpc_store_is_ours "$store" || return 1
        printf '%s' "$store"
        return 0
    done < "$bindings"

    return 1
}

# The worktree holding a directory: nearest ancestor-or-self carrying .git.
# Tested for existence rather than directory-ness, because a submodule or a
# linked worktree keeps .git as a file. Walked rather than asked of git: this
# runs before the store walk on every session, and a subprocess to learn what a
# few stat calls already know is a tax.
zpc_worktree_root() {
    local dir="${1%/}"
    [ -n "$dir" ] || dir="/"
    while :; do
        [ -e "$dir/.git" ] && { printf '%s' "$dir"; return 0; }
        [ "$dir" = "/" ] && break
        dir="${dir%/*}"
        [ -n "$dir" ] || dir="/"
    done
    return 1
}

# Where zpc would resolve a store from here — the upward walk resolve_zpc_dir
# does (tools/agent-zpc/lib/common.sh) — but bounded and ownership-checked,
# because this walk runs unattended at session start and whatever it finds gets
# read to the agent as trusted memory.
#
# The ceiling: a git worktree stops at its toplevel; otherwise a cwd under
# $HOME stops at $HOME; a cwd outside both walks nowhere at all and only ever
# probes itself. Unbounded, a session opened anywhere under /tmp would find a
# world-writable store planted above it and inject a stranger's lessons under a
# heading that tells the agent to trust them.
#
# The ownership check is the second lock: a store is used only when the current
# uid owns it. One we do not own is stepped over, not treated as fatal, and the
# walk carries on above it. Stopping there looks like the careful choice and is
# not one: the foreign store is refused either way, by this same check, so
# stopping guards nothing — it only hands anyone who can write a directory on
# your path a silent way to black out the real store above it.
zpc_store_root() {
    local dir="${1%/}" home under_home toplevel ceiling target

    [ -n "$dir" ] || return 1
    home="${HOME:-}"
    home="${home%/}"

    under_home=0
    if [ -n "$home" ]; then
        case "$dir" in
            "$home"|"$home"/*) under_home=1 ;;
        esac
    fi

    if toplevel=$(zpc_worktree_root "$dir"); then
        ceiling="$toplevel"
        # A repo that contains $HOME must not lift the floor back off.
        if [ "$under_home" = 1 ] && [ ${#toplevel} -lt ${#home} ]; then
            ceiling="$home"
        fi
    elif [ "$under_home" = 1 ]; then
        ceiling="$home"
    else
        # No worktree and outside $HOME: probe this directory and stop.
        ceiling="$dir"
    fi

    while :; do
        # Not ours: fall through and keep climbing. A real store at a rung
        # answers before that rung's binding does — memory sitting in front of
        # you outranks a note about memory elsewhere.
        if [ -d "$dir/.zpc" ] && _zpc_store_is_ours "$dir/.zpc"; then
            printf '%s' "$dir"
            return 0
        fi
        if target=$(zpc_binding_for "$dir"); then
            printf '%s' "${target%/.zpc}"
            return 0
        fi
        [ "$dir" = "$ceiling" ] && break
        [ "$dir" = "/" ] && break
        dir="${dir%/*}"
        [ -n "$dir" ] || dir="/"
    done
    return 1
}

# At least one recorded line under .zpc/memory/. An initialized-but-empty store
# has nothing worth embedding, so it keeps the advisory.
zpc_has_records() {
    local file
    for file in "$1"/.zpc/memory/*.jsonl; do
        [ -f "$file" ] || continue
        grep -q '[^[:space:]]' "$file" 2>/dev/null && return 0
    done
    return 1
}

# Mark where this session started, for the Stop-event write nudge
# (agent-do-zpc-write-nudge.sh) to measure against. Two facts plus one clock:
# HEAD at the mark, recorded rows at the mark, and the file's own mtime, which
# is what lets the nudge tell this session's edits from dirt that was already
# in the tree. Written here rather than lazily at the first Stop so that work
# done in the opening turn still counts.
zpc_write_session_baseline() {
    local state_dir baseline total n f store_root
    [ -n "$CWD" ] || return 0
    [ -n "$SESSION_ID" ] || return 0
    store_root=$(zpc_store_root "$CWD") || return 0

    state_dir="$store_root/.zpc/.state"
    mkdir -p "$state_dir" 2>/dev/null || return 0

    # One marker pair per session accumulates forever otherwise. Session-start
    # is the once-per-session place to sweep it.
    find "$state_dir" -maxdepth 1 -type f \
        \( -name 'session-*.baseline' -o -name 'write-nudge-*.done' \) \
        -mtime +7 -delete 2>/dev/null

    baseline="$state_dir/session-$(printf '%s' "$SESSION_ID" | tr -c 'A-Za-z0-9._-' '_' | cut -c1-64).baseline"
    # SessionStart fires again on resume and compact with the same session_id.
    # Keeping the first mark keeps the clock honest.
    [ -f "$baseline" ] && return 0

    total=0
    for f in "$store_root"/.zpc/memory/*.jsonl; do
        [ -f "$f" ] || continue
        n=$(wc -l < "$f" 2>/dev/null | tr -d '[:space:]')
        case "$n" in
            ''|*[!0-9]*) continue ;;
        esac
        total=$((total + n))
    done

    {
        printf 'head=%s\n' "$(cd "$store_root" && git rev-parse HEAD 2>/dev/null || printf '')"
        printf 'zpc_lines=%s\n' "$total"
    } > "$baseline" 2>/dev/null || return 0
}

# Preferences are the user's, not the project's, so they travel: an empty store
# and a directory that will never have one both get them. Emits nothing and
# reports failure unless there is real content, which keeps every caller's
# existing fallback intact.
append_zpc_preferences() {
    local prefs_out prefs_rc

    [ "${AGENT_DO_ZPC_INJECT:-1}" != "0" ] || return 1
    [ -n "$AGENT_DO_DIR" ] || return 1
    [ -x "$AGENT_DO_DIR/agent-do" ] || return 1

    prefs_out=$(cd "$1" && export AGENT_DO_ZPC_SOURCE=hook && bounded_run 3 "$AGENT_DO_DIR/agent-do" zpc inject --preferences 2>/dev/null)
    prefs_rc=$?
    [ "$prefs_rc" -eq 0 ] && [ -n "$prefs_out" ] || return 1

    # No second cut here. `inject --preferences` fits its own blob to a budget
    # read from the quantity authority and marks what it dropped with both
    # numbers; a belt applied on top of that would cut at a byte offset it has
    # no way to place, which is exactly how the project blob came to deliver
    # zero claims. This hook's constraint is time, and bounded_run above is it.

    CONTEXT="$CONTEXT

---

## ZPC Preferences (global memory)

Preferences recorded across earlier sessions, loaded below. They are user-level, not project-level: they hold here regardless of what this directory contains.

$prefs_out

Log new ones where they happen: \`agent-do zpc learn\` and \`agent-do zpc decide\`."
    return 0
}

append_zpc_memory() {
    local inject_out inject_rc store_root

    [ -n "$CWD" ] || return 0

    # No store anywhere up the tree, and none coming: auto-init already declined
    # this directory (not a git worktree, or it has no store-only mode to use).
    # Preferences are still his, so they still arrive.
    if ! store_root=$(zpc_store_root "$CWD"); then
        append_zpc_preferences "$CWD"
        return 0
    fi

    # The advisory below only *asks* the agent to go read the store, and asking
    # is not a mechanism. When there are records to show, put the memory itself
    # in context. Every failure mode (kill-switch, empty store, missing
    # dispatcher, nonzero exit, timeout) falls through to the advisory, so the
    # section degrades instead of disappearing.
    if [ "${AGENT_DO_ZPC_INJECT:-1}" != "0" ] &&
       [ -n "$AGENT_DO_DIR" ] &&
       [ -x "$AGENT_DO_DIR/agent-do" ]; then
        if zpc_has_records "$store_root"; then
            # Run from the store's own root, which is $CWD for a session opened
            # at the top and the walked-up answer otherwise. AGENT_DO_ZPC_SOURCE
            # tags the access log; the export dies with the subshell so it never
            # leaks into the rest of the hook.
            inject_out=$(cd "$store_root" && export AGENT_DO_ZPC_SOURCE=hook && bounded_run 3 "$AGENT_DO_DIR/agent-do" zpc inject 2>/dev/null)
            inject_rc=$?

            if [ "$inject_rc" -eq 0 ] && [ -n "$inject_out" ]; then
                # The blob arrives already fitted. It used to be cut again here,
                # at 6000 characters, and the receipt is worth keeping: against a
                # store of 197 rows that cut landed inside the protocol header,
                # so the session received the boilerplate, none of the claims,
                # and the four words `[zpc inject truncated]` to describe the
                # loss. Two bounds on one payload is one bound too many — only
                # inject can rank what it is cutting, so only inject cuts. What
                # this hook owes the session is time, and bounded_run is that.

                CONTEXT="$CONTEXT

---

## ZPC Project Memory

This project's recorded memory, loaded below. Read it before coding; it is already in context, so do not re-run \`agent-do zpc inject\`.

$inject_out

Keep the loop closed: \`agent-do zpc learn\` and \`agent-do zpc decide\` as you work, \`agent-do zpc harvest\` after significant work."
                return 0
            fi
        else
            # A store with nothing in it yet — every project's first session,
            # now that init runs automatically. Preferences beat an advisory
            # nobody reads.
            append_zpc_preferences "$store_root" && return 0
        fi
    fi

    CONTEXT="$CONTEXT

---

## ZPC Memory Available

This project has ZPC memory at \`.zpc/\`. At session start:
\`\`\`
agent-do zpc status      # Memory health + counts
agent-do zpc patterns    # Established conventions — read before coding
\`\`\`
Log lessons and decisions as you work. Run \`agent-do zpc harvest\` after significant work."
}

# --- Inject tooling reminder ---
CONTEXT="## TOOLING REMINDER - agent-do

BEFORE using raw commands (xcrun, adb, osascript, curl for APIs, etc.), CHECK if agent-do has a tool:

\`\`\`
agent-do <tool> <command> [args...]
agent-do -n \"natural language description of what you want\"
agent-do --how \"...\"     # Explain without executing
\`\`\`

Discovery: agent-do suggest \"<task>\" | agent-do suggest --project | agent-do find <keyword> | agent-do --list | agent-do <tool> --help

Prefer agent-do over raw CLI commands when a tool exists.
Use agent-do <tool> --help to see available commands."

# --- Load always-active skill: artful-claude ---
SKILL_FILE="$HOME/.claude/skills/artful-claude/SKILL.md"
if [ -f "$SKILL_FILE" ]; then
    SKILL_CONTENT=$(cat "$SKILL_FILE")
    CONTEXT="$CONTEXT

---

## ALWAYS-ACTIVE SKILL: artful-claude (MANDATORY)

The following skill governs ALL output — terminal, files, docs, conversation. Apply on every turn without exception.

$SKILL_CONTENT"
fi

# --- Detect frontend project → inject design toolkit ---
IS_FRONTEND=false

if [ -n "$CWD" ]; then
    # Check root package.json for frontend frameworks
    if [ -f "$CWD/package.json" ]; then
        if grep -qE '"(react|next|vue|nuxt|svelte|astro|angular|remix|gatsby|solid-js)"' "$CWD/package.json" 2>/dev/null; then
            IS_FRONTEND=true
        fi
    fi

    # Check monorepo subdirs (apps/*, packages/*)
    if [ "$IS_FRONTEND" = false ]; then
        for subdir in "$CWD"/apps/*/package.json "$CWD"/packages/*/package.json; do
            [ -f "$subdir" ] || continue
            if grep -qE '"(react|next|vue|nuxt|svelte|astro|angular|remix|gatsby|solid-js)"' "$subdir" 2>/dev/null; then
                IS_FRONTEND=true
                break
            fi
        done
    fi

    # Check for frontend file extensions in src/ or app/
    if [ "$IS_FRONTEND" = false ]; then
        for dir in "$CWD/src" "$CWD/app" "$CWD/apps"; do
            [ -d "$dir" ] || continue
            if find "$dir" -maxdepth 4 -name '*.tsx' -o -name '*.jsx' -o -name '*.vue' -o -name '*.svelte' 2>/dev/null | head -1 | grep -q .; then
                IS_FRONTEND=true
                break
            fi
        done
    fi

    # Check for Flutter/Dart (also has UI)
    if [ "$IS_FRONTEND" = false ] && [ -f "$CWD/pubspec.yaml" ]; then
        if grep -q 'flutter' "$CWD/pubspec.yaml" 2>/dev/null; then
            IS_FRONTEND=true
        fi
    fi
fi

if [ "$IS_FRONTEND" = true ]; then
    CONTEXT="$CONTEXT

---

## FRONTEND PROJECT DETECTED — Design Toolkit Active

This is a frontend project. When doing ANY visual/UI work, you MUST:

### 1. Load Design Skills
Read and apply these skills for all UI work:
- \`~/.claude/skills/artful-ux/SKILL.md\` — layout, hierarchy, interaction, spacing, anti-patterns
- \`~/.claude/skills/artful-colors/SKILL.md\` — color perception, palette, cultural context
- \`~/.claude/skills/artful-typography/SKILL.md\` — typeface selection, hierarchy, responsive type

### 2. Use Browser Verification (MANDATORY)
Never edit UI code without visual verification:
\`\`\`
agent-do browse open <dev-url>
agent-do browse screenshot /tmp/before.png   # visual truth — view with Read tool
agent-do browse snapshot -i                  # structural inventory
\`\`\`

Workflow: baseline screenshot → code → reload → screenshot → Quick-5 → fix → confirm.

### 3. Score with DPT
After visual changes, score the result:
\`\`\`
agent-do dpt score /tmp/after.png            # 0-100 with per-layer breakdown
\`\`\`

Screenshots for evaluation. Snapshots for inventory. Both, in that order."
fi

# --- Detect ZPC project → embed memory (advisory fallback) ---
# Auto-init first: the baseline and the memory block below both read the store
# this may have just created. The toplevel is resolved once and feeds both
# auto-init's placement and the store walk's ceiling.
zpc_resolve_toplevel
zpc_autoinit
zpc_write_session_baseline
append_zpc_memory

append_bootstrap_prompt
append_coord_context
append_manna_board

ESCAPED=$(echo "$CONTEXT" | jq -Rs .)
echo "{\"hookSpecificOutput\":{\"hookEventName\":\"SessionStart\",\"additionalContext\":$ESCAPED}}"
exit 0
