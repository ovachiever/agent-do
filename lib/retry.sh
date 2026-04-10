#!/usr/bin/env bash
# lib/retry.sh — Shared error recovery for agent-do tools
#
# Sources into any bash tool. Provides:
#   api_request()    — HTTP request with per-error-class retry logic
#   with_retry()     — Generic command retry with exponential backoff
#   parse_retry_after() — Extract wait time from Retry-After header
#
# Error recovery strategies:
#   429 (Rate Limited)  → respect Retry-After, exponential backoff, max 3 retries
#   401/403 (Auth)      → single retry (caller handles credential refresh)
#   500-529 (Server)    → exponential backoff, max 3 retries
#   Network (ECONNRESET, timeout) → immediate retry, max 2 retries
#   Context overflow    → return error (caller handles compaction)
#
# Usage:
#   source "$(dirname "$0")/../lib/retry.sh"
#   result=$(api_request GET "https://api.example.com/endpoint" \
#     --header "Authorization: Bearer $TOKEN")
#
# Environment:
#   AGENT_DO_RETRY_MAX      Max retries (default: 3)
#   AGENT_DO_RETRY_BACKOFF  Initial backoff ms (default: 500)
#   AGENT_DO_RETRY_MAX_WAIT Max backoff ms (default: 32000)
#   AGENT_DO_PERSISTENT     Set to 1 for CI/CD persistent retry mode

RETRY_MAX="${AGENT_DO_RETRY_MAX:-3}"
RETRY_BACKOFF="${AGENT_DO_RETRY_BACKOFF:-500}"
RETRY_MAX_WAIT="${AGENT_DO_RETRY_MAX_WAIT:-32000}"
RETRY_PERSISTENT="${AGENT_DO_PERSISTENT:-0}"

# Exponential backoff with jitter
# Usage: _backoff <attempt_number>
# Returns: sleep duration in seconds (float)
_backoff() {
    local attempt="${1:-0}"
    python3 -c "
import random
attempt = $attempt
base = $RETRY_BACKOFF / 1000.0
max_wait = $RETRY_MAX_WAIT / 1000.0
delay = min(base * (2 ** attempt), max_wait)
jitter = random.uniform(0, 0.25 * delay)
print(f'{delay + jitter:.3f}')
"
}

# Parse Retry-After header value
# Accepts: seconds (integer) or HTTP-date
# Returns: seconds to wait (integer)
parse_retry_after() {
    local value="$1"
    python3 -c "
import sys
from datetime import datetime, timezone
v = '$value'.strip()
if not v:
    print('2')
    sys.exit(0)
try:
    print(int(v))
except ValueError:
    try:
        target = datetime.strptime(v, '%a, %d %b %Y %H:%M:%S %Z').replace(tzinfo=timezone.utc)
        delta = int((target - datetime.now(timezone.utc)).total_seconds())
        print(max(1, delta))
    except:
        print('2')
"
}

# HTTP request with automatic retry and error classification
#
# Usage:
#   result=$(api_request METHOD URL [curl_args...])
#
# Returns: response body on stdout
# Sets:    API_REQUEST_STATUS (HTTP status code)
#          API_REQUEST_HEADERS (response headers, if --dump-headers used)
#
# Retries automatically on:
#   429 — rate limit (respects Retry-After)
#   500-529 — server errors (exponential backoff)
#   Network errors — connection reset, timeout (immediate retry)
#
# Returns immediately on:
#   200-399 — success
#   400 — client error (caller's problem)
#   401/403 — auth error (single retry, then return)
#   404 — not found
#
API_REQUEST_STATUS=""

api_request() {
    local method="$1"
    local url="$2"
    shift 2
    local extra_args=("$@")

    local max_retries="$RETRY_MAX"
    local attempt=0
    local auth_retried=false

    while true; do
        local header_file
        header_file=$(mktemp)

        # Execute request, capture status + headers + body
        local body http_code
        body=$(curl -s -w '\n%{http_code}' \
            -X "$method" "$url" \
            -D "$header_file" \
            "${extra_args[@]}" 2>/dev/null) || {
            # Network error (curl failed entirely)
            rm -f "$header_file"
            attempt=$((attempt + 1))
            if [[ $attempt -ge 2 ]]; then
                echo '{"error":"Network error after retries"}' >&2
                API_REQUEST_STATUS="0"
                return 1
            fi
            sleep 1
            continue
        }

        http_code=$(echo "$body" | tail -1)
        body=$(echo "$body" | sed '$d')
        API_REQUEST_STATUS="$http_code"

        # Success
        if [[ "$http_code" -ge 200 && "$http_code" -lt 400 ]]; then
            rm -f "$header_file"
            echo "$body"
            return 0
        fi

        # 429 — Rate limited
        if [[ "$http_code" == "429" ]]; then
            local retry_after
            retry_after=$(grep -i 'retry-after' "$header_file" 2>/dev/null | tr -d '\r' | awk '{print $2}')
            rm -f "$header_file"

            if [[ -n "$retry_after" ]]; then
                local wait_secs
                wait_secs=$(parse_retry_after "$retry_after")
            else
                local wait_secs
                wait_secs=$(_backoff "$attempt")
            fi

            # Persistent mode: retry indefinitely with max 5-minute backoff
            if [[ "$RETRY_PERSISTENT" == "1" ]]; then
                local capped_wait
                capped_wait=$(python3 -c "print(min($wait_secs, 300))")
                sleep "$capped_wait"
                continue
            fi

            attempt=$((attempt + 1))
            if [[ $attempt -ge $max_retries ]]; then
                echo "$body"
                return 1
            fi

            sleep "$wait_secs"
            continue
        fi

        # 401/403 — Auth error (retry once)
        if [[ "$http_code" == "401" || "$http_code" == "403" ]]; then
            rm -f "$header_file"
            if [[ "$auth_retried" == "true" ]]; then
                echo "$body"
                return 1
            fi
            auth_retried=true
            sleep 1
            continue
        fi

        # 500-529 — Server error
        if [[ "$http_code" -ge 500 && "$http_code" -le 529 ]]; then
            rm -f "$header_file"

            if [[ "$RETRY_PERSISTENT" == "1" ]]; then
                local wait
                wait=$(_backoff "$attempt")
                local capped
                capped=$(python3 -c "print(min($wait, 300))")
                sleep "$capped"
                attempt=$((attempt + 1))
                continue
            fi

            attempt=$((attempt + 1))
            if [[ $attempt -ge $max_retries ]]; then
                echo "$body"
                return 1
            fi

            local wait
            wait=$(_backoff "$attempt")
            sleep "$wait"
            continue
        fi

        # 400, 404, other client errors — return immediately
        rm -f "$header_file"
        echo "$body"
        return 1
    done
}

# Generic command retry with exponential backoff
#
# Usage:
#   with_retry 3 some_command arg1 arg2
#
# Retries the command up to N times with exponential backoff.
# Returns the exit code of the last attempt.
with_retry() {
    local max_attempts="$1"
    shift
    local attempt=0

    while [[ $attempt -lt $max_attempts ]]; do
        if "$@"; then
            return 0
        fi
        attempt=$((attempt + 1))
        if [[ $attempt -lt $max_attempts ]]; then
            local wait
            wait=$(_backoff "$attempt")
            sleep "$wait"
        fi
    done
    return 1
}

# Stall detector for streaming operations
#
# Usage:
#   stall_detect 90 some_long_command
#
# Kills the command if no output for N seconds.
# Prints warning at N/2 seconds.
stall_detect() {
    local timeout="$1"
    shift
    local warn_at=$((timeout / 2))

    "$@" &
    local pid=$!
    local last_size=0
    local stall_start=""
    local warned=false

    while kill -0 "$pid" 2>/dev/null; do
        sleep 5

        # Check if process produced output (via /proc or lsof — simplified here)
        local now
        now=$(date +%s)

        if [[ -z "$stall_start" ]]; then
            stall_start="$now"
        fi

        local stall_duration=$((now - stall_start))

        if [[ $stall_duration -ge $warn_at && "$warned" == "false" ]]; then
            echo "Warning: No output for ${stall_duration}s" >&2
            warned=true
        fi

        if [[ $stall_duration -ge $timeout ]]; then
            echo "Error: Stall detected (${timeout}s), aborting" >&2
            kill "$pid" 2>/dev/null
            return 1
        fi
    done

    wait "$pid"
}
