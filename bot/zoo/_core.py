"""
Nucleo compartido de los bots del zoo.

El zoo NO son variantes de nuestro agente: son estrategias deliberadamente
distintas, para que el A/B no degenere en espejo (dos bots casi iguales colocan
en las mismas celdas, todo queda neutral y la partida acaba 0-0).

Cada bot del zoo es un fichero propio que llama a run() con su modo. Tienen que
ser ficheros separados porque dos bots del mismo proceso comparten el entorno,
asi que no se pueden diferenciar por variable de entorno.

Modos:
  pairs     conecta pares deseados, del mas barato al mas caro. Sin disrupcion.
  hugger    igual, pero prefiere fuertemente las regiones CON town, que son
            inmunes a DISRUPT: red a prueba de sabotaje.
  maxcells  igual que pairs, pero nunca desperdicia paint: lo que sobra lo gasta
            extendiendo la red. Pone a prueba la hipotesis de que la recompensa
            es proporcional a celdas propias.
  aggro     construccion minima y disrupcion agresiva y pegajosa sobre la region
            con mas tracks del rival.
"""

from heapq import heappush, heappop

COST = (1, 2, 3, 3)
INF = float("inf")


def run(read, write, mode="pairs"):
    my_id = int(read())
    foe_id = 1 - my_id
    w = int(read())
    h = int(read())
    n = w * h

    region = [0] * n
    terrain = [0] * n
    for i in range(n):
        a, b = read().split()
        region[i] = int(a)
        terrain[i] = int(b)
    n_regions = max(region) + 1
    base = [COST[t] for t in terrain]

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

    region_has_town = [False] * n_regions
    for idx in towns.values():
        region_has_town[region[idx]] = True

    # coste de busqueda: en modo hugger las regiones con town salen mucho mas
    # baratas, asi que la ruta se pega a lo que el rival no puede borrar.
    if mode == "hugger":
        search = [base[i] * 3 - (2 if region_has_town[region[i]] else 0)
                  for i in range(n)]
    else:
        search = [base[i] for i in range(n)]

    track = [-1] * n
    inked = [False] * n_regions
    instab = [0] * n_regions
    disrupt_target = [None]

    def passable(i):
        return track[i] != -1 or town_at[i] != -1

    def buildable(i):
        return track[i] == -1 and town_at[i] == -1 and not inked[region[i]]

    def cheapest(src, dst):
        dist = [INF] * n
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
                c = 0 if passable(v) else search[v]
                if not done[v] and d + c < dist[v]:
                    dist[v] = d + c
                    par[v] = u
                    heappush(pq, (d + c, v))
        if dist[dst] == INF:
            return None, []
        path = []
        u = dst
        while u != -1:
            path.append(u)
            u = par[u]
        path.reverse()
        return dist[dst], [i for i in path if buildable(i)]

    def pick_disrupt():
        prev = disrupt_target[0]
        if prev is not None and not inked[prev] and \
                any(track[i] == foe_id for i in range(n) if region[i] == prev):
            return prev
        best, best_n = None, 0
        for r in range(n_regions):
            if region_has_town[r] or inked[r]:
                continue
            cnt = 0
            for i in range(n):
                if region[i] == r and track[i] == foe_id:
                    cnt += 1
            if cnt > best_n:
                best_n, best = cnt, r
        disrupt_target[0] = best
        return best

    while True:
        try:
            read()
            read()
        except (EOFError, ValueError):
            return
        for i in range(n):
            parts = read().split()
            track[i] = int(parts[0])
            r = region[i]
            instab[r] = int(parts[1])
            inked[r] = parts[2] == "1"

        paint = 1 if mode == "aggro" else 3
        actions = []
        used = set()

        jobs = []
        for a, b in pairs:
            d, cells = cheapest(towns[a], towns[b])
            if d is not None and cells:
                jobs.append((d, cells))
        jobs.sort(key=lambda j: j[0])

        for _, cells in jobs:
            if paint <= 0:
                break
            for i in cells:
                if paint <= 0:
                    break
                if i in used or not buildable(i):
                    continue
                if base[i] <= paint:
                    actions.append("PLACE_TRACKS %d %d" % (i % w, i // w))
                    used.add(i)
                    paint -= base[i]

        if mode == "maxcells" and paint > 0:
            # no desperdiciar nunca: extender la red por donde se pueda
            frontier = []
            for i in range(n):
                if track[i] == my_id or town_at[i] != -1:
                    for v in nb[i]:
                        if buildable(v) and v not in used and base[v] <= paint:
                            frontier.append(v)
            for v in frontier:
                if paint <= 0:
                    break
                if v in used or not buildable(v) or base[v] > paint:
                    continue
                actions.append("PLACE_TRACKS %d %d" % (v % w, v // w))
                used.add(v)
                paint -= base[v]

        if mode == "aggro":
            r = pick_disrupt()
            if r is not None:
                actions.append("DISRUPT %d" % r)

        write(";".join(actions) if actions else "WAIT")
