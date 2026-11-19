# HexaHavoc

HexaHavoc runs `mitm6` and Impacket's `ntlmrelayx` in tmux for authorized IPv6 DNS and NTLM relay testing. Use it only on networks you have permission to assess.

## Requirements

- Linux with IPv6 enabled, root privileges, and an interactive terminal outside tmux
- Bash, Python 3, tmux, iproute2, `mitm6`, and `impacket-ntlmrelayx`

## Usage

Run `./hexahavoc.sh -h` for the available options. Use `--check` to validate local prerequisites and `--status`, `--attach`, or `--stop` to manage sessions created by the launcher. Use `--session <name>` to select a session. Older unmarked sessions must be managed directly in tmux.

Detaching leaves the session running. With `--duration`, the session stops at the deadline or if the timer exits early or a window is removed.

## Output

Each run saves separate tool logs in a private, timestamped directory under `dumps/` by default. Restrict access, redact sensitive data before sharing, and follow the assessment's retention and deletion requirements.

## Tests

```sh
bash -n hexahavoc.sh
python3 -B -m unittest discover -s tests -v
python3 -B tests/tmux_smoke.py -v
```

The smoke test uses an isolated tmux server and inert commands.
