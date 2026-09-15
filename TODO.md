# Cola de hipótesis

Estado del agente: **Silver, puesto ~428/714, score 15,4** (percentil 40).
Mediana de la liga 18,0. Mejor 44,8.

## Reglas del banco de pruebas

Aprendidas a base de equivocarse durante la sesión. No saltárselas:

1. **Nunca comparar dos variantes casi iguales entre sí.** Hacen espejo: colocan
   en las mismas celdas, todo queda neutral y la partida acaba 0-0. Medir siempre
   contra un **tercer** bot (`bot/zoo/ref_v1.py` o `bot/zoo/aggro.py`).
2. **Usar `sim/paired.py`**, que compara sobre los MISMOS mapas. La varianza
   entre mapas es enorme (de 300 a 60.000 puntos) y dos tandas con semillas
   distintas no son comparables.
3. **Exigir |t| ≥ 2** antes de dar nada por bueno. Con n=40 casi nada llega.
4. **Solo `aggro` y el self-play reproducen el régimen real.** Contra rivales que
   no sabotean los marcadores son 7× mayores y las partidas llegan al turno 100:
   ese juego no existe en la liga.
5. **No comparar medias sobre poblaciones distintas** (semillas distintas,
   duraciones distintas, jugadores de distinto nivel). Es el error que más veces
   se ha colado.
6. El score del ranking es tipo TrueSkill: mide **a quién ganas**, no cuánto
   puntúas. El score medio por partida entre jugadores distintos no dice nada.

## Pendientes, por orden

- [ ] **H-SEPARATOR · Inkear un CONJUNTO de regiones que forme un separador.**
      Sucesora de H-CUT, que fracaso por un motivo medido: en 12 mapas, **0 de
      533 regiones disruptables parte el grafo al eliminarla**. El grafo de
      regiones es plano tipo rejilla, con 4,7 vecinas de media, o sea
      practicamente 2-conexo: ninguna region es punto de articulacion, y una
      evaluacion de UN paso nunca puede ver un corte.
      El mapa solo se parte inkeando VARIAS regiones a la vez. Eso es elegir un
      conjunto separador, no un maximo local: es el problema de *critical node
      detection* / interdiccion de red que ya esta en GAME-MODEL.md P4.
      Implementar: buscar el separador de coste minimo (numero de regiones, a 4
      puntos de disrupcion cada una) que aisle towns cuyos pares favorezcan al
      rival, y luego COMPROMETERSE a inkearlo entero. Tenemos ~50 puntos de
      disrupcion por partida = 12 regiones, asi que un separador de 3-5 regiones
      es asequible.
- [ ] **H-COMPUTE · Usar el presupuesto de cómputo.** Gastamos ~1,7 ms de los 50;
      Saelyos gasta 28,6. Hay 30× sin tocar. Es donde cabe el beam search sobre
      el orden de construcción (Churchill & Buro, ver GAME-MODEL.md §H2).
- [ ] **H-CLOSE · Cerrar pronto yendo por delante.** Nuestras partidas son las más
      largas de los cuatro perfiles medidos. Acabar antes congela la victoria.
      Ligado a H-CUT.
- [ ] **H3 · Evitar atajos propios (efecto Braess).** Implementación arreglada
      (`bot/bot_v2.py`, `BTK_ADJ`) pero sin validar: 58,6% con IC [45,9, 71,3].
      Repetir contra `ref_v1` con n grande.
- [ ] **H-STEAL · Robar pares donde puntúan celdas neutrales.** `BTK_STEALN` en
      `bot_v2.py`. Nunca se midió bien.

## Descartadas, con su número

No reintentar sin motivo nuevo:

- **Inflado de rutas** — neutro en test pareado (t=−1,23). Además el régimen real
  (partidas de 44-67 turnos, no 100) reduce el tiempo de amortización.
- **`TIE_JITTER`** — 35,8% de victorias sobre 600 partidas, IC [31,9, 39,7].
- **Cacheo de plan** y **preferir regiones con town** — no concluyentes, medidos
  además en el régimen equivocado.
- **H-CUT · Corte por region unica** — +1,3%, t=0,31, n=120; y contra el
  mecanismo que decia atacar: alarga las partidas (80,3 turnos frente a 78,8)
  en vez de acortarlas. Causa medida: **ninguna region individual es punto de
  articulacion** (0 de 533). Reformulada como H-SEPARATOR.
- **H-CONC · Concentrar la disrupción** (subir el peso de la inestabilidad
  acumulada para terminar regiones antes de abrir nuevas) — **+0,4%, t=0,10,
  59 de 120 mapas**. El primer test dio +18,7% con t=2,05 sobre 40 mapas y era
  ruido. Que inkeemos 15,6 regiones frente a las 10,4 del nº1 sigue siendo
  cierto, pero concentrar sin mas no es la respuesta: apunta a H-CUT, que cambia
  el CRITERIO de eleccion en vez de la reparticion.

## Validadas y en producción

- **`REVERSE_PLAN`** — construir desde el extremo lejano. 63,0% sobre 1000
  partidas, IC [60,0, 66,0].
- **`PreemptiveDisrupt`** — disruptar desde el turno 1 repartiendo. Junto con
  `TERRAIN_AVOID` y `FILL_IDLE_PAINT`: score 10,94 → 15,37 en la liga real,
  y 116 puestos.
