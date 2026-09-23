#!/usr/bin/env python3
"""Todos los commits de la historia estan firmados por el autor esperado.

Hermana de test_atribucion.py: aquella cubre el CONTENIDO, esta la AUTORIA.
Un historial mal firmado se arregla reescribiendolo, asi que conviene que se
ponga rojo antes de publicar y no despues.

Se comprueban las cuatro identidades de cada commit, no solo la del autor: un
commit puede llevar autor correcto y committer distinto (un rebase, un merge
hecho desde la interfaz web, un cherry-pick ajeno).

Sobre el dominio: la regla es una LISTA BLANCA — el correo tiene que terminar
en DOMINIO_ESPERADO. Eso ya excluye cualquier dominio corporativo sin
necesidad de nombrarlo aqui, y nombrarlo seria contraproducente: este
repositorio es publico y personal, y escribir el dominio del empleador en una
prueba filtra justo la asociacion que el proyecto no quiere tener.

Uso:  python3 tests/test_autoria.py     |     pytest tests/test_autoria.py
"""

import os
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent

NOMBRE_ESPERADO = "kurisutina132"

# Dominio admitido para el correo de los commits. Decision tomada: direccion
# personal verificada en GitHub, no la noreply. Cambiar aqui si cambia.
DOMINIO_ESPERADO = "gmail.com"

_CAMPOS = ("autor", "correo del autor", "committer", "correo del committer")


def commits():
    """(sha, nombre_autor, correo_autor, nombre_committer, correo_committer)."""
    salida = subprocess.run(
        ["git", "-C", str(REPO), "log", "--all",
         "--format=%H%x1f%an%x1f%ae%x1f%cn%x1f%ce%x00"],
        capture_output=True, text=True,
    )
    if salida.returncode != 0:
        return []  # repositorio sin historia todavia
    filas = []
    for entrada in salida.stdout.split("\0"):
        entrada = entrada.strip("\n")
        if not entrada:
            continue
        partes = entrada.split("\x1f")
        if len(partes) == 5:
            filas.append(tuple(partes))
    return filas


def _fallos():
    malos = []
    for sha, an, ae, cn, ce in commits():
        for campo, valor in zip(_CAMPOS, (an, ae, cn, ce)):
            esperado_nombre = campo in ("autor", "committer")
            if esperado_nombre:
                if valor != NOMBRE_ESPERADO:
                    malos.append(
                        f"{sha[:12]}: {campo} es '{valor}', se esperaba '{NOMBRE_ESPERADO}'")
            else:
                if not valor.endswith("@" + DOMINIO_ESPERADO):
                    malos.append(
                        f"{sha[:12]}: {campo} es '{valor}', "
                        f"tiene que terminar en '@{DOMINIO_ESPERADO}'")
    return malos


def test_todos_los_commits_llevan_el_autor_esperado():
    malos = _fallos()
    assert not malos, (
        f"Identidad equivocada en {len(malos)} punto(s) de la historia:\n  "
        + "\n  ".join(malos)
        + "\n\nUn historial mal firmado se arregla reescribiendolo. Configura la "
          "identidad LOCAL antes de volver a commitear:\n"
          f"  git config --local user.name  \"{NOMBRE_ESPERADO}\"\n"
          f"  git config --local user.email \"<tu-direccion>@{DOMINIO_ESPERADO}\""
    )


def test_ningun_commit_usa_un_dominio_fuera_de_la_lista_blanca():
    """La exigencia de 'ningun dominio corporativo', por lista blanca."""
    fuera = []
    for sha, _an, ae, _cn, ce in commits():
        for etiqueta, correo in (("autor", ae), ("committer", ce)):
            dominio = correo.rpartition("@")[2]
            if dominio != DOMINIO_ESPERADO:
                fuera.append(f"{sha[:12]}: {etiqueta} usa el dominio '{dominio}'")
    assert not fuera, (
        "Dominios fuera de la lista blanca (solo se admite "
        f"'{DOMINIO_ESPERADO}'):\n  " + "\n  ".join(fuera))


def test_la_identidad_local_esta_configurada():
    """Sin esto, el primer commit hereda la identidad global de la maquina.

    Esta comprobacion es sobre el CLON, no sobre el repositorio: un clon que
    nunca va a commitear —el de un runner de CI— no tiene por que tener
    identidad local, y exigirsela seria pedirle que finja ser un puesto de
    trabajo. Lo que si vale en todas partes es la firma de la historia, y de
    eso se encargan las dos pruebas de arriba, que en CI son las que mandan.

    El corte se hace con CI=true, que ponen todos los proveedores. No es un
    permiso para saltarse nada: en CI la historia SE sigue comprobando entera,
    y con fetch-depth 0 para que haya historia que comprobar."""
    if os.environ.get("CI"):
        print("    (clon de CI: no commitea, asi que no se le exige identidad "
              "local; la firma de la historia si se comprueba)")
        return

    def cfg(clave):
        r = subprocess.run(["git", "-C", str(REPO), "config", "--local", "--get", clave],
                           capture_output=True, text=True)
        return r.stdout.strip() if r.returncode == 0 else ""

    nombre, correo = cfg("user.name"), cfg("user.email")
    assert nombre == NOMBRE_ESPERADO, (
        f"git config --local user.name es '{nombre}', se esperaba '{NOMBRE_ESPERADO}'. "
        "Sin identidad local, el commit hereda la global de la maquina.")
    assert correo.endswith("@" + DOMINIO_ESPERADO), (
        f"git config --local user.email es '{correo}', "
        f"tiene que terminar en '@{DOMINIO_ESPERADO}'.")


if __name__ == "__main__":
    n = len(commits())
    print(f"(historia: {n} commit(s))")
    fallos = []
    for fn in (test_todos_los_commits_llevan_el_autor_esperado,
               test_ningun_commit_usa_un_dominio_fuera_de_la_lista_blanca,
               test_la_identidad_local_esta_configurada):
        try:
            fn()
            print(f"ok   {fn.__name__}")
        except AssertionError as exc:
            fallos.append(fn.__name__)
            print(f"FALLO {fn.__name__}\n  {exc}")
    sys.exit(1 if fallos else 0)
