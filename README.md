# CodinGame — Summer Challenge 2026 · Back Track King

Repo de trabajo para el contest (7–21 sep 2026).
Como CodinGame no versiona el código, **la fuente de verdad del bot vive aquí**
y se pega en el IDE.

```
MECHANICS.md        reglas completas de las 3 ligas, verificadas contra el referee
STRATEGY.md         literatura aplicable + palancas explotables + hoja de ruta
bot/bot.py          EL BOT. Archivo unico, se copia/pega en CodinGame
sim/referee.py      port a Python del referee (motor de reglas fiel)
sim/arena.py        arena local: N partidas entre dos bots, estadisticas
tools/paste_helper.html   pagina para copiar bot.py al portapapeles de un clic
referee/            clon del referee Java oficial (para brutaltester, opcional)
```

---

## Iterar

### 1. Probar en local (rápido, sin red)

```bash
python sim/arena.py --p1 "python bot/bot.py" --p2 random --games 20 --league 3
```

Rivales internos sin subproceso: `wait` (boss de Wood 2), `random` (boss de
Wood 1). Para enfrentar dos versiones del bot entre sí, copia `bot/bot.py` a
`bot/bot_old.py` y pásalo como `--p2`.

⚠️ Dos bots **idénticos y deterministas** dan 0–0: colocan en las mismas celdas
y todo queda neutral. Es correcto, no es un bug del simulador.

Flags: `--league 1|2|3`, `--games N`, `--seed S`, `--verbose`.
La arena reporta el **peor turno en ms** — el límite de CodinGame es 50 ms.

### 2. Pegar en CodinGame

```bash
python -m http.server 8765 --bind 127.0.0.1
```

Abre `http://127.0.0.1:8765/tools/paste_helper.html`, pulsa **Copiar bot.py**,
ve al IDE de CodinGame, click en el editor, `Ctrl+A`, `Ctrl+V`.

(La página relee el fichero en cada click, así que no hay que recargarla entre
iteraciones.)

### 3. Referee Java oficial (opcional, más fiel)

Sólo hace falta para validar desempates exactos o reproducir una seed concreta.
Requiere **Maven** (no instalado ahora mismo):

```bash
cd referee && mvn package
java -jar cg-brutaltester.jar -r "java -jar target/summer-challenge-2026-back-track-king-1.0-SNAPSHOT.jar -league 3" -p1 "python bot/bot.py" -p2 "python referee/config/level2/Boss.py" -t 2 -n 20
```

---

## Estado

| Liga | Estado |
|---|---|
| Wood 2 | ✅ superada (5/5 en arena) |
| Wood 1 | ✅ superada (mejor que el boss) |
| Bronze | en curso — aquí empieza el juego de verdad |

El bot usa `LEAGUE = "auto"` en `bot/bot.py`: una sola estrategia para todas las
ligas. La política de disrupción **se auto-desactiva mientras no haya ningún
track enemigo en el mapa**, por lo que en Wood 2 nunca se dispara.

## Arquitectura del bot

```
Board          mapa estatico    (terreno, regiones, towns, pares deseados)
State          estado del turno (tracks, instability, inked, conexiones activas)
Rules          port fiel del referee: costes, TrainBFS, dijkstra de construccion
Strategy       QUE construir    -> ConnectFirstStrategy | NetworkStrategy
DisruptPolicy  QUE sabotear     -> NoDisrupt | ValueDisrupt
Agent          compone strategy + policy y reparte los 3 paint del turno
```

Para una liga/idea nueva: añadir una `Strategy` o `DisruptPolicy` y registrarla
en `build_agent()`. Nada más debería cambiar.

`bot/bot.py` es a la vez pegable en CodinGame e importable: `main(read, write)`
acepta E/S inyectada, así que el simulador puede pilotarlo en proceso.
