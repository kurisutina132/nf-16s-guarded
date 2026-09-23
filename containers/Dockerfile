# Imagen del pipeline. Versiones FIJADAS, ninguna etiqueta movil.
#
# Base fijada por DIGEST: mambaorg/micromamba:2.0.5-debian12-slim al
# 2026-09-19. Una etiqueta se reconstruye con el mismo nombre y otro contenido;
# el digest no.
FROM mambaorg/micromamba@sha256:8d0d4cad074afe3ac93b58dce88bd2659153d3fa6de3a6968f501710e8d3c832

# Etiquetas de procedencia del ARTEFACTO, no de quien tecleo.
LABEL org.opencontainers.image.title="nf-16s-guarded" \
      org.opencontainers.image.description="Amplicon 16S: descarga verificada, control de calidad y perfilado" \
      org.opencontainers.image.licenses="MIT" \
      org.opencontainers.image.source="https://github.com/kurisutina132/nf-16s-guarded"

USER root
COPY containers/env.yml /tmp/env.yml
RUN micromamba install -y -n base -f /tmp/env.yml \
 && micromamba clean --all --yes \
 && rm -f /tmp/env.yml
USER $MAMBA_USER

ENV PATH=/opt/conda/bin:$PATH

# Comprobacion de humo dentro de la propia imagen: si una herramienta no
# responde, la imagen no se da por buena. Se comprueba ademas que la version
# que responde es la que se fijo, no una que el solver haya sustituido.
RUN curl --version | head -1 \
 && md5sum --version | head -1 \
 && python3 --version \
 && fastp --version 2>&1 | grep -q '0\.24\.0' \
 && kraken2 --version | grep -q '2\.1\.3' \
 && multiqc --version | grep -q '1\.25\.1'
