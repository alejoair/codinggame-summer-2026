"""
Back Track King  -  CodinGame Summer Challenge 2026
Agente. Archivo unico: se copia/pega tal cual en el IDE de CodinGame.

Arquitectura (por capas, de abajo a arriba):

    Board      -> mapa estatico (terreno, regiones, towns, pares deseados)
    State      -> estado dinamico del turno (tracks, instability, inked, conexiones activas)
    Rules      -> port fiel del referee (costes, BFS de tren, dijkstra de construccion)
    Strategy   -> QUE construir       (ConnectFirstStrategy, NetworkStrategy, ...)
    DisruptPolicy -> QUE sabotear     (NoDisrupt, ValueDisrupt, ...)
    Agent      -> compone strategy + policy, reparte el presupuesto y emite acciones

Para ligas superiores se anade una Strategy/Policy nueva y se registra en build_agent().
Nada mas de este archivo deberia cambiar.
"""

import sys
from heapq import heappush, heappop
from collections import deque

# --------------------------------------------------------------------------
# CONFIG
# --------------------------------------------------------------------------

# "auto" = un solo bot para todas las ligas. La politica de disrupcion se
# auto-desactiva mientras no exista ningun track enemigo en el mapa, asi que en
# Wood 2 (el boss hace WAIT) nunca se dispara. Alternativas: 1 / 2 / 3.
LEAGUE = "auto"

DEBUG = True

# Construir el plan empezando por el extremo LEJANO: la celda pegada al town aun
# desconectado, no la pegada a nuestra red. Las celdas del extremo lejano son las
# disputadas; las de nuestro lado no nos las va a quitar nadie.
# Medido: 63,0% de victorias sobre 1000 partidas, IC95 [60,0%, 66,0%].
REVERSE_PLAN = True

# Probado y DESCARTADO: un desempate aleatorio por jugador parecia inofensivo
# (solo separa rutas de coste identico) pero midio 35,8% de victorias sobre 600
# partidas, IC95 [31,9%, 39,7%]. Se deja a 0 como recordatorio de que no ayuda.
TIE_JITTER = 0.0

import os as _os
# (A) rehuir regiones que el rival esta inkeando: construir en una con
#     instability 3 es tirar el paint, se borra al turno siguiente.
RISK_WEIGHT = float(_os.environ.get("BTK_RISK", "0"))
# (B) robar tambien pares donde puntuan celdas neutrales (no dan puntos a nadie)
STEAL_NEUTRAL = _os.environ.get("BTK_STEALN", "0") == "1"
# (C) si la componente principal no puede crecer (inking la ha aislado), hacer
#     crecer otra en vez de quedarse parado. Es la causa de los 18 turnos ociosos.
EXPAND_FALLBACK = _os.environ.get("BTK_FALLBACK", "0") == "1"
# (D) H3/Braess: una celda con 2+ vecinos transitables crea un atajo que acorta
#     caminos activos propios y nos quita puntos.
ADJ_PENALTY = float(_os.environ.get("BTK_ADJ", "0"))

PAINT_PER_TURN = 3
DISRUPT_PER_TURN = 1
INSTABILITY_THRESHOLD = 4
MAX_TURNS = 100

PLAINS, RIVER, MOUNTAIN, POI = 0, 1, 2, 3
COST = (1, 2, 3, 3)

TRACK_NONE, TRACK_NEUTRAL = -1, 2
INF = float("inf")


def log(*a):
    if DEBUG:
        print(*a, file=sys.stderr, flush=True)


# --------------------------------------------------------------------------
# Board  -  mapa estatico
# --------------------------------------------------------------------------

class Town:
    __slots__ = ("id", "x", "y", "idx", "desired")

    def __init__(self, tid, x, y, idx, desired):
        self.id = tid
        self.x = x
        self.y = y
        self.idx = idx
        self.desired = desired          # list[townId]


class Board:
    """Todo lo que no cambia en toda la partida."""

    def __init__(self, my_id, w, h, region, terrain, towns):
        self.my_id = my_id
        self.foe_id = 1 - my_id
        self.w = w
        self.h = h
        self.n = w * h
        self.region = region            # list[int]  region por celda
        self.terrain = terrain          # list[int]  tipo por celda
        self.towns = towns              # list[Town]
        self.n_regions = max(region) + 1

        # celda -> townId  (-1 si no hay town)
        self.town_at = [-1] * self.n
        for t in towns:
            self.town_at[t.idx] = t.id

        # vecinos ortogonales precalculados (orden N,E,S,W como el referee)
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

        # pares deseados (a, b) con b en a.desired
        self.pairs = []
        for t in towns:
            for other in t.desired:
                self.pairs.append((t.id, other))

        # pares en los que participa cada town
        self.pairs_of_town = [[] for _ in towns]
        for pi, (a, b) in enumerate(self.pairs):
            self.pairs_of_town[a].append(pi)
            self.pairs_of_town[b].append(pi)

        # celdas de cada region
        self.region_cells = [[] for _ in range(self.n_regions)]
        for i in range(self.n):
            self.region_cells[self.region[i]].append(i)

        # una region con town no se puede disruptar nunca
        self.region_has_town = [False] * self.n_regions
        for t in towns:
            self.region_has_town[self.region[t.idx]] = True

        self.cost = [COST[terrain[i]] for i in range(self.n)]

    def xy(self, i):
        return i % self.w, i // self.w

    def manhattan(self, i, j):
        return abs(i % self.w - j % self.w) + abs(i // self.w - j // self.w)


# --------------------------------------------------------------------------
# State  -  estado dinamico
# --------------------------------------------------------------------------

class State:
    """Lo que cambia cada turno. Se reconstruye entero en cada parse()."""

    __slots__ = ("board", "turn", "my_score", "foe_score",
                 "track", "instability", "inked", "act_count", "act_raw")

    def __init__(self, board):
        self.board = board
        self.turn = 0
        self.my_score = 0
        self.foe_score = 0
        self.track = [TRACK_NONE] * board.n
        self.instability = [0] * board.n_regions
        self.inked = [False] * board.n_regions
        self.act_count = [0] * board.n          # nº de conexiones activas que usan la celda
        self.act_raw = ["x"] * board.n

    # --- consultas basicas ------------------------------------------------

    def turns_left(self):
        return MAX_TURNS - self.turn

    def is_town(self, i):
        return self.board.town_at[i] != -1

    def passable(self, i):
        """Por aqui pasa un tren: hay track (de quien sea) o es un town."""
        return self.track[i] != TRACK_NONE or self.board.town_at[i] != -1

    def buildable(self, i):
        """Celda libre en la que se puede poner un track."""
        return (self.track[i] == TRACK_NONE
                and self.board.town_at[i] == -1
                and not self.inked[self.board.region[i]])

    def mine(self, i):
        return self.track[i] == self.board.my_id

    def foes(self, i):
        return self.track[i] == self.board.foe_id

    def any_foe_track(self):
        fid = self.board.foe_id
        return any(t == fid for t in self.track)

    # --- parsing ----------------------------------------------------------

    def parse_turn(self, read):
        b = self.board
        self.turn += 1
        self.my_score = int(read())
        self.foe_score = int(read())
        for i in range(b.n):
            parts = read().split()
            self.track[i] = int(parts[0])
            r = b.region[i]
            self.instability[r] = int(parts[1])
            self.inked[r] = parts[2] == "1"
            raw = parts[3]
            self.act_raw[i] = raw
            self.act_count[i] = 0 if raw == "x" else raw.count(",") + 1


# --------------------------------------------------------------------------
# Rules  -  port fiel del referee
# --------------------------------------------------------------------------

class Rules:
    """Funciones puras que replican el referee. No deciden nada."""

    @staticmethod
    def components(st):
        """
        Componentes conexas del grafo de tracks+towns (adyacencia ortogonal).
        Devuelve comp[] por celda (-1 si la celda no es transitable).
        Es exactamente la relacion que usa el referee para decidir si dos towns
        estan conectados.
        """
        b = st.board
        comp = [-1] * b.n
        c = 0
        for s in range(b.n):
            if comp[s] != -1 or not st.passable(s):
                continue
            dq = deque([s])
            comp[s] = c
            while dq:
                u = dq.popleft()
                for v in b.nb[u]:
                    if comp[v] == -1 and st.passable(v):
                        comp[v] = c
                        dq.append(v)
            c += 1
        return comp, c

    @staticmethod
    def train_bfs(st, src, dst):
        """
        Camino activo tal y como lo elige el referee (TrainBFS): BFS sobre celdas
        transitables, expandiendo vecinos en orden N,E,S,W. Devuelve [] si no hay.
        Solo se usa para evaluar hipoteticos: el estado real ya viene en act_raw.
        """
        b = st.board
        if src == dst:
            return [src]
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
            for v in b.nb[u]:
                if v not in prev and st.passable(v):
                    prev[v] = u
                    dq.append(v)
        return []

    @staticmethod
    def build_dijkstra(st, sources, blocked_owner=None):
        """
        Dijkstra sobre coste de PAINT, igual que AUTOPLACE (AutobuildAStar):
        entrar en una celda transitable cuesta 0 (se reaprovecha el track que ya
        existe, sea de quien sea); entrar en una celda libre cuesta su terreno.
        Las regiones inked son intransitables.

        blocked_owner: si se pasa un playerId, sus tracks se tratan como muro
                       (sirve para buscar rutas que no regalen puntos al rival).

        Devuelve (dist, parent).
        """
        b = st.board
        dist = [INF] * b.n
        par = [-1] * b.n
        pq = []
        for s in sources:
            if dist[s] != 0:
                dist[s] = 0
                heappush(pq, (0, s))
        done = [False] * b.n
        while pq:
            d, u = heappop(pq)
            if done[u]:
                continue
            done[u] = True          # nodo cerrado: no se vuelve a relajar nunca
            for v in b.nb[u]:
                if st.inked[b.region[v]]:
                    continue
                if blocked_owner is not None and st.track[v] == blocked_owner:
                    continue
                if st.passable(v):
                    w = 0
                else:
                    w = b.cost[v] + RISK_WEIGHT * st.instability[b.region[v]]
                    if ADJ_PENALTY:
                        adj = 0
                        for nv in b.nb[v]:      # OJO: no reutilizar 'u' aqui,
                            if st.passable(nv): # pisaria el nodo en expansion y
                                adj += 1        # par[v] quedaria en un ciclo
                        if adj > 1:
                            w += ADJ_PENALTY * (adj - 1)
                nd = d + w
                if not done[v] and nd < dist[v]:
                    dist[v] = nd
                    par[v] = u
                    heappush(pq, (nd, v))
        return dist, par

    @staticmethod
    def rebuild_path(par, target):
        path = []
        u = target
        while u != -1:
            path.append(u)
            u = par[u]
        path.reverse()
        return path


# --------------------------------------------------------------------------
# Strategies  -  QUE construir
# --------------------------------------------------------------------------

class Strategy:
    """Devuelve una lista ORDENADA de celdas que le gustaria construir."""
    name = "base"

    def plan(self, st):
        raise NotImplementedError


class ConnectFirstStrategy(Strategy):
    """
    Liga Wood 2: basta con formar UNA conexion activa y puntuar.
    Elegimos el par deseado mas barato de unir y lo construimos.
    """
    name = "connect-first"

    def plan(self, st):
        b = st.board
        comp, _ = Rules.components(st)

        best = None
        for (a, bb) in b.pairs:
            ta, tb = b.towns[a], b.towns[bb]
            if comp[ta.idx] != -1 and comp[ta.idx] == comp[tb.idx]:
                return []                      # ya hay conexion: objetivo cumplido
            dist, par = Rules.build_dijkstra(st, [ta.idx])
            d = dist[tb.idx]
            if d < INF and (best is None or d < best[0]):
                best = (d, Rules.rebuild_path(par, tb.idx))
        if best is None:
            return []
        return [i for i in best[1] if st.buildable(i)]


class NetworkStrategy(Strategy):
    """
    Liga Bronze+ : maximizar puntos.

    Los puntos se cobran CADA TURNO por cada track propio que este en el camino
    mas corto de una conexion activa. Luego el objetivo real es:
    conectar toda la red lo antes posible y poseer el maximo de celdas de esos
    caminos.

    Heuristica: arbol de Steiner a la Takahashi-Matsuyama, pero eligiendo el
    siguiente town a enganchar por  valor / coste  en vez de solo por coste.
      - valor = suma de distancias manhattan de los pares deseados que se
                activarian al engancharlo (aproxima los tracks propios que
                acabarian puntuando).
      - coste = paint necesario (dijkstra multi-fuente desde la componente).

    Fase 2 (todo conectado): robar caminos. Si en una conexion activa el rival
    posee celdas, buscamos una ruta alternativa ESTRICTAMENTE mas corta que no
    pase por sus tracks; al ser mas corta pasa a ser la activa y se lleva todos
    los puntos de ese par.
    """
    name = "network"

    def __init__(self):
        self.phase = "expand"

    def plan(self, st):
        b = st.board
        comp, _ = Rules.components(st)

        # towns de cada componente
        towns_in_comp = {}
        for t in b.towns:
            c = comp[t.idx]
            towns_in_comp.setdefault(c, []).append(t.id)

        # componente principal = la que mas towns tiene (desempate: mas tracks mios)
        def comp_weight(c):
            mine = sum(1 for i in range(b.n) if comp[i] == c and st.mine(i))
            return (len(towns_in_comp[c]), mine)

        main = max(towns_in_comp, key=comp_weight)
        main_towns = set(towns_in_comp[main])

        unconnected = [t for t in b.towns if comp[t.idx] != main]
        if unconnected:
            self.phase = "expand"
            plan = self._expand(st, comp, main, main_towns, unconnected)
            if plan:
                return plan
            if EXPAND_FALLBACK:
                for c in sorted(towns_in_comp, key=lambda k: -len(towns_in_comp[k])):
                    if c == main:
                        continue
                    rest = [t for t in b.towns if comp[t.idx] != c]
                    if not rest:
                        continue
                    plan = self._expand(st, comp, c, set(towns_in_comp[c]), rest)
                    if plan:
                        self.phase = "expand2"
                        return plan

        self.phase = "steal"
        return self._steal(st)

    # -- fase 1: enganchar el siguiente town ------------------------------

    def _expand(self, st, comp, main, main_towns, unconnected):
        b = st.board
        sources = [i for i in range(b.n) if comp[i] == main]
        if not sources:
            sources = [b.towns[0].idx]
        dist, par = Rules.build_dijkstra(st, sources)

        best, best_ratio = None, -1.0
        for t in unconnected:
            d = dist[t.idx]
            if d == INF:
                continue
            value = 0
            for pi in b.pairs_of_town[t.id]:
                a, bb = b.pairs[pi]
                other = bb if a == t.id else a
                if other in main_towns:
                    value += b.manhattan(b.towns[a].idx, b.towns[bb].idx)
            # aunque no active nada ahora, engancharlo abre la red para despues
            value += 1
            ratio = value / max(d, 1)
            if ratio > best_ratio:
                best_ratio, best = ratio, t

        if best is None:
            return []
        path = Rules.rebuild_path(par, best.idx)
        return [i for i in path if st.buildable(i)]

    # -- fase 2: robar caminos al rival -----------------------------------

    def _steal(self, st):
        b = st.board
        foe = b.foe_id

        # cuanto gana el rival en cada par activo
        gains = {}
        for i in range(b.n):
            if st.act_count[i] == 0:
                continue
            _t = st.track[i]
            if not (_t == foe or (STEAL_NEUTRAL and _t == TRACK_NEUTRAL)):
                continue
            for tag in st.act_raw[i].split(","):
                gains[tag] = gains.get(tag, 0) + 1
        if not gains:
            return []

        for tag, _ in sorted(gains.items(), key=lambda kv: -kv[1])[:3]:
            try:
                a, bb = (int(v) for v in tag.split("-"))
            except ValueError:
                continue
            ta, tb = b.towns[a], b.towns[bb]
            cur = Rules.train_bfs(st, ta.idx, tb.idx)
            if not cur:
                continue
            alt = self._shortest_without_foe(st, ta.idx, tb.idx)
            if alt and len(alt) < len(cur):
                cells = [i for i in alt if st.buildable(i)]
                if cells:
                    return cells
        return []

    def _shortest_without_foe(self, st, src, dst):
        """BFS por longitud usando solo celdas propias / towns / libres."""
        b = st.board
        foe = b.foe_id
        prev = {src: -1}
        dq = deque([src])
        while dq:
            u = dq.popleft()
            if u == dst:
                return Rules.rebuild_path_dict(prev, u)
            for v in b.nb[u]:
                if v in prev:
                    continue
                if st.inked[b.region[v]]:
                    continue
                if st.track[v] == foe or st.track[v] == TRACK_NEUTRAL:
                    continue
                prev[v] = u
                dq.append(v)
        return []


def _rebuild_path_dict(prev, target):
    path = []
    u = target
    while u != -1:
        path.append(u)
        u = prev[u]
    path.reverse()
    return path


Rules.rebuild_path_dict = staticmethod(_rebuild_path_dict)


# --------------------------------------------------------------------------
# DisruptPolicy  -  QUE sabotear
# --------------------------------------------------------------------------

class DisruptPolicy:
    name = "base"

    def choose(self, st):
        return None


class NoDisrupt(DisruptPolicy):
    name = "none"


class ValueDisrupt(DisruptPolicy):
    """
    1 punto de disrupcion por turno, hacen falta 4 en la MISMA region.
    Por eso la politica es pegajosa: se fija un objetivo y se machaca hasta
    inkearlo.

    Seleccion: region sin town, no inked, con tracks del rival, maximizando
      2*(puntos/turno que pierde el rival) - (puntos/turno que pierdo yo)
    Si no hay ninguna con tracks enemigos no se hace nada  -> en Wood 2 (el boss
    hace WAIT) esta politica nunca se activa, que es justo lo que queremos.
    """
    name = "value"

    def __init__(self):
        self.target = None

    def choose(self, st):
        b = st.board
        if not st.any_foe_track():
            self.target = None
            return None

        # no da tiempo a completar un inkeo nuevo al final de la partida
        if st.turns_left() < INSTABILITY_THRESHOLD:
            if self.target is None:
                return None

        if self.target is not None and self._still_good(st, self.target):
            return self.target

        best, best_score = None, 0.0
        for r in range(b.n_regions):
            if b.region_has_town[r] or st.inked[r]:
                continue
            foe_v = my_v = foe_tracks = 0
            for i in b.region_cells[r]:
                if st.foes(i):
                    foe_tracks += 1
                    foe_v += 1 + st.act_count[i]
                elif st.mine(i):
                    my_v += 1 + st.act_count[i]
            if foe_tracks == 0:
                continue
            # lo ya invertido por cualquiera acerca el inkeo: cuenta a favor
            score = 2.0 * foe_v - my_v + 0.5 * st.instability[r]
            if score > best_score:
                best_score, best = score, r

        self.target = best
        return best

    def _still_good(self, st, r):
        if st.inked[r] or st.board.region_has_town[r]:
            return False
        return any(st.foes(i) for i in st.board.region_cells[r])


# --------------------------------------------------------------------------
# Agent  -  compone y emite
# --------------------------------------------------------------------------

class Agent:
    def __init__(self, strategy, disrupt_policy):
        self.strategy = strategy
        self.disrupt = disrupt_policy
        self.wasted = 0          # paint que no hemos sabido gastar en toda la partida
        self.spent = 0
        self.last_phase = None
        self.was_idle = False

    def act(self, st):
        actions = []

        # --- construccion -------------------------------------------------
        paint = PAINT_PER_TURN
        cells = self.strategy.plan(st)
        if REVERSE_PLAN:
            cells = cells[::-1]
        placed = set()
        for i in cells:
            if paint <= 0:
                break
            if i in placed or not st.buildable(i):
                continue
            c = st.board.cost[i]
            if c <= paint:
                x, y = st.board.xy(i)
                actions.append("PLACE_TRACKS %d %d" % (x, y))
                placed.add(i)
                paint -= c

        # --- sabotaje -----------------------------------------------------
        r = self.disrupt.choose(st)
        if r is not None:
            actions.append("DISRUPT %d" % r)

        if not actions:
            actions.append("WAIT")

        # --- diagnostico ---------------------------------------------------
        # Medido en local: la red queda completa sobre el turno 18 y a partir de
        # ahi el bot no sabe en que gastar los 3 paint/turno. Esto comprueba si
        # tambien pasa contra un rival real.
        self.spent += PAINT_PER_TURN - paint
        self.wasted += paint
        phase = getattr(self.strategy, "phase", self.strategy.name)
        if DEBUG:
            # Solo se escribe cuando cambia algo. Un bloque rojo por turno en la
            # consola de CodinGame entierra los mensajes que de verdad importan.
            idle = paint == PAINT_PER_TURN
            if phase != self.last_phase or idle != self.was_idle or st.turn == 1:
                active = 0
                for c in st.act_count:
                    if c:
                        active += 1
                log("t%-3d fase=%s%s  desp_acum=%d/%d  celdas_activas=%d  %d/%d"
                    % (st.turn, phase, "  SIN GASTAR" if idle else "",
                       self.wasted, self.wasted + self.spent,
                       active, st.my_score, st.foe_score))
            self.last_phase, self.was_idle = phase, idle
            actions.append("MESSAGE %s desp %d%%" %
                           (phase, (100 * self.wasted) // max(1, self.wasted + self.spent)))
        return ";".join(actions)


def build_agent(league):
    """Unico sitio donde se decide que estrategia corre cada liga."""
    if league == 1:
        return Agent(ConnectFirstStrategy(), NoDisrupt())
    if league == 2:
        return Agent(NetworkStrategy(), ValueDisrupt())
    # 3 / "auto"
    return Agent(NetworkStrategy(), ValueDisrupt())


# --------------------------------------------------------------------------
# E/S
# --------------------------------------------------------------------------

def read_board(read):
    my_id = int(read())
    w = int(read())
    h = int(read())
    region = [0] * (w * h)
    terrain = [0] * (w * h)
    for i in range(w * h):
        a, b = read().split()
        region[i] = int(a)
        terrain[i] = int(b)
    town_count = int(read())
    towns = []
    for _ in range(town_count):
        p = read().split()
        tid, tx, ty = int(p[0]), int(p[1]), int(p[2])
        desired = [] if p[3] == "x" else [int(v) for v in p[3].split(",")]
        towns.append(Town(tid, tx, ty, ty * w + tx, desired))
    towns.sort(key=lambda t: t.id)
    return Board(my_id, w, h, region, terrain, towns)


def main(read=input, write=print):
    board = read_board(read)
    state = State(board)
    agent = build_agent(LEAGUE)
    log("map %dx%d towns=%d pairs=%d regions=%d"
        % (board.w, board.h, len(board.towns), len(board.pairs), board.n_regions))
    while True:
        try:
            state.parse_turn(read)
        except (EOFError, ValueError):
            break
        write(agent.act(state))


if __name__ == "__main__":
    main()
