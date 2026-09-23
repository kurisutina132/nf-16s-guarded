#!/usr/bin/env python3
"""Prueba del fichero de procedencia.

Un resultado que no puede explicar de donde sale no es un resultado. Esta
prueba comprueba que la procedencia no pierde nada por el camino: ni una
muestra, ni un checksum, ni un veredicto, ni una version.
"""

import subprocess
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
GUION = REPO / "bin" / "provenance.py"

RUN_META = "pipeline: nf-16s-guarded\nversion: 0.1.0\nperfil: test\n"
PARAMS = ("min_reads: 50000\nkraken_confidence: 0.1\n"
          "kraken_db_md5: " + "c" * 32 + "\n")
VERSIONS = '"FASTP":\n    fastp: 0.24.0\n"KRAKEN2":\n    kraken2: 2.1.3\n'
CHECKSUMS = (
    "sample\tfichero\tmd5\tbytes\testado\n"
    "A\tA_1.fastq.gz\t" + "a" * 32 + "\t100\tOK\n"
    "A\tA_2.fastq.gz\t" + "b" * 32 + "\t200\tOK\n"
    "base_16s\tbase.tgz\t" + "c" * 32 + "\t300\tOK\n")
GATES = (
    "sample\tpares_tras_filtrado\tmin_reads\tveredicto\tmotivo\n"
    "A\t90000\t50000\tPASA\tholgado\n"
    "B\t100\t50000\tNO_PASA\tpor debajo\n")


def _correr(**sustituciones):
    piezas = {"run_meta": RUN_META, "params": PARAMS, "versions": VERSIONS,
              "checksums": CHECKSUMS, "gates": GATES}
    piezas.update(sustituciones)
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        rutas = {}
        for nombre, contenido in piezas.items():
            rutas[nombre] = tmp / f"{nombre}.txt"
            rutas[nombre].write_text(contenido, encoding="utf-8")
        salida = tmp / "provenance.yml"
        r = subprocess.run(
            [sys.executable, str(GUION),
             "--run-meta", str(rutas["run_meta"]), "--params", str(rutas["params"]),
             "--versions", str(rutas["versions"]), "--checksums", str(rutas["checksums"]),
             "--gates", str(rutas["gates"]), "--out", str(salida)],
            capture_output=True, text=True)
        doc = salida.read_text(encoding="utf-8") if salida.exists() else ""
        return r.returncode, r.stderr, doc


def test_estan_todas_las_secciones():
    cod, _err, doc = _correr()
    assert cod == 0
    for seccion in ("corrida:", "parametros:", "herramientas:", "checksums:",
                    "puerta_de_calidad:"):
        assert seccion in doc, f"falta la seccion {seccion}"


def test_no_pierde_ningun_checksum():
    """Tres ficheros con checksum entran, tres tienen que salir — incluida la
    base de referencia, que es tan parte del resultado como las lecturas."""
    cod, _err, doc = _correr()
    assert cod == 0
    for md5 in ("a" * 32, "b" * 32, "c" * 32):
        assert md5 in doc, f"se perdio el checksum {md5[:8]}..."
    assert doc.count("estado: OK") == 3


def test_conserva_el_veredicto_negativo():
    """La muestra que NO pasa tiene que quedar escrita. Una procedencia que
    solo cuenta lo que salio bien es propaganda."""
    cod, _err, doc = _correr()
    assert cod == 0
    assert "veredicto: NO_PASA" in doc
    assert "sample: B" in doc


def test_registra_las_versiones_de_las_herramientas():
    cod, _err, doc = _correr()
    assert "fastp: 0.24.0" in doc
    assert "kraken2: 2.1.3" in doc


def test_parametros_en_su_propia_seccion():
    cod, _err, doc = _correr()
    i_par = doc.index("parametros:")
    i_herr = doc.index("herramientas:")
    bloque = doc[i_par:i_herr]
    assert "min_reads: 50000" in bloque
    assert "kraken_confidence: 0.1" in bloque


def test_entradas_vacias_no_rompen_pero_dejan_la_seccion():
    """Sin checksums, sin veredictos y sin versiones el documento sigue
    teniendo todas sus secciones.

    Los parametros van SIN kraken_db_md5 a proposito: declarar un md5 de base y
    no tener ningun checksum verificado de ella ya no es una entrada vacia, es
    una contradiccion, y tiene su propia prueba mas abajo."""
    cod, _err, doc = _correr(params="min_reads: 50000\n",
                             checksums="", gates="", versions="")
    assert cod == 0
    for seccion in ("checksums:", "puerta_de_calidad:", "herramientas:"):
        assert seccion in doc


def test_procedencia_que_se_contradice_no_se_escribe():
    """Regresion de un fallo real: la guarda del checksum de la base podia no
    llegar a correr, y la procedencia acababa declarando un md5 distinto del
    verificado. Un documento de procedencia que se contradice parece una prueba
    y no lo es."""
    cod, err, doc = _correr(params="min_reads: 50000\nkraken_db_md5: " + "9" * 32 + "\n")
    assert cod == 2
    assert doc == "", "no se escribe un documento que afirma algo falso"
    assert "se contradice" in err
    assert "9" * 32 in err and "c" * 32 in err


def test_base_declarada_pero_nunca_verificada_no_se_escribe():
    sin_base = "\n".join(l for l in CHECKSUMS.splitlines() if "base_16s" not in l) + "\n"
    cod, err, doc = _correr(checksums=sin_base)
    assert cod == 2
    assert "no paso por la guarda" in err


def test_fichero_que_falta_es_error():
    r = subprocess.run(
        [sys.executable, str(GUION), "--run-meta", "/no/existe", "--params", "/no/existe",
         "--versions", "/no/existe", "--checksums", "/no/existe", "--gates", "/no/existe",
         "--out", "/tmp/no_deberia_escribirse.yml"],
        capture_output=True, text=True)
    assert r.returncode == 2
    assert "no se puede construir la procedencia" in r.stderr


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
