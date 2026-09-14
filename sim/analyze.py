"""
Autopsia de una partida, turno a turno.

Juega UNA partida en el simulador y saca un diagnostico numerico por turno, mas
un render ASCII del tablero final. Sirve para encontrar ineficiencias concretas
(paint desperdiciado, conexiones que tardan, celdas neutralizadas) que un
marcador agregado esconde.

    python sim/analyze.py --p1 "python bot/bot.py" --p2 random --seed 5
    python sim/analyze.py --p1 "python bot/bot.py" --p2 wait --seed 5 --board
"""

import argparse
import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import referee as ref
from arena import make_bot

TERRAIN_CH = {ref.PLAINS: ".", ref.RIVER: "~", ref.MOUNTAIN: "^"}


def render(game, me=0):
    """Tablero final. Mayusculas = towns, o = mio, x = rival, = = neutral."""
    m = game.m
    out = []
    for y in range(m.h):
        row = []
        for x in range(m.w):
            i = y * m.w + x
            if m.town_at[i] != -1:
                row.append(str(m.town_at[i] % 10))
            elif game.inked[m.region[i]]:
                row.append("#")
            elif game.track[i] == me:
                row.append("o")
            elif game.track[i] == 1 - me:
                row.append("x")
            elif game.track[i] == ref.TRACK_NEUTRAL:
                row.append("=")
            else:
                row.append(TERRAIN_CH[m.terrain[i]])
        out.append("".join(row))
    return "\n".join(out)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--p1", default="python bot/bot.py")
    ap.add_argument("--p2", default="random")
    ap.add_argument("--seed", type=int, default=5)
    ap.add_argument("--league", type=int, default=3)
    ap.add_argument("--board", action="store_true", help="pintar el tablero final")
    ap.add_argument("--every", type=int, default=5, help="cada cuantos turnos imprimir")
    a = ap.parse_args()

    rng = random.Random(a.seed)
    while True:
        try:
            gmap = ref.generate_map(rng)
            break
        except ValueError:
            continue

    game = ref.Game(gmap, league=a.league)
    bots = [make_bot(a.p1, rng), make_bot(a.p2, rng)]
    for pid, b in enumerate(bots):
        b.start(game.init_lines(pid))

    n_pairs = sum(len(d) for d in gmap.desired)
    print("mapa %dx%d  towns=%d  pares=%d  regiones=%d"
          % (gmap.w, gmap.h, len(gmap.towns), n_pairs, gmap.n_regions))
    print("turno  paint_gast/desp  score      d_score  conex/tot  mios neutr riv  inked")

    prev_spent = [0, 0]
    prev_score = [0, 0]
    wasted_total = [0, 0]
    all_connected_turn = None

    while True:
        intents = [[], []]
        for pid, bot in enumerate(bots):
            line = bot.ask(game.turn_lines(pid))
            try:
                intents[pid] = game.parse(pid, line)
            except ValueError as e:
                print("DQ jugador %d: %s" % (pid, e))
                return
        over = game.step(intents)

        spent = game.paint_spent[0] - prev_spent[0]
        prev_spent[0] = game.paint_spent[0]
        wasted = max(0, ref.PAINT_PER_TURN - spent)
        wasted_total[0] += wasted
        wasted_total[1] += max(0, ref.PAINT_PER_TURN - (game.paint_spent[1] - prev_spent[1]))
        prev_spent[1] = game.paint_spent[1]

        # conexiones activas distintas
        active = set()
        for tags in game.active:
            for t in tags:
                active.add(t)

        mine = sum(1 for t in game.track if t == 0)
        neutral = sum(1 for t in game.track if t == ref.TRACK_NEUTRAL)
        foe = sum(1 for t in game.track if t == 1)
        inked = sum(1 for v in game.inked if v)

        if all_connected_turn is None and len(active) >= n_pairs:
            all_connected_turn = game.turn

        if game.turn % a.every == 0 or over:
            print("%5d  %6d/%-8d %5d-%-5d %6d   %3d/%-3d   %4d %5d %3d  %5d"
                  % (game.turn, spent, wasted,
                     game.score[0], game.score[1],
                     game.score[0] - prev_score[0],
                     len(active), n_pairs, mine, neutral, foe, inked))
        prev_score[0] = game.score[0]
        if over:
            break

    for b in bots:
        b.stop()

    print()
    print("resultado           %d - %d  (turno %d)" % (game.score[0], game.score[1], game.turn))
    print("paint desperdiciado p1=%d de %d  (%.0f%%)   p2=%d"
          % (wasted_total[0], game.turn * ref.PAINT_PER_TURN,
             100.0 * wasted_total[0] / max(1, game.turn * ref.PAINT_PER_TURN),
             wasted_total[1]))
    print("todas las conexiones activas en el turno: %s"
          % (all_connected_turn if all_connected_turn else "NUNCA"))
    mine = sum(1 for t in game.track if t == 0)
    neutral = sum(1 for t in game.track if t == ref.TRACK_NEUTRAL)
    print("celdas finales: mias=%d neutras=%d rival=%d"
          % (mine, neutral, sum(1 for t in game.track if t == 1)))
    if neutral:
        print("  -> %d celdas neutralizadas por colision: paint gastado que no puntua a nadie"
              % neutral)
    if a.board:
        print()
        print(render(game))


if __name__ == "__main__":
    main()
