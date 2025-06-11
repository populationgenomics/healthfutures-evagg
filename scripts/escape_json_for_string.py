#!/usr/bin/env python3
"""Escape JSON to be included as a string field in another JSON structure."""

import json
import sys


def escape_json_for_string(json_path: str = None):
    """Read JSON and output it as a properly escaped string."""
    
    if json_path:
        with open(json_path, 'r') as f:
            data = json.load(f)
    else:
        data = json.load(sys.stdin)
    
    # Convert to compact JSON string
    json_string = json.dumps(data, separators=(',', ':'))
    
    # Now escape it to be included as a string in another JSON
    print(json.dumps(json_string))


if __name__ == "__main__":
    json_file = sys.argv[1] if len(sys.argv) > 1 else None
    escape_json_for_string(json_file)
