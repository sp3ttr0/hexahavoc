# hexahavoc

Automates mitm6 and ntlmrelayx in tmux for authorized IPv6 DNS and NTLM relay testing. Use only on networks you have permission to assess.

## Requirements

- Linux with IPv6 enabled; run as root from an interactive terminal outside tmux.
- Bash, Python 3, tmux, and iproute2 (`ip`).
- `mitm6` and `impacket-ntlmrelayx` available in PATH.
- Standard utilities: `mkdir`, `sleep`, `date`, `mktemp`, and `tee`.

## Usage

```bash
chmod +x hexahavoc.sh
sudo ./hexahavoc.sh -d example.com -t 192.168.1.10 -i eth0 --duration 60
```

| Option | Description |
| --- | --- |
| `-d <domain>` | Target domain (required). |
| `-t <IP>` | Target IPv4/IPv6 address (required; no hostnames or zone IDs). |
| `-i <interface>` | Network interface; default: `eth0`. |
| `-l <folder>` | Output parent folder; default: `dumps/`. |
| `--duration <seconds>` | Positive whole seconds before closing the new session; default: unlimited. |
| `--check` | Check local prerequisites and supplied settings without starting a run. |
| `--status` | List running hexahavoc sessions; no target arguments needed. |
| `--attach` / `--stop` | Attach to or stop the only running session. |
| `--session <name>` | Select an exact session for status, attach, or stop. Required if attaching/stopping with multiple sessions. |
| `-v` | Trace launcher commands. |
| `-s` | Hide launcher status messages; tool output and errors remain visible. Cannot combine with `-v`. |
| `-h` | Show help. |

## Preflight and session controls

```bash
sudo ./hexahavoc.sh --check -d example.com -t 192.168.1.10 -i eth0
sudo ./hexahavoc.sh --status
sudo ./hexahavoc.sh --attach
sudo ./hexahavoc.sh --stop
# Select one when multiple sessions are running:
sudo ./hexahavoc.sh --stop --session ipv6_dns_takeover_example_com
```

`--check` also works without targets; it validates dependencies, privileges, the interface, and output path permissions without creating files. Supplied target settings are validated locally; reachability is not tested. Session controls require only tmux and root, cannot be combined with run settings, and leave saved logs intact. Attaching does not reset the duration timer. Status lists sessions, not tool health or assessment success.

## Output and sessions

Each run creates a timestamped folder such as `dumps/2026-09-29_14-30-00_a1B2c3/`, containing separate `mitm6.log` and `ntlmrelayx.log` files plus any files ntlmrelayx generates. Logs include output and errors, remain visible in tmux, and are retained even if the attempt fails. Their presence does not confirm success.

Detaching leaves the tools running. With `--duration`, the session closes automatically even after detaching; leave its `duration` window open. The timer starts after session creation and applies only to new sessions. Without a duration, stop the session manually when finished.

## Offline tests

```bash
bash -n hexahavoc.sh
python3 -m unittest discover -s tests -v
```

Tests use mocks and do not run network attacks.

## Disclaimer

This tool is provided for educational and authorized security testing purposes only. Unauthorized use may violate laws and regulations. The authors and contributors of this tool are not responsible for any misuse or damage. By using this script, you accept full responsibility for your actions.
