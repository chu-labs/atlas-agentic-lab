"""python -m board.db migrate | seed | reset"""
from __future__ import annotations

import sys

from ..logging_setup import configure


def main(argv: list[str]) -> int:
    configure()
    cmd = argv[0] if argv else "migrate"
    if cmd == "migrate":
        from .migrate import migrate

        print("applied:", migrate() or "nothing")
    elif cmd == "seed":
        from .migrate import migrate
        from .seed import seed

        migrate()
        print(seed())
    elif cmd == "reset":
        from .migrate import migrate
        from .seed import reset, seed

        migrate()
        reset()
        print(seed())
    else:
        print(__doc__)
        return 2
    return 0


if __name__ == "__main__":
    try:
        code = main(sys.argv[1:])
    finally:
        from .pool import pool

        pool().close()
    sys.exit(code)
