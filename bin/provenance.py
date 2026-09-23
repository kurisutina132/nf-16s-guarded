#!/usr/bin/env python3
"""Fichero de procedencia de la corrida.

Junta en un solo documento lo que hace falta para volver a llegar al mismo
resultado: que corrio, con que parametros, con que versiones de que
herramientas, sobre que ficheros (con su checksum) y con que veredicto de la
puerta de calidad.

Sin dependencias: el YAML se escribe a mano a proposito, para que este guion
corra en cualquier imagen con Python y no arrastre un paquete mas.
"""

import argparse
import sys
from datetime import datetime, timezone

SECCIONES_OBLIGATORIAS = ("corrida", "parametros", "herramientas", "checksums", "puerta_de_calidad")


def comprobar_coherencia(parametros, filas_checksum):
    """El md5 declarado para la base tiene que ser el que se verifico.

    Existe porque hubo un caso real: con el almacen de referencias cacheado, la
    guarda de checksum no llegaba a correr y la procedencia acababa afirmando
    un md5 que no era el de la base usada. Un documento de procedencia que se
    contradice a si mismo es peor que no tenerlo, porque parece una prueba.
    """
    declarado = None
    for linea in parametros.splitlines():
        if linea.strip().startswith("kraken_db_md5:"):
            declarado = linea.split(":", 1)[1].strip()
            break
    if declarado is None:
        return None

    verificados = [f.get("md5", "") for f in filas_checksum if f.get("sample") == "base_16s"]
    if not verificados:
        return ("se declara kraken_db_md5 pero no hay ningun checksum verificado "
                "de la base: la base no paso por la guarda en esta corrida")
    if declarado not in verificados:
        return (f"el md5 declarado para la base ({declarado}) no coincide con el "
                f"verificado ({', '.join(verificados)})")
    return None


def _leer(ruta):
    with open(ruta, encoding="utf-8") as fh:
        return fh.read()


def _tsv(texto):
    lineas = [l for l in texto.splitlines() if l.strip()]
    if not lineas:
        return [], []
    cab = lineas[0].split("\t")
    return cab, [dict(zip(cab, l.split("\t"))) for l in lineas[1:]
                 if l.split("\t") != cab]


def _sangrar(texto, espacios):
    relleno = " " * espacios
    return "\n".join(relleno + l if l.strip() else l for l in texto.rstrip().splitlines())


def construir(run_meta, parametros, versiones, checksums, veredictos):
    ahora = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    partes = ["# Procedencia de la corrida. Generado por el pipeline.",
              f"# Escrito: {ahora}",
              "",
              "corrida:",
              _sangrar(run_meta, 2),
              "",
              "parametros:",
              _sangrar(parametros, 2) if parametros.strip() else "  {}",
              "",
              "herramientas:",
              _sangrar(versiones, 2) if versiones.strip() else "  {}",
              "",
              "checksums:"]

    _cab, filas = _tsv(checksums)
    if filas:
        for f in filas:
            partes.append(f"  - sample: {f.get('sample', '')}")
            partes.append(f"    fichero: {f.get('fichero', '')}")
            partes.append(f"    md5: {f.get('md5', '')}")
            partes.append(f"    bytes: {f.get('bytes', '')}")
            partes.append(f"    estado: {f.get('estado', '')}")
    else:
        partes.append("  []")

    partes += ["", "puerta_de_calidad:"]
    _cab, filas = _tsv(veredictos)
    if filas:
        for f in filas:
            partes.append(f"  - sample: {f.get('sample', '')}")
            partes.append(f"    pares_tras_filtrado: {f.get('pares_tras_filtrado', '')}")
            partes.append(f"    min_reads: {f.get('min_reads', '')}")
            partes.append(f"    veredicto: {f.get('veredicto', '')}")
            partes.append(f"    motivo: \"{f.get('motivo', '')}\"")
    else:
        partes.append("  []")

    return "\n".join(partes).rstrip() + "\n"


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--run-meta", required=True)
    ap.add_argument("--params", required=True)
    ap.add_argument("--versions", required=True)
    ap.add_argument("--checksums", required=True)
    ap.add_argument("--gates", required=True)
    ap.add_argument("--out", required=True)
    args = ap.parse_args(argv)

    # Todas las lecturas dentro del try, y una sola vez cada fichero: antes la
    # comprobacion de coherencia volvia a leer fuera del try y un fallo de E/S
    # salia como traza en vez de como el codigo 2 documentado.
    try:
        texto_params = _leer(args.params)
        texto_checksums = _leer(args.checksums)
        doc = construir(_leer(args.run_meta), texto_params, _leer(args.versions),
                        texto_checksums, _leer(args.gates))
    except OSError as exc:
        print(f"ERROR no se puede construir la procedencia: {exc}", file=sys.stderr)
        return 2

    faltan = [s for s in SECCIONES_OBLIGATORIAS if f"{s}:" not in doc]
    if faltan:
        print(f"ERROR la procedencia sale incompleta, faltan secciones: {faltan}",
              file=sys.stderr)
        return 2

    _cab, filas = _tsv(texto_checksums)
    incoherencia = comprobar_coherencia(texto_params, filas)
    if incoherencia:
        print(f"ERROR la procedencia se contradice: {incoherencia}", file=sys.stderr)
        print("  no se escribe un documento de procedencia que afirme algo falso",
              file=sys.stderr)
        return 2

    with open(args.out, "w", encoding="utf-8") as fh:
        fh.write(doc)
    print(f"[PROCEDENCIA] escrita en {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
