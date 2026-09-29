# hexahavoc

**hexahavoc** is an automation script designed to facilitate an IPv6 DNS takeover attack. It leverages **mitm6** and **impacket-ntlmrelayx** within a **tmux** session to enable network administrators and penetration testers to conduct research and test IPv6 DNS vulnerabilities.

This script performs a man-in-the-middle attack via IPv6 rogue DNS server, allowing for NTLM relay attacks and DNS takeover simulations.

## Prerequisites

Run this script on **Linux**, as root, from an interactive terminal outside tmux. macOS is not supported. Ensure that the following tools are installed:

- **Bash**, **Python 3**, and **iproute2** (`ip`): For the launcher and local input validation.
- **tmux**: For managing multiple terminal sessions.
- **mitm6**: To facilitate IPv6 DNS takeover attacks.
- **impacket**: For NTLM relay and credential dumping.
- **date**, **mktemp**, and **tee**: For timestamped run folders and console logging.

Install them if they are not available in your environment.

## Usage:
```bash
sudo ./hexahavoc.sh -d <target_domain> -t <target_ip> [-i <interface>] [-l <loot_dir>] [--duration <seconds>] [-v | -s]
```

## Options
```
-d <target_domain>    (Required) Specifies the target domain for the DNS takeover.
-t <target_ip>        (Required) Specifies a literal IPv4 or IPv6 address. Hostnames and IPv6 zone IDs are not accepted.
-i <interface>        (Optional) Network interface to use. Defaults to eth0.
-l <folder>           (Optional) Parent directory for timestamped run folders. Defaults to dumps/.
--duration <seconds> (Optional) Close the new tmux session after 1–2147483647 whole seconds. Default: no time limit.
-v                    (Optional) Trace launcher commands; arguments may appear in terminal output.
-s                    (Optional) Suppress launcher status messages; errors, prompts, and tool output remain visible. Cannot be combined with -v.
-h                    Show help.
```

## Example
```bash
sudo ./hexahavoc.sh -d example.com -t 192.168.1.10 -i eth1 -l /tmp/loot -v
```

Run for 60 seconds, then automatically close the session and its tool panes:

```bash
sudo ./hexahavoc.sh -d example.com -t 192.168.1.10 -i eth1 --duration 60
```

`--duration=60` is also accepted. The timer starts just after session creation, before the startup checks, and keeps running if you detach. An attached launcher exits when the session closes. The timer runs in a separate `duration` window; leave that window open to retain the time limit. Closing the entire session early also closes its timer. A duration cannot be added to an existing session through this flag.

## Saved logs

Each new run creates a folder named with the local execution date and time, plus a unique suffix to prevent collisions:

```text
dumps/
└── 2026-09-29_14-30-00_a1B2c3/
    ├── mitm6.log
    └── ntlmrelayx.log
```

Each file captures its tool's standard output and standard error from startup, while the same output remains visible in tmux. Python output is unbuffered to reduce logging delays. Logs remain on disk after detaching, startup failure, or duration expiry. Output not yet emitted by a tool when it is stopped cannot be captured.

The `-l` flag changes the parent directory. Additional files produced by ntlmrelayx are saved inside the same run folder. Existing-session attachment continues the original logs rather than creating a new folder. New run folders are private (`700`) and log files are private (`600`).

## Session lifecycle

The launcher checks that both session-owned processes remain alive during a three-second startup interval. This does not confirm service readiness or a successful assessment; inspect the tool output in tmux.

Startup or attachment failures trigger cleanup of the session created by that invocation. A successful detach deliberately leaves the session running until its duration expires, or indefinitely if no duration was supplied. Stop it explicitly with tmux when finished. Existing sessions are never automatically cleaned up: without `--duration`, the launcher prompts to attach or kill and exit.

Output paths containing spaces are supported. New directories and files use a restrictive umask; existing directory permissions are unchanged. The launcher does not require a successful ping or perform DNS resolution to validate the target.

## Important Notes
- Use Responsibly: This script is intended solely for authorized testing and research purposes. Always ensure that you have explicit permission to perform penetration testing or security assessments on the target network.
- IPv6 Requirement: This attack only works in environments with IPv6 enabled. Ensure your target network is IPv6-enabled for successful execution.

## Offline checks

From the tool directory, run:

```bash
bash -n hexahavoc.sh
python3 -m unittest discover -s tests -v
```

The tests replace tmux and network commands with mocks and bypass the root guard only in a temporary test copy. They do not run an assessment or verify compatibility with installed tool versions.

## Disclaimer
This tool is provided for educational and authorized security testing purposes only. Unauthorized use may violate laws and regulations. The authors and contributors of this tool are not responsible for any misuse or damage. By using this script, you accept full responsibility for your actions.
