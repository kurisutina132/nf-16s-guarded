# Pendientes

Lo que falta o está a medias, con fecha. Vive aquí y no en la cabeza de nadie:
una tarea que solo existe en una conversación se pierde en cuanto se cierra.

## Revisado

- **Etapas [B] y [C] revisadas el 2026-09-22.** Salieron nueve defectos reales,
  todos corregidos y con prueba de regresión. Los dos graves: ejecución de
  órdenes arbitrarias desde una fila del samplesheet, y `storeDir` saltándose
  la guarda de checksum de la base. Ambos se reprodujeron antes de arreglarlos
  y se volvieron a atacar después. Los detalles, en «decisiones de diseño» del
  README.

## Sin verificar

- **La caché plana de referencias quedó huérfana** (2026-09-22). Al pasar el
  almacén a direccionado por contenido, un `${reference_dir}/16S_SILVA138_k2db`
  de antes ya no se encuentra y provoca una descarga de 112 MB. No hay
  migración automática a propósito: mover ficheros por la cara en el directorio
  de otro es peor que una descarga.
- **`_sin_procesos_lanzados` mira dos marcas de motor** (2026-09-22): la de
  Nextflow 26 y la de las series 24/25, porque el manifiesto admite >=24.04.0.
  Sólo se ha podido ejercitar contra la 26, que es la instalada aquí.

- **El perfil `docker` corre a medias** (2026-09-23). El primer `push` lo
  ejecutó por primera vez y murió en `FETCH_KRAKEN_DB`. Corregido; queda
  pendiente verlo llegar al final.

## Herramientas que mienten

- **`gh run watch --exit-status` salió con código 0 con dos trabajos en rojo**
  (2026-09-23). Si se hubiera creído ese código, se habría dado la CI por
  verde. **El estado de la CI se lee de la API, por trabajo (`conclusion`), y
  nunca del código de salida de `gh run watch`:**

      gh api repos/<owner>/<repo>/actions/runs/<id>/jobs --jq '.jobs[].conclusion'

  Si algún día se automatiza la comprobación del estado de la CI, que sea por
  ahí.

## Encontrado corriendo, no leyendo

- **Dos imágenes elegidas leyendo, dos corridas rojas** (2026-09-23).
  `debian:12.11-slim` no trae `curl`; `buildpack-deps:bookworm-curl` no trae
  `ps`, que Nextflow exige dentro del contenedor, y la tarea murió sin
  imprimir nada. Lo que un Dockerfile enumera no es lo que la imagen tiene. De
  ahí la regla: lo que la imagen provee se comprueba **construyéndola y
  ejecutándola**, y hay guarda con ataque (`tests/test_imagen.py`).
- **Una comprobación de conformidad que ocultaba el motivo** (2026-09-23).
  `bash -lc '… 2>&1 | grep -q …'`: el shell de login reescribía `PATH` y el
  `grep -q` se tragaba el `command not found`. Falló con cero líneas de salida.

- **`--retry` de curl no reintentaba el error 56** (2026-09-22). Tres reintentos
  configurados que nunca se usaban; una conexión cortada a mitad de descarga
  tumbaba la corrida entera. Apareció al correr el pipeline en un clon limpio.
  Corregido con `--retry-all-errors`. Vale la pena recordarlo: la revisión de
  código no lo vio, y las pruebas de ataque tampoco, porque sirven sus ficheros
  desde `127.0.0.1` y ahí no se corta nada.

## Decisiones tomadas que conviene revisitar

- **La base 16S está congelada en 2020-03-26** y su md5 es un checksum
  calculado en local, no publicado por el proveedor. Ver «Los datos» en el
  README. Para un estudio real, actualizar la base.
- **Las pruebas de ataque corren sobre el ejecutor local**, porque sirven sus
  fixtures desde `127.0.0.1` y un contenedor no vería ese puerto sin red de
  anfitrión. Si la CI las corre con un perfil de contenedor, hay que resolver
  eso primero. Cierra con la etapa [D].
