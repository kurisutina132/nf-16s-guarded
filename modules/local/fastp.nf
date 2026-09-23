/*
 * FASTP — control de calidad y recorte, con informe JSON.
 *
 * El JSON no es decorativo: es la entrada de la puerta de calidad. De ahi que
 * sea una salida con nombre propio y no un subproducto del HTML.
 */

process FASTP {

    tag "${meta.id}"

    container "${params.container_fastp}"
    conda     "${params.conda_fastp}"

    publishDir "${params.outdir}/fastp", mode: 'copy', pattern: '*.{json,html}'

    input:
    tuple val(meta), path(lectura_1), path(lectura_2)

    output:
    tuple val(meta), path("${meta.id}_1.trim.fastq.gz"), path("${meta.id}_2.trim.fastq.gz"), emit: reads
    tuple val(meta), path("${meta.id}.fastp.json"),                                          emit: json
    path "${meta.id}.fastp.html",                                                            emit: html
    path "versions.yml",                                                                     emit: versions

    script:
    """
    set -euo pipefail

    fastp \\
        --in1 ${lectura_1} --in2 ${lectura_2} \\
        --out1 ${meta.id}_1.trim.fastq.gz \\
        --out2 ${meta.id}_2.trim.fastq.gz \\
        --json ${meta.id}.fastp.json \\
        --html ${meta.id}.fastp.html \\
        --qualified_quality_phred ${params.fastp_min_quality} \\
        --length_required ${params.fastp_min_length} \\
        --detect_adapter_for_pe \\
        --thread ${task.cpus}

    # fastp puede terminar con codigo 0 y dejar un JSON a medias si el disco se
    # llena. La puerta de calidad depende de ese fichero, asi que se comprueba
    # aqui y no alli.
    if [ ! -s "${meta.id}.fastp.json" ]; then
        echo "ERROR [${meta.id}] fastp no dejo informe JSON, o quedo vacio" >&2
        exit 1
    fi

    cat <<-END_VERSIONS > versions.yml
    "${task.process}":
        fastp: \$(fastp --version 2>&1 | sed 's/^fastp //')
    END_VERSIONS
    """
}
