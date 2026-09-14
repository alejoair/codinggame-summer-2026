"""Bot del zoo: modo hugger. Ver _core.py."""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _core import run


def main(read=input, write=print):
    run(read, write, mode="hugger")


if __name__ == "__main__":
    main()
