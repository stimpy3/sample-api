#!/usr/bin/env python
"""Export the FastAPI app's OpenAPI spec to YAML.

api-guard calls this via `generate_cmd` in api-guard.yaml. It never imports
FastAPI itself — the project tells it how to produce a spec, and it runs that
command. That indirection is what lets the same tool work on a Spring Boot or
Express project.

The output must be BYTE-STABLE across runs and across machines. The freshness
check compares this output against the committed openapi.yaml, so any
instability here fails every build for no reason and the gate loses
credibility. Three things guarantee it:

  * `sort_keys=True`      — dict iteration order never leaks into the output
  * explicit `width`      — don't inherit a PyYAML default that could change
  * raw bytes, LF only    — Windows must not translate "\\n" into "\\r\\n"

The last one is the easy mistake: `print()` on Windows emits CRLF, so the
generated text would differ from a committed LF file on every single run.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from app.main import app  # noqa: E402  (import must follow the sys.path tweak)

DEFAULT_OUTPUT = REPO_ROOT / "openapi.yaml"


def generate() -> bytes:
    """Build the spec and serialise it deterministically as UTF-8 with LF endings."""
    # FastAPI memoises the schema on first access; clear it so repeated calls in
    # one process genuinely rebuild rather than returning the cached object.
    app.openapi_schema = None
    spec = app.openapi()

    text = yaml.safe_dump(
        spec,
        sort_keys=True,
        default_flow_style=False,
        allow_unicode=True,
        width=88,
    )
    return text.encode("utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    target = parser.add_mutually_exclusive_group()
    target.add_argument(
        "--stdout",
        action="store_true",
        help="Write the spec to stdout (how api-guard invokes this).",
    )
    target.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_OUTPUT,
        help=f"File to write the spec to (default: {DEFAULT_OUTPUT.name}).",
    )
    args = parser.parse_args()

    spec = generate()

    if args.stdout:
        # Bytes straight to the buffer: text mode would rewrite newlines on Windows.
        sys.stdout.buffer.write(spec)
    else:
        args.output.write_bytes(spec)
        print(f"Wrote {len(spec)} bytes to {args.output}", file=sys.stderr)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
