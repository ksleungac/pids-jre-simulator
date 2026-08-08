# SPDX-License-Identifier: MIT
"""T1 — frame_stream.resolve_bind_host: launch flags -> bind address.

Oracle is independent of the implementation: the exposure contract. LAN
binding must require an explicit opt-in, and streaming must be off unless
asked for. A regression here silently exposes the app on every network the
user joins, which is exactly the class of thing no smoke test would notice.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import frame_stream  # noqa: E402

CASES = [
    # (stream, lan, expected)
    (False, False, None),  # default launch -> streaming off entirely
    (True, False, "127.0.0.1"),  # --stream -> loopback only, no firewall prompt
    (False, True, "0.0.0.0"),  # --stream-lan alone implies streaming
    (True, True, "0.0.0.0"),  # both -> LAN wins (widest requested)
]


def main() -> int:
    failed = 0
    for stream, lan, expected in CASES:
        got = frame_stream.resolve_bind_host(stream, lan)
        if got != expected:
            print(f"FAIL  stream={stream} lan={lan}: expected {expected!r}, got {got!r}")
            failed += 1

    # Exposure invariant, stated independently of the table above.
    if frame_stream.resolve_bind_host(stream=True, lan=False) == "0.0.0.0":
        print("FAIL  --stream alone must NOT bind the LAN")
        failed += 1

    print(f"test_stream_bind: {len(CASES)} cases, {failed} failed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
