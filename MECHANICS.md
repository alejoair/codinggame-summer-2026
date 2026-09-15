# Back Track King — Mecánicas completas

CodinGame **Summer Challenge 2026 — Back Track King** (7–21 sep 2026).
Fuente de verdad: el referee oficial, `https://github.com/CGjupoulton/SummerChallenge2026`
(clonado en `referee/`). Todo lo de este documento está verificado **contra el código**,
no solo contra el enunciado.

> El enunciado completo de las **3 ligas** está en `referee/config/statement_en.html.tpl`
> (usa marcadores `<!-- BEGIN level1 level2 level3 -->`). Es decir: ya conocemos las reglas
> de Bronce sin haber llegado a Bronce.

---

## 1. Estructura de ligas

Sólo existen **3 niveles de reglas**. Silver/Gold/Legend (si existen) **no añaden reglas**,
sólo suben la fuerza del boss.

| Nivel referee | Liga | Reglas nuevas | Objetivo |
|---|---|---|---|
| `level1` | **Wood 2** | juego base (tracks, conexiones, score) | Objetivo tutorial 1: formar **una** conexión activa |
| `level2` | **Wood 1** | `DISRUPT` / instability / inked | Objetivo tutorial 2: **inkear** una región con track enemigo |
| `level3` | **Bronze+** | ninguna nueva | Juego completo: **más puntos a los 100 turnos** |

En Wood 2 y Wood 1 el juego completo se simula pero **sólo se gana cumpliendo el objetivo**
(`TutorialManager.objectiveComplete()`). Si no lo cumples en 100 turnos, pierdes.
Best-of-5 contra el boss, ganar ≥3.

**Bosses:**
- Wood 2 (`config/level1/Boss.py`): `while True: print('WAIT')` — literalmente no hace nada.
- Wood 1 (`config/level2/Boss.py`): cada turno elige **dos towns al azar** y hace
  `AUTOPLACE ax ay bx by`. Nunca usa `DISRUPT`.

---

## 2. El mapa

Generado por `GridMaker.java`. Parámetros reales:

- `height = random[14, 20]`, `width = round(height * 1.5)` → **21 ≤ w ≤ 30**, **14 ≤ h ≤ 20**.
- Terreno por celda (`type`):
  - `0` **plains** — coste 1 paint
  - `1` **river** — coste 2 paint
  - `2` **mountain** — coste 3 paint
  - `3` `TYPE_POI` existe en el código (coste 3) pero **no se genera** en esta versión.
- **Montañas**: `nMountains ≈ random(0, w*h*0.04)`, mínimo 2; cada una es un blob de 2–8 celdas.
- **Ríos**: ~`w*h*0.07` celdas, serpentean desde bordes (y uno desde el centro), con splits
  (5.5%), longitud mínima 3. **Los ríos parten el mapa** — son el cuello de botella real.
- El mapa se genera con `ySymetry = true` en el `Grid`, pero **la generación no es simétrica**
  (la simetría no se usa para espejar terreno). No asumas simetría.

### Regiones (zones)

- `averageTilesPerZone = height / 2` (7..10 celdas)
- `nZones = (h*w) / averageTilesPerZone` ≈ **2·w** → ~42–60 regiones de ~7–10 celdas.
- Se generan por crecimiento tipo Voronoi desde semillas en rejilla → blobs contiguos.
- Cada celda tiene `regionId`. Las regiones son la unidad de `DISRUPT`.

### Towns

- `nTowns = max(4, (h*w)/50)` → **4..12** towns.
- Restricciones: sólo en **plains**, nunca en el borde, **distancia Manhattan ≥ 4** entre towns,
  **una por región**, y **dos regiones vecinas no pueden tener ambas town**.
- `desiredConnections`: cada town pide entre `min(3, n-1)` y `max(atLeast, n-4)` towns al azar;
  después se eliminan las **recíprocas** (si A pide B, B no pedirá A).
  → Con 12 towns salen típicamente **25–45 pares deseados**. Son muchos.
- Un town puede tener 0 `desiredConnections`, pero **siempre es objeto de al menos una**.

---

## 3. Economía y acciones

Cada turno, cada jugador recibe:
- **3 paint points** (`PASSIVE_INCOME = 3`) — **no acumulables**, se pierden.
- **1 disruption point** (`BLOT_POINTS_PER_TURN = 1`) — **no acumulable** (liga 2+).

### Acciones (una línea, separadas por `;`)

| Acción | Efecto |
|---|---|
| `PLACE_TRACKS x y` | pone un track en una celda libre. Coste = 1/2/3 según terreno. |
| `AUTOPLACE fx fy tx ty` | genera la ruta **más barata en paint** de `from` a `to` y la ejecuta. **Máx 1 por turno.** No hace nada si ya hay camino. |
| `DISRUPT regionId` | +1 instability a la región. También acepta `DISRUPT x y` (región de esa celda). |
| `MESSAGE texto` | texto en el viewer (no es una acción de juego, no consume nada). |
| `WAIT` | nada. |

**Regex del parser** (`ActionType.java`): las coordenadas son `\d+` → **no acepta negativos**.
Case-insensitive. Cualquier comando que no matchee ⇒ **descalificado** (no es un skip).

### Orden de resolución de un turno (`Game.performGameUpdate`)

1. `doIncome()` — 3 paint, 1 disrupt.
2. `computeAutobuilds()` — expande `AUTOPLACE` a una lista de `PLACE_TRACK`.
3. `doActions()`:
   a. **Todos los PLACE_TRACK** (jugador 0 primero, luego jugador 1) — se registran intenciones.
   b. Se aplican: si **una** sola persona puso ahí → `track = playerId`.
      Si **ambos** el mismo turno en la misma celda → `track = 2` (**neutral**).
   c. **Después**, los `DISRUPT`.
4. `doInstabilityCheck()` — regiones con `instability >= 4` se **inkean**.
5. `moveTrains()` — se recalculan conexiones activas y **se puntúa**.
6. Fin de partida si procede.

**Clave: los puntos se otorgan AL FINAL, después del inking.**

### Reglas de colocación

- No se puede poner track sobre un **town**, ni sobre un **track existente**, ni en región **inked**.
- Si no te llega el paint: acción descartada. Si venía de un `AUTOPLACE`, **se interrumpe el
  resto del AUTOPLACE** (aunque el resto fuera pagable).
- Una acción imposible se **salta** (error en el summary), no descalifica. Sólo un **comando
  mal formado** descalifica.

---

## 4. Conexiones y puntuación ← **lo más importante**

```
Para cada par (A,B) tal que B ∈ A.desiredConnections:
    si existe camino de tracks/towns entre A y B:
        path = camino MÁS CORTO (en nº de celdas) por BFS
        conexión activa
        cada jugador gana +1 punto POR CADA TILE DEL PATH QUE POSEE
```

Detalles verificados en `Game.moveTrains()` y `TrainBFS.java`:

- **Se puntúa CADA TURNO**, mientras la conexión siga activa. No es un pago único.
- Un **path** es una secuencia de celdas ortogonalmente adyacentes con **track o town**
  (`Grid.canTrainPass`: `isTown() || track != -1`). **El dueño del track no importa para
  la conectividad** — el camino puede pasar por tracks enemigos.
- Sólo puntúas por las celdas **cuyo `track == tu playerId`**.
  → Los tracks **neutrales (owner 2) no puntúan para nadie.**
- El path incluye las celdas de los dos towns (que no son de nadie) → una conexión de N celdas
  reparte como mucho N−2 puntos.
- **Una misma celda puntúa una vez por cada conexión activa que la usa.** Un corredor
  compartido por 6 pares te da **6 puntos/turno**.
- Desempate entre caminos igual de cortos: BFS expandiendo vecinos en orden
  **NORTH, EAST, SOUTH, WEST** desde el town que pide hacia el deseado.

### Las tres consecuencias estratégicas

1. **Valor de una celda = (nº de conexiones que la usan) × (turnos restantes).**
   Una celda puesta en el turno 5 vale 95 puntos por conexión que sirva. En el turno 90, 10.
   → **La velocidad al principio lo es todo.**

2. **El camino activo es el MÁS CORTO, no el que tú construiste.**
   Si el rival construye un atajo, tu ruta larga deja de puntuar. Y al revés: puedes
   *robarle* puntuación al rival creando un atajo más corto que pase por tus tiles.

3. **Caminos deliberadamente largos rinden más** si son el único camino: una celda extra
   cuesta 1 paint (⅓ de turno) y rinde +1 punto/turno durante el resto de la partida.
   El coste-beneficio es brutalmente favorable antes del turno ~70.
   *Pero* sólo mientras nadie construya un atajo más corto.

---

## 5. Disruption (liga 2+)

- 1 punto de disrupción por turno. `DISRUPT regionId` → `instability += 1`.
- `instability >= 4` ⇒ región **inked**:
  - **todos** los tracks de la región desaparecen (tuyos y del rival),
  - **no se puede volver a construir ahí nunca**,
  - las conexiones que pasaban por ahí se cortan.
- `INSTABILITY_THRESHOLD_INCREASE = 0` → el umbral **siempre es 4**, no sube.
- **No se puede disruptar** una región ya inked ni **una región que contenga un town**.
- Cuesta **4 turnos** de disrupción concentrada en la misma región. Es una inversión cara:
  4 turnos de disrupción = todo tu presupuesto de sabotaje durante 4 turnos.
- La instability es **compartida**: si los dos jugadores disruptan la misma región,
  se inkea en 2 turnos. El rival puede "ayudarte" sin querer.
- Como el inking destruye tracks de **ambos**, sólo merece la pena en regiones donde
  el rival tiene mucho más que tú.

**Objetivo de liga Wood 1**: hacer que una región con **al menos un track enemigo** se inkee,
y que **tú** hayas sido quien la disruptó el turno en que se inkea
(`succesfulBlotsThisTurn.get(0) == zone.id && rekt[1] > 0`).

---

## 6. Fin de partida

- **100 turnos** (`MAX_TURNS = 100`).
- O antes: si **ninguna** `desiredConnection` es ya posible por terreno
  (`isAnyConnectionStillPossible()` con A* sobre terreno, ignorando tracks) — sólo puede
  pasar si el inking ha partido el mapa.
- Victoria Bronce: **más puntos**. Empate → empate.
- Timeout o comando inválido ⇒ score −1 y derrota.

---

## 7. Protocolo de E/S

### Inicialización
```
myId                      # 0 o 1
width
height
height*width líneas:  regionId  type
townCount
townCount líneas:     townId  townX  townY  desiredConnections
                      # desiredConnections = "1,2,4"  o  "x" si ninguna
```

### Cada turno
```
myScore
foeScore
height*width líneas (mismo orden, fila a fila):
    trackOwner              # -1 libre, 0 / 1 jugador, 2 neutral
    instability             # instability de la REGIÓN de esta celda
    inked                   # 1 si la región está inked
    partOfActiveConnections # "1-2,1-3,4-7"  o  "x"
```

⚠️ `instability` e `inked` son **de la región**, se repiten en todas sus celdas.

⚠️ `partOfActiveConnections` refleja el estado **al final del turno anterior** — es
información gratis y fiable sobre qué caminos están puntuando ahora mismo.

### Salida
Una línea, acciones separadas por `;`. Máximo **un** `AUTOPLACE`.

### Límites
- **50 ms** por turno, **1000 ms** el primero.
- El referee llama `setMaxTurns(400)` pero el juego acaba en `turn >= 100`.

---

## 8. Detalles finos del referee que sí importan

| Detalle | Dónde | Por qué importa |
|---|---|---|
| `AUTOPLACE` minimiza **paint**, no longitud | `AutobuildAStar.cost` | La ruta más barata puede ser larga y retorcida. Para puntuar tú quieres controlar la forma. |
| `AUTOPLACE` **reutiliza tracks existentes gratis, incluidos los del rival** | `AutobuildAStar.getSuccessors` (`isTrackOrTown()` no mira dueño) | Puedes engancharte a la red enemiga a coste 0. Y él a la tuya. |
| Su heurística es `manhattanTo(sí mismo)` = **0** | `AutobuildAStar.heuristic:108` | Es un Dijkstra, no un A*. Correcto pero sin guía: el desempate de rutas empatadas es por `Direction.ordinal` (N,E,S,W). |
| `AUTOPLACE` acaba al tocar **cualquier celda del bloque de raíles** del destino | `isPartOfRailBlock` | No llega hasta el town: para al tocar la red conectada al destino. |
| Empate de colocación ⇒ **neutral**, no puntúa a nadie | `doActions` | Herramienta de **denegación**: si predices dónde va a construir, puedes neutralizarle la celda. Te cuesta lo mismo que a él. |
| Los PLACE_TRACK resuelven **antes** que los DISRUPT | `doActions` | Puedes construir y disruptar la misma región el mismo turno. |
| Los puntos se dan **después** del inking | `performGameUpdate` | Si inkeas su corredor, deja de puntuar **ese mismo turno**. |
| Regiones **con town no son disruptables** | `doInstabilityCheck` / `doActions` | Las towns y su región inmediata son santuario. Los cuellos de botella junto a towns son seguros. |
| `isFreeOfTracks` sólo mira que **tú** no hayas pedido ya esa celda este turno | `Game.java:577` | Dos PLACE_TRACKS tuyos en la misma celda el mismo turno: el segundo se descarta (y pagas una vez). |
