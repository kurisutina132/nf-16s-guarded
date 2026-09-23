#!/usr/bin/env python3
"""Prueba del dictamen sobre la puerta de calidad.

assert_gate.py es lo ultimo que se interpone entre una corrida con muestras
caidas y un verde en la CI.
"""

import subprocess
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
GUION = REPO / "bin" / "assert_gate.py"

CAB = ("muestras_declaradas\tcon_veredicto\tpasan\tno_pasan\tsin_veredicto"
       "\tinconsistencias")
CAB_FILAS = "sample\tpares_tras_filtrado\tmin_reads\tveredicto\tmotivo"


def _resumen(cuentas, filas):
    return "\n".join([CAB, "\t".join(str(c) for c in cuentas), "", CAB_FILAS] + filas) + "\n"


def _correr(texto):
    with tempfile.TemporaryDirectory() as tmp:
        ruta = Path(tmp) / "resumen.tsv"
        ruta.write_text(texto, encoding="utf-8")
        r = subprocess.run([sys.executable, str(GUION), "--resumen", str(ruta)],
                           capture_output=True, text=True)
        return r.returncode, r.stdout, r.stderr


def test_todas_pasan_da_por_buena_la_corrida():
    cod, out, _err = _correr(_resumen(
        [2, 2, 2, 0, 0, 0],
        ["A\t90000\t50000\tPASA\tholgado", "B\t80000\t50000\tPASA\tholgado"]))
    assert cod == 0
    assert "2/2 muestras pasan" in out


def test_una_caida_tumba_la_corrida():
    cod, _out, err = _correr(_resumen(
        [2, 2, 1, 1, 0, 0],
        ["A\t90000\t50000\tPASA\tholgado",
         "B\t10000\t50000\tNO_PASA\tsolo 10000 pares, faltan 40000"]))
    assert cod == 1
    assert "NO SE DA POR BUENA" in err
    assert "B: solo 10000 pares" in err
    assert "queda publicado en" in err, "tiene que decir donde mirar el detalle"


def test_muestra_sin_veredicto_tumba_la_corrida():
    cod, _out, err = _correr(_resumen(
        [3, 2, 2, 0, 1, 0],
        ["A\t90000\t50000\tPASA\tok", "B\t80000\t50000\tPASA\tok"]))
    assert cod == 1
    assert "sin veredicto" in err


def test_resumen_con_otra_cabecera_no_se_da_por_bueno():
    """Si el formato cambia, el dictamen no puede responder 'todo bien' por no
    encontrar nada que objetar."""
    cod, _out, err = _correr("otra\tcosa\nA\tB\n")
    assert cod == 2
    assert "cabecera inesperada" in err


def test_cuentas_no_numericas_no_se_dan_por_buenas():
    cod, _out, err = _correr(_resumen(
        ["dos", 2, 2, 0, 0, 0], ["A\t90000\t50000\tPASA\tok"]))
    assert cod == 2
    assert "no son enteros" in err


def test_inconsistencias_tumban_la_corrida():
    """Veredictos repetidos o de mas. El resumen los cuenta; aqui se cobran."""
    cod, _out, err = _correr(_resumen(
        [1, 2, 2, 0, 0, 1],
        ["A\t90000\t50000\tPASA\tok", "A\t90000\t50000\tPASA\tok"]))
    assert cod == 1
    assert "inconsistencia" in err


def test_cuentas_que_no_cuadran_con_el_detalle_no_se_dan_por_buenas():
    """El resumen dice que cayo una y el detalle no trae ninguna caida. Creerle
    al detalle y dar verde seria creerle a la mitad del fichero."""
    cod, _out, err = _correr(_resumen(
        [2, 2, 1, 1, 0, 0],
        ["A\t90000\t50000\tPASA\tok", "B\t80000\t50000\tPASA\tok"]))
    assert cod == 2
    assert "se contradice" in err
    assert "no_pasan=1" in err


def test_fila_de_cuentas_corta_da_mensaje_no_traza():
    """zip() truncaba en silencio y el KeyError saltaba fuera del try: salia
    una traza de Python en vez del error documentado."""
    cod, out, err = _correr(CAB + "\n2\t2\t2\n")
    assert cod == 2
    assert "Traceback" not in err and "Traceback" not in out
    assert "campos y la cabecera declara" in err


if __name__ == "__main__":
    fallos = []
    pruebas = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in pruebas:
        try:
            fn(); print(f"ok   {fn.__name__}")
        except AssertionError as exc:
            fallos.append(fn.__name__); print(f"FALLO {fn.__name__}\n  {exc}")
    print(f"\n{len(pruebas)-len(fallos)}/{len(pruebas)} en verde")
    sys.exit(1 if fallos else 0)
