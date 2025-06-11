#!/usr/bin/env python3
"""Convert TSV pipeline benchmark output to new JSON format."""

import csv
import json
import sys
from datetime import datetime
from pathlib import Path


def convert_tsv_to_json(tsv_path: str, json_path: str = None):
    """Convert TSV format to JSON format matching JSONOutputWriter output."""
    
    # Read TSV file
    with open(tsv_path, 'r') as f:
        lines = f.readlines()
    
    # Extract generated timestamp from first line
    generated_line = lines[0].strip()
    if generated_line.startswith('# Generated '):
        # Parse the timestamp string (format: "YYYY-MM-DD HH:MM:SS TZ")
        timestamp_str = generated_line.replace('# Generated ', '')
        # Convert to ISO format
        dt = datetime.strptime(timestamp_str.replace(' AEST', ''), '%Y-%m-%d %H:%M:%S')
        # Add timezone info (assuming AEST is UTC+10)
        generated_iso = dt.isoformat() + '+10:00'
    else:
        # Fallback to current time if format is unexpected
        generated_iso = datetime.now().astimezone().isoformat()
    
    # Parse TSV data
    reader = csv.DictReader(lines[1:], delimiter='\t')
    data = list(reader)
    
    # Create JSON structure
    json_output = {
        "generated": generated_iso,
        "data": data
    }
    
    # Write output
    if json_path:
        with open(json_path, 'w') as f:
            json.dump(json_output, f, indent=2)
        print(f"Converted {tsv_path} to {json_path}")
    else:
        json.dump(json_output, sys.stdout, indent=2)


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python convert_tsv_to_json.py <tsv_file> [json_file]")
        print("If json_file is not provided, output will be printed to stdout")
        sys.exit(1)
    
    tsv_file = sys.argv[1]
    json_file = sys.argv[2] if len(sys.argv) > 2 else None
    
    if not Path(tsv_file).exists():
        print(f"Error: TSV file '{tsv_file}' not found")
        sys.exit(1)
    
    convert_tsv_to_json(tsv_file, json_file)