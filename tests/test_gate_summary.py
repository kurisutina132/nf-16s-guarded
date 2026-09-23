#!/usr/bin/env python3
"""Prueba del resumen de la puerta de calidad.

gate_summary.py REPORTA: cuenta, ordena y escribe el resumen, y sale 0 aunque
haya muestras caidas, para que el fichero se publique siempre. Quien tumba la
corrida es assert_gate.py, que tiene su propia prueba.

Las dos cosas que el resumen tiene que reflejar son distintas: una muestra que
NO pasa, y una muestra que DESAPARECE sin dejar veredicto. La segunda es la
peligrosa, porque no deja rastro en ningun sitio si nadie la cuenta.
"""

import subprocess
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
GUION = REPO / "bin" / "gate_summary.py"

CAB = "sample\tpares_tras_filtrado\tmin_reads\tveredicto\tmotivo"


def _fila(sample, pares, minimo=50000, veredicto="PASA", motivo="motivo"):
    return f"{sample}\t{pares}\t{minimo}\t{veredicto}\t{motivo}"


def _correr(lineas, esperadas):
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        entrada, salida = tmp / "v.tsv", tmp / "resumen.tsv"
        entrada.write_text("\n".join([CAB] + lineas) + "\n", encoding="utf-8")
        r = subprocess.run(
            [sys.executable, str(GUION), "--veredictos", str(entrada),
             "--esperadas", str(esperadas), "--out", str(salida)],
            capture_output=True, text=True)
        texto = salida.read_text(encoding="utf-8") if salida.exists() else ""
        return r.returncode, r.stdout, r.stderr, texto


def test_todas_pasan_es_verde():
    cod, out, _err, texto = _correr(
        [_fila("A", 90000), _fila("B", 80000)], esperadas=2)
    assert cod == 0
    assert "2/2 muestras pasan" in out
    assert "2\t2\t2\t0\t0\t0" in texto


def test_la_caida_queda_en_el_resumen_y_el_guion_no_falla():
    """El resumen se escribe y sale 0: si fallara aqui, Nextflow no publicaria
    el fichero y se perderia el motivo de la caida."""
    cod, _out, err, texto = _correr(
        [_fila("A", 90000), _fila("B", 10000, veredicto="NO_PASA", motivo="solo 10000 pares")],
        esperadas=2)
    assert cod == 0, "reportar no es juzgar"
    assert "2\t2\t1\t1\t0\t0" in texto
    assert "NO_PASA" in texto and "solo 10000 pares" in texto
    assert "B: solo 10000 pares" in err


def test_muestra_desaparecida_se_cuenta():
    """Dos muestras declaradas, un solo veredicto. La corrida terminaria en
    verde con la mitad de los datos si nadie contara."""
    cod, _out, err, texto = _correr([_fila("A", 90000)], esperadas=2)
    assert cod == 0
    assert "2\t1\t1\t0\t1\t0" in texto
    assert "1 muestra(s) declarada(s) sin veredicto" in err


def test_veredicto_duplicado_queda_contado_en_inconsistencias():
    """Antes esto se escribia en stderr y se perdia: `sin_veredicto` se recorta
    a cero y nada convertia el problema en un codigo de salida. Ahora tiene
    columna propia, y el dictamen la mira."""
    cod, _out, err, texto = _correr(
        [_fila("A", 90000), _fila("A", 90000)], esperadas=1)
    assert cod == 0
    assert "repetido" in err
    cuentas = texto.splitlines()[1].split("\t")
    assert cuentas[-1] != "0", f"inconsistencias deberia ser >0: {cuentas}"


def test_mas_veredictos_que_muestras_queda_contado():
    cod, _out, err, texto = _correr(
        [_fila("A", 90000), _fila("B", 90000), _fila("C", 90000)], esperadas=2)
    assert cod == 0
    assert "3 veredictos para 2 muestras" in err
    assert texto.splitlines()[1].split("\t")[-1] == "1"


def test_cabecera_inesperada_es_error():
    """Si el formato del veredicto cambia y nadie actualiza esto, mejor un
    error ruidoso que un resumen que cuenta columnas equivocadas."""
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        entrada, salida = tmp / "v.tsv", tmp / "r.tsv"
        entrada.write_text("muestra\tveredicto\nA\tPASA\n", encoding="utf-8")
        r = subprocess.run(
            [sys.executable, str(GUION), "--veredictos", str(entrada),
             "--esperadas", "1", "--out", str(salida)],
            capture_output=True, text=True)
        assert r.returncode == 2
        assert "cabecera inesperada" in r.stderr
        assert not salida.exists()


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
