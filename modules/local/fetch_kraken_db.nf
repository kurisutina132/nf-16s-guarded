/*
 * FETCH_KRAKEN_DB — baja la base 16S y verifica su checksum.
 *
 * Misma guarda que para los FASTQ, por el mismo motivo: una base truncada no
 * revienta, clasifica peor. Y clasificar peor en silencio es exactamente el
 * fallo que este repositorio persigue.
 *
 * storeDir la deja cacheada fuera de work/: se baja una vez por maquina, no una
 * vez por corrida. OJO con esto, que costo un fallo real: storeDir NO ejecuta
 * el proceso si las salidas ya estan en su sitio, asi que con un storeDir fijo
 * bastaba con que la base estuviera cacheada para que la guarda de checksum no
 * llegara a correr — y una corrida con un md5 declarado falso terminaba en
 * verde. Por eso el almacen va direccionado por contenido: la ruta incluye el
 * md5 declarado, de modo que cambiarlo obliga a bajar y verificar otra vez.
 *
 * Residuo conocido: esto protege contra un md5 declarado distinto, no contra
 * alguien que corrompa a mano los ficheros ya desplegados en el almacen.
 */

process FETCH_KRAKEN_DB {

    tag "${params.kraken_db_dir}"

    storeDir "${params.reference_dir}/${params.kraken_db_md5}"

    container "${params.container_fetch}"
    conda     "${params.conda_fetch}"

    output:
    path "${params.kraken_db_dir}",              emit: db
    path "${params.kraken_db_dir}.checksum.tsv", emit: checksum

    script:
    """
    set -euo pipefail

    echo "[BASE] bajando ${params.kraken_db_url}"
    if ! curl --location --fail --silent --show-error \\
              --retry ${params.fetch_retries} --retry-delay 5 --retry-connrefused \\
              --retry-all-errors \\
              --max-time ${params.fetch_timeout} \\
              --output base.tgz '${params.kraken_db_url}' ; then
        echo 'ERROR no se pudo bajar la base 16S desde ${params.kraken_db_url}' >&2
        exit 1
    fi

    bytes=\$(stat -c %s base.tgz)
    md5_calculado=\$(md5sum base.tgz | awk '{print \$1}')

    if [ "\${md5_calculado}" != "${params.kraken_db_md5}" ]; then
        echo "ERROR el md5 de la base 16S NO coincide" >&2
        echo "  declarado en nextflow.config : ${params.kraken_db_md5}" >&2
        echo "  calculado sobre lo bajado    : \${md5_calculado}" >&2
        echo "  bytes recibidos              : \${bytes}" >&2
        echo "  origen                       : ${params.kraken_db_url}" >&2
        exit 1
    fi

    tar xzf base.tgz
    rm -f base.tgz

    # El tgz podria traer otra estructura en una version futura. Se comprueba
    # que esta lo que kraken2 necesita, no solo que el tar no fallo.
    for pieza in hash.k2d opts.k2d taxo.k2d ; do
        if [ ! -s "${params.kraken_db_dir}/\${pieza}" ]; then
            echo "ERROR la base descomprimida no trae ${params.kraken_db_dir}/\${pieza}" >&2
            exit 1
        fi
    done

    printf 'sample\\tfichero\\tmd5\\tbytes\\testado\\n' > "${params.kraken_db_dir}.checksum.tsv"
    printf 'base_16s\\t%s\\t%s\\t%s\\tOK\\n' \\
        "\$(basename '${params.kraken_db_url}')" "\${md5_calculado}" "\${bytes}" \\
        >> "${params.kraken_db_dir}.checksum.tsv"

    echo "[BASE] md5 OK (\${bytes} bytes), desplegada en ${params.kraken_db_dir}/"
    """
}
