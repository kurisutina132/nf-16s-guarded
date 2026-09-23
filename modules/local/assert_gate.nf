/*
 * ASSERT_GATE — dictamina sobre el resumen de la puerta.
 *
 * Existe separado de GATE_SUMMARY por un motivo concreto, descubierto
 * atacando: cuando el proceso que escribe el resumen era tambien el que
 * fallaba, Nextflow no publicaba su salida — porque no publica salidas de
 * tareas fallidas — y se perdia justo el fichero que explicaba que muestra se
 * habia caido. Reportar y juzgar son dos trabajos.
 */

process ASSERT_GATE {

    container "${params.container_python}"
    conda     "${params.conda_python}"

    input:
    path resumen

    script:
    """
    set -euo pipefail
    assert_gate.py --resumen ${resumen}
    """
}
