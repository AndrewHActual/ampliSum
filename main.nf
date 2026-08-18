#!/usr/bin/env nextflow

nextflow.enable.dsl=2

/*
 * Pipeline parameters
 */
params.data_dir   = null                 // top-level directory containing per-sample subdirectories
params.primer_map = null                 // path to primerplatepoolmapping.csv
params.outdir     = "results"
params.fasta_suffix = ".final.unique.fasta"
params.hist_bins  = 30                   // number of histogram bins for the copies plot

if (params.data_dir == null) {
    exit 1, "ERROR: Please provide --data_dir pointing to the top-level amplicon data directory"
}
if (params.primer_map == null) {
    exit 1, "ERROR: Please provide --primer_map pointing to primerplatepoolmapping.csv"
}

log.info """
====================================================
 Amplicon Header Summary Pipeline
====================================================
 data_dir     : ${params.data_dir}
 primer_map   : ${params.primer_map}
 fasta_suffix : ${params.fasta_suffix}
 outdir       : ${params.outdir}
====================================================
"""

/*
 * Build a channel of sample subdirectories (first-level only).
 * Each element is a tuple: (sample_dir_name, path_to_sample_dir)
 */
workflow {

    primer_map_ch = Channel.fromPath(params.primer_map, checkIfExists: true)

    sample_dirs_ch = Channel
        .fromPath("${params.data_dir}/*", type: 'dir')
        .map { dir -> tuple(dir.getName(), dir) }

    PARSE_SAMPLE(sample_dirs_ch, primer_map_ch.first())

    // Collect all per-sample TSVs and merge into one master TSV
    MERGE_SUMMARIES(PARSE_SAMPLE.out.summary_tsv.collect())

    // Generate a stacked histogram of copies vs pool_match from the merged TSV
    PLOT_HISTOGRAM(MERGE_SUMMARIES.out)
}

/*
 * Process: parse fasta headers for a single sample directory
 * and produce a per-sample summary TSV.
 */
process PARSE_SAMPLE {
    tag "${sample_name}"
    publishDir "${params.outdir}/per_sample", mode: 'copy'

    input:
    tuple val(sample_name), path(sample_dir)
    path primer_map

    output:
    path "${sample_name}.summary.tsv", emit: summary_tsv

    script:
    """
    parse_fasta_headers.py \\
        --sample-dir ${sample_dir} \\
        --sample-name ${sample_name} \\
        --primer-map ${primer_map} \\
        --fasta-suffix "${params.fasta_suffix}" \\
        --output ${sample_name}.summary.tsv
    """
}

/*
 * Process: merge all per-sample summary TSVs into one master TSV.
 */
process MERGE_SUMMARIES {
    publishDir "${params.outdir}", mode: 'copy'

    input:
    path tsv_files

    output:
    path "all_samples.summary.tsv"

    script:
    """
    combine_summaries.py --output all_samples.summary.tsv ${tsv_files}
    """
}

/*
 * Process: generate a stacked histogram of 'copies' values, split by
 * pool_match (TRUE vs FALSE), from the merged master summary TSV.
 */
process PLOT_HISTOGRAM {
    publishDir "${params.outdir}", mode: 'copy'

    input:
    path summary_tsv

    output:
    path "copies_histogram.png"
    path "copies_histogram_log.png"

    script:
    """
    plot_histogram.py \\
        --input ${summary_tsv} \\
        --output-linear copies_histogram.png \\
        --output-log copies_histogram_log.png \\
        --bins ${params.hist_bins}
    """
}