#!/usr/bin/env nextflow
/*
 * nf-16s-guarded
 *
 * Descarga verificada -> control de calidad -> puerta de lecturas minimas ->
 * clasificacion taxonomica -> informe -> procedencia.
 *
 * Principio que gobierna este fichero: un parametro ausente no se asume. Si
 * falta algo que gobierna una guarda, el pipeline se para ANTES de lanzar el
 * primer proceso y dice exactamente que falta. Fallar a mitad de una corrida,
 * con la mitad de las salidas escritas, es peor que no arrancar.
 */

nextflow.enable.dsl = 2

include { FETCH_READS      } from './modules/local/fetch_reads.nf'
include { FASTP            } from './modules/local/fastp.nf'
include { QUALITY_GATE     } from './modules/local/quality_gate.nf'
include { FETCH_KRAKEN_DB  } from './modules/local/fetch_kraken_db.nf'
include { KRAKEN2          } from './modules/local/kraken2.nf'
include { MULTIQC          } from './modules/local/multiqc.nf'
include { GATE_SUMMARY     } from './modules/local/gate_summary.nf'
include { ASSERT_GATE      } from './modules/local/assert_gate.nf'
include { PROVENANCE       } from './modules/local/provenance.nf'

// ---------------------------------------------------------------------------
// Contrato del samplesheet
// ---------------------------------------------------------------------------

// Nextflow 26 usa sintaxis estricta: a nivel de script solo caben
// declaraciones, no asignaciones sueltas. De ahi que el contrato viva en
// funciones en vez de en constantes de modulo.

def columnasObligatorias() {
    return ['sample', 'fastq_1', 'fastq_2', 'md5_1', 'md5_2']
}

def esMd5(String v)  { return v ==~ /^[0-9a-f]{32}$/ }
def esIdent(String v){ return v ==~ /^[A-Za-z0-9][A-Za-z0-9._-]*$/ }

// Lista BLANCA de caracteres, no lista negra. La version anterior era
// `^(https?|ftp)://\S+$`, que admite `https://x/$(orden)y.gz`: como la URL se
// interpola en el guion de la tarea, eso era ejecucion de ordenes arbitrarias
// desde una fila del samplesheet. Comprobado que se ejecutaban de verdad.
// Los caracteres que quedan fuera —$ ` ' " ; | & < > ( ) \ y espacios— no
// hacen falta para una URL de un FASTQ, y son justo los que dan shell. La coma
// tambien queda fuera, porque el samplesheet se separa por comas.
//
// Y una leccion de esto: la primera version de la lista blanca admitia `;`
// mientras el mensaje de error decia que lo rechazaba. El mensaje mentia, y lo
// destapo la prueba que ataca con `;`. Si la lista cambia, el mensaje cambia.
def esUrl(String v)  { return v ==~ /^(https?|ftp):\/\/[A-Za-z0-9._~:\/?#\[\]@!*+=%-]+$/ }

// ---------------------------------------------------------------------------
// Guardas de arranque
// ---------------------------------------------------------------------------

def exigirParametro(String nombre, String paraQue) {
    def valor = params.containsKey(nombre) ? params[nombre] : null
    // `true` aparece cuando se escribe `--outdir` sin valor detras: Nextflow lo
    // interpreta como bandera. Tambien es un parametro ausente.
    if (valor == null || valor.toString().trim() in ['', 'null', 'true']) {
        error """
            |Falta el parametro obligatorio --${nombre} (${paraQue}).
            |
            |No hay valor por defecto y no se va a inventar uno: un defecto
            |permisivo convierte un olvido en un resultado silenciosamente malo.
            |
            |Ejemplo:  nextflow run . -profile test --${nombre} <valor>
            """.stripMargin()
    }
    return valor.toString().trim()
}

def exigirEnteroPositivo(String nombre, String paraQue) {
    def crudo = exigirParametro(nombre, paraQue)
    if (!(crudo ==~ /^[0-9]+$/) || crudo.toInteger() <= 0) {
        error "El parametro --${nombre} tiene que ser un entero positivo; recibido: '${crudo}'"
    }
    return crudo.toInteger()
}

def exigirFraccion(String nombre, String paraQue) {
    def crudo = exigirParametro(nombre, paraQue)
    def valor
    try {
        valor = crudo.toDouble()
    } catch (NumberFormatException e) {
        error "El parametro --${nombre} tiene que ser un numero entre 0 y 1; recibido: '${crudo}'"
    }
    if (valor < 0.0 || valor > 1.0) {
        error "El parametro --${nombre} tiene que estar entre 0 y 1; recibido: ${crudo}"
    }
    return valor
}

def exigirOpcion(String nombre, List admitidos, String paraQue) {
    def valor = exigirParametro(nombre, paraQue)
    if (!(valor in admitidos)) {
        error """
            |El parametro --${nombre} vale '${valor}', que no es una opcion valida.
            |  admitidas: ${admitidos.join(', ')}
            |Un valor que no se entiende no se interpreta a la baja: se para.
            """.stripMargin()
    }
    return valor
}

// ---------------------------------------------------------------------------
// Lectura estricta del samplesheet
//
// Se hace aqui, en tiempo de construccion del flujo, no dentro de un proceso.
// Asi un samplesheet mal formado se caza al arrancar y no a mitad de camino.
// ---------------------------------------------------------------------------

def leerSamplesheet(String ruta) {
    def f = file(ruta)

    if (!f.exists()) {
        error "El samplesheet no existe: ${ruta}"
    }
    if (f.size() == 0) {
        error "El samplesheet esta vacio (0 bytes): ${ruta}"
    }

    def lineas = f.readLines().findAll { it.trim() != '' }
    if (lineas.size() < 2) {
        error "El samplesheet no tiene ninguna fila de datos (solo cabecera o menos): ${ruta}"
    }

    def cabecera = lineas[0].split(',', -1).collect { it.trim() }
    def obligatorias = columnasObligatorias()
    def faltan       = obligatorias.findAll { !(it in cabecera) }
    if (faltan) {
        error """
            |Samplesheet invalido: ${ruta}
            |  columnas obligatorias que faltan : ${faltan.join(', ')}
            |  cabecera encontrada              : ${cabecera.join(', ')}
            |  cabecera esperada                : ${obligatorias.join(', ')}
            |
            |Sin md5 declarado no hay verificacion posible, asi que la columna no
            |es opcional.
            """.stripMargin()
    }

    def filas = []
    def vistos = [] as Set

    lineas[1..-1].eachWithIndex { linea, i ->
        def nLinea = i + 2   // 1 = cabecera
        def campos = linea.split(',', -1).collect { it.trim() }

        if (campos.size() != cabecera.size()) {
            error "Samplesheet ${ruta}, linea ${nLinea}: tiene ${campos.size()} campos y la cabecera declara ${cabecera.size()}"
        }

        def fila = [cabecera, campos].transpose().collectEntries()

        obligatorias.each { col ->
            if (!fila[col]) {
                error "Samplesheet ${ruta}, linea ${nLinea}: el campo '${col}' esta vacio"
            }
        }

        if (!esIdent(fila.sample as String)) {
            error "Samplesheet ${ruta}, linea ${nLinea}: identificador de muestra invalido '${fila.sample}'"
        }
        if (fila.sample in vistos) {
            error "Samplesheet ${ruta}, linea ${nLinea}: la muestra '${fila.sample}' esta repetida"
        }
        vistos << fila.sample

        ['fastq_1', 'fastq_2'].each { col ->
            if (!esUrl(fila[col] as String)) {
                error """
                    |Samplesheet ${ruta}, linea ${nLinea}: '${col}' no es una URL admisible: '${fila[col]}'
                    |  se admite http/https/ftp y caracteres corrientes de URL.
                    |  quedan fuera los que dan shell: \$ ` ' " ; | & < > ( ) \\ y espacios,
                    |  porque la URL acaba dentro del guion que ejecuta la tarea,
                    |  y la coma, porque el samplesheet se separa por comas.
                    """.stripMargin()
            }
        }
        ['md5_1', 'md5_2'].each { col ->
            if (!esMd5(fila[col] as String)) {
                error "Samplesheet ${ruta}, linea ${nLinea}: '${col}' no es un md5 de 32 digitos hexadecimales en minuscula: '${fila[col]}'"
            }
        }

        filas << fila
    }

    return filas
}

// ---------------------------------------------------------------------------
// Flujo
// ---------------------------------------------------------------------------

// ---------------------------------------------------------------------------
// PREPARACION — todo lo que ocurre antes de clasificar.
//
// Es un workflow con nombre, no una comodidad de organizacion: se puede correr
// solo, con `--etapa preparacion`, y eso es lo que permite que las pruebas de
// ataque de tests/test_ataques.py ejerciten las guardas de integridad y la
// puerta de calidad sin bajarse la base de 112 MB ni tocar la red.
//
// (El parser estricto de Nextflow 26 no admite `-entry`; el propio motor
// remite a un parametro para elegir workflow, que es lo que hace --etapa.)
// ---------------------------------------------------------------------------

workflow PREPARACION {

    main:

    def rutaSamplesheet = exigirParametro('samplesheet', 'CSV con las muestras y sus md5')
    def dirSalida       = exigirParametro('outdir',      'directorio de resultados')
    def minLecturas     = exigirEnteroPositivo('min_reads',         'puerta de calidad, en pares de lecturas')
    def longMinima      = exigirEnteroPositivo('fastp_min_length',  'longitud minima que conserva fastp')
    def calidadMinima   = exigirEnteroPositivo('fastp_min_quality', 'calidad Phred minima por base en fastp')

    // Estos tres se interpolan en el guion de las tareas o en una ruta del
    // almacen, asi que se validan como cualquier otra entrada de fuera.
    exigirEnteroPositivo('fetch_timeout', 'segundos maximos por descarga')
    exigirEnteroPositivo('fetch_retries', 'reintentos de red por descarga')

    def filas = leerSamplesheet(rutaSamplesheet)

    log.info """
        |--------------------------------------------------
        | ${workflow.manifest.name} ${workflow.manifest.version}
        |--------------------------------------------------
        | samplesheet : ${rutaSamplesheet}
        | muestras    : ${filas.size()} (${filas*.sample.join(', ')})
        | outdir      : ${dirSalida}
        | min_reads   : ${minLecturas} pares
        | fastp       : Q>=${calidadMinima}, longitud>=${longMinima}
        | perfil      : ${workflow.profile}
        |--------------------------------------------------
        """.stripMargin()

    ch_muestras = Channel
        .fromList(filas)
        .map { fila ->
            tuple([id: fila.sample], fila.fastq_1, fila.fastq_2, fila.md5_1, fila.md5_2)
        }

    // 1. Descarga con verificacion de integridad
    FETCH_READS(ch_muestras)

    // 2. Control de calidad y recorte
    FASTP(FETCH_READS.out.reads)

    // 3. Puerta de calidad: emite veredicto, no lo ejecuta
    QUALITY_GATE(FASTP.out.json)

    // Se unen lecturas recortadas y veredicto por muestra, y se separan las dos
    // ramas. Una muestra que no pasa no llega al clasificador: no produce
    // salida taxonomica, que es justo lo que la guarda promete.
    ch_ramas = FASTP.out.reads
        .join(QUALITY_GATE.out.gate)
        .map { meta, lectura_1, lectura_2, tsv ->
            def datos = tsv.readLines().findAll { it && !it.startsWith('sample\t') }
            def veredicto = datos ? datos[0].split('\t')[3] : 'SIN_VEREDICTO'
            tuple(meta, lectura_1, lectura_2, veredicto)
        }
        .branch { meta, lectura_1, lectura_2, veredicto ->
            pasan: veredicto == 'PASA'
            caen : true
        }

    ch_ramas.caen.subscribe { meta, lectura_1, lectura_2, veredicto ->
        log.warn "muestra ${meta.id} apartada por la puerta de calidad (${veredicto}): no se perfila"
    }

    // Reportar y juzgar viven AQUI, no en el flujo completo. Estaban mas
    // abajo y eso dejaba un agujero: con --etapa preparacion una muestra por
    // debajo del umbral solo producia un log.warn y la corrida salia en verde.
    // Comprobado que salia en verde. La puerta tiene que juzgar en las dos
    // etapas, porque la promesa de la guarda no depende de hasta donde llegue
    // la corrida.
    ch_gates_resumen = QUALITY_GATE.out.gate
        .map { meta, f -> f }
        .collectFile(name: 'veredictos_resumen.tsv', keepHeader: true, skip: 1, sort: true)

    GATE_SUMMARY(ch_gates_resumen, Channel.value(filas.size()))
    ASSERT_GATE(GATE_SUMMARY.out.summary)

    emit:
    reads      = ch_ramas.pasan.map { meta, lectura_1, lectura_2, veredicto -> tuple(meta, lectura_1, lectura_2) }
    fastp_json = FASTP.out.json
    gates      = QUALITY_GATE.out.gate
    checksums  = FETCH_READS.out.checksums
    versions   = FETCH_READS.out.versions.mix(FASTP.out.versions, QUALITY_GATE.out.versions)
    muestras   = Channel.value(filas.size())
}

// ---------------------------------------------------------------------------
// Flujo completo
// ---------------------------------------------------------------------------

workflow {

    def dirSalida       = exigirParametro('outdir', 'directorio de resultados')
    def rutaSamplesheet = exigirParametro('samplesheet', 'CSV con las muestras y sus md5')
    def etapa           = exigirOpcion('etapa', ['completa', 'preparacion'],
                                       'hasta donde llega la corrida')

    // En sintaxis estricta el manejador vive dentro del workflow de entrada, y
    // ahi dentro el nombre `workflow` queda sombreado y resuelve a null. Hay
    // que capturar la referencia fuera del closure.
    def corrida = workflow
    workflow.onComplete {
        log.info(corrida.success
            ? "Corrida OK. Resultados en: ${dirSalida}"
            : "Corrida FALLIDA: ${corrida.errorMessage ?: 'ver el mensaje de arriba'}")
    }

    PREPARACION()

    if (etapa == 'preparacion') {
        log.info "etapa=preparacion: se para tras la puerta de calidad; no se clasifica"
        return
    }

    def dirReferencias  = exigirParametro('reference_dir', 'donde se cachea la base 16S')
    def confianza       = exigirFraccion('kraken_confidence', 'umbral de confianza de kraken2')

    // kraken_db_md5 es ademas un componente de la ruta del almacen, asi que un
    // valor libre podria escribir fuera de reference_dir. Se valida como md5.
    def md5Base = exigirParametro('kraken_db_md5', 'checksum de la base 16S')
    if (!esMd5(md5Base)) {
        error "El parametro --kraken_db_md5 tiene que ser un md5 de 32 digitos hexadecimales en minuscula; recibido: '${md5Base}'"
    }
    def urlBase = exigirParametro('kraken_db_url', 'de donde se baja la base 16S')
    if (!esUrl(urlBase)) {
        error "El parametro --kraken_db_url no es una URL admisible: '${urlBase}'"
    }

    // 4. Clasificacion taxonomica contra la base 16S fijada y verificada
    FETCH_KRAKEN_DB()
    KRAKEN2(PREPARACION.out.reads, FETCH_KRAKEN_DB.out.db)

    // 5. Informe unico de la corrida
    MULTIQC(
        PREPARACION.out.fastp_json.map { meta, j -> j }
            .mix(KRAKEN2.out.report.map { meta, r -> r })
            .collect()
    )

    // 6. Procedencia. Los veredictos ya los juzgo PREPARACION.
    ch_gates_proc = PREPARACION.out.gates
        .map { meta, f -> f }
        .collectFile(name: 'veredictos_procedencia.tsv', keepHeader: true, skip: 1, sort: true)

    ch_versiones = PREPARACION.out.versions
        .mix(KRAKEN2.out.versions, MULTIQC.out.versions)
        .map { it.text }
        .unique()
        .collectFile(name: 'versions.yml', sort: true)

    ch_checksums = PREPARACION.out.checksums
        .mix(FETCH_KRAKEN_DB.out.checksum)
        .collectFile(name: 'checksums.tsv', keepHeader: true, skip: 1, sort: true)

    ch_meta_corrida = Channel.of(
        """
        |pipeline: ${workflow.manifest.name}
        |version: ${workflow.manifest.version}
        |perfil: ${workflow.profile}
        |orden: "${workflow.commandLine.replace('"', '\\"')}"
        |sesion: ${workflow.sessionId}
        |inicio: ${workflow.start}
        |motor: ${nextflow.version}
        |revision: ${workflow.commitId ?: 'sin control de versiones'}
        """.stripMargin().trim()
    ).collectFile(name: 'run_meta.yml')

    ch_parametros = Channel.of(
        """
        |samplesheet: ${rutaSamplesheet}
        |referencias: ${dirReferencias}
        |min_reads: ${params.min_reads}
        |fastp_min_length: ${params.fastp_min_length}
        |fastp_min_quality: ${params.fastp_min_quality}
        |kraken_confidence: ${confianza}
        |kraken_db_url: ${params.kraken_db_url}
        |kraken_db_md5: ${params.kraken_db_md5}
        |kraken_db_dir: ${params.kraken_db_dir}
        """.stripMargin().trim()
    ).collectFile(name: 'params.yml')

    PROVENANCE(ch_meta_corrida, ch_parametros, ch_versiones, ch_checksums, ch_gates_proc)
}
