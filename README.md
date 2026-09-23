# nf-16s-guarded

[![ci](https://github.com/kurisutina132/nf-16s-guarded/actions/workflows/ci.yml/badge.svg)](https://github.com/kurisutina132/nf-16s-guarded/actions/workflows/ci.yml)

Cada guarda de este pipeline tiene un caso de ataque, y se ha visto fallar antes
de darla por buena.

Pipeline de amplicón 16S en Nextflow DSL2 sobre dos muestras públicas de ENA.
Descarga los FASTQ y verifica su integridad, los pasa por control de calidad y
una puerta de lecturas mínimas, y perfila la composición taxonómica.
Cada salida lleva anotado qué versión de qué herramienta la produjo.

> **Estado: la CI ya ha corrido, y su primera corrida salió roja.** Encontró
> dos cosas que ninguna revisión de código había visto, las dos por haber
> elegido una imagen leyendo su Dockerfile en vez de ejecutándola: la imagen de
> descarga no traía `ps`, que Nextflow necesita dentro del contenedor, y la
> comprobación de conformidad de la propia imagen se tragaba su diagnóstico y
> fallaba sin imprimir nada. Ambas corregidas, y convertidas en guarda con su
> ataque. Lo que quede abierto vive en
> [docs/PENDIENTES.md](docs/PENDIENTES.md), con fecha.

## Correrlo

```bash
make image                                   # una vez: construye la imagen
nextflow run main.nf -profile test,docker
```

Sin construir nada: `-profile test,conda`.

El perfil `test` trae el samplesheet de ejemplo. La primera corrida descarga 34 MB de lecturas desde ENA
y 112 MB de base de referencia; la base queda cacheada fuera de `work/` y no se
vuelve a bajar. En una máquina limpia, de cero a resultados: **unos 4 minutos**.

## Puesta en marcha (una vez por clon)

```bash
make setup                                        # hooks + identidad local
git config --local user.email "<tu correo>"       # sólo si vas a commitear
make test                                         # pruebas sin red
```

`make setup` deja la identidad de los commits fijada **en local**, no en global,
para no tocar la de ningún otro repositorio de la máquina. Deja el correo a
propósito sin poner: es una decisión de cada quien, y `make test` se pone rojo
hasta que lo pongas, con el comando exacto en el mensaje.

Si sólo quieres mirar el repositorio sin intención de commitear, lo que importa
es `make test-procesos` y `make test-ataques`: ninguno pide identidad ni red.

`make setup` hace falta porque `core.hooksPath` **es local de cada clon y no
viaja con el repositorio**: el directorio `.githooks/` sí se clona, pero sin esa
línea los hooks están y no corren.

## Guardas

Ninguna guarda tiene defecto permisivo. Un parámetro ausente no se asume: el
pipeline se para y dice cuál falta.

Todas las filas de esta tabla son pruebas ejecutables. Las que atacan el
pipeline entero están en [`tests/test_ataques.py`](tests/test_ataques.py)
(`make test-ataques`, 16 pruebas en unos 80 segundos); las dos últimas filas
—las que atacan la lógica de la puerta sin levantar el pipeline— viven en
[`tests/test_quality_gate.py`](tests/test_quality_gate.py), con el resto de
pruebas de unidad. Las de ataque son herméticas: generan sus propios FASTQ
sintéticos, los sirven desde `127.0.0.1` y usan una base 16S de relleno, así
que no tocan la red ni bajan los 112 MB de la base real.

Y se han comprobado por el otro lado: falsificando cada guarda una por una
—quitar la comparación de md5, quitar la comprobación de tamaño, dejar de
exigir columnas, hacer que la puerta apruebe siempre— y verificando que su
prueba se pone **roja**. Las seis mutaciones se cazaron. Una prueba que nunca
ha fallado no protege nada.

| Guarda | Qué la ataca | Qué mensaje sale |
|---|---|---|
| md5 del fichero descargado | Cambiar un md5 del samplesheet por ceros | `ERROR [MUESTRA] el md5 NO coincide para MUESTRA_1.fastq.gz` + declarado, calculado, bytes recibidos y origen. No se publica ningún checksum |
| Fichero truncado | Servir el 60 % de un `.gz` con el md5 del entero | Mismo error de md5, con `bytes recibidos` reales y `el fichero puede estar truncado, corrupto o no ser el que dice ser` |
| Fichero vacío | Servidor que responde 200 con 0 bytes | `ERROR [VACIA] fichero VACIO tras la descarga: VACIA_1.fastq.gz` + origen |
| Descarga fallida | URL que no existe | `curl: (22) The requested URL returned error: 404` + `ERROR [NOHAY] la descarga fallo: NOHAY_1.fastq.gz` |
| Columna ausente en el samplesheet | Recortar la columna `md5_2` | `Samplesheet invalido: … columnas obligatorias que faltan : md5_2`, con cabecera encontrada y esperada. Falla **al arrancar**: no se lanza ni una tarea |
| md5 mal formado | `noesunmd5` en la columna | `'md5_1' no es un md5 de 32 digitos hexadecimales en minuscula`, con fichero y línea |
| URL que no es URL | Una ruta local en `fastq_1` | `'fastq_1' no es una URL http/https/ftp` |
| Muestra repetida | Dos filas con el mismo identificador | `la muestra 'IGUAL' esta repetida` |
| Campo vacío | Dejar `fastq_1` en blanco | `el campo 'fastq_1' esta vacio` |
| Samplesheet sin filas | Sólo cabecera | `no tiene ninguna fila de datos` |
| Parámetro obligatorio ausente | Correr sin `--min_reads` | `Falta el parametro obligatorio --min_reads (puerta de calidad…)` y `no se va a inventar uno` |
| Valor de parámetro no admitido | `--etapa perfilado` | `vale 'perfilado', que no es una opcion valida. admitidas: completa, preparacion` |
| Ejecución de órdenes desde el samplesheet | URL con `$(id)`, backtick, `;`, `\|`, `&`, `>` o comilla | `'fastq_1' no es una URL admisible` + la lista de caracteres excluidos y por qué. Falla al arrancar |
| Base cacheada con md5 cambiado | Dos corridas con el mismo almacén, la segunda con otro md5 | `ERROR el md5 de la base 16S NO coincide`. Antes esto pasaba en verde |
| Procedencia que se contradice | md5 declarado ≠ md5 verificado | `ERROR la procedencia se contradice: el md5 declarado para la base (…) no coincide con el verificado (…)`, y **no se escribe el documento** |
| Veredictos repetidos o de más | Dos veredictos para la misma muestra | columna `inconsistencias` > 0 en el resumen, y `LA CORRIDA NO SE DA POR BUENA: N inconsistencia(s)` |
| Resumen con cuentas que no cuadran | `no_pasan=1` con detalle sin caídas | `ERROR el resumen se contradice: dice no_pasan=1 pero el detalle trae 0 fila(s) caída(s)` |
| La imagen no provee lo que el pipeline usa | Construir una imagen derivada **sin `ps`** y pasarle la guarda | `la imagen nf-16s-guarded:0.1.0 no provee: ps`, con la salida real de la imagen. La guarda ejecuta la imagen: `docker run --rm <imagen> sh -c 'command -v curl tar ps'` |
| md5 de la base de referencia | Declarar un md5 de efes | `ERROR el md5 de la base 16S NO coincide` + declarado, calculado, bytes y origen |
| Base descomprimida incompleta | Tarball sin `hash.k2d` | `ERROR la base descomprimida no trae 16S_SILVA138_k2db/hash.k2d` |
| Puerta de lecturas mínimas | Muestra de 50 pares con `--min_reads 1000` | `muestra POCAS apartada por la puerta de calidad (NO_PASA): no se perfila`, y después `LA CORRIDA NO SE DA POR BUENA: POCAS: solo 50 pares tras el filtrado, por debajo del umbral 1000: faltan 950`. **No existe `results/kraken2/`**, y el resumen sí se publica |
| Informe de fastp vacío o con otra forma | JSON truncado, o sin `summary.after_filtering.total_reads` | `ERROR [<muestra>] fastp no dejó informe JSON, o quedó vacío` / `el informe de fastp no trae summary.after_filtering.total_reads` |
| Umbral de calidad no positivo | `--min_reads 0` | `--min-reads tiene que ser un entero positivo` — un umbral de 0 es un defecto permisivo disfrazado de configuración |

**El caso positivo, que es la mitad que se olvida**, también es una prueba:
`test_muestra_buena_produce_exactamente_las_salidas_esperadas` compara el
conjunto **exacto** de ficheros producidos contra el esperado —falla tanto si
falta uno como si sobra— y además revisa el contenido: que los dos md5 son los
correctos, que las dos líneas dicen `OK`, y que el veredicto es `PASA` con los
2.000 pares que entraron.

Sobre las dos muestras del samplesheet, la corrida completa da: 73.135 y 93.960
pares tras el recorte (umbral 50.000), y 97,1 % y 98,0 % de lecturas
clasificadas, con *Bacteroidota* y *Firmicutes* dominando — lo que se espera de
16S fecal humano.

Un detalle que salió al atacar: un servidor que devuelve una página de error
con código 200 **no** cae en la guarda de fichero vacío —el cuerpo no está
vacío— sino en la de md5. Las dos guardas hacen falta, y la de md5 es la que
cubre el caso general de «esto no es lo que dice ser».

## Los datos

Estudio **PRJEB6070** — Zeller G, Tap J, Voigt AY, *et al.* «Potential of fecal
microbiota for early-stage detection of colorectal cancer». *Molecular Systems
Biology* 10:766 (2014). doi:[10.15252/msb.20145645](https://doi.org/10.15252/msb.20145645),
PMID 25432777.

Amplicón · metagenómico · emparejado · Illumina MiSeq · *Homo sapiens*.

| Run | Lecturas | Bases | Ficheros |
|---|---|---|---|
| ERR674093 | 74.651 | 37.474.802 | 6.519.806 B + 7.764.574 B |
| ERR674112 | 96.928 | 48.657.856 | 9.165.725 B + 10.749.547 B |

Cifras y md5 tomados de la API de ENA, no de memoria:

```
https://www.ebi.ac.uk/ena/portal/api/filereport?accession=PRJEB6070&result=read_run&fields=run_accession,read_count,base_count,fastq_bytes,fastq_md5,instrument_model,library_strategy&format=tsv
```

### La base de referencia

Colección 16S de kraken2 construida sobre **SILVA 138**, congelada el
2020-03-26:

```
https://genome-idx.s3.amazonaws.com/kraken/16S_Silva138_20200326.tgz
117.933.493 B   md5 94ecb2c851f3e4f02335559d42013f0f
```

**Ese md5 no lo publica el proveedor.** La página que sirve estas colecciones
da md5 para las grandes, pero no para las 16S. El que está fijado en
`nextflow.config` se calculó en local sobre la descarga el 2026-09-22. Es una
afirmación más débil que la de los FASTQ —que vienen del API de ENA— y conviene
decirlo: no prueba que la descarga original fuera correcta, pero fija el
artefacto desde ese momento, y cualquier cambio posterior aborta la corrida.

Los FASTQ **no se versionan**: el samplesheet lleva la URL y el md5, y el
pipeline los descarga. El repositorio pesa unos pocos MB.

## Decisiones de diseño

**El md5 se declara en el samplesheet, no se descubre.** Una columna de
checksum es una columna más que mantener, y se descartó la alternativa cómoda
—bajar el md5 de ENA en tiempo de corrida— porque entonces la verificación
compara la descarga contra la misma fuente que la sirvió: si ENA sirve un
fichero truncado, el md5 que ENA devuelve en ese momento puede cuadrar igual.
Un checksum versionado en el repositorio es una afirmación fechada contra la
que se puede fallar.

**El samplesheet se valida al construir el flujo, no dentro de un proceso.**
Validar dentro de un proceso significa que la columna que falta se descubre
cuando ya hay tareas lanzadas y salidas a medio escribir. Aquí el fichero se
lee y se comprueba entero antes de lanzar la primera tarea.

**La imagen del pipeline es la del repositorio, no la de un tercero.** Los
pasos de descarga corrían en imágenes públicas elegidas **leyendo** lo que
decían traer. Dos corridas rojas seguidas: `debian:12.11-slim` no trae `curl`,
y `buildpack-deps:bookworm-curl` —cuyo Dockerfile oficial lista
`ca-certificates curl gnupg netbase sq wget`, todo cierto— no trae `ps`, que
Nextflow exige dentro del contenedor para recoger métricas. La tarea murió sin
imprimir una sola línea. Lo que un Dockerfile enumera no es lo que la imagen
tiene. Ahora esos pasos usan la imagen de `containers/`, que además deja de ser
una pieza que sólo se construye, y `containers/env.yml` es la única fuente de
versiones del repositorio.

De ahí sale una regla, y es una guarda: **lo que la imagen provee se comprueba
construyéndola y ejecutándola**, nunca leyendo un Dockerfile.
[`tests/test_imagen.py`](tests/test_imagen.py) ejecuta la imagen y pregunta por
cada herramienta **una por una**, exige también el paquete de certificados,
comprueba que **todas** las imágenes declaradas traen `ps` —la generalización
del fallo real— y se ataca a sí misma construyendo una imagen derivada sin `ps`
para verse en rojo.

Un aviso que salió al escribirla, y que es la misma lección otra vez: la forma
corta de esa comprobación **no sirve**.

```
$ docker run --rm <imagen> sh -c 'command -v curl tar esto_no_existe'
/opt/conda/bin/curl
$ echo $?
0
```

`/bin/sh` es dash, y su `command -v` sólo mira el primer argumento: aprueba una
imagen a la que le falten las demás, y sólo falla si la ausente va primera. Hay
que preguntar de una en una, que es lo que hace la prueba.

**Una comprobación de conformidad no puede ocultar el motivo del
incumplimiento.** La del trabajo `imagen` era
`bash -lc '… 2>&1 | grep -q …'` y falló con **cero líneas de salida**. Dos
errores en una línea: `bash -l` relee `/etc/profile` y reescribe `PATH`,
llevándose por delante el `/opt/conda` que fija el Dockerfile; y el
`2>&1 | grep -q` mandaba el `command not found` a `grep`, que lo silenciaba.
Es exactamente el patrón contra el que existe este repositorio, y me lo hice a
mí mismo. Sin `-l`, y stderr se imprime.

**Los reintentos de red hay que pedirlos bien.** `--retry` de curl sólo
reintenta lo que curl considera transitorio —timeouts y 5xx— y **no** reintenta
el error 56, un EOF a mitad de transferencia, que es justo el fallo más común
bajando de un FTP público. Con tres reintentos configurados que nunca llegaban
a usarse, una conexión cortada tumbaba la corrida entera. Lo destapó correr el
pipeline en un clon limpio, no una revisión de código: hace falta
`--retry-all-errors`, y ahora está.

**`errorStrategy = 'terminate'`, sin reintentos.** Reintentar una guarda que
falla solo consigue que falle tres veces más tarde. Los reintentos viven en
`curl` (fallos de red, que sí son transitorios), no en el proceso.

**Sintaxis estricta de Nextflow.** Obliga a que nada quede a nivel de script
suelto. Costó reescribir las constantes como funciones y mover el manejador
`onComplete` dentro del workflow, pero deja el fichero sin estado global.

**Versiones fijadas, y comprobadas contra el registro antes de escribirlas.**
Una etiqueta que no existe rompe el clon limpio de otro, no el mío. Las
etiquetas de este repositorio se consultaron contra Docker Hub, quay.io y
anaconda.org; la primera candidata de `fastp` que se probó no existía.

Las imágenes base van **por digest**, no por etiqueta: `bookworm-curl` y
`3.12.7-slim` se reconstruyen cada pocos días con el mismo nombre y otro
contenido. Y la imagen de descarga era `debian:12.11-slim`, que son 28 MB y
**no trae curl**: el perfil de contenedores habría fallado en su primer uso con
`curl: not found`. Nadie lo había ejercitado nunca; salió al preparar la CI.

**Clasificación con kraken2 contra una base 16S pequeña, no inferencia de
ASV.** kraken2 casa k-meros exactos contra una referencia versionada: es
determinista, cabe en 112 MB y clasifica las dos muestras en segundos, así que
entra en un runner público sin trucos. Lo que se descartó:

- *Inferencia de ASV (tipo DADA2)*: mejor resolución —distingue variantes de un
  solo nucleótido— pero aprende un modelo de error **por corrida**, de modo que
  el resultado de una muestra depende de con quién se la procese. Para un
  repositorio cuyo argumento es la reproducibilidad, esa dependencia es una
  propiedad incómoda, y además no cabe en el presupuesto de tiempo de la CI.
- *Suites completas tipo QIIME2*: contenedor grande y formato de artefactos
  propio; mucha maquinaria para seis procesos.
- *Alineamiento contra una referencia propia*: habría que construir y versionar
  la referencia, que es justo el trabajo que la colección 16S ya publicada
  ahorra.

Lo que hay que decir de la opción elegida, porque un revisor lo va a buscar: la
base está **congelada en 2020** y la taxonomía se ha movido desde entonces, y
kraken2 sobre amplicón 16S es fiable a nivel de género, no de especie. Para un
estudio real se actualizaría la base; para demostrar el andamiaje, una base
fijada y verificable es exactamente lo que se quiere.

**`--confidence 0.1`, no el valor por defecto.** El defecto de kraken2 es 0, que
acepta una asignación con un solo k-mero coincidente. Es un defecto permisivo, y
aquí los defectos permisivos no pasan: el valor se declara en la configuración y
sin él el pipeline no arranca.

**La puerta juzga en las dos etapas, no sólo en la completa.** Una revisión
encontró que con `--etapa preparacion` una muestra por debajo del umbral
producía sólo un aviso y la corrida salía **en verde**. Se comprobó que salía
en verde. `GATE_SUMMARY` y `ASSERT_GATE` viven ahora dentro de `PREPARACION`:
la promesa de una guarda no puede depender de hasta dónde llegue la corrida.

**El almacén de referencias va direccionado por contenido.** `storeDir` no
ejecuta el proceso si sus salidas ya están en su sitio — así que con una ruta
fija bastaba con tener la base cacheada para que la guarda de checksum **no
llegara a correr**, y una corrida con un md5 declarado falso terminaba en
verde, con una procedencia que afirmaba un md5 que no era el de la base usada.
La ruta del almacén incluye ahora el md5 declarado. Efecto secundario: quien
tuviera una caché plana de una versión anterior se la encuentra huérfana y
vuelve a bajar 112 MB una vez.

**Las URL del samplesheet se validan por lista blanca de caracteres.** El
validador anterior aceptaba cualquier cosa sin espacios, y la URL se interpola
en el guion de la tarea: una fila del samplesheet podía ejecutar órdenes
arbitrarias, y se comprobó que las ejecutaba. Dos capas ahora: lista blanca al
validar, y comillas simples en el guion. Lo mismo para `kraken_db_url`, y
`kraken_db_md5` se valida como md5 porque además es un componente de ruta.

**Reportar y juzgar son dos procesos distintos.** La primera versión tenía un
solo proceso que escribía el resumen de la puerta *y* tumbaba la corrida. Al
atacarlo apareció el fallo: Nextflow no publica las salidas de una tarea
fallida, así que cuando una muestra se caía desaparecía justo el fichero que
explicaba cuál y por qué. Ahora `GATE_SUMMARY` escribe y siempre termina bien, y
`ASSERT_GATE` dictamina aparte.

**La puerta emite veredicto, no aborta en la primera muestra mala.** Con veinte
muestras, abortar en la primera obligaría a veinte corridas para enterarse de
cuáles fallan. Se recogen todos los veredictos, se aparta del clasificador a las
que no pasan —no generan salida taxonómica— y la corrida termina en rojo con la
lista completa. No permite un verde falso y da la información de una vez.

## CI

Cuatro trabajos en cada `push`, de más barato a más caro, en
[`.github/workflows/ci.yml`](.github/workflows/ci.yml):

| Trabajo | Qué demuestra |
|---|---|
| `pruebas-rapidas` | Que ninguna superficie menciona la herramienta con que se escribió, que la historia está firmada por quien debe, y que cada pieza del pipeline hace lo que dice. Sin red, sin contenedores, segundos |
| `imagen` | Que `containers/Dockerfile` **construye**, y que las herramientas de dentro responden con las versiones fijadas — no con las que el solver haya decidido |
| `ataques` | Las 18 pruebas de ataque. Sin red: sirven sus propios FASTQ desde `127.0.0.1` |
| `pipeline-completo` | El pipeline entero con `-profile test,docker` sobre las dos muestras reales de ENA, y después comprueba que están las salidas prometidas y que las dos muestras pasaron la puerta |

El último es el que dice el badge. Si ese no pasa, el repositorio no sirve para
lo que se hizo.

Dos detalles que no son adorno:

- **Las acciones van fijadas por SHA de commit, no por etiqueta.** `@v7` se
  mueve igual que se mueve `:latest`. Una dependencia que puede cambiar sola no
  está fijada, sólo lo parece.
- **`ataques` corre sobre el ejecutor local, no con contenedores.** Las pruebas
  sirven sus fixtures desde `127.0.0.1`, que un contenedor no ve sin red de
  anfitrión. Las herramientas se instalan en el runner con los mismos pines que
  la imagen: `containers/env.yml` es la única fuente de versiones.

## Atribución

Ningún artefacto de este repositorio menciona con qué herramienta se escribió:
ni mensajes de commit, ni documentación, ni comentarios, ni etiquetas de
imagen, ni ficheros de procedencia, ni workflows de CI.

Eso no es una declaración de intenciones, que nadie comprueba. Son dos capas
deterministas:

- `.githooks/commit-msg` limpia el mensaje de commit. Es quirúrgico: borra solo
  patrones de atribución conocidos. Un mensaje que menciona un fichero legítimo
  del repositorio en el cuerpo sale intacto; se probó.
- `tests/test_atribucion.py` barre el árbol entero —ficheros versionados y sin
  versionar, sus nombres, y los mensajes de toda la historia— y falla si
  aparece alguno. El hook cubre los commits; esta prueba cubre el resto.

- `tests/test_autoria.py` lleva la misma idea a la autoría: comprueba que
  todos los commits de la historia —autor y committer, nombre y correo— están
  firmados por la identidad esperada, con el dominio en lista blanca. Un
  historial mal firmado se arregla reescribiéndolo, así que se pone rojo antes
  de publicar y no después.

La prueba de contenido arma sus patrones por trozos, de modo que el fichero no contiene
ninguna de las cadenas que persigue y puede escanearse a sí mismo. Tiene una
sola exclusión, el propio hook, que necesita nombrar los patrones para poder
borrarlos; una tercera prueba comprueba que esa lista de exclusiones no crece.

## Licencia

MIT. Ver [LICENSE](LICENSE).
