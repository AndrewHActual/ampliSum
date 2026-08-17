#!/usr/bin/env python3
"""
combine_summaries.py

Concatenate multiple per-sample summary TSVs (all sharing the same
header/columns) into a single master TSV.
"""

import argparse
import csv
import sys


def parse_args():
    p = argparse.ArgumentParser(description="Merge per-sample summary TSVs into one master TSV.")
    p.add_argument("--output", required=True, help="Path to the merged output TSV.")
    p.add_argument("inputs", nargs="+", help="Per-sample summary TSV files to merge.")
    return p.parse_args()


def main():
    args = parse_args()

    fieldnames = None
    all_rows = []

    for path in args.inputs:
        with open(path, newline="") as f:
            reader = csv.DictReader(f, delimiter="\t")
            if fieldnames is None:
                fieldnames = reader.fieldnames
            elif reader.fieldnames != fieldnames:
                sys.stderr.write(
                    f"WARNING: column mismatch in {path}; "
                    f"expected {fieldnames}, got {reader.fieldnames}\n"
                )
            for row in reader:
                all_rows.append(row)

    if fieldnames is None:
        sys.stderr.write("ERROR: no input files provided or all were empty.\n")
        sys.exit(1)

    with open(args.output, "w", newline="") as out_f:
        writer = csv.DictWriter(out_f, fieldnames=fieldnames, delimiter="\t")
        writer.writeheader()
        for row in all_rows:
            writer.writerow(row)

    sys.stderr.write(f"Merged {len(all_rows)} total rows from {len(args.inputs)} files into {args.output}\n")


if __name__ == "__main__":
    main()