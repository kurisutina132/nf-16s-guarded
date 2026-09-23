/*
 * KRAKEN2 — clasificacion taxonomica del amplicon contra la base 16S.
 *
 * Se guarda el informe por taxon, no la asignacion por lectura: el segundo pesa
 * mas que los propios FASTQ y no se usa aguas abajo. Si hiciera falta, la
 * corrida es reproducible a partir de la procedencia.
 *
 * SIN --report-minimizer-data a proposito. Esa opcion anade dos columnas utiles
 * (minimizadores distintos, que ayudan a oler asignaciones espurias) pero
 * convierte el informe de 6 columnas en uno de 8, y eso lo deja fuera del
 * formato que esperan Bracken y la mayoria de los lectores de informes de
 * kraken2. Un fichero que se llama informe de kraken2 tiene que poder leerse
 * como tal.
 */

process KRAKEN2 {

    tag "${meta.id}"

    container "${params.container_kraken2}"
    conda     "${params.conda_kraken2}"

    publishDir "${params.outdir}/kraken2", mode: 'copy', pattern: '*.report.txt'

    input:
    tuple val(meta), path(lectura_1), path(lectura_2)
    path base

    output:
    tuple val(meta), path("${meta.id}.kraken2.report.txt"), emit: report
    path "versions.yml",                                    emit: versions

    script:
    """
    set -euo pipefail

    kraken2 \\
        --db ${base} \\
        --paired \\
        --threads ${task.cpus} \\
        --confidence ${params.kraken_confidence} \\
        --report ${meta.id}.kraken2.report.txt \\
        --output /dev/null \\
        ${lectura_1} ${lectura_2}

    if [ ! -s "${meta.id}.kraken2.report.txt" ]; then
        echo "ERROR [${meta.id}] kraken2 no dejo informe, o quedo vacio" >&2
        exit 1
    fi

    cat <<-END_VERSIONS > versions.yml
    "${task.process}":
        kraken2: \$(kraken2 --version | head -n1 | awk '{print \$NF}')
        base_16s: "${params.kraken_db_url}"
        confianza: ${params.kraken_confidence}
    END_VERSIONS
    """
}
