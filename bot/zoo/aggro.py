"""Bot del zoo: modo aggro. Ver _core.py."""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _core import run


def main(read=input, write=print):
    run(read, write, mode="aggro")


if __name__ == "__main__":
    main()
