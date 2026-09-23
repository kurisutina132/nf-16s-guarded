# Puesta en marcha y pruebas. Una orden por cosa.

.PHONY: setup image test test-atribucion test-autoria test-procesos test-ataques test-imagen test-todo run clean

## Activa los hooks versionados. core.hooksPath NO se clona: es configuracion
## local de cada clon, asi que esto hay que correrlo una vez por clon.
setup:
	@chmod +x .githooks/*
	@git config core.hooksPath .githooks
	@git config --local user.name "kurisutina132"
	@echo "hooks activados: core.hooksPath = $$(git config core.hooksPath)"
	@echo "identidad local : $$(git config --local --get user.name) <$$(git config --local --get user.email || echo 'PENDIENTE')>"

## Construye la imagen del pipeline. Hace falta para -profile docker.
image:
	@docker build -f containers/Dockerfile -t nf-16s-guarded:0.1.0 .

## Rapido: todo lo que no necesita Nextflow.
test: test-atribucion test-autoria test-procesos

## Todo, incluidas las pruebas de ataque al pipeline.
test-todo: test test-ataques

test-atribucion:
	@python3 tests/test_atribucion.py

test-autoria:
	@python3 tests/test_autoria.py

## Pruebas de las piezas del pipeline: puerta de calidad, resumen, dictamen y
## procedencia. Informes sinteticos, sin descargar nada.
test-procesos:
	@for t in tests/test_quality_gate.py tests/test_gate_summary.py \
	          tests/test_assert_gate.py tests/test_provenance.py ; do \
	    echo "--- $$t"; python3 $$t || exit 1; \
	done

## Exige que la imagen provea lo que el pipeline necesita, EJECUTANDOLA.
## Necesita docker y la imagen construida (`make image`).
test-imagen:
	@python3 tests/test_imagen.py

## Ataca cada guarda del pipeline y comprueba que la caza. Necesita nextflow y
## las herramientas del pipeline; NO necesita red: sirve sus propios FASTQ
## sinteticos desde 127.0.0.1 y usa una base 16S de mentira.
test-ataques:
	@python3 tests/test_ataques.py

## Corrida de demostracion: descarga las dos muestras de ENA y verifica su md5.
run:
	@nextflow run main.nf -profile test

clean:
	@rm -rf work results .nextflow .nextflow.log*
