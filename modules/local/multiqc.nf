/*
 * MULTIQC — un informe por corrida con lo de fastp y lo de kraken2.
 */

process MULTIQC {

    container "${params.container_multiqc}"
    conda     "${params.conda_multiqc}"

    publishDir "${params.outdir}/multiqc", mode: 'copy'

    input:
    path ficheros

    output:
    path "multiqc_report.html", emit: report
    path "multiqc_report_data", emit: data
    path "versions.yml",        emit: versions

    script:
    """
    set -euo pipefail

    multiqc --force --no-ansi --filename multiqc_report.html .

    if [ ! -s multiqc_report.html ]; then
        echo "ERROR multiqc no dejo informe, o quedo vacio" >&2
        exit 1
    fi

    cat <<-END_VERSIONS > versions.yml
    "${task.process}":
        multiqc: \$(multiqc --version | awk '{print \$NF}')
    END_VERSIONS
    """
}
