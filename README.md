<!-- Language: English | [Español](README.es.md) -->

# nf-16s-guarded

[![ci](https://github.com/kurisutina132/nf-16s-guarded/actions/workflows/ci.yml/badge.svg)](https://github.com/kurisutina132/nf-16s-guarded/actions/workflows/ci.yml)

A **guarded** Nextflow (DSL2) pipeline for 16S rRNA amplicon profiling. Its
distinguishing feature is not that it runs, but *how it refuses to run when
something is wrong*: **every validation guard has a documented attack case that
broke it before it was trusted**, and each guard was falsified in the source to
confirm its test went red.

> Working principle: **a test that has never failed protects nothing.**

The pipeline is self-contained and uses only public tools and public data — no
proprietary code or data.

## What it does

```
samplesheet ─▶ download + MD5 verify ─▶ fastp QC ─▶ quality gate ─▶ kraken2 / SILVA 138 ─▶ report
                     (ENA)                          (min reads)        (taxonomy)      (+ tool versions)
```

1. Downloads paired-end 16S FASTQ from the **ENA** (PRJEB6070) and verifies each
   file by **MD5 checksum**.
2. Quality control and filtering with **fastp**.
3. A **quality gate** enforcing a minimum threshold of surviving read pairs
   per sample.
4. Taxonomic classification with **kraken2** against a frozen **SILVA 138** 16S
   reference (deterministic exact k-mer matching — reproducible across runs).
5. A report with per-tool version tracking.

A full run on the two public ENA samples (ERR674093, 74,651 read pairs;
ERR674112, 96,928) takes about 4 minutes on a clean machine — measured from an
empty directory, downloading reads and reference.

## Quick start

```bash
make setup      # activate the versioned git hooks and set the local identity
make image      # build the pipeline container (once, needed by -profile docker)

# Demo run on the two public ENA samples. Downloads ~34 MB of reads and
# 112 MB of reference on the first run; the reference is then cached.
nextflow run . -profile test,docker
```

Your own data:

```bash
nextflow run . -profile docker \
    --samplesheet samplesheet.csv \
    --outdir results \
    --reference_dir references \
    --etapa completa \
    --min_reads 50000 \
    --fastp_min_length 100 \
    --fastp_min_quality 20 \
    --kraken_confidence 0.1
```

Every one of those parameters is mandatory and has **no default**. A guard that
falls back to a permissive default is not a guard, so a missing parameter stops
the run before the first task and names itself:

```
Falta el parametro obligatorio --min_reads (puerta de calidad, en pares de lecturas).

No hay valor por defecto y no se va a inventar uno: un defecto
permisivo convierte un olvido en un resultado silenciosamente malo.
```

`conf/test.config` is a worked example of declaring them all.

`samplesheet.csv`:

```csv
sample,fastq_1,fastq_2,md5_1,md5_2
SAMPLE_A,<url_R1>,<url_R2>,<md5_R1>,<md5_R2>
```

The MD5 columns are not optional: without a declared checksum there is nothing
to verify against. They are declared here rather than fetched at run time on
purpose — downloading a checksum from the same host that served the file
verifies nothing.

## The guard system (core feature)

The repository documents **22 guards**. Each row of the guard table in
[README.es.md](README.es.md) names the guard, the attack that exercises it, and
the exact message it prints.

- The **attack cases are versioned tests**: 18 of them in
  `tests/test_ataques.py`, which launch the real pipeline against synthetic
  FASTQ served from `127.0.0.1`, plus the logic-level cases in the unit tests.
- Each guard was additionally validated by **mutation**: falsifying the guard in
  the source — removing the checksum comparison, making the quality gate always
  pass — and confirming its test went red. Those mutations were applied,
  observed and reverted during development; they are not kept in the tree. One
  mutation test *is* built into the suite:
  `tests/test_imagen.py` derives an image with `ps` deleted and requires the
  image guard to catch it.

Examples of what the guards catch:

| Guard | Attack it survives |
|---|---|
| MD5 verification of downloads | corrupted / truncated / empty files |
| Samplesheet validation | missing columns, malformed URLs, injection payloads |
| Content-addressed reference cache | false cache hit with the wrong checksum |
| Image verification | container missing a required binary |
| Quality-gate consistency | contradictory verdicts between report and assertion |

Two design decisions worth calling out:

- **Separation of reporting and judgment.** The summary step *always* succeeds
  and writes diagnostics; a *separate* assertion is what fails the run — so a
  failure is never silent.
- **Validation before launch.** The samplesheet is fully validated *before* any
  task starts, preventing partial writes on error.

## Reproducibility

- **Nextflow DSL2** — one process per file under `modules/local/`, a named
  sub-workflow (`PREPARACION`) that can be run on its own with
  `--etapa preparacion`, samplesheet-driven, `-resume` for interrupted runs.
  Written against Nextflow's strict parser.
- **Custom container**, built from `containers/Dockerfile`; a guard checks the
  image actually provides its required binaries by executing it, not by reading
  the Dockerfile.
- **Reference database pinned by MD5** in `nextflow.config` — a dated checkpoint
  against silent remote changes; the cache path is content-addressed by that MD5.
- **CI (GitHub Actions), four jobs on every push:** fast unit tests (no network),
  container build with pinned tool versions, the attack suite against synthetic
  localhost fixtures, and the full pipeline on real ENA data. Actions are pinned
  by **commit SHA**, not tag, to prevent silent upgrades.

## Tests

```bash
make test              # fast loop: no network, no Nextflow  (37 tests)
make test-procesos     # unit tests for the scripts in bin/  (31 tests)
make test-ataques      # 18 attack tests, synthetic FASTQ from 127.0.0.1, no network
make test-imagen       # 5 tests that execute the container  (needs docker + make image)
make test-todo         # everything except the container tests
```

60 tests in eight files:

| File | Tests | What it checks |
|---|---|---|
| `tests/test_ataques.py` | 18 | the attack suite: each pipeline guard catches its attack |
| `tests/test_provenance.py` | 9 | the provenance document loses nothing and refuses to contradict itself |
| `tests/test_quality_gate.py` | 8 | quality-gate logic, including the exact threshold boundary |
| `tests/test_assert_gate.py` | 8 | the run is not declared good when samples were lost |
| `tests/test_gate_summary.py` | 6 | the gate summary reports without judging |
| `tests/test_imagen.py` | 5 | the container provides its required tools — by executing it |
| `tests/test_atribucion.py` | 3 | no artifact in the tree names the tooling used to write it |
| `tests/test_autoria.py` | 3 | every commit in history is signed by the expected author |

## Repository layout

```
main.nf                 # workflow + samplesheet validation + startup guards
nextflow.config         # params, profiles (test / docker / conda), pinned versions
conf/test.config        # the profile CI runs; a worked example of every parameter
modules/local/          # one DSL2 process per file (9 of them)
bin/                    # scripts the modules call, each with its own unit tests
containers/             # Dockerfile + env.yml, the single source of tool versions
assets/samplesheet.csv  # the two public ENA samples, with their checksums
tests/                  # Python test suite (unit + attack + container)
docs/PENDIENTES.md      # what is open or unverified, dated
.githooks/              # versioned hooks, activated by `make setup`
.github/workflows/ci.yml # CI, four jobs
Makefile                # setup, image and test targets
README.es.md            # Spanish version: full guard table, design decisions
```

## Requirements

Nextflow ≥ 24.04.0 (declared in the manifest) · Docker, or Conda via
`-profile conda` · Make · Python 3 for the test suite

No credentials and no private registries: every container and every byte of
data is public.

## License

MIT — Cristy Medina Armijo · github.com/kurisutina132
