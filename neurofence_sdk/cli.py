from __future__ import annotations

import argparse
import json
import sys
from typing import Any, Optional

from neurofence_sdk.client import NeuroFenceClient


def _print_json(obj: Any) -> None:
    print(json.dumps(obj, indent=2, sort_keys=True))


def cmd_health(args: argparse.Namespace) -> int:
    client = NeuroFenceClient(base_url=args.url, timeout_seconds=args.timeout)
    data = client.health()
    _print_json(data)
    return 0


def cmd_intercept(args: argparse.Namespace) -> int:
    client = NeuroFenceClient(base_url=args.url, timeout_seconds=args.timeout)
    data = client.intercept(sender=args.sender, recipient=args.recipient, content=args.content)
    _print_json(data)
    return 0


def cmd_init(args: argparse.Namespace) -> int:
    base_url = args.url
    snippet = f'''# NeuroFence integration (Python)
# 1) pip install neurofence-sdk
# 2) run NeuroFence service (Docker/VM/K8s)
# 3) wrap your message send function

from neurofence_sdk import wrap_send

def send_message(sender: str, recipient: str, content: str):
    # TODO: replace with your real delivery
    deliver(sender, recipient, content)

send_message = wrap_send(
    send_message,
    base_url="{base_url}",
    timeout_s=5,
    block_flagged=True,
)
'''
    print(snippet)
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="neurofence", description="NeuroFence SDK CLI")
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--url", default="http://localhost:8000", help="NeuroFence base URL")
    common.add_argument("--timeout", type=float, default=10.0, help="HTTP timeout seconds")

    sub = p.add_subparsers(dest="command", required=True)

    h = sub.add_parser("health", help="Check NeuroFence /health", parents=[common])
    h.set_defaults(func=cmd_health)

    i = sub.add_parser("intercept", help="Call NeuroFence /intercept", parents=[common])
    i.add_argument("--sender", required=True)
    i.add_argument("--recipient", default=None)
    i.add_argument("--content", required=True)
    i.set_defaults(func=cmd_intercept)

    init = sub.add_parser("init", help="Print a minimal integration snippet", parents=[common])
    init.set_defaults(func=cmd_init)

    return p


def main(argv: Optional[list[str]] = None) -> int:
    argv = sys.argv[1:] if argv is None else argv

    # Make the CLI forgiving about flag ordering.
    # Users often type: `neurofence health --url http://...`.
    # Argparse only supports "global" options before the subcommand, so we
    # normalize `--url/--timeout` that appear before the subcommand by moving
    # them after it.
    if argv and not any(a in ("-h", "--help") for a in argv):
        commands = {"health", "intercept", "init"}
        cmd_index = next((i for i, a in enumerate(argv) if a in commands), None)
        if cmd_index is not None and cmd_index > 0:
            argv = [argv[cmd_index], *argv[:cmd_index], *argv[cmd_index + 1 :]]

    parser = build_parser()
    args = parser.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
