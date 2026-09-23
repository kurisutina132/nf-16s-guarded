/*
 * FETCH_READS — descarga un par de FASTQ y verifica su md5 contra el declarado
 * en el samplesheet.
 *
 * Sobre --retry-all-errors: sin esa opcion, `--retry` de curl solo reintenta lo
 * que curl considera transitorio —timeouts y 5xx—, y NO reintenta el error 56
 * (EOF a mitad de transferencia), que es justo el fallo mas comun bajando de
 * un FTP publico. Se descubrio corriendo el pipeline en un clon limpio: una
 * conexion cortada tumbaba la corrida entera con tres reintentos configurados
 * que nunca llegaban a usarse.
 *
 * Por que existe esta guarda: un fichero truncado conserva el nombre correcto y
 * sigue siendo un .gz valido hasta donde llega. Sin checksum, el pipeline sigue
 * adelante y produce un resultado que parece bueno. El fallo silencioso es peor
 * que el ruidoso, asi que aqui se aborta.
 */

process FETCH_READS {

    tag "${meta.id}"

    container "${params.container_fetch}"
    conda     "${params.conda_fetch}"

    publishDir "${params.outdir}/checksums", mode: 'copy', pattern: '*.md5.tsv'

    input:
    tuple val(meta), val(url_1), val(url_2), val(md5_1), val(md5_2)

    output:
    tuple val(meta), path("${meta.id}_1.fastq.gz"), path("${meta.id}_2.fastq.gz"), emit: reads
    path "${meta.id}.md5.tsv",                                                     emit: checksums
    path "versions.yml",                                                           emit: versions

    script:
    """
    set -euo pipefail

    descargar_y_verificar () {
        url="\$1"
        destino="\$2"
        md5_declarado="\$3"

        echo "[FETCH] ${meta.id}: \${destino} <- \${url}"

        if ! curl --location --fail --silent --show-error \\
                  --retry ${params.fetch_retries} --retry-delay 5 --retry-connrefused \\
                  --retry-all-errors \\
                  --max-time ${params.fetch_timeout} \\
                  --output "\${destino}" "\${url}" ; then
            echo "ERROR [${meta.id}] la descarga fallo: \${destino}" >&2
            echo "  origen: \${url}" >&2
            exit 1
        fi

        if [ ! -s "\${destino}" ]; then
            echo "ERROR [${meta.id}] fichero VACIO tras la descarga: \${destino}" >&2
            echo "  origen: \${url}" >&2
            exit 1
        fi

        bytes=\$(stat -c %s "\${destino}")
        md5_calculado=\$(md5sum "\${destino}" | awk '{print \$1}')

        if [ "\${md5_calculado}" != "\${md5_declarado}" ]; then
            echo "ERROR [${meta.id}] el md5 NO coincide para \${destino}" >&2
            echo "  declarado en el samplesheet : \${md5_declarado}" >&2
            echo "  calculado sobre lo bajado   : \${md5_calculado}" >&2
            echo "  bytes recibidos             : \${bytes}" >&2
            echo "  origen                      : \${url}" >&2
            echo "  el fichero puede estar truncado, corrupto o no ser el que dice ser" >&2
            exit 1
        fi

        printf '%s\\t%s\\t%s\\t%s\\tOK\\n' "${meta.id}" "\${destino}" "\${md5_calculado}" "\${bytes}" \\
            >> "${meta.id}.md5.tsv"
        echo "[FETCH] ${meta.id}: \${destino} md5 OK (\${bytes} bytes)"
    }

    printf 'sample\\tfichero\\tmd5\\tbytes\\testado\\n' > "${meta.id}.md5.tsv"
    # Comillas SIMPLES a proposito: dentro de comillas dobles, bash sigue
    # expandiendo \$(...) y las comillas invertidas, y estos valores vienen del
    # samplesheet. El validador de main.nf ya rechaza comillas y metacaracteres;
    # esto es la segunda capa, por si el validador se relaja alguna vez.
    descargar_y_verificar '${url_1}' '${meta.id}_1.fastq.gz' '${md5_1}'
    descargar_y_verificar '${url_2}' '${meta.id}_2.fastq.gz' '${md5_2}' 

    cat <<-END_VERSIONS > versions.yml
    "${task.process}":
        curl: \$(curl --version | head -n1 | awk '{print \$2}')
        coreutils(md5sum): \$(md5sum --version | head -n1 | awk '{print \$NF}')
    END_VERSIONS
    """
}
