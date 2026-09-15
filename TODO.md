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

- [ ] **H-COMPUTE · Beam search sobre el ORDEN de construccion, evaluando hasta
      el FINAL de la partida.** Gastamos ~1,7 ms de los 50; el nº1 gasta 28,6.
      Aviso caro, ya pagado: evaluar exactamente UN paso (simular la red y contar
      celdas propias que puntuarian al enganchar cada town) dio **-39,6%,
      t=-5,15**. Fue peor que el proxy manhattan porque es MIOPE: ignora que
      enganchar un town lejano abre la red para los siguientes. La recompensa de
      este juego es una latencia acumulada (GAME-MODEL.md P1), no una tasa
      instantanea, asi que la evaluacion TIENE que simular hasta el horizonte
      (~50 turnos, no 100). Cualquier atajo que evalue un paso volvera a fallar.
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
- **H-SEPARATOR · Asediar un town (inkear todo su anillo para aislarlo)** —
  **-62,7%, t=-7,30, gana 10 de 120 mapas**. Catastrofico, y la causa estaba en
  nuestros propios datos: nuestro ownership medio es 0,41 y el del rival 0,35,
  o sea que sacamos MAS partido de cada par que ellos. Matar pares enteros es
  autolesivo. Ademas se pierden los tracks propios del anillo.
  Corolario general, vale para futuras ideas: **cualquier estrategia que
  destruya valor compartido nos perjudica mas a nosotros**. La disrupcion tiene
  que ir a destruir TRACKS DEL RIVAL, no a destruir el mapa.
  Deja ademas sin explicar por que sus partidas duran 44 turnos y las nuestras
  67: no es porque ellos corten.
- **H-CUT · Corte por region unica** — +1,3%, t=0,31, n=120; y contra el
  mecanismo que decia atacar: alarga las partidas (80,3 turnos frente a 78,8)
  en vez de acortarlas. Causa medida: **ninguna region individual es punto de
  articulacion** (0 de 533). Reformulada como H-SEPARATOR.
- **Desempate por numero de celdas** (`HOP_PENALTY` sobre `route_cost` x10) —
  50,8%, IC [44,5, 57,2], con 260 empates de 500: casi nunca cambia la ruta.
  Con los costes reales restaurados, en llanura minimizar pintura YA es
  minimizar celdas.
- **D9 por enrutamiento · descuento a celdas de mucho transito** — monotono a la
  baja: victorias 92,5% / 89,4% / 83,1% / 85,0% para descuento 0/1/2/3 contra
  ref_v1. Causa: **D9 y D1 son incompatibles**, converger exige desviarse y
  desviarse pierde la carrera del camino mas corto, cuyo premio es indivisible.
  El factor 3 no es accesible enrutando.
- **H-CONC · Concentrar la disrupción** (subir el peso de la inestabilidad
  acumulada para terminar regiones antes de abrir nuevas) — **+0,4%, t=0,10,
  59 de 120 mapas**. El primer test dio +18,7% con t=2,05 sobre 40 mapas y era
  ruido. Que inkeemos 15,6 regiones frente a las 10,4 del nº1 sigue siendo
  cierto, pero concentrar sin mas no es la respuesta: apunta a H-CUT, que cambia
  el CRITERIO de eleccion en vez de la reparticion.

## Hallazgo clave: por que perdemos

Separando 24 partidas reales del arena en 15 victorias y 9 derrotas:

| | Ganadas | Perdidas |
|---|---|---|
| Nuestro score | 2.772 | 1.115 |
| **Su score** | **2.019** | **2.046** |
| Nuestro ownership | 0,43 | 0,31 |
| Su ownership | 0,32 | 0,44 |
| Score del rival en el ranking | 17,1 | 16,2 |

**Su puntuacion es identica gane quien gane. La que se desploma es la nuestra.**
Y el discriminador es el ownership, que se invierte como un espejo. Tampoco
perdemos contra rivales mejores.

No perdemos porque nos ataquen: perdemos porque **nuestras celdas dejan de estar
en los caminos activos**. Es la propiedad P3 de GAME-MODEL.md — la conexion
activa es la mas CORTA en celdas, y quien la tiene se lleva el par entero.
Todo lo que acorte nuestros caminos, o alargue los suyos, ataca la causa real.

## Validadas y en producción

- **`REVERSE_PLAN`** — construir desde el extremo lejano. 63,0% sobre 1000
  partidas, IC [60,0, 66,0].
- **`PreemptiveDisrupt`** — disruptar desde el turno 1 repartiendo. Junto con
  `TERRAIN_AVOID` y `FILL_IDLE_PAINT`: score 10,94 → 15,37 en la liga real,
  y 116 puestos.
