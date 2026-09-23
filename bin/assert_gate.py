#!/usr/bin/env python3
"""Decide si la corrida se da por buena, leyendo el resumen de la puerta.

Es un proceso aparte del que escribe el resumen, a proposito: asi el resumen se
publica pase lo que pase y este guion puede fallar sin llevarselo por delante.

Sale 1 si alguna muestra no paso o si falta el veredicto de alguna declarada.
Sale 2 si el resumen no se puede interpretar — que tampoco es dar por buena la
corrida, solo que el motivo es otro.
"""

import argparse
import sys

CAB_RESUMEN = ["muestras_declaradas", "con_veredicto", "pasan", "no_pasan",
               "sin_veredicto", "inconsistencias"]


def leer_resumen(ruta):
    with open(ruta, encoding="utf-8") as fh:
        lineas = [l.rstrip("\n") for l in fh]

    if not lineas or lineas[0].split("\t") != CAB_RESUMEN:
        raise ValueError(
            f"cabecera inesperada en {ruta}:\n"
            f"  encontrada: {lineas[0].split(chr(9)) if lineas else '(vacio)'}\n"
            f"  esperada  : {CAB_RESUMEN}")

    campos = lineas[1].split("\t") if len(lineas) > 1 else []
    if len(campos) != len(CAB_RESUMEN):
        # zip() truncaria en silencio y el KeyError saltaria mas tarde, fuera
        # del try de main(), como traza en vez de como mensaje.
        raise ValueError(
            f"la fila de cuentas de {ruta} tiene {len(campos)} campos y la "
            f"cabecera declara {len(CAB_RESUMEN)}")
    try:
        cuentas = {k: int(v) for k, v in zip(CAB_RESUMEN, campos)}
    except ValueError as exc:
        raise ValueError(f"las cuentas del resumen no son enteros: {exc}") from exc

    caidas = []
    for linea in lineas[2:]:
        campos = linea.split("\t")
        if len(campos) == 5 and campos[0] not in ("sample", ""):
            if campos[3] != "PASA":
                caidas.append((campos[0], campos[4]))
    return cuentas, caidas


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--resumen", required=True)
    args = ap.parse_args(argv)

    try:
        cuentas, caidas = leer_resumen(args.resumen)
    except (OSError, IndexError, KeyError, ValueError) as exc:
        print(f"ERROR no se puede interpretar el resumen de la puerta: {exc}", file=sys.stderr)
        return 2

    # Las cuentas y el detalle tienen que contarse lo mismo. Si no, el resumen
    # esta truncado o mal formado, y dar por buena la corrida porque el detalle
    # no tiene nada que objetar seria creerle a la mitad del fichero.
    if cuentas["no_pasan"] != len(caidas):
        print(f"ERROR el resumen se contradice: dice no_pasan={cuentas['no_pasan']} "
              f"pero el detalle trae {len(caidas)} fila(s) caida(s)", file=sys.stderr)
        return 2

    problemas = [f"  {sample}: {motivo}" for sample, motivo in caidas]
    if cuentas["inconsistencias"] > 0:
        problemas.append(
            f"  {cuentas['inconsistencias']} inconsistencia(s) en los veredictos "
            "(repetidos, o mas veredictos que muestras declaradas)")
    if cuentas["sin_veredicto"] > 0:
        problemas.append(
            f"  {cuentas['sin_veredicto']} muestra(s) declarada(s) sin veredicto: "
            "desaparecieron antes de la puerta")

    if problemas:
        print("LA CORRIDA NO SE DA POR BUENA:", file=sys.stderr)
        print("\n".join(problemas), file=sys.stderr)
        print("  una corrida que termina en verde con muestras caidas es el mismo "
              "fallo silencioso que esto intenta evitar", file=sys.stderr)
        print(f"  el detalle queda publicado en {args.resumen}", file=sys.stderr)
        return 1

    print(f"[PUERTA] {cuentas['pasan']}/{cuentas['muestras_declaradas']} muestras pasan; "
          "la corrida se da por buena")
    return 0


if __name__ == "__main__":
    sys.exit(main())
