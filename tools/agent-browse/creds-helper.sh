#!/usr/bin/env bash
# creds-helper.sh - Cross-platform secure credential storage
# Supports: macOS Keychain, Windows Credential Manager, Linux Secret Service, env vars (CI)

set -euo pipefail

SERVICE_NAME="agent-browse"

# Detect platform
detect_platform() {
    case "$(uname -s)" in
        Darwin) echo "macos" ;;
        Linux)  echo "linux" ;;
        MINGW*|MSYS*|CYGWIN*) echo "windows" ;;
        *) echo "unknown" ;;
    esac
}

PLATFORM=$(detect_platform)

# Convert domain to credential key: ninety.io -> ninety-io
domain_to_key() {
    local domain="$1"
    echo "$domain" | sed -E 's/^(www\.|app\.|eos\.)?//; s/[^a-zA-Z0-9]/-/g' | tr '[:upper:]' '[:lower:]'
}

# Convert domain to env var prefix: ninety.io -> NINETY
domain_to_prefix() {
    local domain="$1"
    echo "$domain" | sed -E 's/^(www\.|app\.|eos\.)?//; s/\.[a-z]+$//; s/[^a-zA-Z0-9]/_/g' | tr '[:lower:]' '[:upper:]'
}

# ============================================================================
# STORE CREDENTIALS
# ============================================================================

store_macos() {
    local key="$1" email="$2" password="$3"
    # Store email
    security add-generic-password -U -s "${SERVICE_NAME}" -a "${key}-email" -w "$email" 2>/dev/null || \
    security add-generic-password -s "${SERVICE_NAME}" -a "${key}-email" -w "$email"
    # Store password
    security add-generic-password -U -s "${SERVICE_NAME}" -a "${key}-password" -w "$password" 2>/dev/null || \
    security add-generic-password -s "${SERVICE_NAME}" -a "${key}-password" -w "$password"
}

store_linux() {
    local key="$1" email="$2" password="$3"
    if command -v secret-tool &>/dev/null; then
        echo -n "$email" | secret-tool store --label="$SERVICE_NAME $key email" service "$SERVICE_NAME" account "${key}-email"
        echo -n "$password" | secret-tool store --label="$SERVICE_NAME $key password" service "$SERVICE_NAME" account "${key}-password"
    else
        echo "Error: secret-tool not found. Install libsecret-tools." >&2
        return 1
    fi
}

store_windows() {
    local key="$1" email="$2" password="$3"
    # Use PowerShell to store in Windows Credential Manager
    powershell.exe -Command "
        \$cred = New-Object System.Management.Automation.PSCredential('${key}-email', (ConvertTo-SecureString '$email' -AsPlainText -Force))
        cmdkey /generic:${SERVICE_NAME}-${key}-email /user:${key}-email /pass:$email
        cmdkey /generic:${SERVICE_NAME}-${key}-password /user:${key}-password /pass:$password
    " 2>/dev/null
}

store_creds() {
    local domain="$1" email="$2" password="$3"
    local key
    key=$(domain_to_key "$domain")
    
    case "$PLATFORM" in
        macos)   store_macos "$key" "$email" "$password" ;;
        linux)   store_linux "$key" "$email" "$password" ;;
        windows) store_windows "$key" "$email" "$password" ;;
        *)
            echo "Error: Unsupported platform" >&2
            return 1
            ;;
    esac
}

# ============================================================================
# GET CREDENTIALS
# ============================================================================

get_macos() {
    local key="$1"
    local email password
    email=$(security find-generic-password -s "${SERVICE_NAME}" -a "${key}-email" -w 2>/dev/null) || return 1
    password=$(security find-generic-password -s "${SERVICE_NAME}" -a "${key}-password" -w 2>/dev/null) || return 1
    echo "$email"
    echo "$password"
}

get_linux() {
    local key="$1"
    local email password
    if command -v secret-tool &>/dev/null; then
        email=$(secret-tool lookup service "$SERVICE_NAME" account "${key}-email" 2>/dev/null) || return 1
        password=$(secret-tool lookup service "$SERVICE_NAME" account "${key}-password" 2>/dev/null) || return 1
        echo "$email"
        echo "$password"
    else
        return 1
    fi
}

get_windows() {
    local key="$1"
    # Use PowerShell to retrieve from Windows Credential Manager
    local result
    result=$(powershell.exe -Command "
        \$email = (cmdkey /list:${SERVICE_NAME}-${key}-email | Select-String 'User:' | ForEach-Object { \$_.Line.Split(':')[1].Trim() })
        \$pass = (cmdkey /list:${SERVICE_NAME}-${key}-password | Select-String 'User:' | ForEach-Object { \$_.Line.Split(':')[1].Trim() })
        Write-Output \$email
        Write-Output \$pass
    " 2>/dev/null) || return 1
    echo "$result"
}

get_creds() {
    local domain="$1"
    local key prefix email_var pass_var email_val pass_val
    key=$(domain_to_key "$domain")
    prefix=$(domain_to_prefix "$domain")
    email_var="${prefix}_EMAIL"
    pass_var="${prefix}_PASSWORD"
    
    # 1. Check environment variables first (for CI/CD)
    email_val="${!email_var:-}"
    pass_val="${!pass_var:-}"
    if [[ -n "$email_val" && -n "$pass_val" ]]; then
        echo "$email_val"
        echo "$pass_val"
        echo "env"
        return 0
    fi
    
    # 2. Try OS keychain
    local creds source="keychain"
    case "$PLATFORM" in
        macos)   creds=$(get_macos "$key" 2>/dev/null) ;;
        linux)   creds=$(get_linux "$key" 2>/dev/null) ;;
        windows) creds=$(get_windows "$key" 2>/dev/null) ;;
    esac
    
    if [[ -n "$creds" ]]; then
        echo "$creds"
        echo "$source"
        return 0
    fi
    
    return 1
}

# ============================================================================
# DELETE CREDENTIALS
# ============================================================================

delete_macos() {
    local key="$1"
    security delete-generic-password -s "${SERVICE_NAME}" -a "${key}-email" 2>/dev/null || true
    security delete-generic-password -s "${SERVICE_NAME}" -a "${key}-password" 2>/dev/null || true
}

delete_linux() {
    local key="$1"
    if command -v secret-tool &>/dev/null; then
        secret-tool clear service "$SERVICE_NAME" account "${key}-email" 2>/dev/null || true
        secret-tool clear service "$SERVICE_NAME" account "${key}-password" 2>/dev/null || true
    fi
}

delete_windows() {
    local key="$1"
    cmdkey /delete:${SERVICE_NAME}-${key}-email 2>/dev/null || true
    cmdkey /delete:${SERVICE_NAME}-${key}-password 2>/dev/null || true
}

delete_creds() {
    local domain="$1"
    local key
    key=$(domain_to_key "$domain")
    
    case "$PLATFORM" in
        macos)   delete_macos "$key" ;;
        linux)   delete_linux "$key" ;;
        windows) delete_windows "$key" ;;
    esac
}

# ============================================================================
# LIST CREDENTIALS
# ============================================================================

list_creds() {
    case "$PLATFORM" in
        macos)
            security dump-keychain 2>/dev/null | grep -A4 "\"svce\"<blob>=\"${SERVICE_NAME}\"" | grep "\"acct\"" | sed 's/.*"\([^"]*\)".*/\1/' | sed 's/-email$//' | sed 's/-password$//' | sort -u
            ;;
        linux)
            if command -v secret-tool &>/dev/null; then
                secret-tool search --all service "$SERVICE_NAME" 2>/dev/null | grep "account" | sed 's/.*= //' | sed 's/-email$//' | sed 's/-password$//' | sort -u
            fi
            ;;
        windows)
            cmdkey /list 2>/dev/null | grep "${SERVICE_NAME}" | sed "s/.*${SERVICE_NAME}-//" | sed 's/-email$//' | sed 's/-password$//' | sort -u
            ;;
    esac
}

# ============================================================================
# MAIN
# ============================================================================

case "${1:-}" in
    store)
        [[ $# -lt 4 ]] && { echo "Usage: $0 store <domain> <email> <password>" >&2; exit 1; }
        store_creds "$2" "$3" "$4"
        echo "Stored credentials for $2 in $PLATFORM keychain"
        ;;
    get)
        [[ $# -lt 2 ]] && { echo "Usage: $0 get <domain>" >&2; exit 1; }
        get_creds "$2"
        ;;
    delete)
        [[ $# -lt 2 ]] && { echo "Usage: $0 delete <domain>" >&2; exit 1; }
        delete_creds "$2"
        echo "Deleted credentials for $2"
        ;;
    list)
        list_creds
        ;;
    platform)
        echo "$PLATFORM"
        ;;
    *)
        echo "Usage: $0 <store|get|delete|list|platform> [args...]" >&2
        echo "" >&2
        echo "Commands:" >&2
        echo "  store <domain> <email> <password>  Store credentials securely" >&2
        echo "  get <domain>                       Get credentials (email, password, source)" >&2
        echo "  delete <domain>                    Delete stored credentials" >&2
        echo "  list                               List all stored domains" >&2
        echo "  platform                           Show detected platform" >&2
        echo "" >&2
        echo "Credential sources (in priority order):" >&2
        echo "  1. Environment variables (\${DOMAIN}_EMAIL, \${DOMAIN}_PASSWORD)" >&2
        echo "  2. OS Keychain (macOS Keychain, Windows Credential Manager, Linux Secret Service)" >&2
        exit 1
        ;;
esac
