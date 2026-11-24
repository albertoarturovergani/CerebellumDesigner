#!/usr/bin/env bash
set -euo pipefail
cd_helper_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
cd_install_root="$HOME/CerebellumDesigner_WSL"
cd_archive_hash=d98bff221871c5e18678ebaf5dfdacc866c06ee444f076a7476968d791704b17
cd_source_marker="$cd_install_root/.windows-source-sha256"

check_platform() {
    local kernel
    kernel="$(uname -r)"
    if [[ "$kernel" != *WSL2* && "$kernel" != *microsoft-standard* ]]; then
        echo 'WSL2 is required. In Windows run: wsl --set-version Ubuntu-24.04 2' >&2
        return 1
    fi
    if [[ "$(uname -m)" != x86_64 ]]; then
        echo 'This kit targets Windows x64; Windows ARM has not been validated.' >&2
        return 1
    fi
    source /etc/os-release
    if [[ "$ID" != ubuntu || "$VERSION_ID" != 24.04 ]]; then
        echo 'Choose an Ubuntu 24.04 WSL distribution; other installations are left unchanged.' >&2
        return 1
    fi
    if (( EUID == 0 )); then
        echo 'Open Ubuntu first and create/select a normal Linux user. Do not run Designer as root.' >&2
        return 1
    fi
}

prepare_source() {
    local archive staging
    archive="$cd_helper_dir/payload/CerebellumDesigner_Ubuntu_20261123.tar.gz"
    if [[ ! -f "$archive" ]]; then
        archive="$cd_helper_dir/../downloads/CerebellumDesigner_Ubuntu_20261123.tar.gz"
    fi
    if [[ ! -f "$archive" ]]; then
        echo 'Missing payload. Extract the entire Windows ZIP before installing.' >&2
        return 1
    fi
    if [[ "$(sha256sum -- "$archive" | cut -d ' ' -f 1)" != "$cd_archive_hash" ]]; then
        echo 'Source archive checksum mismatch. Nothing extracted.' >&2
        return 1
    fi
    if [[ -e "$cd_install_root" || -L "$cd_install_root" ]]; then
        if [[ -L "$cd_install_root" || ! -f "$cd_source_marker" ]] || [[ "$(cat "$cd_source_marker")" != "$cd_archive_hash" ]]; then
            echo "Existing directory is not this installation: $cd_install_root . Nothing overwritten." >&2
            return 1
        fi
        (cd "$cd_install_root" && python3 verify_kit.py)
        return
    fi
    # Extract on the Linux filesystem, never install the environment under /mnt/c.
    staging="$(mktemp -d "$(dirname -- "$cd_install_root")/.cerebellum-designer-install.XXXXXX")"
    if ! tar --no-same-owner -xzf "$archive" -C "$staging" --strip-components=1; then
        echo "Extraction failed. Partial files preserved in $staging" >&2
        return 1
    fi
    (cd "$staging" && python3 verify_kit.py)
    printf '%s\n' "$cd_archive_hash" > "$staging/.windows-source-sha256"
    # mv -T refuses to merge a concurrent installation into an existing directory.
    mv -T -- "$staging" "$cd_install_root"
}

require_ready() {
    [[ -f "$cd_install_root/.windows-ready" && -x "$cd_install_root/szpaper2/bin/python" ]] || {
        echo 'Installation is incomplete. Run 1_Install_Designer.cmd.' >&2
        return 1
    }
}

main() {
    local action="${1:-check}" port="${2:-8891}"
    check_platform
    case "$action" in
        check) ;;
        install)
            # Lock installation only; never stop an existing Designer or scientific run.
            exec 9>"$HOME/.cerebellum-designer-install.lock"
            flock -n 9 || { echo 'An installation is already running.' >&2; return 1; }
            prepare_source
            rm -f -- "$cd_install_root/.windows-ready"
            bash "$cd_install_root/setup_ubuntu.sh"
            printf '%s\n' "$cd_archive_hash" > "$cd_install_root/.windows-ready"
            ;;
        ready) require_ready ;;
        start)
            require_ready
            [[ "$port" =~ ^[0-9]+$ ]] && (( port >= 1024 && port <= 65535 )) || { echo 'Invalid port' >&2; return 1; }
            source "$cd_install_root/activate.sh"
            cd "$cd_install_root"
            echo "Cerebellum Designer - open http://127.0.0.1:$port/ in your Windows browser. Ctrl+C stops this server."
            exec python -m cereb_remorph.designer --port "$port"
            ;;
        exports)
            require_ready
            wslpath -w "$cd_install_root/DeformationAlgorithm/exports"
            ;;
        terminal)
            require_ready
            export CD_WINDOWS_INSTALL_ROOT="$cd_install_root"
            exec bash --rcfile "$cd_helper_dir/terminal-rc.sh" -i
            ;;
        *) echo 'Unknown action' >&2; return 1 ;;
    esac
}

# Functions can be sourced by offline tests without pretending to run on WSL.
if [[ "${BASH_SOURCE[0]}" == "$0" ]]; then main "$@"; fi
