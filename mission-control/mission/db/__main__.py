"""python -m mission.db migrate"""
from __future__ import annotations

import sys

from ..logging_setup import configure


def main(argv: list[str]) -> int:
    configure()
    cmd = argv[0] if argv else "migrate"
    if cmd == "migrate":
        from .migrate import migrate

        print("applied:", migrate() or "nothing")
        return 0
    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
