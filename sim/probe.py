"""
Localiza donde se cuelga un bot.

Le da a un bot un turno real generado por el simulador y, si no responde en
`--timeout` segundos, vuelca la pila con faulthandler: eso senala la linea
exacta en la que esta atascado, en vez de dejarnos adivinando.

    python sim/probe.py --bot bot/bot_v2.py --seed 4242 --timeout 10
"""

import argparse
import faulthandler
import importlib.util
import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import referee as ref


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--bot", default="bot/bot_v2.py")
    ap.add_argument("--seed", type=int, default=4242)
    ap.add_argument("--timeout", type=int, default=10)
    ap.add_argument("--turns", type=int, default=3)
    a = ap.parse_args()

    rng = random.Random(a.seed)
    while True:
        try:
            gmap = ref.generate_map(rng)
            break
        except ValueError:
            continue
    game = ref.Game(gmap, league=3)
    print("mapa %dx%d towns=%d" % (gmap.w, gmap.h, len(gmap.towns)), file=sys.stderr)

    lines = list(game.init_lines(0))
    for _ in range(a.turns):
        lines.extend(game.turn_lines(0))
    it = iter(lines)

    def read():
        return next(it)

    outputs = []

    def write(s):
        outputs.append(str(s))
        print("turno respondido: %s" % str(s)[:80], file=sys.stderr)

    root = Path(__file__).resolve().parent.parent
    spec = importlib.util.spec_from_file_location("probe_bot", str(root / a.bot))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)

    faulthandler.dump_traceback_later(a.timeout, exit=True)
    try:
        mod.main(read, write)
    except StopIteration:
        pass
    faulthandler.cancel_dump_traceback_later()
    print("OK, %d turnos respondidos" % len(outputs), file=sys.stderr)


if __name__ == "__main__":
    main()
