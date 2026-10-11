"""Validate packet checksums and independently rerun quote checks."""
import argparse
import hashlib
import json
from pathlib import Path

from evidence import validate_evidence, validate_report


def verify(directory: Path) -> None:
    manifest = json.loads((directory / "manifest.json").read_text(encoding="utf-8"))
    expected_files = {"report.json", "REPORT.md", "review.html"}
    if set(manifest["sha256"]) != expected_files:
        raise ValueError("unexpected manifest file list")
    for name in expected_files:
        actual = hashlib.sha256((directory / name).read_bytes()).hexdigest()
        if actual != manifest["sha256"][name]:
            raise ValueError(f"checksum mismatch: {name}")
    bundle = json.loads((directory / "report.json").read_text(encoding="utf-8"))
    if bundle["input_sha256"] != manifest["input_sha256"]:
        raise ValueError("input fingerprint mismatch")
    validate_evidence({"question": bundle["question"], "studies": bundle["sources"]})
    validate_report(bundle["report"], bundle["sources"])


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path)
    args = parser.parse_args()
    verify(args.directory)
    print("Checksums and quote-location checks passed; semantic review is separate.")
