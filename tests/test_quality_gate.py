#!/usr/bin/env python3
"""Prueba de la puerta de calidad, sin Nextflow y sin red.

La puerta es una de las guardas del pipeline, asi que se prueba por los dos
lados: que deja pasar lo que debe y que para lo que debe. Los informes de fastp
son sinteticos a proposito — una prueba de guarda no deberia necesitar 34 MB de
descarga para correr.

Uso:  python3 tests/test_quality_gate.py   |   pytest tests/test_quality_gate.py
"""

import json
import subprocess
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
GUION = REPO / "bin" / "quality_gate.py"


def _informe(total_reads):
    return {"summary": {"after_filtering": {"total_reads": total_reads}}}


def _correr(contenido_json, min_reads=50000, sample="MUESTRA"):
    """Ejecuta el guion y devuelve (codigo, stdout, stderr, filas_del_tsv)."""
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        entrada, salida = tmp / "fastp.json", tmp / "gate.tsv"
        if isinstance(contenido_json, str):
            entrada.write_text(contenido_json, encoding="utf-8")
        else:
            entrada.write_text(json.dumps(contenido_json), encoding="utf-8")

        r = subprocess.run(
            [sys.executable, str(GUION), "--json", str(entrada), "--sample", sample,
             "--min-reads", str(min_reads), "--out", str(salida)],
            capture_output=True, text=True)

        filas = []
        if salida.exists():
            lineas = salida.read_text(encoding="utf-8").strip().splitlines()
            cab = lineas[0].split("\t")
            filas = [dict(zip(cab, l.split("\t"))) for l in lineas[1:]]
        return r.returncode, r.stdout, r.stderr, filas


# --- lo que tiene que pasar -------------------------------------------------

def test_muestra_holgada_pasa():
    cod, out, _err, filas = _correr(_informe(200_000), min_reads=50_000)
    assert cod == 0
    assert filas[0]["veredicto"] == "PASA"
    assert filas[0]["pares_tras_filtrado"] == "100000"   # fastp cuenta lecturas
    assert "PASA" in out


def test_justo_en_el_umbral_pasa():
    """El umbral es 'al menos', no 'mas que'. Un borde mal puesto descarta
    muestras buenas y nadie lo mira."""
    cod, _out, _err, filas = _correr(_informe(100_000), min_reads=50_000)
    assert cod == 0
    assert filas[0]["veredicto"] == "PASA"


# --- lo que tiene que pararse -----------------------------------------------

def test_por_debajo_del_umbral_no_pasa():
    cod, _out, err, filas = _correr(_informe(80_000), min_reads=50_000)
    assert cod == 0, "el veredicto negativo no es un error del proceso"
    assert filas[0]["veredicto"] == "NO_PASA"
    assert filas[0]["pares_tras_filtrado"] == "40000"
    assert "NO PASA" in err
    assert "faltan 10000" in filas[0]["motivo"]
    assert "no continua" in err


def test_uno_por_debajo_no_pasa():
    cod, _out, _err, filas = _correr(_informe(99_998), min_reads=50_000)
    assert cod == 0
    assert filas[0]["veredicto"] == "NO_PASA"


def test_json_ilegible_es_error_no_veredicto():
    cod, _out, err, filas = _correr("{esto no es json", min_reads=50_000)
    assert cod == 2
    assert filas == [], "no se emite veredicto cuando no se puede decidir"
    assert "no se puede leer el informe" in err


def test_informe_con_otra_forma_es_error():
    cod, _out, err, filas = _correr({"summary": {}}, min_reads=50_000)
    assert cod == 2
    assert filas == []
    assert "total_reads" in err


def test_total_impar_es_error():
    """En modo emparejado fastp escribe solo pares completos. Un impar
    significa que el informe no es el que creemos, y dividir por dos seria
    inventarse medio par."""
    cod, _out, err, filas = _correr(_informe(99_999), min_reads=50_000)
    assert cod == 2
    assert filas == []
    assert "impar" in err


def test_umbral_no_positivo_es_error():
    """Un umbral de 0 deja pasar cualquier cosa: es un defecto permisivo
    disfrazado de configuracion."""
    for umbral in (0, -1):
        cod, _out, err, filas = _correr(_informe(200_000), min_reads=umbral)
        assert cod == 2, f"umbral {umbral} deberia ser error"
        assert filas == []
        assert "entero positivo" in err


if __name__ == "__main__":
    fallos = []
    pruebas = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in pruebas:
        try:
            fn()
            print(f"ok   {fn.__name__}")
        except AssertionError as exc:
            fallos.append(fn.__name__)
            print(f"FALLO {fn.__name__}\n  {exc}")
    print(f"\n{len(pruebas) - len(fallos)}/{len(pruebas)} en verde")
    sys.exit(1 if fallos else 0)
