# Qué clase de problema es Back Track King

Definición formal del juego y mapeo a literatura de planificación de otras áreas.
El objetivo del documento no es describir las reglas (eso está en
[MECHANICS.md](MECHANICS.md)) sino **clasificar el problema** para saber en qué
campo buscar algoritmos que ya estén resueltos.

---

## 1. Definición formal

### Estático (fijado en el turno 0)

| | |
|---|---|
| Grafo | `G = (V, E)`, rejilla 4-conexa, `\|V\| = w·h ∈ [294, 600]` |
| Coste de terreno | `c: V → {1, 2, 3}` (llanura / río / montaña) |
| Particion en regiones | `R`, con `\|R\| ≈ 2w` ≈ 42–60, de ~7–10 celdas |
| Towns | `T ⊂ V`, `\|T\| ∈ [4, 12]` |
| Demanda | `D ⊆ T × T` **dirigida y no recíproca**, `\|D\| ≈ 25–45` |

### Dinámico

| | |
|---|---|
| Propiedad | `owner: V → {∅, 0, 1, N}` (libre / jugador / neutral) |
| Inestabilidad | `ι: R → ℕ` |
| Inkeadas | `K ⊆ R`, absorbente (una región inkeada no vuelve) |

### Acción (simultánea, ambos jugadores)

Cada turno, cada jugador elige:
- un multiconjunto de celdas `A ⊆ V` con `Σ_{v∈A} c(v) ≤ 3` — **no acumulable**,
- opcionalmente una región `r ∈ R` a desestabilizar — **no acumulable**.

### Transición

1. Colocaciones **simultáneas**: si ambos eligen `v`, entonces `owner(v) = N`.
2. Disrupciones: `ι(r) += 1`.
3. Inkeo: `ι(r) ≥ 4 ⟹ r ∈ K`, y `owner(v) = ∅ ∀v ∈ r`.
4. Puntuación.

### Recompensa — **es un flujo, no un valor terminal**

```
r_p(t) = Σ            |{ v ∈ SP_t(a,b) : owner(v) = p }|
      (a,b) ∈ D
      conectados

Score_p = Σ_{t=1}^{100} r_p(t)
```

donde `SP_t(a,b)` es el camino **más corto en número de celdas** en el subgrafo
inducido por `{v : owner(v) ≠ ∅} ∪ T`, con desempate BFS en orden N,E,S,W.

**Esta ecuación es el juego entero.** Todo lo demás se deduce de ella.

---

## 2. Clasificación

| Eje | Valor |
|---|---|
| Jugadores | 2 |
| Movimientos | **simultáneos** |
| Información | **perfecta** (no hay nada oculto) |
| Azar | **ninguno** tras la generación del mapa |
| Horizonte | finito, `T = 100` (en la práctica 40–80 por inkeo mutuo) |
| Suma | los scores **no** son suma cero; la victoria **sí** |
| Reversibilidad | **casi monótono**: colocar es irreversible; solo el inkeo resta |
| Factor de ramificación | ~600 celdas, hasta 3 por turno ⇒ ~3,6·10⁷ combinaciones, × ~50 objetivos de disrupción |

Dos consecuencias metodológicas inmediatas:

- **La búsqueda en el árbol de juego no es viable.** Ni con poda. El espacio de
  acciones por turno ya es intratable, y el horizonte es de 100 turnos.
- **La monotonía es explotable.** Como el estado casi solo crece, un *plan*
  construido de antemano sigue siendo casi válido turnos después. Esto favorece
  planificación constructiva + búsqueda local **sobre el plan**, no sobre el estado.

---

## 3. Las cinco propiedades que de verdad mandan

### P1 — La recompensa es una latencia acumulada

Un par conectado en el turno `τ` aporta `(100 − τ) × (celdas propias en su camino)`.
El objetivo no es "construir la red más barata" sino **minimizar el tiempo hasta
que cada demanda empieza a pagar**, ponderado por lo que paga.

### P2 — Ingreso no almacenable

3 puntos por turno, se pierden si no se usan. El presupuesto total no es un
número: es un **caudal**. Desperdiciar 1 punto en el turno 10 no cuesta 1 punto,
cuesta todo lo que ese punto habría rentado durante 90 turnos.

### P3 — La recompensa depende del camino más corto, que el rival puede redirigir

Poseer celdas es **necesario pero no suficiente**. Basta con que alguien
construya un camino más corto para que el tuyo deje de pagar, entero y de golpe.

Corolario incómodo y poco intuitivo: **añadir raíles propios puede reducir tu
propia puntuación**. Si al conectar un town nuevo creas un atajo entre dos towns
que ya estaban conectados, acortas su camino activo y pierdes las celdas que
quedan fuera. Es un efecto tipo **paradoja de Braess** dentro de tu propia red.

### P4 — `DISRUPT` es interdicción con umbral y daño colateral

Presupuesto 1/turno, umbral 4, destruye raíles de **ambos**, e irreversible.
No es "hacer daño": es **elegir un corte**.

### P5 — Movimientos simultáneos con colisión destructiva

Si los dos colocan en la misma celda, el resultado (`neutral`) **no puntúa para
nadie**. Una política determinista es explotable: un rival que prediga tu ruta
puede neutralizarla al mismo precio que te cuesta a ti construirla.

---

## 4. Mapeo a literatura

### P1 → Minimum Latency Problem / Traveling Repairman

El objetivo `Σ_t Σ_demandas` es exactamente una **latencia acumulada**, no un
coste de recorrido. Es la diferencia entre TSP (minimizar el tour) y MLP
(minimizar la espera media de los clientes), y **la solución óptima es distinta**.

- NP-duro **incluso en métricas de árbol**, y sin PTAS salvo P=NP.
- Mejor aproximación conocida para un agente: **3,59α**
  ([Fakcharoenphol et al.](https://arxiv.org/pdf/1411.4573)); versión multi-agente 8,497α.
- Los algoritmos buenos no minimizan coste: hacen **greedy por ratio** o usan
  subrutinas de *k-MST* (árbol más barato que abarca `i` vértices), sirviendo
  primero racimos densos y baratos.

> **H1.** Ordenar la construcción por `Δ(puntos/turno) × turnos_restantes / coste`
> en vez de por coste. Hoy usamos distancia manhattan como proxy del valor y no
> multiplicamos por el horizonte restante.

### P2 → Optimización de build orders en RTS

Es literalmente el mismo problema: un caudal de recursos no almacenable que hay
que convertir en estructuras que rinden de forma continuada.

- [Churchill & Buro, *Build Order Optimization in StarCraft*, AIIDE 2011](https://davechurchill.ca/publications/pdf/aiide11-bo.pdf):
  **branch & bound en profundidad** sobre secuencias concurrentes de acciones,
  con abstracción del ingreso, macro-acciones, limitación de anchura y cotas
  inferiores admisibles. Planes casi óptimos **en tiempo real**.
- La primera regla de oro de ese campo: **no dejar ingreso ocioso jamás**.

> **H2.** Tratar el orden de aristas del árbol como un problema de scheduling y
> hacer *beam search* o branch & bound sobre él, evaluando cada plan con un
> simulador rápido hasta el turno 100. Es la palanca de mayor techo.
>
> **H2b (barata).** No dejar nunca paint sin gastar. Medimos **32% desperdiciado**
> en partida real: es una violación directa de la regla de oro del campo.

### P3 → Interdicción de camino más corto y juegos de enrutamiento

- [Israeli & Wood, *Shortest-Path Network Interdiction*](https://apps.dtic.mil/sti/pdfs/ADA490133.pdf):
  el marco estándar para "cambiar el camino que elige el otro".
- Nuestro caso es el **dual**: no alargamos su camino, creamos uno más corto que
  pasa por celdas nuestras y se lo apropiamos entero.

> **H3.** Verificar antes de construir que la ruta nueva **no acorta** ningún
> camino activo propio. Mantener la red como **árbol**. Hoy no lo comprobamos
> en ningún sitio, y `_steal` crea ciclos por diseño. Es concreto y barato.

### P4 → Network interdiction / Critical Node Detection

- [Survey de modelos de interdicción](https://www.researchgate.net/publication/333849206_A_Survey_of_Network_Interdiction_Models_and_Algorithms);
  variante **distance-based CNDP**, que mide el daño por distancias entre pares
  y no por número de nodos — que es justo nuestra métrica.
- El modelo **trilevel defender-attacker-defender** (Brown, Carlyle, Salmeron & Wood)
  añade la capa defensiva: fortificar. Nuestro equivalente es enrutar por
  regiones con town, que son **inmunes** al inkeo.

> **H4.** Elegir el objetivo de disrupción **simulando la eliminación** y
> recalculando los caminos activos de ambos, en vez de sumar `act_count`. El proxy
> actual ignora el reenrutado: si existe una ruta alternativa, inkear le cuesta al
> rival mucho menos de lo que el proxy promete.

### P5 → Juegos de movimiento simultáneo

Requieren estrategias mixtas; las políticas puras deterministas son explotables
(SM-MCTS desacoplado, regret matching). Nuestro `BREAK_SYMMETRY` es una versión
tosca de esto.

> **H5.** Aleatorizar los desempates con semilla propia, para que un rival que
> calcule nuestra misma ruta no pueda neutralizarnos sistemáticamente.

---

## 5. Hipótesis ordenadas por (valor esperado / esfuerzo)

| | Hipótesis | Origen | Coste | Techo |
|---|---|---|---|---|
| **H3** | No crear atajos que acorten caminos activos propios (mantener árbol) | Braess / interdicción | bajo | medio-alto |
| **H2b** | No dejar paint ocioso nunca | build orders RTS | bajo | medio |
| **H4** | Objetivo de disrupción por simulación real del corte | CNDP | medio | medio |
| **H1** | Greedy por ratio con valor = Δpuntos/turno × horizonte | MLP | medio | medio-alto |
| **H5** | Desempates aleatorizados | juegos simultáneos | bajo | bajo |
| **H2** | Beam search / B&B sobre el orden de construcción | Churchill & Buro | alto | **alto** |

**H3 es la que más me interesa** porque no es una mejora incremental: si el bot
se está autolesionando creando atajos, eso es un defecto, no una carencia. Y sale
directamente de la propiedad P3, que ninguna intuición sobre "construir barato"
te hace ver.

---

## 6. Referencias

- [LP-based approximation for multi-vehicle minimum latency](https://arxiv.org/pdf/1411.4573)
- [PTAS for traveling repairman and minimum latency problems](https://arxiv.org/pdf/1307.4289)
- [Churchill & Buro, Build Order Optimization in StarCraft (AIIDE 2011)](https://davechurchill.ca/publications/pdf/aiide11-bo.pdf)
- [Robust Continuous Build-Order Optimization (IEEE CoG 2019)](https://ieee-cog.org/2019/papers/paper_85.pdf)
- [Israeli & Wood, Shortest-Path Network Interdiction](https://apps.dtic.mil/sti/pdfs/ADA490133.pdf)
- [A Survey of Network Interdiction Models and Algorithms](https://www.researchgate.net/publication/333849206_A_Survey_of_Network_Interdiction_Models_and_Algorithms)
- [Maximum Shortest Path Interdiction by Upgrading Nodes on Trees](https://arxiv.org/html/2504.05190)
- Takahashi & Matsuyama (1980), heurística de Steiner por caminos mínimos — ver [STRATEGY.md](STRATEGY.md)
