#!/usr/bin/env python3
"""Barrido de atribucion de herramientas sobre TODO el repositorio.

El hook `.githooks/commit-msg` cubre una sola superficie: el mensaje de commit.
Esta prueba cubre el resto — README, codigo, .nf, Dockerfile, CI, ficheros de
procedencia, nombres de fichero — y ademas los mensajes ya escritos en la
historia, que es donde se cuela lo que el hook no llego a ver (commits creados
antes de activar core.hooksPath, o con --no-verify).

Los patrones se arman por trozos ("anth" + "ropic"). Asi este fichero NO
contiene literalmente ninguna de las cadenas que persigue y puede escanearse a
si mismo sin falsos positivos. Si alguien escribe el literal aqui, la prueba se
caza sola.

Uso:  python3 tests/test_atribucion.py     |     pytest tests/test_atribucion.py
"""

import re
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent

# Unica exclusion, y a proposito: el hook tiene que nombrar los patrones para
# poder borrarlos. Es una ruta exacta, no un patron: nada mas puede acogerse.
EXCLUDED = {".githooks/commit-msg"}

# Proveedores / herramientas. Partidos para que no aparezcan enteros aqui.
VENDORS = [
    "anth" + "ropic",
    "cla" + "ude",
    "copi" + "lot",
    "chatg" + "pt",
    "g" + "pt",
    "opena" + "i",
    "gemi" + "ni",
]

_VEND_ALT = "|".join(VENDORS)
_ROBOT = chr(0x1F916)

PATTERNS = [
    ("trailer de co-autoria de herramienta",
     re.compile(r"co-auth" + r"ored-by:.*(" + _VEND_ALT + r")", re.I)),
    ("correo de no-respuesta de proveedor",
     re.compile(r"nore" + r"ply@(" + _VEND_ALT + r")\.", re.I)),
    ("marca 'generado con <herramienta>'",
     re.compile(r"gener(ated|ado) (with|con)\s+\S*(" + _VEND_ALT + r")", re.I)),
    ("emoji de robot al principio de linea",
     re.compile(r"^\s*" + _ROBOT)),
    # Frontera propia, NO \b. En un nombre tipo <notas>_<marca>_<notas>.md el
    # guion bajo es caracter de palabra, asi que \b no marca frontera y la
    # marca pegada se colaba (comprobado: se colaba de verdad). Esto trata
    # cualquier caracter no alfanumerico como separador.
    ("nombre de herramienta suelto",
     re.compile(r"(?<![A-Za-z0-9])(" + _VEND_ALT + r")(?![A-Za-z0-9])", re.I)),
]


def _git(*args):
    return subprocess.run(
        ["git", "-C", str(REPO), *args],
        capture_output=True, text=True, check=True,
    ).stdout


def tracked_files():
    """Ficheros versionados MAS los no versionados que no estan ignorados.

    Incluir los no versionados es deliberado: caza un README recien escrito que
    todavia no se ha hecho `git add`, que es justo cuando se cuela."""
    out = _git("ls-files", "-c", "-o", "--exclude-standard", "-z")
    return [p for p in out.split("\0") if p and p not in EXCLUDED]


def scan_text(label, text):
    hits = []
    for lineno, line in enumerate(text.splitlines(), start=1):
        for why, rx in PATTERNS:
            if rx.search(line):
                hits.append(f"{label}:{lineno}: [{why}] {line.strip()[:120]}")
    return hits


def find_violations():
    hits = []

    for rel in tracked_files():
        # El nombre del fichero es tambien una superficie.
        for why, rx in PATTERNS:
            if rx.search(rel):
                hits.append(f"{rel}: [{why}] en el NOMBRE del fichero")
        path = REPO / rel
        if not path.is_file():
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue  # binario o ilegible: no es una superficie de texto
        hits.extend(scan_text(rel, text))

    # La historia. Separador NUL entre commits para no partir cuerpos largos.
    try:
        log = _git("log", "--format=%H%x1f%B%x00", "--all")
    except subprocess.CalledProcessError:
        log = ""  # repositorio sin commits todavia
    for entry in log.split("\0"):
        if "\x1f" not in entry:
            continue
        sha, body = entry.split("\x1f", 1)
        hits.extend(scan_text(f"commit {sha[:12]}", body))

    return hits


def test_ninguna_superficie_menciona_la_herramienta():
    hits = find_violations()
    assert not hits, (
        "Atribucion de herramienta encontrada en "
        f"{len(hits)} sitio(s):\n  " + "\n  ".join(hits)
    )


def test_el_hook_existe_y_es_ejecutable():
    hook = REPO / ".githooks" / "commit-msg"
    assert hook.is_file(), "falta .githooks/commit-msg"
    assert hook.stat().st_mode & 0o111, ".githooks/commit-msg no es ejecutable"


def test_la_lista_de_exclusiones_no_crece():
    # Una exclusion que crece es una puerta abierta. Si hay que anadir otra,
    # que sea una decision visible en el diff de esta prueba.
    assert EXCLUDED == {".githooks/commit-msg"}


if __name__ == "__main__":
    fallos = []
    for fn in (test_ninguna_superficie_menciona_la_herramienta,
               test_el_hook_existe_y_es_ejecutable,
               test_la_lista_de_exclusiones_no_crece):
        try:
            fn()
            print(f"ok   {fn.__name__}")
        except AssertionError as exc:
            fallos.append(fn.__name__)
            print(f"FALLO {fn.__name__}\n  {exc}")
    sys.exit(1 if fallos else 0)
