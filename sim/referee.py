"""
Port a Python del referee de Back Track King (Summer Challenge 2026).

El MOTOR DE REGLAS es fiel al referee Java (orden de resolucion, tracks
neutrales, BFS de conexion con desempate N/E/S/W, inking, puntuacion).
El GENERADOR DE MAPAS reproduce los mismos parametros y restricciones, pero no
es bit-a-bit identico al de Java (usa el RNG de Python): sirve para entrenar y
comparar bots sobre mapas realistas, no para reproducir una seed concreta de
CodinGame.

Para validar comportamientos exactos de desempate esta el referee Java en
referee/ (necesita Maven).
"""

import random
from collections import deque
from heapq import heappush, heappop

PLAINS, RIVER, MOUNTAIN = 0, 1, 2
COST = (1, 2, 3, 3)
TRACK_NONE, TRACK_NEUTRAL = -1, 2

PAINT_PER_TURN = 3
BLOT_POINTS_PER_TURN = 1
INSTABILITY_THRESHOLD = 4
MAX_TURNS = 100
MIN_TOWN_DISTANCE = 4
AVERAGE_TILES_PER_TOWN = 50
MOUNTAIN_TO_CELL_RATIO = 0.04
RIVER_TO_LAND_MIN_RATIO = 0.07
MIN_MOUNTAINS = 2


# ---------------------------------------------------------------- map gen

class Map:
    def __init__(self, w, h, terrain, region, towns, desired):
        self.w, self.h = w, h
        self.n = w * h
        self.terrain = terrain
        self.region = region
        self.towns = towns              # list[(x, y)] indexado por townId
        self.desired = desired          # list[list[townId]]
        self.n_regions = max(region) + 1
        self.town_at = [-1] * self.n
        for tid, (x, y) in enumerate(towns):
            self.town_at[y * w + x] = tid
        self.nb = [[] for _ in range(self.n)]
        for y in range(h):
            for x in range(w):
                i = y * w + x
                if y > 0:
                    self.nb[i].append(i - w)      # N
                if x < w - 1:
                    self.nb[i].append(i + 1)      # E
                if y < h - 1:
                    self.nb[i].append(i + w)      # S
                if x > 0:
                    self.nb[i].append(i - 1)      # W
        self.region_cells = [[] for _ in range(self.n_regions)]
        for i in range(self.n):
            self.region_cells[region[i]].append(i)
        self.region_has_town = [False] * self.n_regions
        for (x, y) in towns:
            self.region_has_town[region[y * w + x]] = True


def generate_map(rng):
    h = rng.randint(14, 20)
    w = round(h * 1.5)
    n = w * h
    terrain = [PLAINS] * n

    def idx(x, y):
        return y * w + x

    def in_b(x, y):
        return 0 <= x < w and 0 <= y < h

    def neigh4(i):
        x, y = i % w, i // w
        out = []
        for dx, dy in ((0, -1), (1, 0), (0, 1), (-1, 0)):
            if in_b(x + dx, y + dy):
                out.append(idx(x + dx, y + dy))
        return out

    def neigh8(i):
        x, y = i % w, i // w
        out = []
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                if (dx or dy) and in_b(x + dx, y + dy):
                    out.append(idx(x + dx, y + dy))
        return out

    # --- montanas: blobs de 2..8 celdas
    n_mountains = max(MIN_MOUNTAINS, round(rng.random() * n * MOUNTAIN_TO_CELL_RATIO))
    free = list(range(n))
    rng.shuffle(free)
    for _ in range(n_mountains):
        if not free:
            break
        base = free.pop()
        size = rng.randint(2, 7)
        blob = [base]
        terrain[base] = MOUNTAIN
        for _ in range(size):
            cand = [v for c in blob for v in neigh4(c) if terrain[v] == PLAINS]
            if not cand:
                break
            nxt = rng.choice(cand)
            terrain[nxt] = MOUNTAIN
            blob.append(nxt)

    # --- rios: serpentean desde los bordes, evitando pegarse a si mismos
    target_river = round(n * RIVER_TO_LAND_MIN_RATIO)
    borders = [idx(x, y) for y in range(h) for x in range(w)
               if (x == 0 or y == 0 or x == w - 1 or y == h - 1)
               and not ((x in (0, w - 1)) and (y in (0, h - 1)))]
    rng.shuffle(borders)
    sources = [idx(w // 2, h // 2)] + borders
    placed = 0
    for src in sources:
        if placed >= target_river:
            break
        if terrain[src] != PLAINS:
            continue
        if any(terrain[v] == RIVER for v in neigh8(src)):
            continue
        x, y = src % w, src // w
        pref = (1, 0) if x == 0 else (-1, 0) if x == w - 1 else (0, 1) if y == 0 else (0, -1)
        cur = src
        terrain[cur] = RIVER
        placed += 1
        hist = [cur]
        while placed < target_river:
            cand = []
            for v in neigh4(cur):
                if terrain[v] != PLAINS:
                    continue
                if any(terrain[u] == RIVER for u in neigh8(v) if u not in hist[-2:]):
                    continue
                cand.append(v)
            if not cand:
                break
            weights = []
            for v in cand:
                d = (v % w - cur % w, v // w - cur // w)
                weights.append(1.75 if d == pref else 0.25 if d == (-pref[0], -pref[1]) else 1.0)
            nxt = rng.choices(cand, weights=weights)[0]
            terrain[nxt] = RIVER
            placed += 1
            hist.append(nxt)
            cur = nxt
            cx, cy = cur % w, cur // w
            if cx in (0, w - 1) or cy in (0, h - 1):
                break

    # --- regiones: semillas en rejilla + crecimiento round-robin
    avg_tiles = h // 2
    n_zones = max(1, n // avg_tiles)
    cols = int(n_zones ** 0.5 + 0.999)
    rows = -(-n_zones // cols)
    region = [-1] * n
    zones = []
    for i in range(n_zones):
        row, col = i // cols, i % cols
        if row == rows - 1 and n_zones % cols != 0:
            cw = w / (n_zones % cols)
        else:
            cw = w / cols
        cx = int((col + 0.5) * cw)
        cy = int((row + 0.5) * (h / rows))
        cx, cy = min(cx, w - 1), min(cy, h - 1)
        c = idx(cx, cy)
        if region[c] != -1:
            cands = [j for j in range(n) if region[j] == -1]
            if not cands:
                break
            c = rng.choice(cands)
        region[c] = i
        zones.append([c])
    blocked = set()
    while len(blocked) < len(zones):
        for zi, cells in enumerate(zones):
            if zi in blocked:
                continue
            cand = [v for c in cells for v in neigh4(c) if region[v] == -1]
            if not cand:
                blocked.add(zi)
                continue
            v = rng.choice(cand)
            region[v] = zi
            cells.append(v)
    for i in range(n):
        if region[i] == -1:                      # celdas huerfanas
            region[i] = region[min(neigh4(i), key=lambda v: region[v] if region[v] >= 0 else 10 ** 9)]

    zone_neigh = [set() for _ in zones]
    for i in range(n):
        for v in neigh4(i):
            if region[v] != region[i]:
                zone_neigh[region[i]].add(region[v])

    # --- towns: una por region, no en el borde, manhattan >= 4, regiones
    #     vecinas no pueden tener las dos town
    n_towns = max(4, n // AVERAGE_TILES_PER_TOWN)
    towns = []
    blacklist = set()
    order = list(range(len(zones)))
    rng.shuffle(order)
    for zi in order:
        if len(towns) >= n_towns or zi in blacklist:
            continue
        cells = zones[zi][:]
        rng.shuffle(cells)
        for c in cells:
            x, y = c % w, c // w
            if terrain[c] != PLAINS or x in (0, w - 1) or y in (0, h - 1):
                continue
            if any(abs(x - tx) + abs(y - ty) < MIN_TOWN_DISTANCE for tx, ty in towns):
                continue
            towns.append((x, y))
            blacklist.add(zi)
            blacklist |= zone_neigh[zi]
            break
    if len(towns) < 4:
        raise ValueError("mapa degenerado")

    # --- conexiones deseadas (recursivamente no reciprocas)
    nt = len(towns)
    desired = []
    for i in range(nt):
        others = [j for j in range(nt) if j != i]
        rng.shuffle(others)
        at_least = min(3, len(others))
        at_most = max(at_least, len(others) - 4)
        k = rng.randint(at_least, at_most)
        desired.append(sorted(others[:k]))
    for i in range(nt):
        desired[i] = [j for j in desired[i] if i not in desired[j]]

    return Map(w, h, terrain, region, towns, desired)


# ---------------------------------------------------------------- engine

class Game:
    def __init__(self, gmap, league=3):
        self.m = gmap
        self.league = league
        self.turn = 0
        self.track = [TRACK_NONE] * gmap.n
        self.instability = [0] * gmap.n_regions
        self.inked = [False] * gmap.n_regions
        self.score = [0, 0]
        self.active = [[] for _ in range(gmap.n)]     # tags "a-b" por celda
        self.blots_this_turn = {}
        self.objective_done = False
        self.errors = [[], []]
        self.paint_spent = [0, 0]

    # -- consultas -----------------------------------------------------

    def passable(self, i):
        return self.track[i] != TRACK_NONE or self.m.town_at[i] != -1

    def rail_cost(self, i):
        return COST[self.m.terrain[i]]

    # -- E/S al bot ----------------------------------------------------

    def init_lines(self, pid):
        m = self.m
        out = [str(pid), str(m.w), str(m.h)]
        for i in range(m.n):
            out.append("%d %d" % (m.region[i], m.terrain[i]))
        out.append(str(len(m.towns)))
        for tid, (x, y) in enumerate(m.towns):
            d = ",".join(str(v) for v in m.desired[tid]) if m.desired[tid] else "x"
            out.append("%d %d %d %s" % (tid, x, y, d))
        return out

    def turn_lines(self, pid):
        m = self.m
        out = [str(self.score[pid]), str(self.score[1 - pid])]
        for i in range(m.n):
            r = m.region[i]
            tags = ",".join(sorted(self.active[i])) if self.active[i] else "x"
            out.append("%d %d %d %s" % (self.track[i], self.instability[r],
                                        1 if self.inked[r] else 0, tags))
        return out

    # -- parseo de acciones --------------------------------------------

    def parse(self, pid, line):
        """Devuelve lista de intents. Lanza ValueError si el comando es invalido
        (equivale a descalificacion en el referee)."""
        intents = []
        autoplace_used = False
        for raw in line.strip().split(";"):
            cmd = raw.strip()
            if not cmd:
                continue
            up = cmd.upper()
            parts = cmd.split()
            if up.startswith("AUTOPLACE"):
                if len(parts) < 5:
                    raise ValueError("AUTOPLACE x1 y1 x2 y2")
                fx, fy, tx, ty = (int(v) for v in parts[1:5])
                if autoplace_used:
                    self.errors[pid].append("solo un AUTOPLACE por turno")
                    continue
                autoplace_used = True
                intents.extend(self._resolve_autoplace(fx, fy, tx, ty))
            elif up.startswith("PLACE_TRACKS"):
                if len(parts) < 3:
                    raise ValueError("PLACE_TRACKS x y")
                intents.append(("place", int(parts[1]), int(parts[2]), False))
            elif up.startswith("DISRUPT"):
                if len(parts) == 2:
                    intents.append(("disrupt", int(parts[1])))
                elif len(parts) >= 3:
                    x, y = int(parts[1]), int(parts[2])
                    intents.append(("disrupt", self.m.region[y * self.m.w + x]))
                else:
                    raise ValueError("DISRUPT zoneId")
            elif up.startswith("MESSAGE") or up.startswith("WAIT"):
                continue
            else:
                raise ValueError("comando desconocido: %r" % cmd)
        return intents

    def _resolve_autoplace(self, fx, fy, tx, ty):
        """Dijkstra sobre coste de paint; reutiliza tracks existentes a coste 0.
        Termina al alcanzar el bloque de rail que contiene el destino."""
        m = self.m
        src, dst = fy * m.w + fx, ty * m.w + tx
        if not (0 <= src < m.n and 0 <= dst < m.n):
            return []
        goals = {dst}
        if self.passable(dst):
            dq, seen = deque([dst]), {dst}
            while dq:
                u = dq.popleft()
                for v in m.nb[u]:
                    if v not in seen and self.passable(v):
                        seen.add(v)
                        dq.append(v)
            goals = seen
        dist = [float("inf")] * m.n
        par = [-1] * m.n
        start_cost = 0 if self.passable(src) else self.rail_cost(src)
        if self.inked[m.region[src]]:
            return []
        dist[src] = start_cost
        pq = [(start_cost, src)]
        end = -1
        while pq:
            d, u = heappop(pq)
            if d > dist[u]:
                continue
            if u in goals:
                end = u
                break
            for v in m.nb[u]:
                if self.inked[m.region[v]]:
                    continue
                w = 0 if self.passable(v) else self.rail_cost(v)
                if d + w < dist[v]:
                    dist[v] = d + w
                    par[v] = u
                    heappush(pq, (d + w, v))
        if end == -1:
            return []
        path = []
        u = end
        while u != -1:
            path.append(u)
            u = par[u]
        path.reverse()
        return [("place", c % m.w, c // m.w, True)
                for c in path if not self.passable(c)]

    # -- turno ---------------------------------------------------------

    def step(self, intents_by_player):
        m = self.m
        self.turn += 1
        self.blots_this_turn = {}
        dosh = [PAINT_PER_TURN, PAINT_PER_TURN]
        blot = [BLOT_POINTS_PER_TURN, BLOT_POINTS_PER_TURN]

        # 1) PLACE_TRACKS de los dos jugadores (orden: jugador 0, luego 1)
        requested = {}
        order = []
        for pid in (0, 1):
            interrupted = False
            for act in intents_by_player[pid]:
                if act[0] != "place":
                    continue
                _, x, y, auto = act
                if interrupted and auto:
                    continue
                if not (0 <= x < m.w and 0 <= y < m.h):
                    self.errors[pid].append("fuera del grid")
                    continue
                i = y * m.w + x
                if m.town_at[i] != -1:
                    self.errors[pid].append("town")
                    continue
                if self.inked[m.region[i]]:
                    self.errors[pid].append("region inked")
                    continue
                if self.track[i] != TRACK_NONE or pid in requested.get(i, ()):
                    self.errors[pid].append("ya hay track")
                    continue
                c = self.rail_cost(i)
                if dosh[pid] < c:
                    if auto:
                        interrupted = True
                    self.errors[pid].append("sin paint")
                    continue
                requested.setdefault(i, []).append(pid)
                if i in order:
                    order.remove(i)
                order.append(i)
                dosh[pid] -= c
                self.paint_spent[pid] += c

        for i in order:
            who = requested[i]
            self.track[i] = who[0] if len(who) == 1 else TRACK_NEUTRAL

        # 2) DISRUPT (siempre despues de construir)
        for pid in (0, 1):
            for act in intents_by_player[pid]:
                if act[0] != "disrupt":
                    continue
                r = act[1]
                if blot[pid] <= 0:
                    self.errors[pid].append("sin disrupcion")
                    continue
                if not (0 <= r < m.n_regions):
                    self.errors[pid].append("region invalida")
                    continue
                if self.inked[r] or m.region_has_town[r]:
                    self.errors[pid].append("region no disruptable")
                    continue
                blot[pid] -= 1
                self.instability[r] += 1
                self.blots_this_turn[pid] = r

        # 3) inking
        for r in range(m.n_regions):
            if self.inked[r] or m.region_has_town[r]:
                continue
            if self.instability[r] < INSTABILITY_THRESHOLD:
                continue
            self.inked[r] = True
            rekt = [0, 0, 0]
            for i in m.region_cells[r]:
                if self.track[i] != TRACK_NONE:
                    rekt[self.track[i]] += 1
                    self.track[i] = TRACK_NONE
            if self.blots_this_turn.get(0) == r and rekt[1] > 0:
                self.objective_done = True

        # 4) conexiones activas + puntuacion
        self._score_connections()
        return self.is_over()

    def _score_connections(self):
        m = self.m
        for i in range(m.n):
            if self.active[i]:
                self.active[i] = []
        for a, dests in enumerate(m.desired):
            ax, ay = m.towns[a]
            src = ay * m.w + ax
            for b in dests:
                bx, by = m.towns[b]
                dst = by * m.w + bx
                path = self._train_bfs(src, dst)
                if not path:
                    continue
                tag = "%d-%d" % (a, b)
                pts = [0, 0]
                for c in path:
                    self.active[c].append(tag)
                    t = self.track[c]
                    if t == 0 or t == 1:
                        pts[t] += 1
                self.score[0] += pts[0]
                self.score[1] += pts[1]

    def _train_bfs(self, src, dst):
        """BFS igual que el referee: vecinos en orden N,E,S,W, visited al encolar."""
        if src == dst:
            return [src]
        m = self.m
        prev = {src: -1}
        dq = deque([src])
        while dq:
            u = dq.popleft()
            if u == dst:
                path = []
                while u != -1:
                    path.append(u)
                    u = prev[u]
                path.reverse()
                return path
            for v in m.nb[u]:
                if v not in prev and self.passable(v):
                    prev[v] = u
                    dq.append(v)
        return []

    def is_over(self):
        if self.league == 1:
            return self.score[0] >= 1 or self.turn >= MAX_TURNS
        if self.league == 2:
            return self.objective_done or self.turn >= MAX_TURNS
        return self.turn >= MAX_TURNS or not self._any_connection_possible()

    def _any_connection_possible(self):
        """A* sobre terreno ignorando tracks: solo falla si el inking parte el mapa."""
        m = self.m
        for a, dests in enumerate(m.desired):
            if not dests:
                continue
            ax, ay = m.towns[a]
            src = ay * m.w + ax
            seen = {src}
            dq = deque([src])
            reach = set()
            while dq:
                u = dq.popleft()
                if m.town_at[u] != -1:
                    reach.add(m.town_at[u])
                for v in m.nb[u]:
                    if v in seen or self.inked[m.region[v]]:
                        continue
                    seen.add(v)
                    dq.append(v)
            if any(b in reach for b in dests):
                return True
        return False

    def winner(self):
        """0 / 1 / None (empate)."""
        if self.league == 1:
            return 0 if self.score[0] >= 1 else 1
        if self.league == 2:
            return 0 if self.objective_done else 1
        if self.score[0] == self.score[1]:
            return None
        return 0 if self.score[0] > self.score[1] else 1
