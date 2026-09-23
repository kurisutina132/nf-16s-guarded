#!/usr/bin/env python3
"""Junta los veredictos de la puerta de calidad en un resumen.

REPORTA, no juzga. Sale con 0 aunque haya muestras caidas, y sale con 2 solo si
no puede construir el resumen.

La separacion no es cosmetica: si el proceso que escribe el resumen fuese
tambien el que tumba la corrida, su salida nunca se publicaria — Nextflow no
publica las salidas de una tarea fallida — y desapareceria justo el fichero que
explica que se cayo. Quien juzga es assert_gate.py, aguas abajo.
"""

import argparse
import sys


def leer_veredictos(ruta):
    with open(ruta, encoding="utf-8") as fh:
        lineas = [l.rstrip("\n") for l in fh if l.strip()]
    if not lineas:
        raise ValueError(f"el fichero de veredictos esta vacio: {ruta}")

    cabecera = lineas[0].split("\t")
    esperada = ["sample", "pares_tras_filtrado", "min_reads", "veredicto", "motivo"]
    if cabecera != esperada:
        raise ValueError(
            f"cabecera inesperada en {ruta}:\n  encontrada: {cabecera}\n  esperada  : {esperada}")

    filas = []
    for n, linea in enumerate(lineas[1:], start=2):
        campos = linea.split("\t")
        if len(campos) != len(cabecera):
            raise ValueError(f"{ruta}, linea {n}: {len(campos)} campos, se esperaban {len(cabecera)}")
        filas.append(dict(zip(cabecera, campos)))
    return filas


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--veredictos", required=True, help="TSV con los veredictos fusionados")
    ap.add_argument("--esperadas", required=True, type=int,
                    help="cuantas muestras declaraba el samplesheet")
    ap.add_argument("--out", required=True, help="TSV resumen")
    args = ap.parse_args(argv)

    try:
        filas = leer_veredictos(args.veredictos)
    except (OSError, ValueError) as exc:
        print(f"ERROR no se pueden leer los veredictos: {exc}", file=sys.stderr)
        return 2

    pasan = [f for f in filas if f["veredicto"] == "PASA"]
    caidas = [f for f in filas if f["veredicto"] != "PASA"]
    faltan = args.esperadas - len(filas)

    # Problemas estructurales: veredictos repetidos, o mas veredictos que
    # muestras declaradas. Tienen columna propia porque `sin_veredicto` se
    # recorta a cero y antes se los tragaba: el problema se detectaba, se
    # escribia en stderr, y aun asi nada lo convertia en un codigo de salida.
    duplicados = len(filas) - len({f["sample"] for f in filas})
    exceso = max(-faltan, 0)
    inconsistencias = duplicados + exceso

    with open(args.out, "w", encoding="utf-8") as fh:
        fh.write("muestras_declaradas\tcon_veredicto\tpasan\tno_pasan\tsin_veredicto"
                 "\tinconsistencias\n")
        fh.write(f"{args.esperadas}\t{len(filas)}\t{len(pasan)}\t{len(caidas)}"
                 f"\t{max(faltan, 0)}\t{inconsistencias}\n")
        fh.write("\nsample\tpares_tras_filtrado\tmin_reads\tveredicto\tmotivo\n")
        for f in sorted(filas, key=lambda x: x["sample"]):
            fh.write("\t".join(f[c] for c in
                     ("sample", "pares_tras_filtrado", "min_reads", "veredicto", "motivo")) + "\n")

    print(f"[PUERTA] {len(pasan)}/{args.esperadas} muestras pasan la puerta de calidad")

    problemas = []
    for f in caidas:
        problemas.append(f"  {f['sample']}: {f['motivo']}")
    if faltan > 0:
        problemas.append(f"  {faltan} muestra(s) declarada(s) sin veredicto: "
                         "desaparecieron antes de la puerta")
    if duplicados:
        problemas.append(f"  {duplicados} veredicto(s) repetido(s) para la misma muestra")
    if exceso:
        problemas.append(f"  hay {len(filas)} veredictos para {args.esperadas} muestras "
                         "declaradas")

    if problemas:
        print("PROBLEMAS EN LA PUERTA DE CALIDAD:", file=sys.stderr)
        print("\n".join(problemas), file=sys.stderr)

    return 0


if __name__ == "__main__":
    sys.exit(main())
