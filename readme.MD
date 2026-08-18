# Hot Amplicon Summary

A Nextflow pipeline (with Python-based processing) that scans per-sample amplicon FASTA files, parses their headers, and cross-references primer/pool assignments against a plate/pool mapping file to flag matches and mismatches.

## Overview

Given a top-level data directory containing one subdirectory per sample, this pipeline:

1. Discovers all first-level sample subdirectories.
2. Finds all `*.final.unique.fasta` files in each subdirectory.
3. Parses every FASTA header to extract the primer name, sample name, and read copy count.
4. Splits the sample name into its component parts (sample ID, replicate, pool number, sample number).
5. Looks up each primer in a primer→plate→pool mapping file and checks whether the mapped pool matches the pool number encoded in the sample name.
6. Writes a per-sample summary TSV, then merges all per-sample TSVs into one master TSV.
7. Generates a stacked histogram (linear and log-scale versions) of `copies` values, split by `pool_match` (True vs False).

## Repository Structure

```
.
├── main.nf
├── nextflow.config
├── bin/
│   ├── parse_fasta_headers.py
│   ├── combine_summaries.py
│   └── plot_histogram.py
└── README.md
```

Nextflow automatically adds `bin/` to `PATH` for every process, so the Python scripts are invoked directly by name in `main.nf`.

## Requirements

- [Nextflow](https://www.nextflow.io/) (DSL2, tested with `nextflow.enable.dsl=2`)
- Python 3.7+
- `matplotlib` and `numpy` (only required for the histogram-plotting step; the parsing/merging steps use only the Python standard library)

## Input Requirements

### 1. Data directory (`--data_dir`)

A directory where each first-level subdirectory represents one sample:

```
data/
├── 2011K-0837_Rep1_5_S21/
│   └── 2011K-0837_Rep1_5_S21.final.unique.fasta
├── 2011K-0838_Rep2_3_S22/
│   └── 2011K-0838_Rep2_3_S22.final.unique.fasta
└── ...
```

The pipeline only descends **one level** — it does not recurse into nested subdirectories.

### 2. Primer/plate/pool mapping (`--primer_map`)

A CSV file with (at minimum) these columns:

| Column       | Type    | Description                              |
|--------------|---------|-------------------------------------------|
| `Primer_name`| String  | Matches the primer name in FASTA headers  |
| `Plate`      | Float   | Plate identifier                          |
| `Pool`       | Integer | Expected pool number for that primer      |

### 3. FASTA header format

Headers are expected to follow this pattern:

```
>SH00687:20:BWR98204-3220:1:1101:1445:3755=OG0003656primerGroup8=2011K-0837_Rep1_5_S21;size=675
```

Which breaks down as:

```
>[read/instrument ID] = [Primer_name] = [sample_name];size=[copies]
```

## Usage

```bash
# Make sure the Python scripts are executable
chmod +x bin/*.py

# Run the pipeline
nextflow run main.nf \
    --data_dir /path/to/data \
    --primer_map /path/to/primerplatepoolmapping.csv \
    --outdir results
```

### Parameters

| Parameter       | Required | Default                   | Description                                      |
|-----------------|----------|----------------------------|---------------------------------------------------|
| `--data_dir`    | Yes      | —                          | Top-level directory containing sample subdirectories |
| `--primer_map`  | Yes      | —                          | Path to `primerplatepoolmapping.csv`              |
| `--outdir`      | No       | `results`                  | Output directory                                  |
| `--fasta_suffix`| No       | `.final.unique.fasta`      | Suffix used to identify relevant FASTA files       |
| `--hist_bins`   | No       | `30`                       | Number of bins used in the copies histogram        |

### Outputs

```
results/
├── per_sample/
│   ├── <sample1>.summary.tsv
│   ├── <sample2>.summary.tsv
│   └── ...
├── all_samples.summary.tsv
├── copies_histogram.png
├── copies_histogram_log.png
├── pipeline_trace.txt
└── pipeline_report.html
```

Each summary TSV (per-sample and merged) contains the following columns:

| Column          | Description                                                         |
|-----------------|-----------------------------------------------------------------------|
| `sample_dir`    | Name of the sample's source subdirectory                             |
| `fasta_file`    | Name of the source FASTA file                                        |
| `Primer_name`   | Primer name parsed from the header                                   |
| `sample_name`   | Full sample name string parsed from the header                       |
| `copies`        | Read copy count (`size=` value)                                      |
| `sample_id`     | First `_`-delimited field of the sample name                         |
| `replicate`     | Second `_`-delimited field (e.g. `Rep1`)                              |
| `pool_number`   | Third `_`-delimited field, parsed as an integer                      |
| `sample_number` | Fourth `_`-delimited field (e.g. `S21`)                               |
| `mapped_plate`  | `Plate` value from the primer map for this `Primer_name`             |
| `mapped_pool`   | `Pool` value from the primer map for this `Primer_name`              |
| `pool_match`    | `True`/`False` — whether `mapped_pool` equals `pool_number`          |

## Logic Summary

### Header parsing (`parse_fasta_headers.py`)

Given a header like:

```
>SH00687:...:3755=OG0003656primerGroup8=2011K-0837_Rep1_5_S21;size=675
```

1. Strip the leading `>` and split on `=`.
2. `Primer_name` = the second field (index 1) after splitting.
3. Rejoin everything after the second `=` (in case later fields contain `=` themselves), giving `"2011K-0837_Rep1_5_S21;size=675"`.
4. Split that on the first `;` → left side is `sample_name`, right side contains `size=NNN`.
5. Extract `copies` as the integer following `size=`.
6. Split `sample_name` on `_` into four parts:
   - `sample_id` (e.g. `2011K-0837`)
   - `replicate` (e.g. `Rep1`)
   - `pool_number` (e.g. `5`, cast to `int`)
   - `sample_number` (e.g. `S21`)

### Pool match logic

1. Load `primerplatepoolmapping.csv` into a dictionary keyed by `Primer_name`, with `Plate` cast to `float` and `Pool` cast to `int`.
2. For each parsed header, look up its `Primer_name` in this dictionary.
3. Set `pool_match = True` if the mapped `Pool` equals the header's parsed `pool_number`, else `False`.
4. If `Primer_name` isn't found in the mapping at all, `pool_match` is set to `False` and a warning is written to stderr (visible in Nextflow's `.command.err` logs for that process).

### Merging (`combine_summaries.py`)

All per-sample TSVs (identical column structure) are concatenated into a single `all_samples.summary.tsv`, with a warning emitted if any file's header columns don't match the expected set.

### Histogram plotting (`plot_histogram.py`)

1. Reads `all_samples.summary.tsv` and coerces `copies` to a float and `pool_match` to a proper boolean (accepts `"True"`/`"False"` strings, case-insensitive).
2. Splits rows into two groups based on `pool_match`.
3. Builds a shared set of bin edges across both groups (so the histograms are directly comparable) and renders a **stacked** bar histogram — `pool_match = True` in green, `pool_match = False` in red/pink.
4. Produces two output images:
   - `copies_histogram.png` — linear x-axis, linear y-axis
   - `copies_histogram_log.png` — log10 x-axis **and** log10 y-axis, with `copies` values floored at 1 to avoid `log(0)` errors on the x-axis
5. Rows with missing or non-numeric `copies`, or an unparseable `pool_match`, are skipped with a warning written to stderr.

The log-scale version is generally the more informative plot for amplicon copy-count data, which tends to be heavily right-skewed (as seen in the example FASTA, where `size=` values range from single digits into the hundreds). Note that on a log y-axis, bins with a count of exactly 0 will not render a visible bar (log(0) is undefined), which is expected matplotlib behavior rather than a bug.

## Notes / Assumptions

- **Directory depth:** Only first-level subdirectories of `--data_dir` are treated as samples. Nested/deeper directories are ignored.
- **File matching:** Only files ending in `.final.unique.fasta` (configurable via `--fasta_suffix`) are parsed; other files in the sample directory are ignored.
- **`=` splitting robustness:** The header is split on `=` and everything after the 2nd `=` is rejoined before further parsing, so the logic is robust even if the trailing portion of the header contains additional `=` characters beyond `size=`.
- **Sample name structure:** Sample names are assumed to follow the 4-field `_`-delimited pattern seen in the example (`sample_id_replicate_pool_samplenum`, e.g. `2011K-0837_Rep1_5_S21`). If a sample name has fewer than 4 fields, missing fields are left blank in the output rather than causing an error. Extra fields beyond the 4th are currently ignored.
- **Pool number typing:** `pool_number` (from the header) and `Pool` (from the mapping CSV) are both cast to `int` before comparison. `Plate` is cast to `float` per the documented schema. Values like `5.0` in the `Pool` column are handled by casting through `float` first, then `int`.
- **Unmapped primers:** If a `Primer_name` parsed from a FASTA header does not exist in `primerplatepoolmapping.csv`, `pool_match` defaults to `False` (not `NA`), and a warning is logged to stderr. If you'd prefer these rows to be flagged differently (e.g., `NA`/blank) or excluded entirely, update the corresponding logic block in `bin/parse_fasta_headers.py`.
- **No external Python dependencies for parsing/merging:** `parse_fasta_headers.py` and `combine_summaries.py` rely solely on the Python standard library. `plot_histogram.py` requires `matplotlib` and `numpy` — ensure these are installed in whatever environment/container runs the `PLOT_HISTOGRAM` process. A `container` directive placeholder is included (commented out) in `nextflow.config` for environments that require containerized execution.
- **Histogram binning:** Bin edges are shared between the TRUE and FALSE groups (computed from the combined value range) so that the stacked bars line up correctly. The log-scale plot floors values at 1 before taking `log10` to avoid errors on zero or negative `copies` values, which should not occur in practice but are handled defensively.
- **Idempotency/re-runs:** Each Nextflow process publishes outputs via `publishDir` with `mode: 'copy'`; re-running the pipeline will overwrite prior outputs in `--outdir`.
- **Malformed headers:** Any header line that doesn't match the expected `=`/`;` structure is skipped, with a warning written to stderr rather than halting the pipeline.

## License

Add your license of choice here (e.g., MIT, Apache 2.0).
