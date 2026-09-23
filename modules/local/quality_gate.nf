/*
 * QUALITY_GATE — decide si una muestra sigue.
 *
 * El veredicto se emite, no se ejecuta: este proceso termina bien aunque la
 * muestra no pase. Quien aparta la muestra es el flujo, y quien impide que la
 * corrida acabe en verde con muestras caidas es GATE_SUMMARY.
 *
 * Separarlo asi tiene un motivo: si la puerta abortase la corrida en la primera
 * muestra mala, con veinte muestras harian falta veinte corridas para enterarse
 * de cuales fallan. Emitir veredictos y fallar al final da la lista completa de
 * una vez, y sigue sin permitir un verde falso.
 */

process QUALITY_GATE {

    tag "${meta.id}"

    container "${params.container_python}"
    conda     "${params.conda_python}"

    publishDir "${params.outdir}/quality_gate", mode: 'copy', pattern: '*.gate.tsv'

    input:
    tuple val(meta), path(informe_fastp)

    output:
    tuple val(meta), path("${meta.id}.gate.tsv"), emit: gate
    path "versions.yml",                          emit: versions

    script:
    """
    set -euo pipefail

    quality_gate.py \\
        --json ${informe_fastp} \\
        --sample ${meta.id} \\
        --min-reads ${params.min_reads} \\
        --out ${meta.id}.gate.tsv

    cat <<-END_VERSIONS > versions.yml
    "${task.process}":
        python: \$(python3 --version | sed 's/^Python //')
    END_VERSIONS
    """
}
