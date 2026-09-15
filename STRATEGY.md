# Estrategia — Back Track King

Qué tipo de juego es, qué dice la literatura, y qué palancas concretas tiene
*este* juego que se pueden explotar.

---

## 1. Qué juego es esto, en realidad

Quitando la temática, el juego es:

> **Construcción competitiva de una red de Steiner sobre una malla con costes,
> con pago por turno proporcional a la propiedad del camino más corto.**

Tres familias de problemas se solapan:

1. **Steiner Tree Problem in Graphs (STP)** — NP-duro. Dado un grafo con costes
   y un conjunto de terminales (las towns), hallar el subárbol de coste mínimo
   que los conecta. Aquí los costes son 1/2/3 (plains/river/mountain) y los
   terminales son las towns.
2. **Network design game / competitive facility location** — dos agentes
   construyen sobre el mismo grafo y el valor de una arista depende de quién la
   construyó primero.
3. **Presupuesto temporal**: 3 paint/turno, 100 turnos. Es un problema de
   *scheduling* además de uno de diseño: no es "qué red construyo" sino "en qué
   orden", porque **cada celda cobra por turno desde que se activa**.

### La función objetivo, escrita bien

```
Score = Σ_{t=1..100}  Σ_{(a,b) ∈ pares deseados}  |{ celdas mías en shortestPath_t(a,b) }|
```

De aquí salen todas las conclusiones. La más importante:

> **El valor de colocar una celda en el turno t que sirve a k conexiones es
> k · (100 − t) puntos.**

Una celda puesta en el turno 5 que acaba sirviendo a 4 conexiones vale **380
puntos**. La misma celda puesta en el turno 80 vale 80. El juego se decide en
los primeros 30 turnos.

---

## 2. Literatura aplicable

### Steiner tree

- **Takahashi & Matsuyama (1980)**, *An approximate solution for the Steiner
  problem in graphs*. Heurística del camino más corto (también llamada
  "Nearest Participant First"): empieza en un terminal, conecta repetidamente el
  terminal más cercano al árbol por su camino mínimo. Garantiza
  **2 − 2/|S|** veces el óptimo. Es barata (|S| Dijkstras) y es lo que usa
  `NetworkStrategy._expand()`, pero ponderada por valor en vez de sólo por coste.
- **Limitación conocida** de las heurísticas basadas sólo en caminos: son
  *pairwise* y no ven los puntos de Steiner que unirían tres o más terminales a
  la vez por un nodo central. En este mapa eso importa: los cuellos de botella
  entre ríos son puntos de Steiner naturales y unen muchos pares de golpe.
  → Mejora pendiente: tras construir el árbol, un paso de **refinamiento
  local** (quitar una rama y reconectarla) suele dar 5–10%.
- **Kruskal-based / multi-level** y los solvers exactos con pocos terminales
  (≤12 towns aquí) son viables: el óptimo de Steiner con 12 terminales se puede
  calcular con **Dreyfus–Wagner**, `O(3^k·n + 2^k·n²)`. Con k=12 son 531441·600
  ≈ 3·10⁸ operaciones: demasiado para 1 s en Python, factible en C++.
  En Python: Dreyfus–Wagner sobre un subconjunto de 8 towns "core" sí entra.

### Juegos de construcción de rutas

- **Ticket to Ride** tiene literatura de optimización (selección de rutas =
  problema de recubrimiento + camino mínimo) y la conclusión recurrente es la
  misma que aquí: **el valor está en las aristas compartidas por varias rutas
  objetivo**, no en las rutas individuales.
- **Blotto / juegos de atrición** para la parte de `DISRUPT`: con 1 punto por
  turno y umbral 4, la disrupción es un juego de concentración de fuerzas. La
  respuesta óptima a un rival que reparte es concentrar, y viceversa.

### Meta de CodinGame

Para un juego con horizonte largo, movimientos simultáneos y espacio de
acciones enorme (600 celdas), el árbol de búsqueda no es tratable. Lo que gana
históricamente en este perfil de contest:

1. **Heurística constructiva fuerte + búsqueda local sobre el *plan*** (no sobre
   el estado del juego). Es decir: generar un plan de construcción completo
   (orden de aristas del árbol), evaluarlo con un simulador rápido hasta el
   turno 100, y hacer *hill climbing* / *simulated annealing* sobre el orden.
   Esto es lo que suele separar Gold de Legend.
2. **Simulación rápida**: se puede evaluar un plan entero sin rival (el score
   propio es casi independiente del rival salvo por robo de caminos). Con un
   evaluador de 1 ms se hacen 40 iteraciones de búsqueda local por turno.
3. En Python el presupuesto es 50 ms. Si se quiere búsqueda local de verdad,
   **hay que reescribir en C++**. Es la decisión de diseño más importante si el
   objetivo es Legend.

---

## 3. Palancas explotables de ESTE juego

Ordenadas por cuánto creo que valen.

### 3.1 ⭐ Caminos largos rinden más que caminos cortos

El camino activo es el **más corto del grafo de raíles**. Si tu red es un
**árbol** (sin ciclos), el camino entre dos towns es **único**, luego es el más
corto por definición — **da igual lo retorcido que sea**.

Consecuencia: una celda extra de desvío cuesta 1 paint (⅓ de turno) y rinde
**+1 punto/turno por cada par que use ese tramo** durante el resto de la
partida. Antes del turno ~70 el retorno es abrumador.

⚠️ Con dos condiciones:
- La red debe mantenerse **acíclica**. Un atajo propio se corta sus propios
  puntos.
- El rival puede crear el atajo. Los tramos largos son vulnerables.

**Estado actual del bot:** NO explota esto (construye el camino más barato).
Es la mejora #1 pendiente, y probablemente la más rentable.
Implementación: en `build_dijkstra`, usar coste `c(celda) − λ` con λ ∈ (0,1),
o mejor, un post-proceso que "infle" el camino elegido mientras quede paint
ocioso.

### 3.2 ⭐ Corredores compartidos

Una celda puntúa **una vez por cada conexión activa que la usa**. Con 25–45
pares deseados, un corredor central puede servir a 10+ pares → 10 puntos/turno
por celda.

Corolario: **converger** las rutas por un tronco común vale mucho más que
trazar rutas directas independientes. Es exactamente lo contrario de lo que
hace un Steiner mínimo ingenuo cuando las towns están dispersas.

**Estado actual:** parcialmente, por accidente (el árbol reutiliza tramos a
coste 0). No está optimizado.

### 3.3 Robo de caminos

Si el camino activo de un par pasa por celdas del rival, él cobra y tú no.
Construir una ruta alternativa **estrictamente más corta** hecha sólo de celdas
tuyas le quita **todos** los puntos de ese par y te los da a ti. Es un swing de
doble valor.

**Estado actual:** implementado en `NetworkStrategy._steal()` (fase 2).

### 3.4 Neutralización

Si los dos colocáis en la misma celda el mismo turno, queda **neutral (owner 2)**
y **no puntúa para nadie**. Es una herramienta de denegación pura: si predices
su siguiente colocación (su bot es determinista y su ruta más barata es
calculable), puedes neutralizarle el corredor por el mismo precio que a él.

Caro y arriesgado, pero contra un bot determinista de la parte alta de la tabla
puede ser decisivo. **No implementado.**

### 3.5 Disrupción quirúrgica

4 turnos de disrupción para inkear una región de ~7–10 celdas. Destruye tracks
de **los dos**. Sólo vale la pena cuando:
- la región es un **cuello de botella** del rival (pocas celdas, muchos pares
  pasando), y
- tú tienes poco o nada ahí.

Las regiones **con town no son disruptables** → las towns y sus regiones son
santuario. Rutas que pasen pegadas a towns son *inmunes al sabotaje*. Esto es
una consideración defensiva real al trazar el árbol.

Dato: inkear una región puede cortar el mapa y **acabar la partida antes de
turno 100** (`isAnyConnectionStillPossible`). Si vas ganando, acelerar el final
es una jugada legítima; si vas perdiendo, es suicida.

**Estado actual:** `ValueDisrupt` elige por valor neto y es pegajosa. No
considera cuellos de botella ni el final anticipado.

### 3.6 Apertura

El primer par que conectas empieza a cobrar antes que ningún otro. Con towns a
distancia manhattan ≥4 y 3 paint/turno, la primera conexión llega sobre el
turno 2–4. Elegir **el par más barato de conectar entre los dos towns de mayor
demanda** es mejor que el simplemente más barato.

---

## 4. Hoja de ruta propuesta

| # | Mejora | Impacto estimado | Coste |
|---|---|---|---|
| 1 | Inflado de rutas (§3.1) con paint ocioso | muy alto | bajo |
| 2 | Evaluador de plan hasta turno 100 + hill climbing del orden de aristas | alto | medio |
| 3 | Convergencia en tronco compartido (§3.2) explícita en el coste | alto | medio |
| 4 | Refinamiento local del árbol de Steiner (quitar-y-reconectar rama) | medio | bajo |
| 5 | Disrupción por cuello de botella (corte mínimo) | medio | medio |
| 6 | Neutralización predictiva | medio | alto |
| 7 | Reescritura a C++ si se busca Legend | alto | alto |

---

## 5. Referencias

- Takahashi, H. & Matsuyama, A. (1980). *An approximate solution for the Steiner
  problem in graphs*. Math. Japonica 24.
- [Steiner Tree Heuristics — A Survey](https://link.springer.com/chapter/10.1007/978-3-642-78910-6_160)
- [Solving the Steiner Tree Problem with few Terminals](https://arxiv.org/pdf/2011.04593) (Dreyfus–Wagner y variantes)
- [A Robust and Scalable Algorithm for the Steiner Problem in Graphs](https://arxiv.org/pdf/1412.2787)
- [Kruskal-based approximation for multi-level Steiner tree](https://arxiv.org/pdf/2002.06421)
- [Steiner Tree Approximations in Graphs and Hypergraphs](https://doi.org/10.3390/a19030232)
- Referee oficial: https://github.com/CGjupoulton/SummerChallenge2026
- Referee + CLI para brutaltester: https://github.com/RunninglVlan/SummerChallenge2026
- [cg-brutaltester](https://github.com/dreignier/cg-brutaltester)
- Otros bots públicos del contest (para comparar enfoques):
  [Epigene](https://github.com/Epigene/codingame_26_summer),
  [stulentsev](https://github.com/stulentsev/cg-summer-2026-back-track-king)
