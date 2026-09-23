#!/usr/bin/env python3
"""Puerta de calidad: decide si una muestra sigue, a partir del informe de fastp.

No filtra ni modifica nada. Emite un veredicto y lo razona. Quien decide que
hacer con el veredicto es el flujo, no este script.

Sale con codigo 0 tanto si pasa como si no: el fallo de una muestra no es un
fallo de ESTE proceso. Lo que no puede pasar es que el veredicto se pierda, y de
eso se encarga el TSV y, mas adelante, la comprobacion final del flujo.
Sale distinto de 0 solo si no puede emitir un veredicto: informe ilegible,
informe con otra forma, umbral sin sentido. Un umbral que no se entiende no se
interpreta a la baja.
"""

import argparse
import json
import sys


def pares_tras_filtrado(informe):
    """Pares que sobreviven al filtrado.

    fastp cuenta LECTURAS, no pares: en modo emparejado `total_reads` suma las
    dos puntas de cada par. Dividir es la unica forma de comparar contra un
    umbral expresado en pares, que es como lo declara la configuracion.
    """
    try:
        total = informe["summary"]["after_filtering"]["total_reads"]
    except (KeyError, TypeError) as exc:
        raise ValueError(
            "el informe de fastp no trae summary.after_filtering.total_reads "
            f"({exc}); no se puede emitir veredicto") from exc

    if not isinstance(total, int) or total < 0:
        raise ValueError(f"total_reads no es un entero no negativo: {total!r}")

    if total % 2:
        raise ValueError(
            f"total_reads es impar ({total}). En modo emparejado fastp escribe "
            "solo pares completos, asi que un impar significa que el informe no "
            "es de una corrida emparejada. No se asume nada: se para.")

    return total // 2


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--json", required=True, help="informe JSON de fastp")
    ap.add_argument("--sample", required=True, help="identificador de la muestra")
    ap.add_argument("--min-reads", required=True, type=int,
                    help="umbral en PARES de lecturas tras el filtrado")
    ap.add_argument("--out", required=True, help="TSV de veredicto")
    args = ap.parse_args(argv)

    if args.min_reads <= 0:
        print(f"ERROR [{args.sample}] --min-reads tiene que ser un entero positivo; "
              f"recibido {args.min_reads}", file=sys.stderr)
        return 2

    try:
        with open(args.json, encoding="utf-8") as fh:
            informe = json.load(fh)
    except (OSError, json.JSONDecodeError) as exc:
        print(f"ERROR [{args.sample}] no se puede leer el informe de fastp "
              f"'{args.json}': {exc}", file=sys.stderr)
        return 2

    try:
        pares = pares_tras_filtrado(informe)
    except ValueError as exc:
        print(f"ERROR [{args.sample}] {exc}", file=sys.stderr)
        return 2

    pasa = pares >= args.min_reads
    veredicto = "PASA" if pasa else "NO_PASA"
    motivo = (f"{pares} pares tras el filtrado, umbral {args.min_reads}"
              if pasa else
              f"solo {pares} pares tras el filtrado, por debajo del umbral "
              f"{args.min_reads}: faltan {args.min_reads - pares}")

    with open(args.out, "w", encoding="utf-8") as fh:
        fh.write("sample\tpares_tras_filtrado\tmin_reads\tveredicto\tmotivo\n")
        fh.write(f"{args.sample}\t{pares}\t{args.min_reads}\t{veredicto}\t{motivo}\n")

    if pasa:
        print(f"[PUERTA] {args.sample}: PASA — {motivo}")
    else:
        print(f"PUERTA DE CALIDAD [{args.sample}] NO PASA — {motivo}", file=sys.stderr)
        print(f"  la muestra {args.sample} no continua: no se perfilara ni "
              "generara salida taxonomica", file=sys.stderr)

    return 0


if __name__ == "__main__":
    sys.exit(main())
