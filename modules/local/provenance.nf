/*
 * PROVENANCE — un fichero por corrida con lo que hizo falta para reproducirla.
 *
 * Versiones, parametros, checksums y veredictos. Si un resultado no puede
 * explicar de donde sale, no es un resultado: es una opinion.
 */

process PROVENANCE {

    container "${params.container_python}"
    conda     "${params.conda_python}"

    publishDir "${params.outdir}/provenance", mode: 'copy'

    input:
    path metadatos
    path parametros
    path versiones
    path checksums
    path veredictos

    output:
    path "provenance.yml", emit: provenance

    script:
    """
    set -euo pipefail

    provenance.py \\
        --run-meta ${metadatos} \\
        --params ${parametros} \\
        --out provenance.yml \\
        --versions ${versiones} \\
        --checksums ${checksums} \\
        --gates ${veredictos}
    """
}
