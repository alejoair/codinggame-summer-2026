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

# Gastar siempre los 3 puntos: si el plan no los consume, extender la red.
FILL_IDLE_PAINT = True

# Dinamica 1: la carrera del camino mas corto. El par entero se lo lleva quien
# tenga el camino MAS CORTO, no hay reparto. Medido en 24 partidas reales: el
# ownership decide (0,43/0,32 ganando, 0,31/0,44 perdiendo) y el score del rival
# es identico gane quien gane. Disputar un camino mueve puntos por partida DOBLE:
# le quitamos los suyos y nos llevamos los nuestros.
CONTEST = True
CONTEST_MIN_GAIN = 3      # puntos/turno minimos de vuelco para que compense
CONTEST_MAX_COST = 12     # pintura maxima, ~4 turnos de presupuesto
CONTEST_PAIRS = 6         # pares candidatos que se examinan por turno

PAINT_PER_TURN = 3
DISRUPT_PER_TURN = 1
INSTABILITY_THRESHOLD = 4
MAX_TURNS = 100

PLAINS, RIVER, MOUNTAIN, POI = 0, 1, 2, 3
COST = (1, 2, 3, 3)
# Coste para ELEGIR ruta. Estuvo en (1,3,5,5) para rodear rio y montana, imitando
# al nº1 de la liga, y era una REGRESION: rodear alarga el camino en CELDAS, y la
# conexion activa es la mas corta en celdas, asi que regalabamos el par al rival
# que cruzaba en linea recta. Medido al aislarlo: +20,6% de score (t=3,29, n=120)
# y 54,2% de victorias cara a cara, IC95 [50,3%, 58,0%] sobre 800 partidas.
# Entro en el mismo paquete que subio el score un 41% y nunca lo ablacione.
TERRAIN_AVOID = (1, 2, 3, 3)

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

        # Coste para ELEGIR ruta (no es lo que se paga). Penaliza rio y montana
        # mas de lo que cuestan: el bot nº1 de la liga construyo 102 celdas en
        # llanura y solo 6 en rio y 2 en montana. Rodear sale mejor que pagar,
        # sobre todo con el tablero desapareciendo por el inking.
        self.route_cost = [TERRAIN_AVOID[terrain[i]] for i in range(self.n)]

        # corridor[r]: cuantas celdas de la region r caen en el trazado directo
        # entre towns que se desean conectar. Aproxima "por donde tendra que
        # pasar el rival", y sirve para sembrar inestabilidad antes de que
        # construya nada.
        self.corridor = [0] * self.n_regions
        for (a, bb) in self.pairs:
            x0, y0 = towns[a].x, towns[a].y
            x1, y1 = towns[bb].x, towns[bb].y
            x, y = x0, y0
            while x != x1:
                x += 1 if x1 > x else -1
                self.corridor[self.region[y * w + x]] += 1
            while y != y1:
                y += 1 if y1 > y else -1
                self.corridor[self.region[y * w + x]] += 1

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
                    w = b.route_cost[v]
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
# Director  -  QUE DINAMICA explotar en cada momento
# --------------------------------------------------------------------------

class Director:
    """
    Lee el estado del mundo y decide que dinamica del juego conviene explotar
    este turno. Las dinamicas estan documentadas en GAME-MODEL.md; aqui solo se
    deciden, no se ejecutan.

    Existe porque ninguna dinamica es buena siempre:
      - disputar caminos (D1) solo renta si el rival nos esta ganando alguno;
      - la disrupcion (D2) es una carrera armamentistica que destruye el tablero
        de los dos, y nos perjudica mas a nosotros cuando poseemos mas (D8);
      - construir (D9) deja de pagar cuando la ventana se cierra (D3), y a
        partir de ahi la pintura es desperdicio forzado (D10).
    """

    # Umbrales. Sacados de lo medido, no elegidos a ojo: las partidas reales
    # duran 44-67 turnos y el pico de conexiones activas esta sobre el 36.
    VENTANA_FIN = 0.75          # fraccion de regiones inkeadas que mata el tablero
    HORIZONTE = 60              # turno a partir del cual construir casi no renta

    def assess(self, st):
        """Rasgos del mundo, todos baratos de calcular."""
        b = st.board
        inked = sum(1 for r in range(b.n_regions) if st.inked[r])
        mias = suyas = activas = 0
        for i in range(b.n):
            c = st.act_count[i]
            if not c:
                continue
            activas += 1
            if st.mine(i):
                mias += c
            elif st.foes(i):
                suyas += c
        return {
            "turno": st.turn,
            "inked": inked / max(1, b.n_regions),
            "celdas_activas": activas,
            "renta_mia": mias,          # puntos/turno que sacamos ahora
            "renta_suya": suyas,        # los que saca el rival
            "voy_ganando": st.my_score >= st.foe_score,
            "tablero_vivo": inked / max(1, b.n_regions) < self.VENTANA_FIN,
        }

    def modo_construccion(self, f):
        """Que hacer con los 3 puntos de pintura."""
        if not f["tablero_vivo"] or f["turno"] > self.HORIZONTE:
            # D3/D10: la ventana se ha cerrado. Construir ya casi no paga, pero
            # la pintura caduca igual, asi que se sigue por si acaso.
            return "resto"
        if f["renta_suya"] > f["renta_mia"]:
            # D1: nos estan ganando las carreras de camino. Disputar rinde doble.
            return "contest"
        return "expand"                 # D9: componer renta cuanto antes

    def agresividad_disrupcion(self, f):
        """
        Cuanto conviene destruir. D2 dice que no se puede dejar de disruptar,
        pero D8 dice que destruir nos perjudica mas cuando poseemos mas: si
        vamos por delante en renta, destruir el tablero es regalar el empate.
        """
        if f["renta_mia"] > 0 and f["renta_mia"] > 1.5 * f["renta_suya"]:
            return 0.5                  # dominamos: preservar el tablero
        if f["renta_suya"] > f["renta_mia"]:
            return 1.5                  # nos gana: negar mas fuerte
        return 1.0


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
        self.modo = "expand"        # lo fija el Director cada turno

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

        # Disputar un camino rinde el doble que construir uno nuevo: le quitamos
        # sus puntos Y nos llevamos los nuestros. Se evalua SIEMPRE, no solo al
        # final: antes vivia en la fase 2 y casi nunca llegaba a ejecutarse.
        if CONTEST and self.modo in ("contest", "resto"):
            cells, gain, cost = self._contest(st)
            if cells and gain >= CONTEST_MIN_GAIN and cost <= CONTEST_MAX_COST:
                self.phase = "contest"
                return cells

        unconnected = [t for t in b.towns if comp[t.idx] != main]
        if unconnected:
            self.phase = "expand"
            plan = self._expand(st, comp, main, main_towns, unconnected)
            if plan:
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

    def _contest(self, st):
        """
        Busca el par activo donde mas gana el rival y mira si podemos trazar una
        ruta ESTRICTAMENTE mas corta hecha solo de celdas nuestras o libres. Al
        ser mas corta pasa a ser la activa y el par cambia de dueno entero.

        Devuelve (celdas_a_construir, vuelco_en_puntos_por_turno, coste).
        """
        b = st.board
        foe = b.foe_id

        # cuanto saca el rival de cada par activo
        gains = {}
        for i in range(b.n):
            if st.act_count[i] == 0 or st.track[i] != foe:
                continue
            for tag in st.act_raw[i].split(","):
                gains[tag] = gains.get(tag, 0) + 1
        if not gains:
            return None, 0, 0

        mejor = (None, 0, 0)
        mejor_ratio = 0.0
        for tag, _ in sorted(gains.items(), key=lambda kv: -kv[1])[:CONTEST_PAIRS]:
            try:
                a, bb = (int(v) for v in tag.split("-"))
            except ValueError:
                continue
            cur = Rules.train_bfs(st, b.towns[a].idx, b.towns[bb].idx)
            if not cur:
                continue
            alt = self._shortest_without_foe(st, b.towns[a].idx, b.towns[bb].idx)
            if not alt or len(alt) >= len(cur):
                continue

            quitado = sum(1 for c in cur if st.track[c] == foe)
            mio_ahora = sum(1 for c in cur if st.mine(c))
            # alt excluye rival y neutrales: toda celda no-town acabara siendo
            # nuestra, sea porque ya lo es o porque la vamos a construir
            mio_luego = sum(1 for c in alt if b.town_at[c] == -1)
            vuelco = quitado + (mio_luego - mio_ahora)

            celdas = [c for c in alt if st.buildable(c)]
            coste = sum(b.cost[c] for c in celdas)
            if not celdas or coste <= 0:
                continue
            ratio = vuelco / coste
            if ratio > mejor_ratio:
                mejor_ratio = ratio
                mejor = (celdas, vuelco, coste)
        return mejor

    # -- fase 2: robar caminos al rival -----------------------------------

    def _steal(self, st):
        b = st.board
        foe = b.foe_id

        # cuanto gana el rival en cada par activo
        gains = {}
        for i in range(b.n):
            if st.track[i] != foe or st.act_count[i] == 0:
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


class PreemptiveDisrupt(DisruptPolicy):
    gain = 1.0

    """
    Politica copiada del comportamiento observado en el bot nº1 de la liga
    (Saelyos), leyendo su stdout real de una partida del arena.

    Hace dos cosas que la version anterior NO hacia, y ambas resultaron caras:

    1. Disrupta DESDE EL TURNO 1, haya o no tracks enemigos. La inestabilidad se
       acumula para siempre, asi que un punto puesto pronto madura justo a tiempo
       de borrar lo que el rival construya despues. Esperar a ver sus tracks es
       llegar tarde y tirar los primeros puntos, que son los mas valiosos.
    2. REPARTE entre varias regiones en vez de machacar una. Deja varias
       "cebadas" en inestabilidad 3 y remata la que de verdad interese, que puede
       decidirse un turno antes de inkear.

    Objetivo temprano: los corredores por donde tendran que pasar las conexiones,
    evitando aquellos donde estamos construyendo nosotros.
    Objetivo tardio: donde el rival puntua mas y nosotros menos.
    """
    name = "preemptive"

    def choose(self, st):
        b = st.board
        # Sin tiempo material para completar un inkeo nuevo: solo rematar los ya
        # cebados, si queda alguno a 3.
        last_chance = st.turns_left() < INSTABILITY_THRESHOLD

        # D8: si dominamos en renta, destruir el tablero nos cuesta mas que al
        # rival. No se deja de disruptar (D2 lo prohibe), se hace mas exigente.
        exigencia = 0.0 if self.gain >= 1.0 else 3.0

        best, best_score = None, -1e9
        for r in range(b.n_regions):
            if b.region_has_town[r] or st.inked[r]:
                continue
            inst = st.instability[r]
            if inst >= INSTABILITY_THRESHOLD:
                continue

            foe_v = my_v = 0
            for i in b.region_cells[r]:
                if st.foes(i):
                    foe_v += 1 + st.act_count[i]
                elif st.mine(i):
                    my_v += 1 + st.act_count[i]

            if last_chance and inst < INSTABILITY_THRESHOLD - 1:
                continue            # ya no llegaria a 4

            # Valor de rematar ahora vs seguir cebando. El corredor solo cuenta
            # mientras no haya informacion mejor (tracks reales sobre el terreno).
            score = 2.0 * foe_v - 1.5 * my_v + 0.15 * b.corridor[r]
            if inst == INSTABILITY_THRESHOLD - 1:
                # a un punto de inkear: solo rematar si compensa de verdad
                if foe_v <= my_v:
                    score -= 50.0
                else:
                    score += 10.0
            score += 0.4 * inst     # aprovechar lo ya invertido por cualquiera

            if score * self.gain > best_score and score > exigencia:
                best_score, best = score * self.gain, r

        return best


# --------------------------------------------------------------------------
# Agent  -  compone y emite
# --------------------------------------------------------------------------

class Agent:
    def __init__(self, strategy, disrupt_policy):
        self.strategy = strategy
        self.disrupt = disrupt_policy
        self.director = Director()
        self.wasted = 0          # paint que no hemos sabido gastar en toda la partida
        self.spent = 0
        self.last_phase = None
        self.was_idle = False

    def _frontier(self, st, placed):
        """
        Celdas libres pegadas a nuestra red, ordenadas por lo prometedoras que
        son: primero las baratas y las que estan en corredores muy transitados,
        y se descartan las regiones que ya estan a punto de inkearse.
        """
        b = st.board
        seen = set()
        out = []
        for i in range(b.n):
            if st.track[i] != b.my_id and b.town_at[i] == -1:
                continue
            for v in b.nb[i]:
                if v in seen or v in placed or not st.buildable(v):
                    continue
                seen.add(v)
                r = b.region[v]
                # Una region a punto de inkearse es mal sitio, pero NO es motivo
                # para no gastar: la pintura caduca al acabar el turno, asi que
                # una celda que quiza se borre siempre vale mas que un punto
                # tirado. Se penaliza para dejarla la ultima, no se descarta.
                risk = 12.0 if st.instability[r] >= INSTABILITY_THRESHOLD - 1 else 0.0
                out.append((b.route_cost[v] + risk - 0.05 * b.corridor[r], v))
        out.sort()
        return [v for _, v in out]

    def act(self, st):
        actions = []

        # --- construccion -------------------------------------------------
        f = self.director.assess(st)
        if hasattr(self.strategy, "modo"):
            self.strategy.modo = self.director.modo_construccion(f)
        self.disrupt.gain = self.director.agresividad_disrupcion(f)

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

        # --- no desperdiciar pintura ---------------------------------------
        # El bot nº1 de la liga coloca sus 3 puntos TODOS los turnos (110 tracks
        # en 40 turnos). Nosotros mediamos 32-44% desperdiciado en partidas
        # reales: jugabamos con 2 puntos por turno contra sus 3.
        if paint > 0 and FILL_IDLE_PAINT:
            for i in self._frontier(st, placed):
                if paint <= 0:
                    break
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
    return Agent(NetworkStrategy(), PreemptiveDisrupt())


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
