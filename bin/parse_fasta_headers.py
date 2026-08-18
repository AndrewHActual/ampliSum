#!/usr/bin/env python3
"""
parse_fasta_headers.py

Scan all FASTA files in a sample directory matching a given suffix,
parse the headers, and write a per-sample summary TSV.

Header format example:

>SH00687:20:BWR98204-3220:1:1101:1445:3755=OG0003656primerGroup8=2011K-0837_Rep1_5_S21;size=675

Parsing rules:
  - Split header (minus leading '>') on '='
    - field[0] = read/instrument identifier (ignored)
    - field[1] = Primer_name                (e.g. OG0003656primerGroup8)
    - field[2] = "<sample_name>;size=<n>"
  - sample_name  = text between the 2nd '=' and the following ';'
  - copies       = integer after the 3rd '=' (i.e. after "size=")
  - sample_name is further split on '_' into:
        sample_id, replicate, pool_number, sample_number
    e.g. "2011K-0837_Rep1_5_S21" ->
        sample_id      = 2011K-0837
        replicate      = Rep1
        pool_number    = 5
        sample_number  = S21

Pool match:
  - Look up Primer_name in the primer/plate/pool mapping CSV
    (columns: Primer_name, Plate, Pool)
  - pool_match = True if mapping's Pool == pool_number parsed from header
                 (numeric comparison), else False.
  - If Primer_name is not found in the mapping, pool_match = False and
    a warning is emitted (recorded as "NA" is avoided in favor of False
    so the column stays boolean; see --strict flag if you'd prefer NA).
"""

import argparse
import csv
import glob
import os
import sys


def parse_args():
    p = argparse.ArgumentParser(description="Parse amplicon FASTA headers into a summary TSV.")
    p.add_argument("--sample-dir", required=True, help="Path to the sample's first-level subdirectory.")
    p.add_argument("--sample-name", required=True, help="Name of the sample (subdirectory name), used for logging/tagging.")
    p.add_argument("--primer-map", required=True, help="Path to primerplatepoolmapping.csv")
    p.add_argument("--fasta-suffix", default=".final.unique.fasta", help="Suffix used to find relevant FASTA files.")
    p.add_argument("--output", required=True, help="Output TSV path.")
    return p.parse_args()


def load_primer_map(path):
    """
    Load primerplatepoolmapping.csv into a dict:
        { Primer_name: {"Plate": <float or None>, "Pool": <int or None>} }
    """
    mapping = {}
    with open(path, newline="") as f:
        reader = csv.DictReader(f)
        # Normalize column names in case of stray whitespace
        reader.fieldnames = [c.strip() for c in reader.fieldnames]
        for row in reader:
            # TODO: The .strip() that occurs in the fieldnames grab does not remove the \ufeff
            # Byte Order Mark, which only appears at the start of the document? So I set it
            # here as hardcoded in, which ain't the best idea. Not to mention the headers are
            # hardcoded in, which is also suboptimal.
            primer = row.get("\ufeffPrimer_name", "").strip()
            if not primer:
                continue
            plate_raw = row.get("Plate", "")
            pool_raw = row.get("Pool", "")

            plate_val = None
            if plate_raw not in (None, ""):
                try:
                    plate_val = float(plate_raw)
                except ValueError:
                    plate_val = None

            pool_val = None
            if pool_raw not in (None, ""):
                try:
                    pool_val = int(float(pool_raw))
                except ValueError:
                    pool_val = None

            mapping[primer] = {"Plate": plate_val, "Pool": pool_val}
    return mapping


def find_fasta_files(sample_dir, suffix):
    pattern = os.path.join(sample_dir, f"*{suffix}")
    files = sorted(glob.glob(pattern))
    return files


def parse_header(header_line):
    """
    Parse a single FASTA header line (starting with '>') into its components.
    Returns a dict or None if the header doesn't match the expected format.
    """
    line = header_line.strip()
    if line.startswith(">"):
        line = line[1:]

    parts = line.split("=")
    if len(parts) < 3:
        return None

    primer_name = parts[1].strip()

    # Everything after the 2nd '=' may itself contain '=' (e.g. "size=675"),
    # so rejoin remaining parts before extracting sample_name / size.
    remainder = "=".join(parts[2:])  # "2011K-0837_Rep1_5_S21;size=675"

    if ";" not in remainder:
        return None
    sample_name, tail = remainder.split(";", 1)
    sample_name = sample_name.strip()

    # tail looks like "size=675" (possibly with more '=' separated fields later;
    # we only need the value after 'size=')
    copies = None
    if "size=" in tail:
        size_str = tail.split("size=", 1)[1]
        # size value ends at next ';' if present, else end of string
        size_str = size_str.split(";")[0].strip()
        try:
            copies = int(size_str)
        except ValueError:
            copies = None

    # Split sample_name into sample_id, replicate, pool_number, sample_number
    sample_fields = sample_name.split("_")
    sample_id = sample_fields[0] if len(sample_fields) > 0 else None
    replicate = sample_fields[1] if len(sample_fields) > 1 else None
    pool_number_raw = sample_fields[2] if len(sample_fields) > 2 else None
    sample_number = sample_fields[3] if len(sample_fields) > 3 else None

    pool_number = None
    if pool_number_raw is not None:
        try:
            pool_number = int(pool_number_raw)
        except ValueError:
            pool_number = None

    return {
        "Primer_name": primer_name,
        "sample_name": sample_name,
        "copies": copies,
        "sample_id": sample_id,
        "replicate": replicate,
        "pool_number": pool_number,
        "sample_number": sample_number,
    }


def main():
    args = parse_args()

    primer_map = load_primer_map(args.primer_map)
    fasta_files = find_fasta_files(args.sample_dir, args.fasta_suffix)

    if not fasta_files:
        sys.stderr.write(
            f"WARNING: no files matching *{args.fasta_suffix} found in {args.sample_dir}\n"
        )

    rows = []
    for fasta_path in fasta_files:
        fasta_file_name = os.path.basename(fasta_path)
        with open(fasta_path) as f:
            for line in f:
                if not line.startswith(">"):
                    continue
                parsed = parse_header(line)
                if parsed is None:
                    sys.stderr.write(f"WARNING: could not parse header in {fasta_file_name}: {line.strip()}\n")
                    continue

                primer_name = parsed["Primer_name"]
                pool_number = parsed["pool_number"]

                map_entry = primer_map.get(primer_name)
                if map_entry is None:
                    sys.stderr.write(
                        f"WARNING: Primer_name '{primer_name}' not found in primer map; "
                        f"pool_match set to False\n"
                    )
                    pool_match = False
                    mapped_pool = None
                    mapped_plate = None
                else:
                    mapped_pool = map_entry["Pool"]
                    mapped_plate = map_entry["Plate"]
                    pool_match = (mapped_pool is not None
                                  and pool_number is not None
                                  and mapped_pool == pool_number)

                rows.append({
                    "sample_dir": args.sample_name,
                    "fasta_file": fasta_file_name,
                    "Primer_name": primer_name,
                    "sample_name": parsed["sample_name"],
                    "copies": parsed["copies"],
                    "sample_id": parsed["sample_id"],
                    "replicate": parsed["replicate"],
                    "pool_number": pool_number,
                    "sample_number": parsed["sample_number"],
                    "mapped_plate": mapped_plate,
                    "mapped_pool": mapped_pool,
                    "pool_match": pool_match,
                })

    fieldnames = [
        "sample_dir",
        "fasta_file",
        "Primer_name",
        "sample_name",
        "copies",
        "sample_id",
        "replicate",
        "pool_number",
        "sample_number",
        "mapped_plate",
        "mapped_pool",
        "pool_match",
    ]

    with open(args.output, "w", newline="") as out_f:
        writer = csv.DictWriter(out_f, fieldnames=fieldnames, delimiter="\t")
        writer.writeheader()
        for row in rows:
            writer.writerow(row)

    sys.stderr.write(f"Wrote {len(rows)} rows to {args.output}\n")


if __name__ == "__main__":
    main()