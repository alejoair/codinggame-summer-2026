"""
Empaqueta el bot para pegarlo en CodinGame.

Quita comentarios y docstrings (el codigo legible vive en el repo; el IDE solo
necesita ejecutarlo) y saca el resultado comprimido en base64, que es lo que se
inyecta en el editor. Reduce ~24 KB a ~3 KB.

    python tools/pack.py bot/bot.py            # base64 comprimido a stdout
    python tools/pack.py bot/bot.py --plain    # fuente desnuda, para revisar
"""

import argparse
import base64
import ast
import sys
import zlib


def strip(source):
    """
    Reescribe el fuente sin comentarios ni docstrings.

    Se hace sobre el AST y no sobre los tokens: quitar un docstring a mano puede
    dejar un cuerpo vacio y romper la sintaxis. ast.unparse siempre emite codigo
    valido, y los comentarios desaparecen solos porque no estan en el AST.
    """
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if not isinstance(node, (ast.Module, ast.ClassDef,
                                 ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        body = node.body
        if (body and isinstance(body[0], ast.Expr)
                and isinstance(body[0].value, ast.Constant)
                and isinstance(body[0].value.value, str)):
            if len(body) == 1:
                body[0] = ast.Pass()      # cuerpo que era solo docstring
            else:
                node.body = body[1:]
    return ast.unparse(tree) + "\n"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("path")
    ap.add_argument("--plain", action="store_true")
    a = ap.parse_args()

    src = open(a.path, encoding="utf-8").read()
    packed = strip(src)

    compile(packed, a.path, "exec")          # si no compila, no se emite nada

    if a.plain:
        sys.stdout.write(packed)
        return

    blob = base64.b64encode(zlib.compress(packed.encode("utf-8"), 9)).decode()
    sys.stderr.write("original %d  desnudo %d  base64 comprimido %d\n"
                     % (len(src), len(packed), len(blob)))
    sys.stdout.write(blob)


if __name__ == "__main__":
    main()
