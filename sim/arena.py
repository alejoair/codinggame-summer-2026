"""
Arena local: lanza N partidas del simulador entre dos bots (subprocesos, misma
E/S que CodinGame) y saca estadisticas.

    python sim/arena.py --p1 "python bot/bot.py" --p2 wait --games 20 --league 1
    python sim/arena.py --p1 "python bot/bot.py" --p2 "python referee/config/level2/Boss.py" --games 20 --league 2
    python sim/arena.py --p1 "python bot/bot.py" --p2 "python bot/bot.py" --games 30 --league 3

Bots internos sin subproceso (mas rapido): "wait", "random".
"""

import argparse
import importlib.util
import os
import queue
import random
import threading
import re
import subprocess
import tempfile
import sys
import time
from pathlib import Path
from concurrent.futures import ProcessPoolExecutor

sys.path.insert(0, str(Path(__file__).resolve().parent))
import referee as ref

ROOT = Path(__file__).resolve().parent.parent


class ProcBot:
    """Bot externo por stdin/stdout, exactamente como en CodinGame."""

    def __init__(self, cmd, name):
        self.cmd = cmd
        self.name = name
        self.p = None
        self.max_ms = 0.0
        self.first_ms = 0.0
        self.total_ms = 0.0
        self.turns = 0
        self.stderr_tail = []

    def start(self, init_lines):
        # stderr va a un FICHERO temporal, no a un pipe: un pipe que nadie vacia
        # se llena con el log del bot y el proceso se bloquea a mitad de partida.
        self._errf = tempfile.TemporaryFile(mode="w+")
        self.p = subprocess.Popen(
            self.cmd, shell=True, cwd=str(ROOT),
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=self._errf,
            text=True, bufsize=1,
        )
        self._send(init_lines)

    def _send(self, lines):
        self.p.stdin.write("\n".join(lines) + "\n")
        self.p.stdin.flush()

    def ask(self, lines):
        t0 = time.perf_counter()
        self._send(lines)
        out = self.p.stdout.readline()
        ms = (time.perf_counter() - t0) * 1000
        self.turns += 1
        self.total_ms += ms
        if self.turns == 1:
            self.first_ms = ms          # incluye arranque del interprete
        else:
            self.max_ms = max(self.max_ms, ms)
        if not out:
            raise RuntimeError("%s murio (sin salida)" % self.name)
        return out.strip()

    def stop(self):
        if self.p is None:
            return
        try:
            self.p.stdin.close()
            self.p.terminate()
            try:
                self.p.communicate(timeout=2)
            except Exception:
                self.p.kill()
        except Exception:
            pass
        try:
            self._errf.seek(0)
            self.stderr_tail = self._errf.read().strip().splitlines()[-15:]
            self._errf.close()
        except Exception:
            pass


class InProcBot:
    """
    Ejecuta un bot Python DENTRO de este proceso, en un hilo, con colas en
    memoria en lugar de pipes. Evita arrancar dos interpretes por partida, que
    es ~la mitad del coste de una partida en Windows.

    Requiere que el bot exponga main(read, write) con E/S inyectable, que es
    justo como esta escrito bot.py. El guard `if __name__ == "__main__"` impide
    que main() se dispare al importarlo.

    No reproduce la E/S real de CodinGame: para la validacion final usar ProcBot.
    """

    def __init__(self, path, name):
        self.path = path
        self.name = name
        self.inq = queue.Queue()
        self.outq = queue.Queue()
        self.thread = None
        self.max_ms = 0.0
        self.first_ms = 0.0
        self.total_ms = 0.0
        self.turns = 0
        self.stderr_tail = []
        self.error = None

    def _read(self):
        item = self.inq.get()
        if item is None:
            raise EOFError
        return item

    def _write(self, s):
        self.outq.put(str(s))

    def start(self, init_lines):
        spec = importlib.util.spec_from_file_location(
            "botmod_%d_%d" % (os.getpid(), id(self)), self.path)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)

        def run():
            try:
                mod.main(self._read, self._write)
            except EOFError:
                pass
            except Exception as e:                      # el bot ha reventado
                self.error = "%s: %s" % (type(e).__name__, e)
                self.stderr_tail = [self.error]
                self.outq.put(None)

        for line in init_lines:
            self.inq.put(line)
        self.thread = threading.Thread(target=run, daemon=True)
        self.thread.start()

    def ask(self, lines):
        t0 = time.perf_counter()
        for line in lines:
            self.inq.put(line)
        try:
            out = self.outq.get(timeout=60)
        except queue.Empty:
            raise RuntimeError("%s no respondio" % self.name)
        ms = (time.perf_counter() - t0) * 1000
        self.turns += 1
        self.total_ms += ms
        if self.turns == 1:
            self.first_ms = ms
        else:
            self.max_ms = max(self.max_ms, ms)
        if out is None:
            raise RuntimeError("%s murio: %s" % (self.name, self.error))
        return out.strip()

    def stop(self):
        self.inq.put(None)
        if self.thread is not None:
            self.thread.join(timeout=1)


class WaitBot:
    """El boss de Wood 2."""
    name = "wait"
    max_ms = total_ms = 0.0
    turns = 0
    stderr_tail = []

    def start(self, init_lines):
        pass

    def ask(self, lines):
        return "WAIT"

    def stop(self):
        pass


class RandomBot:
    """El boss de Wood 1: AUTOPLACE entre dos towns al azar cada turno."""
    name = "random"
    max_ms = total_ms = 0.0
    turns = 0
    stderr_tail = []

    def __init__(self, rng):
        self.rng = rng
        self.towns = []

    def start(self, init_lines):
        n_towns = int(init_lines[3 + int(init_lines[1]) * int(init_lines[2])])
        base = 4 + int(init_lines[1]) * int(init_lines[2])
        self.towns = []
        for k in range(n_towns):
            p = init_lines[base + k].split()
            self.towns.append((int(p[1]), int(p[2])))

    def ask(self, lines):
        if len(self.towns) < 2:
            return "WAIT"
        a, b = self.rng.sample(self.towns, 2)
        return "AUTOPLACE %d %d %d %d" % (a[0], a[1], b[0], b[1])

    def stop(self):
        pass


INPROC_RE = re.compile(r"^\s*python3?\s+(\S+\.py)\s*$")


def make_bot(spec, rng, inproc=False):
    if spec == "wait":
        return WaitBot()
    if spec == "random":
        return RandomBot(rng)
    if inproc:
        m = INPROC_RE.match(spec)
        if m:
            path = ROOT / m.group(1)
            if path.exists():
                return InProcBot(str(path), spec)
    return ProcBot(spec, spec)


def play(gmap, bots, league, verbose=False):
    game = ref.Game(gmap, league=league)
    for pid, bot in enumerate(bots):
        bot.start(game.init_lines(pid))

    dq = [None, None]
    while True:
        intents = [[], []]
        for pid, bot in enumerate(bots):
            line = bot.ask(game.turn_lines(pid))
            dq[pid] = line
            try:
                intents[pid] = game.parse(pid, line)
            except ValueError as e:
                return {"winner": 1 - pid, "dq": pid, "reason": str(e),
                        "score": game.score, "turn": game.turn}
        if game.step(intents):
            break
        if verbose:
            print("t%-3d %s  %s" % (game.turn, game.score, dq))
    return {"winner": game.winner(), "dq": None, "reason": "",
            "score": game.score, "turn": game.turn}


def _play_job(job):
    """
    Una partida completa, autocontenida y serializable: se ejecuta en un proceso
    worker. El mapa se regenera aqui a partir de la semilla, asi que el resultado
    es identico al de la version secuencial.
    """
    seed, league, spec_a, spec_b, swapped, inproc = job
    rng_map = random.Random(seed)
    while True:
        try:
            gmap = ref.generate_map(rng_map)
            break
        except ValueError:
            continue
    rng = random.Random(seed)
    specs = (spec_b, spec_a) if swapped else (spec_a, spec_b)
    bots = [make_bot(specs[0], rng, inproc), make_bot(specs[1], rng, inproc)]
    side_of = (1, 0) if swapped else (0, 1)   # side_of[bot] -> lado del tablero
    try:
        r = play(gmap, bots, league, False)
    except Exception as e:
        err = []
        for b in bots:
            b.stop()
            if b.stderr_tail:
                err.append("[%s] %s" % (b.name, " | ".join(b.stderr_tail[-5:])))
        return {"error": str(e), "swapped": swapped, "stderr": err}
    ms = [0.0, 0.0]
    err = []
    for side, b in enumerate(bots):
        ms[side_of.index(side)] = b.max_ms
        b.stop()
        if r["dq"] is not None and b.stderr_tail:
            err.append("[%s] %s" % (b.name, " | ".join(b.stderr_tail[-5:])))
    r["swapped"] = swapped
    r["side_of"] = side_of
    r["ms"] = ms
    r["stderr"] = err
    r["error"] = None
    return r


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--p1", default="python bot/bot.py")
    ap.add_argument("--p2", default="wait")
    ap.add_argument("--games", type=int, default=10)
    ap.add_argument("--league", type=int, default=1)
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--verbose", action="store_true")
    ap.add_argument("--swap", action="store_true",
                    help="juega cada mapa dos veces intercambiando lados (A/B justo)")
    ap.add_argument("--quiet", action="store_true", help="solo el resumen final")
    ap.add_argument("--inproc", action="store_true",
                    help="ejecutar los bots en hilos de este proceso (rapido); "
                         "para validar la E/S real, omitir")
    ap.add_argument("--jobs", type=int, default=0,
                    help="procesos en paralelo (0 = cpu_count-2)")
    a = ap.parse_args()

    # wins/scores estan SIEMPRE indexados por bot (0 = --p1, 1 = --p2),
    # no por lado del tablero, para que --swap no mezcle las cuentas.
    wins = [0, 0]
    draws = 0
    scores = [0, 0]
    dqs = [0, 0]
    worst_ms = [0.0, 0.0]
    as_p0 = [0, 0]          # victorias de cada bot jugando como jugador 0
    t0 = time.perf_counter()

    swaps = [False] if not a.swap else [False, True]
    jobs = [(a.seed + g, a.league, a.p1, a.p2, sw, a.inproc)
            for g in range(a.games) for sw in swaps]

    n_jobs = a.jobs if a.jobs > 0 else max(1, (os.cpu_count() or 2) - 2)
    n_jobs = min(n_jobs, len(jobs))
    print("%d partidas en %d procesos" % (len(jobs), n_jobs))

    if n_jobs == 1:
        results = [_play_job(j) for j in jobs]
    else:
        # Cada partida lanza sus dos bots como subprocesos, asi que el worker
        # esta casi todo el rato esperando E/S: se pueden solapar muchos.
        with ProcessPoolExecutor(max_workers=n_jobs) as ex:
            results = list(ex.map(_play_job, jobs))

    for k, r in enumerate(results):
        tag = "R" if r.get("swapped") else " "
        if r.get("error"):
            print("game %2d%s ERROR: %s" % (k // len(swaps), tag, r["error"]))
            for e in r.get("stderr", []):
                print("  " + e)
            continue
        side_of = r["side_of"]
        for bot_i in (0, 1):
            worst_ms[bot_i] = max(worst_ms[bot_i], r["ms"][bot_i])
        if r["dq"] is not None:
            dqs[side_of.index(r["dq"])] += 1
            print("game %2d%s  DQ: %s" % (k // len(swaps), tag, r["reason"]))
            for e in r.get("stderr", []):
                print("  " + e)
        if r["winner"] is None:
            draws += 1
        else:
            w = side_of.index(r["winner"])
            wins[w] += 1
            if r["winner"] == 0:
                as_p0[w] += 1
        scores[0] += r["score"][side_of[0]]
        scores[1] += r["score"][side_of[1]]
        if not a.quiet:
            label = "p1" if r["winner"] == side_of[0] else (
                "p2" if r["winner"] == side_of[1] else "empate")
            print("game %2d%s  %s  turno %d  score %d-%d"
                  % (k // len(swaps), tag, label, r["turn"],
                     r["score"][side_of[0]], r["score"][side_of[1]]))

    n = len(jobs)
    decided = wins[0] + wins[1]
    print("\n" + "=" * 60)
    print("liga %d   %d partidas%s   %.1fs"
          % (a.league, n, " (lados intercambiados)" if a.swap else "",
             time.perf_counter() - t0))
    print("p1 %-30s %3d victorias (%.0f%%)" % (a.p1[:30], wins[0], 100.0 * wins[0] / max(n, 1)))
    print("p2 %-30s %3d victorias (%.0f%%)" % (a.p2[:30], wins[1], 100.0 * wins[1] / max(n, 1)))
    if draws:
        print("empates: %d" % draws)
    if any(dqs):
        print("descalificaciones: p1=%d p2=%d" % tuple(dqs))
    print("score medio: %.1f - %.1f" % (scores[0] / max(n, 1), scores[1] / max(n, 1)))
    if a.swap:
        print("ventaja de lado: p1 gano %d de sus %d partidas como jugador 0"
              % (as_p0[0], wins[0]))
    # Intervalo de Wald al 95% sobre la tasa de victorias de p1 entre partidas decididas.
    if decided:
        p = wins[0] / decided
        err = 1.96 * (p * (1 - p) / decided) ** 0.5
        lo, hi = max(0.0, p - err), min(1.0, p + err)
        veredicto = ("p1 mejor" if lo > 0.5 else
                     "p2 mejor" if hi < 0.5 else
                     "NO CONCLUYENTE - hacen falta mas partidas")
        print("tasa p1: %.1f%%  IC95 [%.1f%%, %.1f%%]  ->  %s"
              % (100 * p, 100 * lo, 100 * hi, veredicto))
    print("peor turno (sin arranque): p1 %.1f ms   p2 %.1f ms   (limite CG: 50 ms)"
          % (worst_ms[0], worst_ms[1]))
    if n_jobs > 1:
        print("  ^ NO FIABLE con --jobs>1: los procesos compiten por la CPU.")
        print("    Para medir tiempos de verdad: --jobs 1")


if __name__ == "__main__":
    main()
