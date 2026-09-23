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

- **La CI nunca se ha ejecutado** (2026-09-22). El repositorio no se ha
  publicado, así que GitHub Actions no ha tenido ocasión de correr y el badge
  no está verde. Se cierra con el primer `push`. Sustituto local: se copiaron
  los ficheros versionables a un directorio vacío y se siguió el README desde
  cero — 55 pruebas y el pipeline completo, 3 min 54 s, en verde.
- **`containers/Dockerfile` nunca se ha construido** (2026-09-22). No hay Docker
  en la máquina donde se escribió. El trabajo `imagen` de la CI lo construye y
  comprueba que las versiones de dentro son las fijadas. Hasta ese primer
  `push`, sigue siendo la pieza sin probar.
- **El perfil `docker` no se ha ejercitado** (2026-09-22). Lo verificado en
  local es `-profile test` con las herramientas en el PATH. Al preparar la CI
  se encontró y corrigió un fallo que lo habría roto en su primer uso
  (`debian:12.11-slim` no trae `curl`), pero eso es razonamiento, no ejecución:
  lo verifica el trabajo `pipeline-completo`.

## Encontrado corriendo, no leyendo

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
