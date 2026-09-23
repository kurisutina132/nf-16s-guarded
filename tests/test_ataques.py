#!/usr/bin/env python3
"""Pruebas de ataque: cada guarda del pipeline, atacada de verdad.

Lo que distingue a estas de las pruebas de `bin/`: aqui se lanza Nextflow y se
ataca el pipeline entero, no una funcion. Cada prueba escribe el rodeo,
comprueba que la guarda lo caza, y lo deja documentado en el mensaje que
espera. El mensaje forma parte del contrato: si cambia y nadie lo mira, la
prueba lo dice.

HERMETICAS. No tocan la red ni bajan los 112 MB de la base 16S:

  · las lecturas son FASTQ sinteticos generados aqui mismo y servidos por un
    servidor HTTP local en 127.0.0.1;
  · la base 16S es un tarball de mentira con ficheros .k2d de relleno, que basta
    para ejercitar la guarda de checksum y la de estructura;
  · lo que no necesita clasificar corre con `--etapa preparacion`.

Por eso corren sobre el ejecutor local (perfil `test`): un perfil de contenedor
no veria el 127.0.0.1 del anfitrion sin red de anfitrion. El perfil se puede
cambiar con la variable PERFIL_PRUEBAS.

Requisitos: `nextflow` en el PATH, y las herramientas del pipeline para las
pruebas que llegan a fastp.

Uso:  python3 tests/test_ataques.py   |   pytest tests/test_ataques.py
"""

import gzip
import hashlib
import http.server
import os
import shutil
import socketserver
import subprocess
import sys
import tempfile
import threading
import tarfile
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
PERFIL = os.environ.get("PERFIL_PRUEBAS", "test")

_servidor = None
_raiz = None
_base_url = None
_temporales = []   # arboles de trabajo de cada corrida, para barrerlos al final


# ---------------------------------------------------------------------------
# Fixtures: se generan, no se versionan
# ---------------------------------------------------------------------------

def _fastq_gz(destino, n_lecturas, longitud=120, semilla="A"):
    """FASTQ emparejable, deterministico y de calidad alta."""
    bases = "ACGT"
    # GzipFile.close() no cierra ni vacia un fileobj que no abrio el, asi que
    # el `with` anidado no es cosmetico: sin el, los bytes solo llegan al disco
    # cuando el recolector se lleva el objeto.
    with open(destino, "wb") as bruto, \
         gzip.GzipFile(filename="", mode="wb", fileobj=bruto, mtime=0) as gz:
        for i in range(n_lecturas):
            sec = "".join(bases[(i * 7 + j * 3) % 4] for j in range(longitud))
            gz.write(f"@lectura{i}/{semilla}\n{sec}\n+\n{'I' * longitud}\n".encode())


def _md5(ruta):
    h = hashlib.md5()
    with open(ruta, "rb") as fh:
        for trozo in iter(lambda: fh.read(65536), b""):
            h.update(trozo)
    return h.hexdigest()


def _preparar_fixtures():
    """Genera las lecturas, sus versiones saboteadas y las bases de mentira."""
    global _raiz
    _raiz = Path(tempfile.mkdtemp(prefix="ataques-fixtures-"))

    _fastq_gz(_raiz / "buenas_1.fastq.gz", 2000, semilla="1")
    _fastq_gz(_raiz / "buenas_2.fastq.gz", 2000, semilla="2")
    _fastq_gz(_raiz / "pocas_1.fastq.gz", 50, semilla="1")
    _fastq_gz(_raiz / "pocas_2.fastq.gz", 50, semilla="2")

    # Truncado: mismo nombre, mismo aspecto, menos bytes. El caso que motiva
    # toda la verificacion de checksum.
    crudo = (_raiz / "buenas_1.fastq.gz").read_bytes()
    (_raiz / "truncado_1.fastq.gz").write_bytes(crudo[: int(len(crudo) * 0.6)])

    (_raiz / "vacio.fastq.gz").write_bytes(b"")

    # Base de mentira: no sirve para clasificar, sirve para atacar la guarda de
    # checksum y la de estructura, que es lo que se prueba aqui.
    for nombre, piezas in (("base_ok.tgz", ["hash.k2d", "opts.k2d", "taxo.k2d"]),
                           ("base_coja.tgz", ["opts.k2d", "taxo.k2d"])):
        contenido = _raiz / f"contenido_{nombre}"
        (contenido / "16S_SILVA138_k2db").mkdir(parents=True, exist_ok=True)
        for pieza in piezas:
            (contenido / "16S_SILVA138_k2db" / pieza).write_bytes(b"relleno" * 100)
        with tarfile.open(_raiz / nombre, "w:gz") as tar:
            tar.add(contenido / "16S_SILVA138_k2db", arcname="16S_SILVA138_k2db")


def _arrancar_servidor():
    global _servidor, _base_url
    raiz = _raiz

    class Manejador(http.server.SimpleHTTPRequestHandler):
        def __init__(self, *a, **kw):
            super().__init__(*a, directory=str(raiz), **kw)

        def log_message(self, *a):
            pass

    _servidor = socketserver.ThreadingTCPServer(("127.0.0.1", 0), Manejador)
    _servidor.daemon_threads = True
    puerto = _servidor.server_address[1]
    threading.Thread(target=_servidor.serve_forever, daemon=True).start()
    _base_url = f"http://127.0.0.1:{puerto}"


def _parar_servidor():
    if _servidor:
        _servidor.shutdown()
    if _raiz and _raiz.exists():
        shutil.rmtree(_raiz, ignore_errors=True)
    # Cada corrida deja un work/ entero. Quince corridas sin barrer son varios
    # cientos de MB olvidados en /tmp por cada pasada de la suite.
    for ruta in _temporales:
        shutil.rmtree(ruta, ignore_errors=True)
    _temporales.clear()


def url(nombre):
    return f"{_base_url}/{nombre}"


# ---------------------------------------------------------------------------
# Lanzar el pipeline
# ---------------------------------------------------------------------------

CABECERA = "sample,fastq_1,fastq_2,md5_1,md5_2"


def samplesheet(filas, cabecera=CABECERA):
    return "\n".join([cabecera] + filas) + "\n"


def correr(texto_samplesheet=None, extra=None, etapa="preparacion", sheet_path=None,
           refdir=None):
    """Lanza el pipeline y devuelve (codigo, salida_completa, directorio_outdir).

    `refdir` se puede fijar para compartir el almacen de referencias entre dos
    corridas, que es como se reproduce el fallo del storeDir."""
    tmp = Path(tempfile.mkdtemp(prefix="ataque-"))
    _temporales.append(tmp)
    outdir = tmp / "resultados"
    refdir = Path(refdir) if refdir else tmp / "referencias"

    if sheet_path is None:
        sheet_path = tmp / "samplesheet.csv"
        sheet_path.write_text(texto_samplesheet, encoding="utf-8")

    # Sin -quiet a proposito: `-quiet` suprime los log.warn, y el aviso de
    # "muestra apartada" es una senal para quien mira la corrida, no ruido.
    # Una prueba que no lo viera dejaria de proteger ese aviso.
    orden = ["nextflow", "run", str(REPO / "main.nf"),
             "-profile", PERFIL,
             "-work-dir", str(tmp / "work"),
             "--samplesheet", str(sheet_path),
             "--outdir", str(outdir),
             "--reference_dir", str(refdir),
             "--etapa", etapa]
    orden += (extra or [])

    r = subprocess.run(orden, capture_output=True, text=True, cwd=str(tmp))
    return r.returncode, (r.stdout + r.stderr), outdir


def buenas(md5_1=None, md5_2=None, sample="MUESTRA"):
    return (f"{sample},{url('buenas_1.fastq.gz')},{url('buenas_2.fastq.gz')},"
            f"{md5_1 or _md5(_raiz / 'buenas_1.fastq.gz')},"
            f"{md5_2 or _md5(_raiz / 'buenas_2.fastq.gz')}")


# ---------------------------------------------------------------------------
# ATAQUES a la integridad de los ficheros
# ---------------------------------------------------------------------------

def test_md5_que_no_cuadra_aborta():
    cod, salida, outdir = correr(samplesheet([buenas(md5_1="0" * 32)]))
    assert cod != 0, "un md5 que no cuadra no puede terminar en verde"
    assert "el md5 NO coincide para MUESTRA_1.fastq.gz" in salida
    assert "declarado en el samplesheet : " + "0" * 32 in salida
    assert "calculado sobre lo bajado" in salida
    assert not (outdir / "checksums").exists(), "no se publica checksum de algo que no cuadra"


def test_fichero_truncado_aborta_y_dice_cuantos_bytes_llegaron():
    """Un truncado conserva el nombre y sigue siendo un .gz valido hasta donde
    llega. Sin checksum, el pipeline seguiria adelante."""
    entero = _raiz / "buenas_1.fastq.gz"
    truncado = _raiz / "truncado_1.fastq.gz"
    fila = (f"TRUNCA,{url('truncado_1.fastq.gz')},{url('buenas_2.fastq.gz')},"
            f"{_md5(entero)},{_md5(_raiz / 'buenas_2.fastq.gz')}")
    cod, salida, _ = correr(samplesheet([fila]))
    assert cod != 0
    assert "el md5 NO coincide para TRUNCA_1.fastq.gz" in salida
    assert f"bytes recibidos             : {truncado.stat().st_size}" in salida
    assert "puede estar truncado" in salida


def test_fichero_vacio_aborta_nombrandolo():
    fila = (f"VACIA,{url('vacio.fastq.gz')},{url('buenas_2.fastq.gz')},"
            f"{'0' * 32},{_md5(_raiz / 'buenas_2.fastq.gz')}")
    cod, salida, _ = correr(samplesheet([fila]))
    assert cod != 0
    assert "fichero VACIO tras la descarga: VACIA_1.fastq.gz" in salida


def test_url_que_no_existe_aborta():
    fila = (f"NOHAY,{url('no_existe.fastq.gz')},{url('buenas_2.fastq.gz')},"
            f"{'0' * 32},{'0' * 32}")
    cod, salida, _ = correr(samplesheet([fila]))
    assert cod != 0
    assert "la descarga fallo: NOHAY_1.fastq.gz" in salida


# ---------------------------------------------------------------------------
# ATAQUES al samplesheet: tienen que fallar AL ARRANCAR
# ---------------------------------------------------------------------------

def _sin_procesos_lanzados(salida):
    """Fallar al arrancar significa que no se ha lanzado NI UNA tarea.

    La primera version de esto era un `or` de dos condiciones y pasaba casi
    siempre, incluso si una tarea se habia lanzado con exito: comprobaba poco y
    daba tranquilidad. Nextflow anuncia cada tarea con una linea `[PROCESS ...]`,
    asi que la ausencia de esa marca es la senal directa.

    Se miran DOS marcas: Nextflow 26 escribe `[PROCESS ...]` y las series 24 y
    25 escriben `Submitted process > ...`. El manifiesto admite >=24.04.0, asi
    que comprobar solo la de 26 volveria esto una tautologia — otra vez —
    en cualquier motor admitido mas antiguo."""
    return "[PROCESS" not in salida and "Submitted process" not in salida


def test_columna_ausente_falla_al_arrancar():
    fila = f"MUESTRA,{url('buenas_1.fastq.gz')},{url('buenas_2.fastq.gz')},{'a' * 32}"
    cod, salida, _ = correr(samplesheet([fila], cabecera="sample,fastq_1,fastq_2,md5_1"))
    assert cod != 0
    assert "columnas obligatorias que faltan : md5_2" in salida
    assert "cabecera encontrada" in salida
    assert _sin_procesos_lanzados(salida), "tiene que parar antes de lanzar nada"


def test_md5_mal_formado_falla_al_arrancar():
    cod, salida, _ = correr(samplesheet([buenas(md5_1="noesunmd5")]))
    assert cod != 0
    assert "no es un md5 de 32 digitos hexadecimales en minuscula" in salida
    assert _sin_procesos_lanzados(salida)


def test_url_que_no_es_url_falla_al_arrancar():
    fila = f"MUESTRA,/ruta/local/lecturas_1.fastq.gz,{url('buenas_2.fastq.gz')},{'a' * 32},{'b' * 32}"
    cod, salida, _ = correr(samplesheet([fila]))
    assert cod != 0
    assert "no es una URL admisible" in salida
    assert "quedan fuera los que dan shell" in salida
    assert _sin_procesos_lanzados(salida)


def test_url_con_sustitucion_de_ordenes_falla_al_arrancar():
    """Regresion de un agujero real: ejecucion de ordenes desde el samplesheet.

    El validador de URL era `^(https?|ftp)://\\S+$`, que admite
    `https://x/$(orden)y.gz`. Como la URL se interpola en el guion de la tarea
    y ahi estaba entre comillas DOBLES, bash expandia la sustitucion. Se
    comprobo que la orden se ejecutaba de verdad.

    Dos capas cierran esto: lista blanca de caracteres al validar, y comillas
    simples en el guion. Aqui se ataca la primera."""
    for carga in ["https://ejemplo.invalido/$(id)x.gz",
                  "https://ejemplo.invalido/`id`x.gz",
                  "https://ejemplo.invalido/x.gz;id",
                  "https://ejemplo.invalido/x.gz|id",
                  "https://ejemplo.invalido/x.gz&id",
                  "https://ejemplo.invalido/x.gz>/tmp/z",
                  "https://ejemplo.invalido/x'y.gz"]:
        fila = f"INY,{carga},{url('buenas_2.fastq.gz')},{'a' * 32},{'b' * 32}"
        cod, salida, _ = correr(samplesheet([fila]))
        assert cod != 0, f"esta carga colo: {carga}"
        assert "no es una URL admisible" in salida, f"rechazada por otro motivo: {carga}"
        assert _sin_procesos_lanzados(salida), f"se lanzo una tarea con: {carga}"


def test_muestra_repetida_falla_al_arrancar():
    cod, salida, _ = correr(samplesheet([buenas(sample="IGUAL"), buenas(sample="IGUAL")]))
    assert cod != 0
    assert "esta repetida" in salida
    assert _sin_procesos_lanzados(salida)


def test_campo_vacio_falla_al_arrancar():
    fila = f"MUESTRA,,{url('buenas_2.fastq.gz')},{'a' * 32},{'b' * 32}"
    cod, salida, _ = correr(samplesheet([fila]))
    assert cod != 0
    assert "el campo 'fastq_1' esta vacio" in salida


def test_samplesheet_sin_filas_falla_al_arrancar():
    cod, salida, _ = correr(CABECERA + "\n")
    assert cod != 0
    assert "no tiene ninguna fila de datos" in salida


def test_valor_de_parametro_no_admitido_falla_al_arrancar():
    """Un valor que no se entiende no se interpreta a la baja."""
    cod, salida, _ = correr(samplesheet([buenas()]), etapa="perfilado")
    assert cod != 0
    assert "que no es una opcion valida" in salida
    assert "admitidas: completa, preparacion" in salida
    assert _sin_procesos_lanzados(salida)


def test_parametro_obligatorio_ausente_falla_al_arrancar():
    cod, salida, _ = correr(samplesheet([buenas()]), extra=["--min_reads", "null"])
    assert cod != 0
    assert "Falta el parametro obligatorio --min_reads" in salida
    assert "no se va a inventar uno" in salida
    assert _sin_procesos_lanzados(salida)


# ---------------------------------------------------------------------------
# ATAQUES a la base de referencia
# ---------------------------------------------------------------------------

def test_md5_de_la_base_que_no_cuadra_aborta():
    cod, salida, _ = correr(
        samplesheet([buenas()]), etapa="completa",
        extra=["--kraken_db_url", url("base_ok.tgz"), "--kraken_db_md5", "f" * 32])
    assert cod != 0
    assert "el md5 de la base 16S NO coincide" in salida
    assert "declarado en nextflow.config : " + "f" * 32 in salida


def test_base_a_la_que_le_falta_una_pieza_aborta():
    cod, salida, _ = correr(
        samplesheet([buenas()]), etapa="completa",
        extra=["--kraken_db_url", url("base_coja.tgz"),
               "--kraken_db_md5", _md5(_raiz / "base_coja.tgz")])
    assert cod != 0
    assert "la base descomprimida no trae 16S_SILVA138_k2db/hash.k2d" in salida


def test_cambiar_el_md5_de_la_base_obliga_a_reverificarla():
    """Regresion de un fallo real.

    El almacen de referencias usaba una ruta fija, y storeDir NO ejecuta el
    proceso cuando sus salidas ya estan en su sitio. Con la base cacheada, la
    guarda de checksum no llegaba a correr: una corrida con un md5 declarado
    falso terminaba EN VERDE, y la procedencia acababa afirmando un md5 que no
    era el de la base usada.

    Aqui se reproduce el escenario exacto: dos corridas que comparten almacen,
    la primera buena y la segunda con el md5 cambiado."""
    almacen = Path(tempfile.mkdtemp(prefix="almacen-"))
    _temporales.append(almacen)
    md5_bueno = _md5(_raiz / "base_ok.tgz")

    cod, salida, _ = correr(
        samplesheet([buenas()]), etapa="completa", refdir=almacen,
        extra=["--min_reads", "1000",
               "--kraken_db_url", url("base_ok.tgz"), "--kraken_db_md5", md5_bueno])
    # La primera corrida deja la base en el almacen. Puede fallar mas adelante
    # (la base de relleno no clasifica), pero la guarda de checksum tiene que
    # haberla dado por buena Y el almacen tiene que quedar poblado: sin esta
    # comprobacion, si FETCH_KRAKEN_DB dejara de funcionar por cualquier otro
    # motivo, la segunda corrida bajaria de cero y la prueba pasaria sin haber
    # ejercitado nunca el camino cacheado que existe para proteger.
    assert "el md5 de la base 16S NO coincide" not in salida
    assert (almacen / md5_bueno / "16S_SILVA138_k2db").is_dir(), (
        "la primera corrida no dejo la base en el almacen: la prueba no estaria "
        "probando el camino cacheado")

    cod, salida, _ = correr(
        samplesheet([buenas()]), etapa="completa", refdir=almacen,
        extra=["--min_reads", "1000",
               "--kraken_db_url", url("base_ok.tgz"), "--kraken_db_md5", "f" * 32])
    assert cod != 0, "con la base cacheada, un md5 falso seguia pasando: ese era el fallo"
    assert "el md5 de la base 16S NO coincide" in salida
    assert "declarado en nextflow.config : " + "f" * 32 in salida
    assert md5_bueno in salida, "tiene que decir cual es el md5 real"


# ---------------------------------------------------------------------------
# ATAQUE a la puerta de calidad
# ---------------------------------------------------------------------------

def test_muestra_bajo_el_umbral_no_genera_salida_taxonomica():
    """La promesa de la guarda es concreta: la muestra no sigue. Se comprueba
    que NO hay salida taxonomica, no solo que el mensaje aparece."""
    fila = (f"POCAS,{url('pocas_1.fastq.gz')},{url('pocas_2.fastq.gz')},"
            f"{_md5(_raiz / 'pocas_1.fastq.gz')},{_md5(_raiz / 'pocas_2.fastq.gz')}")
    cod, salida, outdir = correr(
        samplesheet([fila]), etapa="completa",
        extra=["--min_reads", "1000",
               "--kraken_db_url", url("base_ok.tgz"),
               "--kraken_db_md5", _md5(_raiz / "base_ok.tgz")])

    assert cod != 0, "una corrida que pierde muestras no termina en verde"
    assert "apartada por la puerta de calidad" in salida
    assert "LA CORRIDA NO SE DA POR BUENA" in salida
    assert "POCAS: solo 50 pares tras el filtrado, por debajo del umbral 1000" in salida

    assert not (outdir / "kraken2").exists(), "la muestra caida no puede tener perfilado"

    # Y el resumen SI se publica: separar reportar de juzgar existe por esto.
    resumen = (outdir / "quality_gate" / "quality_gate_summary.tsv").read_text(encoding="utf-8")
    assert "1\t1\t0\t1\t0" in resumen
    assert "NO_PASA" in resumen


# ---------------------------------------------------------------------------
# EL CASO POSITIVO — la mitad que se olvida
# ---------------------------------------------------------------------------

def test_muestra_buena_produce_exactamente_las_salidas_esperadas():
    cod, salida, outdir = correr(samplesheet([buenas(sample="BUENA")]),
                                 extra=["--min_reads", "1000"])
    assert cod == 0, f"el caso positivo no puede fallar:\n{salida[-3000:]}"

    esperadas = {
        "checksums/BUENA.md5.tsv",
        "fastp/BUENA.fastp.json",
        "fastp/BUENA.fastp.html",
        "quality_gate/BUENA.gate.tsv",
        # El resumen se publica tambien en la etapa de preparacion: la puerta
        # juzga en las dos etapas. Esta linea la anadio la propia prueba al
        # ponerse roja cuando cambio el comportamiento, que es su trabajo.
        "quality_gate/quality_gate_summary.tsv",
    }
    presentes = {str(f.relative_to(outdir)) for f in outdir.rglob("*") if f.is_file()}
    presentes -= {p for p in presentes if p.startswith("pipeline_info/")}
    assert presentes == esperadas, (
        f"salidas inesperadas o ausentes\n  faltan : {esperadas - presentes}"
        f"\n  sobran : {presentes - esperadas}")

    # Y el contenido, no solo el nombre del fichero.
    checksums = (outdir / "checksums" / "BUENA.md5.tsv").read_text(encoding="utf-8")
    assert _md5(_raiz / "buenas_1.fastq.gz") in checksums
    assert _md5(_raiz / "buenas_2.fastq.gz") in checksums
    assert checksums.count("\tOK\n") == 2

    veredicto = (outdir / "quality_gate" / "BUENA.gate.tsv").read_text(encoding="utf-8")
    assert "\tPASA\t" in veredicto
    assert "\t2000\t1000\t" in veredicto, "2000 pares entran, 2000 pares sobreviven"


# ---------------------------------------------------------------------------

def _principal():
    if not shutil.which("nextflow"):
        print("FALLO: no hay `nextflow` en el PATH; estas pruebas lo necesitan",
              file=sys.stderr)
        return 1

    _preparar_fixtures()
    _arrancar_servidor()
    try:
        pruebas = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
        fallos = []
        for fn in pruebas:
            try:
                fn()
                print(f"ok   {fn.__name__}")
            except AssertionError as exc:
                fallos.append(fn.__name__)
                print(f"FALLO {fn.__name__}\n  {exc}")
        print(f"\n{len(pruebas) - len(fallos)}/{len(pruebas)} en verde")
        return 1 if fallos else 0
    finally:
        _parar_servidor()


# pytest: montar y desmontar una sola vez para todo el modulo
def setup_module(module):
    _preparar_fixtures()
    _arrancar_servidor()


def teardown_module(module):
    _parar_servidor()


if __name__ == "__main__":
    sys.exit(_principal())
