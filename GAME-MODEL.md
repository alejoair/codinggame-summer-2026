# Qué clase de problema es Back Track King

Segunda versión. La primera se escribió razonando sobre el referee; esta
incorpora lo medido en partidas reales del arena y en el simulador, y **corrige
varias cosas que la primera daba por buenas**.

Reglas verificadas contra el código: [MECHANICS.md](MECHANICS.md).
Cola de hipótesis y reglas del banco de pruebas: [TODO.md](TODO.md).

---

## 1. Definición formal

### Estático

| | |
|---|---|
| Grafo | rejilla 4-conexa, `21 ≤ w ≤ 30`, `14 ≤ h ≤ 20` |
| Terreno | `c: V → {1,2,3}` (llanura / río / montaña) |
| Regiones | `\|R\| ≈ 2w` (47–60 medidas), de ~7–10 celdas, **4,7 vecinas de media** |
| Towns | 4–12 |
| Demanda | `D ⊆ T×T` dirigida y no recíproca, **12–52 pares** |

### Acción por turno (simultánea)

3 puntos de pintura **que caducan** + 1 punto de disrupción **que caduca**.

### Recompensa

```
Score_p = Σ_{t}  Σ_{(a,b) ∈ D activos en t}  |{ v ∈ SP_t(a,b) : dueño(v) = p }|
```

`SP_t` = camino **más corto en número de celdas** sobre el grafo de raíles.

---

## 2. El régimen real — lo que la primera versión no sabía

La primera versión asumía 100 turnos y una red que, una vez construida, sigue
rentando. **Las dos cosas son falsas.** Medido:

| | Valor medido |
|---|---|
| Duración real de una partida | **44–67 turnos**, no 100 |
| Pares deseados que llegan a estar activos | **10–23%** (12 de 52, 5 de 30) |
| Pico de conexiones activas | turno **~36** |
| Conexiones activas al final | **0** |
| Regiones inkeadas al final | **43 de 60** |
| Turnos finales sin puntuar nada | **el último ~25%** |

Traza real (semilla 4242, 52 pares deseados):

```
turno 12 → 10/52 activas, +110 puntos/turno
turno 36 → 12/52 activas, +188 puntos/turno   ← pico
turno 60 →  5/52 activas,  +66 puntos/turno
turno 72 →  0/52 activas,    0 puntos/turno   ← tablero muerto
turno 94 →  0/52 activas, 43 de 60 regiones inkeadas
```

### P0 — Hay una VENTANA de puntuación, y se cierra

El juego no es "construir una red y cosecharla". Es **acumular puntos antes de
que el tablero muera**. La ventana útil va de ~turno 10 a ~turno 60, y la
destrucción es **mutua, acumulativa e irreversible**: los dos jugadores gastan
1 punto de disrupción por turno y ninguno puede devolver una región inkeada.

Corolario que duele: en el último cuarto de partida seguimos gastando los 3
puntos de pintura colocando celdas que están en **cero** conexiones activas.

---

## 3. Descomposición del objetivo

```
Score ≈ Σ_t  (pares activos en t) × (longitud media del camino) × (fracción nuestra)
```

Los cuatro factores, con lo medido:

| Factor | Nosotros | Comentario |
|---|---|---|
| Pares activos | 10–23% de los deseados, **decayendo** | el factor que más margen tiene |
| Longitud del camino | — | no medido aún |
| **Fracción propia (ownership)** | **0,43 ganando / 0,31 perdiendo** | **decide las partidas** |
| Turnos activos | ventana de ~50, no 100 | |

Cada celda nuestra aporta solo **0,2–0,6 puntos por turno**, o sea que está en
menos de una conexión activa de media. Si estuvieran en tres, puntuaríamos el
triple con la misma pintura.

---

## 4. El núcleo competitivo: la carrera del camino más corto

24 partidas reales del arena, separadas en 15 victorias y 9 derrotas:

| | Ganadas | Perdidas |
|---|---|---|
| Nuestro score | 2.772 | **1.115** |
| **Su score** | **2.019** | **2.046** |
| Ownership nuestro / suyo | 0,43 / 0,32 | **0,31 / 0,44** |
| Puesto del rival en el ranking | 17,1 | 16,2 |

**La puntuación del rival es idéntica gane quien gane.** La que se desploma es la
nuestra, y el ownership se invierte como un espejo. No perdemos contra rivales
mejores.

> **P3 (confirmada empíricamente).** No se pierde porque te ataquen: se pierde
> porque tus celdas dejan de estar en el camino activo. La conexión activa es la
> **más corta en celdas**, y quien la tiene se lleva el par **entero**.

Consecuencia directa y ya cobrada: penalizar río y montaña para rodearlos
(`TERRAIN_AVOID=(1,3,5,5)`) era una **regresión**, porque alarga el camino en
celdas y regala el par a quien cruza recto. Aislado: +20,6% de score al quitarlo
(t=3,29) y 54,2% de victorias cara a cara sobre 800 partidas.

---

## 5. Hechos estructurales medidos

| Hecho | Medición | Implicación |
|---|---|---|
| Ninguna región es punto de articulación | **0 de 533** en 12 mapas | el grafo de regiones es plano y 2-conexo: **una** región nunca corta el mapa |
| Aislar un town siempre es posible | **0 de 121** imposibles; 18,5 puntos de disrupción (4,6 regiones) | la regla "dos regiones vecinas nunca tienen ambas town" garantiza que el anillo es disruptable |
| …pero es autolesivo | **−62,7%, t=−7,30** | nuestro ownership (0,43) es mayor que el suyo (0,32): matar pares nos quita más a nosotros |
| Presupuesto de disrupción | ~50 puntos = 12 regiones inkeables | |
| Presupuesto de cómputo | usamos **1,7 ms de 50**; el nº1 usa 28,6 | 30× sin tocar |

> **Regla general que sale de aquí:** cualquier estrategia que **destruya valor
> compartido** nos perjudica más a nosotros. La disrupción debe destruir
> **tracks del rival**, no el mapa.

---

## 6. Por qué los proxies ganan a la evaluación exacta

Sustituir el proxy de distancia manhattan por una evaluación **exacta a un paso**
(simular la red y contar celdas propias que puntuarían) midió **−39,6%, t=−5,15**.

No es un fallo de implementación, es la estructura del problema: la recompensa es
una **latencia acumulada** (P1), no una tasa instantánea. Enganchar un town
lejano rinde poco *ahora* y abre la red para todo lo que viene después. El proxy
manhattan sobrevalora los pares grandes y con eso captura ese valor futuro por
accidente; la evaluación exacta lo destruye.

> Cualquier uso del presupuesto de cómputo **tiene que simular hasta el
> horizonte** (~50 turnos). Evaluar mejor un solo paso vuelve a fallar.

---

## 7. Literatura aplicable

- **P0/P1 · Latencia acumulada** → Minimum Latency Problem / Traveling Repairman.
  NP-duro incluso en árboles, sin PTAS, mejor aproximación 3,59α. Los algoritmos
  buenos hacen greedy **por ratio**, no por coste.
  [LP-based approximation](https://arxiv.org/pdf/1411.4573) ·
  [PTAS para MLP](https://arxiv.org/pdf/1307.4289)
- **P2 · Ingreso no almacenable** → *build order optimization* en RTS.
  [Churchill & Buro, AIIDE 2011](https://davechurchill.ca/publications/pdf/aiide11-bo.pdf).
  Regla de oro del campo: no dejar ingreso ocioso. Matiz nuestro: gastar en
  celdas que no puntúan **no es** cumplirla.
- **P3 · Carrera del camino más corto** → interdicción de camino mínimo
  ([Israeli & Wood](https://apps.dtic.mil/sti/pdfs/ADA490133.pdf)); nuestro caso
  es el dual.
- **P4 · Disrupción** → *network interdiction* / *critical node detection*
  ([survey](https://www.researchgate.net/publication/333849206_A_Survey_of_Network_Interdiction_Models_and_Algorithms)).
  Medido: cortar el mapa exige un **conjunto**, no un nodo — y encima no compensa.
- **Meta de competición** → liga con *exploiters* estilo
  [AlphaStar](https://deepmind.google/blog/alphastar-mastering-the-real-time-strategy-game-starcraft-ii/);
  explotación segura de rivales subóptimos
  ([safe opponent exploitation](https://www.researchgate.net/publication/372584179_Safe_Opponent_Exploitation_For_Epsilon_Equilibrium_Strategies)).

---

## 8. Principios corregidos

1. **Maximizar el ownership de los caminos activos**, no el tamaño de la red.
   Es lo único que separa nuestras victorias de nuestras derrotas.
2. **Caminos cortos en celdas.** Rodear terreno caro pierde la carrera.
3. **La ventana se cierra hacia el turno 60.** Todo lo que se construya después
   es casi seguro pintura tirada, y todo lo construido antes rinde el doble de
   lo que parece.
4. **No destruir valor compartido.** Sacamos más de cada par que el rival.
5. **Una celda vale por el número de conexiones que la usan.** Las nuestras están
   en menos de una de media: ahí hay un factor 3 sin tocar.
6. **Cualquier evaluación debe llegar al horizonte**, no a un paso.

---

## 9. Dinamicas: cuales explotamos

Las mecanicas son las reglas; las dinamicas son lo que emerge al jugarlas.

| # | Dinamica | Explotada | Evidencia |
|---|---|---|---|
| 1 | Carrera del camino mas corto (premio indivisible) | parcial | `_contest`, ahora activado por el Director cuando el rival nos gana renta |
| 2 | Espiral de destruccion mutua | si | disruptamos siempre; quitarlo baja del 93,8% al 35,6% de victorias |
| 3 | La ventana de puntuacion se cierra | parcial | el Director conoce `HORIZONTE=60` y la salud del tablero |
| 4 | Aniquilacion entre estrategias parecidas | no, la sufrimos | 12 celdas neutras por partida; 600 empates a cero en espejo |
| 5 | Parasitismo de red | si, pasivo | el dijkstra da coste 0 a railes de cualquiera |
| 6 | Auto-sabotaje por atajo (Braess) | no | H3 implementado pero sin validar |
| 7 | Santuarios (regiones con town, inmunes) | no | |
| 8 | Asimetria del incentivo destructor | **si** | el Director baja la disrupcion cuando dominamos en renta: +622 de margen, t=5,56 |
| 9 | El rico se hace mas rico | apenas | cada celda nuestra da 0,2-0,6 puntos/turno: esta en menos de una conexion |
| 10 | Desperdicio terminal forzado | no | |

El **Director** (`bot/bot.py`) es la capa que lee el estado del mundo y decide
que dinamica explotar cada turno. Existe porque ninguna es buena siempre:
disputar caminos solo renta si el rival nos esta ganando alguno, y destruir el
tablero nos perjudica mas a nosotros cuando poseemos mas que el.

### Tension medida entre D1 y D9

Son **incompatibles por enrutamiento**. Hacer converger rutas en troncos
compartidos (D9) exige desviarse, y desviarse alarga el camino en celdas, que es
perder la carrera del camino mas corto (D1).

Barrido del descuento por transito, victorias contra ref_v1:

| descuento | 0 | 1 | 2 | 3 |
|---|---|---|---|---|
| victorias | **92,5%** | 89,4% | 83,1% | 85,0% |

Monotono a la baja. D1 gana el pulso: el premio del par es **indivisible**, asi
que perder una carrera cuesta el par entero, mientras que compartir un trecho
solo suma puntos de a uno.

Consecuencia: el factor 3 que hay sobre la mesa (nuestras celdas estan en menos
de una conexion activa) **no es accesible enrutando**. En una rejilla los caminos
mas cortos entre pares distintos apenas se solapan, y forzar el solape se paga
mas caro de lo que renta. El solape solo sirve donde ocurre **de forma natural**,
es decir en cuellos de botella que la geometria ya impone.

## 10. Lo que sigue sin explicar

- **Por qué sus partidas duran 44 turnos y las nuestras 67.** Descartado que sea
  porque corten el mapa (§5). Podría ser una propiedad del emparejamiento —dos
  bots que destruyen mucho acaban antes— y no del jugador.
- **`PreemptiveDisrupt` nunca se aisló.** Entró en el paquete que subió el score
  un 41% junto a `FILL_IDLE_PAINT` y `TERRAIN_AVOID`, y este último resultó ser
  una regresión. No sabemos cuál de los tres aportaba. **Es el próximo test
  obligatorio**, sobre todo sabiendo que la disrupción cierra la ventana de
  puntuación de ambos.
