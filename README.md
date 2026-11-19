# HexaHavoc

HexaHavoc runs `mitm6` and Impacket's `ntlmrelayx` in tmux for authorized IPv6 DNS and NTLM relay testing.

## Requirements

- Linux with IPv6 enabled, root privileges, and an interactive terminal outside tmux
- Bash, Python 3, tmux, iproute2, `mitm6`, and `impacket-ntlmrelayx`

## Usage

| Flag | Purpose |
| --- | --- |
| `-d <domain>` | Domain for a new run. Required. |
| `-t <IP>` | Target IPv4 or IPv6 address for a new run. Required. |
| `-i <interface>` | Network interface. Defaults to `eth0`. |
| `-l <directory>` | Parent directory for saved output. Defaults to `dumps/`. |
| `--duration <seconds>` | Set a shutdown deadline in positive whole seconds. |
| `--check` | Validate local prerequisites and supplied settings without starting tools. |
| `--status` | List running HexaHavoc sessions. |
| `--attach` | Attach to a running HexaHavoc session. |
| `--stop` | Stop a running HexaHavoc session and keep saved output. |
| `--session <name>` | Select a session by exact name for status, attach, or stop. Required for attach or stop when multiple sessions exist. |
| `-v` | Trace launcher commands. May expose arguments in terminal output. |
| `-s` | Hide launcher status messages. Tool output and errors stay visible. Incompatible with `-v`. |
| `-h` | Show built-in help with `./hexahavoc.sh -h`. |

Older unmarked sessions must be managed directly in tmux.

Detaching leaves the session running. With `--duration`, the session stops at the deadline or if the timer exits early or a window is removed.

## Output

Each run saves separate tool logs in a private, timestamped directory under `dumps/` by default. Restrict access, redact sensitive data before sharing, and follow the assessment's retention and deletion requirements.

## Tests

```sh
bash -n hexahavoc.sh
python3 -B -m unittest discover -s tests -v
python3 -B tests/tmux_smoke.py -v
```

The smoke test requires tmux and uses an isolated server with inert commands. The tests can run without root privileges.

## Disclaimer

HexaHavoc is provided as is for authorized security testing and education. Use it only on systems and networks you own or have explicit permission to test. You are responsible for staying within the agreed scope and complying with applicable laws.
