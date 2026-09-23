#!/usr/bin/env python3
"""La imagen del pipeline provee lo que el pipeline necesita.

REGLA DE ESTE FICHERO: nada se comprueba leyendo un Dockerfile, ni el nuestro ni
el de nadie. Todo se comprueba CONSTRUYENDO Y EJECUTANDO la imagen. La regla no
es teorica, sale de dos corridas rojas seguidas:

  · debian:12.11-slim se eligio leyendo, y no trae `curl`.
  · buildpack-deps:bookworm-curl se eligio leyendo su Dockerfile oficial, que
    lista ca-certificates, curl, gnupg, netbase, sq y wget — todo cierto, y aun
    asi no trae `ps`, que Nextflow necesita DENTRO del contenedor para recoger
    metricas de la tarea. La corrida murio sin imprimir una sola linea.

Lo que un Dockerfile enumera no es lo que la imagen tiene.

Necesita `docker` y la imagen construida:  make image && make test-imagen
Con IMAGEN_PRUEBAS se puede apuntar a otra etiqueta.

Uso:  python3 tests/test_imagen.py   |   pytest tests/test_imagen.py
"""

import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
IMAGEN = os.environ.get("IMAGEN_PRUEBAS", "nf-16s-guarded:0.1.0")

# El minimo que el pipeline usa dentro del contenedor de fontaneria.
HERRAMIENTAS = ("curl", "tar", "ps")

# Rutas donde puede vivir el paquete de certificados, segun la base.
BUNDLES_CA = (
    "/opt/conda/ssl/cacert.pem",
    "/etc/ssl/certs/ca-certificates.crt",
    "/opt/conda/share/ca-certificates",
)


def _hay_docker():
    return shutil.which("docker") is not None


def _en_imagen(imagen, guion):
    """Ejecuta un guion sh dentro de la imagen. Sin -l: un shell de login relee
    /etc/profile y reescribe PATH, que es como se perdio el /opt/conda de esta
    misma imagen en la primera CI."""
    return subprocess.run(
        ["docker", "run", "--rm", "--entrypoint", "", imagen, "sh", "-c", guion],
        capture_output=True, text=True)


def faltan_herramientas(imagen, herramientas=HERRAMIENTAS):
    """Devuelve (faltan, informe). No silencia stderr: el motivo se imprime."""
    guion = "; ".join(
        f'command -v {h} >/dev/null 2>&1 && echo "HAY {h} $(command -v {h})" || echo "FALTA {h}"'
        for h in herramientas)
    r = _en_imagen(imagen, guion)
    informe = (r.stdout + r.stderr).strip()
    faltan = [l.split()[1] for l in r.stdout.splitlines() if l.startswith("FALTA ")]
    if r.returncode != 0 and not r.stdout.strip():
        faltan = list(herramientas)          # ni siquiera arranco el contenedor
    return faltan, informe


def imagenes_declaradas():
    """Las imagenes que el pipeline declara, sacadas de nextflow.config."""
    texto = (REPO / "nextflow.config").read_text(encoding="utf-8")
    vistas = []
    for m in re.finditer(r"^\s*container_\w+\s*=\s*'([^']+)'", texto, re.M):
        if m.group(1) not in vistas:
            vistas.append(m.group(1))
    return vistas


# --- lo que tiene que cumplirse -------------------------------------------

def test_hay_docker_para_esta_prueba():
    """Se para en vez de saltarse: una prueba de imagen que se salta sin decirlo
    da la misma falsa tranquilidad que el `grep -q` que se tragaba el error."""
    assert _hay_docker(), (
        "no hay `docker` en el PATH. Esta prueba EJECUTA la imagen a proposito; "
        "no se puede sustituir por leer el Dockerfile. `make test` no la incluye.")


def test_la_imagen_provee_las_herramientas_minimas():
    faltan, informe = faltan_herramientas(IMAGEN)
    assert not faltan, (
        f"la imagen {IMAGEN} no provee: {', '.join(faltan)}\n"
        f"--- salida de la imagen ---\n{informe}")


def test_la_imagen_trae_certificados():
    pruebas = " || ".join(f'[ -e {b} ]' for b in BUNDLES_CA)
    r = _en_imagen(IMAGEN, f'if {pruebas}; then echo HAY_CA; else echo FALTA_CA; fi')
    assert "HAY_CA" in r.stdout, (
        f"la imagen {IMAGEN} no trae paquete de certificados en ninguna de "
        f"{BUNDLES_CA}; curl no podria hablar https.\n{r.stdout}{r.stderr}")


def test_todas_las_imagenes_declaradas_traen_ps():
    """La generalizacion del fallo real.

    `ps` no falto por casualidad en una imagen: falta en casi cualquier imagen
    adelgazada, y Nextflow lo exige en TODAS. Si manana se cambia la imagen de
    fastp por otra mas pequena, esto salta aqui y no a mitad de corrida."""
    sin_ps = []
    for imagen in imagenes_declaradas():
        faltan, informe = faltan_herramientas(imagen, ("ps",))
        if faltan:
            sin_ps.append(f"{imagen}\n{informe}")
    assert not sin_ps, (
        "Nextflow necesita `ps` dentro del contenedor para recoger metricas; "
        "sin el, la tarea muere sin imprimir nada:\n  " + "\n  ".join(sin_ps))


# --- y el ataque: quitar una y verla en rojo ------------------------------

def test_quitar_una_herramienta_pone_la_guarda_en_rojo():
    """Se construye una imagen derivada sin `ps` y se comprueba que la guarda la
    caza. Sin esto, la guarda solo demuestra que hoy pasa, no que proteja."""
    with tempfile.TemporaryDirectory() as tmp:
        dockerfile = Path(tmp) / "Dockerfile"
        dockerfile.write_text(
            f"FROM {IMAGEN}\n"
            "USER root\n"
            "RUN rm -f $(command -v ps)\n", encoding="utf-8")
        etiqueta = "nf-16s-guarded:ataque-sin-ps"
        construir = subprocess.run(
            ["docker", "build", "-q", "-f", str(dockerfile), "-t", etiqueta, tmp],
            capture_output=True, text=True)
        assert construir.returncode == 0, (
            f"no se pudo construir la imagen del ataque:\n{construir.stderr}")
        try:
            faltan, informe = faltan_herramientas(etiqueta)
            assert "ps" in faltan, (
                "se quito `ps` de la imagen y la guarda no lo noto: no protege\n"
                f"{informe}")
            assert "curl" not in faltan and "tar" not in faltan, (
                "el ataque tenia que quitar SOLO ps; la guarda dice que faltan "
                f"mas: {faltan}")
        finally:
            subprocess.run(["docker", "rmi", "-f", etiqueta],
                           capture_output=True, text=True)


if __name__ == "__main__":
    if not _hay_docker():
        print("FALLO: no hay `docker` en el PATH; esta prueba EJECUTA la imagen",
              file=sys.stderr)
        sys.exit(1)
    fallos = []
    pruebas = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in pruebas:
        try:
            fn(); print(f"ok   {fn.__name__}")
        except AssertionError as exc:
            fallos.append(fn.__name__); print(f"FALLO {fn.__name__}\n  {exc}")
    print(f"\n{len(pruebas) - len(fallos)}/{len(pruebas)} en verde")
    sys.exit(1 if fallos else 0)
