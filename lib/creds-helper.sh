#!/usr/bin/env bash
# lib/creds-helper.sh - Cross-platform secure secret storage for agent-do

set -euo pipefail

AGENT_DO_CREDS_SERVICE="${AGENT_DO_CREDS_SERVICE:-agent-do}"

detect_creds_platform() {
    case "$(uname -s)" in
        Darwin) echo "macos" ;;
        Linux) echo "linux" ;;
        MINGW*|MSYS*|CYGWIN*) echo "windows" ;;
        *) echo "unknown" ;;
    esac
}

AGENT_DO_CREDS_PLATFORM="${AGENT_DO_CREDS_PLATFORM:-$(detect_creds_platform)}"

normalize_secret_key() {
    local key="${1:-}"
    printf '%s' "$key" | tr '[:lower:]' '[:upper:]'
}

creds_store_macos() {
    local key="$1" value="$2"
    security add-generic-password -U -s "${AGENT_DO_CREDS_SERVICE}" -a "${key}" -w "$value" 2>/dev/null || \
    security add-generic-password -s "${AGENT_DO_CREDS_SERVICE}" -a "${key}" -w "$value"
}

creds_store_linux() {
    local key="$1" value="$2"
    if command -v secret-tool &>/dev/null; then
        printf '%s' "$value" | secret-tool store --label="${AGENT_DO_CREDS_SERVICE} ${key}" service "$AGENT_DO_CREDS_SERVICE" account "$key"
    else
        echo "Error: secret-tool not found. Install libsecret-tools." >&2
        return 1
    fi
}

creds_store_windows() {
    local key="$1" value="$2"
    AGENT_DO_CREDS_WIN_SERVICE="$AGENT_DO_CREDS_SERVICE" \
    AGENT_DO_CREDS_WIN_KEY="$key" \
    AGENT_DO_CREDS_WIN_VALUE="$value" \
    powershell.exe -NoProfile -NonInteractive -Command '
        $root = Join-Path ([Environment]::GetFolderPath("LocalApplicationData")) ("agent-do\\creds\\" + $env:AGENT_DO_CREDS_WIN_SERVICE)
        New-Item -ItemType Directory -Force -Path $root | Out-Null
        $path = Join-Path $root ($env:AGENT_DO_CREDS_WIN_KEY + ".txt")
        $secure = ConvertTo-SecureString $env:AGENT_DO_CREDS_WIN_VALUE -AsPlainText -Force
        $encrypted = ConvertFrom-SecureString $secure
        Set-Content -Path $path -Value $encrypted
    ' >/dev/null
}

creds_store() {
    local key value
    key="$(normalize_secret_key "${1:-}")"
    value="${2:-}"
    [[ -n "$key" ]] || { echo "Error: key is required" >&2; return 1; }

    case "$AGENT_DO_CREDS_PLATFORM" in
        macos) creds_store_macos "$key" "$value" ;;
        linux) creds_store_linux "$key" "$value" ;;
        windows) creds_store_windows "$key" "$value" ;;
        *)
            echo "Error: Unsupported platform for credential storage" >&2
            return 1
            ;;
    esac
}

creds_get_macos() {
    local key="$1"
    security find-generic-password -s "${AGENT_DO_CREDS_SERVICE}" -a "${key}" -w 2>/dev/null
}

creds_get_linux() {
    local key="$1"
    if command -v secret-tool &>/dev/null; then
        secret-tool lookup service "$AGENT_DO_CREDS_SERVICE" account "$key" 2>/dev/null
    else
        return 1
    fi
}

creds_get_windows() {
    local key="$1"
    AGENT_DO_CREDS_WIN_SERVICE="$AGENT_DO_CREDS_SERVICE" \
    AGENT_DO_CREDS_WIN_KEY="$key" \
    powershell.exe -NoProfile -NonInteractive -Command '
        $root = Join-Path ([Environment]::GetFolderPath("LocalApplicationData")) ("agent-do\\creds\\" + $env:AGENT_DO_CREDS_WIN_SERVICE)
        $path = Join-Path $root ($env:AGENT_DO_CREDS_WIN_KEY + ".txt")
        if (-not (Test-Path $path)) { exit 1 }
        $encrypted = Get-Content -Path $path -Raw
        $secure = ConvertTo-SecureString $encrypted
        $plain = [System.Net.NetworkCredential]::new("", $secure).Password
        Write-Output $plain
    ' 2>/dev/null
}

creds_get_from_store() {
    local key
    key="$(normalize_secret_key "${1:-}")"
    [[ -n "$key" ]] || return 1

    case "$AGENT_DO_CREDS_PLATFORM" in
        macos) creds_get_macos "$key" ;;
        linux) creds_get_linux "$key" ;;
        windows) creds_get_windows "$key" ;;
        *) return 1 ;;
    esac
}

creds_get() {
    local key
    key="$(normalize_secret_key "${1:-}")"
    local env_value="${!key:-}"
    if [[ -n "$env_value" ]]; then
        printf '%s' "$env_value"
        return 0
    fi
    creds_get_from_store "$key"
}

creds_get_source() {
    local key
    key="$(normalize_secret_key "${1:-}")"
    local env_value="${!key:-}"
    if [[ -n "$env_value" ]]; then
        printf 'env'
        return 0
    fi
    if creds_get_from_store "$key" >/dev/null 2>&1; then
        printf 'store'
        return 0
    fi
    return 1
}

creds_has() {
    creds_get "${1:-}" >/dev/null 2>&1
}

creds_delete_macos() {
    local key="$1"
    security delete-generic-password -s "${AGENT_DO_CREDS_SERVICE}" -a "${key}" >/dev/null 2>&1 || true
}

creds_delete_linux() {
    local key="$1"
    if command -v secret-tool &>/dev/null; then
        secret-tool clear service "$AGENT_DO_CREDS_SERVICE" account "$key" 2>/dev/null || true
    fi
}

creds_delete_windows() {
    local key="$1"
    AGENT_DO_CREDS_WIN_SERVICE="$AGENT_DO_CREDS_SERVICE" \
    AGENT_DO_CREDS_WIN_KEY="$key" \
    powershell.exe -NoProfile -NonInteractive -Command '
        $root = Join-Path ([Environment]::GetFolderPath("LocalApplicationData")) ("agent-do\\creds\\" + $env:AGENT_DO_CREDS_WIN_SERVICE)
        $path = Join-Path $root ($env:AGENT_DO_CREDS_WIN_KEY + ".txt")
        Remove-Item -Force -ErrorAction SilentlyContinue -Path $path
    ' >/dev/null 2>&1 || true
}

creds_delete() {
    local key
    key="$(normalize_secret_key "${1:-}")"
    [[ -n "$key" ]] || { echo "Error: key is required" >&2; return 1; }

    case "$AGENT_DO_CREDS_PLATFORM" in
        macos) creds_delete_macos "$key" ;;
        linux) creds_delete_linux "$key" ;;
        windows) creds_delete_windows "$key" ;;
        *) return 1 ;;
    esac
}

creds_list_store_macos() {
    security dump-keychain 2>/dev/null | grep -A4 "\"svce\"<blob>=\"${AGENT_DO_CREDS_SERVICE}\"" | grep "\"acct\"" | sed 's/.*"\([^"]*\)".*/\1/' | sort -u
}

creds_list_store_linux() {
    if command -v secret-tool &>/dev/null; then
        secret-tool search --all service "$AGENT_DO_CREDS_SERVICE" 2>/dev/null | grep "account" | sed 's/.*= //' | sort -u
    fi
}

creds_list_store_windows() {
    AGENT_DO_CREDS_WIN_SERVICE="$AGENT_DO_CREDS_SERVICE" \
    powershell.exe -NoProfile -NonInteractive -Command '
        $root = Join-Path ([Environment]::GetFolderPath("LocalApplicationData")) ("agent-do\\creds\\" + $env:AGENT_DO_CREDS_WIN_SERVICE)
        if (-not (Test-Path $root)) { exit 0 }
        Get-ChildItem -Path $root -Filter "*.txt" | ForEach-Object { $_.BaseName } | Sort-Object
    ' 2>/dev/null
}

creds_list_store() {
    case "$AGENT_DO_CREDS_PLATFORM" in
        macos) creds_list_store_macos ;;
        linux) creds_list_store_linux ;;
        windows) creds_list_store_windows ;;
        *) return 1 ;;
    esac
}

creds_export_line() {
    local key value
    key="$(normalize_secret_key "${1:-}")"
    value="$(creds_get "$key")" || return 1

    python3 - "$key" "$value" <<'PY'
import shlex
import sys

key = sys.argv[1]
value = sys.argv[2]
print(f"export {key}={shlex.quote(value)}")
PY
}
