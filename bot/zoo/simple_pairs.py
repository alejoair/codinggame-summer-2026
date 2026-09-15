"""
BASELINE 1 - "pares, del mas barato al mas caro"

Sin arbol de Steiner, sin componentes, sin fases. Cada turno:
  1. calcula el camino mas barato de cada par deseado aun no conectado,
  2. los ordena por coste,
  3. gasta los 3 paint en el mas barato, y si sobra, en el siguiente.

Es aproximadamente lo que hace el bot publico de Epigene, que esta en el tercio
bajo de Silver. Sirve como suelo: si nuestro bot no le saca una diferencia
clara, toda la maquinaria de Steiner no esta pagando.

Sin disrupcion a proposito, para aislar la parte constructiva.
"""

import sys
from heapq import heappush, heappop

COST = (1, 2, 3, 3)


def main(read=input, write=print):
    my_id = int(read())
    w = int(read())
    h = int(read())
    n = w * h
    region = [0] * n
    terrain = [0] * n
    for i in range(n):
        a, b = read().split()
        region[i] = int(a)
        terrain[i] = int(b)
    cost = [COST[t] for t in terrain]

    nb = [[] for _ in range(n)]
    for y in range(h):
        for x in range(w):
            i = y * w + x
            if y > 0:
                nb[i].append(i - w)
            if x < w - 1:
                nb[i].append(i + 1)
            if y < h - 1:
                nb[i].append(i + w)
            if x > 0:
                nb[i].append(i - 1)

    tc = int(read())
    town_at = [-1] * n
    towns = {}
    pairs = []
    for _ in range(tc):
        p = read().split()
        tid, tx, ty = int(p[0]), int(p[1]), int(p[2])
        idx = ty * w + tx
        towns[tid] = idx
        town_at[idx] = tid
        if p[3] != "x":
            for o in p[3].split(","):
                pairs.append((tid, int(o)))

    track = [-1] * n
    inked = [False] * (max(region) + 1)

    def passable(i):
        return track[i] != -1 or town_at[i] != -1

    def buildable(i):
        return track[i] == -1 and town_at[i] == -1 and not inked[region[i]]

    def cheapest(src, dst):
        """Dijkstra sobre paint. Devuelve (coste, celdas_a_construir)."""
        dist = [float("inf")] * n
        par = [-1] * n
        done = [False] * n
        dist[src] = 0
        pq = [(0, src)]
        while pq:
            d, u = heappop(pq)
            if done[u]:
                continue
            done[u] = True
            if u == dst:
                break
            for v in nb[u]:
                if inked[region[v]]:
                    continue
                c = 0 if passable(v) else cost[v]
                if not done[v] and d + c < dist[v]:
                    dist[v] = d + c
                    par[v] = u
                    heappush(pq, (d + c, v))
        if dist[dst] == float("inf"):
            return None, []
        path = []
        u = dst
        while u != -1:
            path.append(u)
            u = par[u]
        return dist[dst], [i for i in reversed(path) if buildable(i)]

    while True:
        try:
            read()      # my_score
            read()      # foe_score
        except (EOFError, ValueError):
            break
        for i in range(n):
            parts = read().split()
            track[i] = int(parts[0])
            inked[region[i]] = parts[2] == "1"

        jobs = []
        for a, b in pairs:
            d, cells = cheapest(towns[a], towns[b])
            if d is not None and cells:
                jobs.append((d, cells))
        jobs.sort(key=lambda j: j[0])

        paint = 3
        actions = []
        used = set()
        for _, cells in jobs:
            for i in cells:
                if paint <= 0:
                    break
                if i in used or not buildable(i):
                    continue
                if cost[i] <= paint:
                    actions.append("PLACE_TRACKS %d %d" % (i % w, i // w))
                    used.add(i)
                    paint -= cost[i]
            if paint <= 0:
                break
        write(";".join(actions) if actions else "WAIT")


if __name__ == "__main__":
    main()
