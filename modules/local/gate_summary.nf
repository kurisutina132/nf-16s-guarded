/*
 * GATE_SUMMARY — junta los veredictos y decide el destino de la corrida.
 *
 * Aqui es donde una muestra caida deja de ser una nota y pasa a ser un fallo.
 * Una corrida que termina en verde habiendo perdido muestras por el camino es
 * el fallo silencioso de siempre, con otro disfraz.
 */

process GATE_SUMMARY {

    container "${params.container_python}"
    conda     "${params.conda_python}"

    publishDir "${params.outdir}/quality_gate", mode: 'copy'

    input:
    path veredictos
    val  muestras_declaradas

    output:
    path "quality_gate_summary.tsv", emit: summary

    script:
    """
    set -euo pipefail

    gate_summary.py \\
        --veredictos ${veredictos} \\
        --esperadas ${muestras_declaradas} \\
        --out quality_gate_summary.tsv
    """
}
