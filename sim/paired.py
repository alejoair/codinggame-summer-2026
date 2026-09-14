"""
Comparacion PAREADA de dos bots sobre los MISMOS mapas.

La varianza de score entre mapas de este juego es enorme (de 5.000 a 60.000),
asi que comparar dos medias de tandas distintas no distingue una mejora del
10% del ruido. Aqui cada mapa se juega con los dos bots contra el mismo rival,
y se analiza la DIFERENCIA por mapa, que elimina la varianza del mapa.

    python sim/paired.py --a "python bot/bot.py" --b "python bot/bot_v2.py" \
        --env-b "BTK_INFLATE=1 BTK_FACTOR=1.4 BTK_SAFE=0" --games 30
"""

import argparse
import os
import random
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import referee as ref
from arena import make_bot, ProcBot

ROOT = Path(__file__).resolve().parent.parent


def run_one(gmap, spec, opp_spec, rng_seed, env=None):
    """Devuelve (score_bot, score_rival) jugando el bot como jugador 0."""
    rng = random.Random(rng_seed)
    game = ref.Game(gmap, league=3)
    bot = make_bot(spec, rng)
    if isinstance(bot, ProcBot) and env:
        bot._extra_env = env
    opp = make_bot(opp_spec, rng)
    for pid, b in enumerate((bot, opp)):
        b.start(game.init_lines(pid))
    try:
        while True:
            intents = [[], []]
            for pid, b in enumerate((bot, opp)):
                line = b.ask(game.turn_lines(pid))
                try:
                    intents[pid] = game.parse(pid, line)
                except ValueError:
                    return (-1, -1)
            if game.step(intents):
                break
    finally:
        bot.stop()
        opp.stop()
    return (game.score[0], game.score[1])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--a", default="python bot/bot.py")
    ap.add_argument("--b", default="python bot/bot_v2.py")
    ap.add_argument("--env-b", default="", help='p.ej. "BTK_FACTOR=1.4 BTK_SAFE=0"')
    ap.add_argument("--opp", default="random")
    ap.add_argument("--games", type=int, default=30)
    ap.add_argument("--seed", type=int, default=1000)
    args = ap.parse_args()

    env_b = {}
    for kv in args.env_b.split():
        if "=" in kv:
            k, v = kv.split("=", 1)
            env_b[k] = v

    diffs = []
    a_tot = b_tot = 0
    b_better = 0
    for g in range(args.games):
        rng_map = random.Random(args.seed + g)
        while True:
            try:
                gmap = ref.generate_map(rng_map)
                break
            except ValueError:
                continue
        sa, _ = run_one(gmap, args.a, args.opp, args.seed + g)
        # el entorno del bot B se inyecta en el proceso hijo via os.environ
        old = {k: os.environ.get(k) for k in env_b}
        os.environ.update(env_b)
        try:
            sb, _ = run_one(gmap, args.b, args.opp, args.seed + g)
        finally:
            for k, v in old.items():
                if v is None:
                    os.environ.pop(k, None)
                else:
                    os.environ[k] = v
        if sa < 0 or sb < 0:
            print("mapa %d: descalificacion, descartado" % g)
            continue
        d = sb - sa
        diffs.append(d)
        a_tot += sa
        b_tot += sb
        if d > 0:
            b_better += 1
        print("mapa %2d   A=%-7d B=%-7d  dif=%+d" % (g, sa, sb, d))

    n = len(diffs)
    if n < 2:
        print("muestras insuficientes")
        return
    mean = sum(diffs) / n
    var = sum((d - mean) ** 2 for d in diffs) / (n - 1)
    sd = var ** 0.5
    se = sd / (n ** 0.5)
    t = mean / se if se else 0.0
    print("\n" + "=" * 60)
    print("A: %s" % args.a)
    print("B: %s %s" % (args.b, args.env_b))
    print("medias:  A=%.0f   B=%.0f   (%+.1f%%)"
          % (a_tot / n, b_tot / n, 100.0 * (b_tot - a_tot) / max(1, a_tot)))
    print("B gana en %d de %d mapas" % (b_better, n))
    print("diferencia pareada: %+.0f  (sd=%.0f, se=%.0f, t=%.2f, n=%d)"
          % (mean, sd, se, t, n))
    if abs(t) < 2.0:
        print("VEREDICTO: no concluyente (|t| < 2). Mas partidas o la mejora no existe.")
    else:
        print("VEREDICTO: diferencia real, a favor de %s" % ("B" if mean > 0 else "A"))


if __name__ == "__main__":
    main()
