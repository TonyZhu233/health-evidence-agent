"""Retrieve a small PubMed abstract set with search provenance. Never publish by default."""
import argparse
import json
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

from clients import pubmed_search


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--query", required=True, help="Explicit, user-reviewed PubMed search expression")
    parser.add_argument("--question", required=True)
    parser.add_argument("--limit", type=int, default=10)
    parser.add_argument("--email", default="", help="Optional NCBI contact email; omitted from saved provenance")
    parser.add_argument("--output", type=Path, required=True, help="NEW local JSON file, preferably under runs/")
    args = parser.parse_args()
    try:
        if args.output.exists():
            raise ValueError("output exists; choose a new filename")
        data = pubmed_search(args.question, args.query, args.limit, args.email)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        with args.output.open("x", encoding="utf-8") as handle:
            json.dump(data, handle, ensure_ascii=False, indent=2)
        print(f"Retrieved {len(data['studies'])} usable records; {len(data['provenance']['dropped'])} dropped. Saved to {args.output}.")
    except (OSError, ValueError, RuntimeError, ET.ParseError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
