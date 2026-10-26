#!/usr/bin/env python3
"""Compare pip-audit JSON output against the committed baseline of known advisories.

The pinned GeoNode 5.0.3 dependency set carries a three-digit number of open advisories, so a
workflow that fails on any finding is red forever and tells nobody anything. This gate fails only
on advisory IDs that are new relative to security/pip-audit-known.txt, and prints a Markdown
summary of everything pip-audit found so the full picture stays visible in the job summary.

Usage:
    pip-audit -f json | python3 security/pip_audit_gate.py                  # gate
    pip-audit -f json | python3 security/pip_audit_gate.py --write-baseline # refresh baseline
"""

import argparse
import json
import pathlib
import sys

BASELINE = pathlib.Path(__file__).with_name("pip-audit-known.txt")


def load_findings(report):
    """-> {package: {advisory_id: [fix_version, ...]}}, skipping packages without advisories."""
    findings = {}
    for package in report.get("dependencies", []):
        for vuln in package.get("vulns", []):
            advisories = findings.setdefault(package["name"], {})
            advisories.setdefault(vuln["id"], sorted(vuln.get("fix_versions", [])))
    return findings


def flatten(findings):
    return {f"{name}:{advisory}" for name, advisories in findings.items() for advisory in advisories}


def markdown_summary(report, findings, new):
    versions = {p["name"]: p.get("version", "?") for p in report.get("dependencies", [])}
    lines = ["## pip-audit", ""]
    if new:
        lines += [f"**{len(new)} advisory/advisories not in the baseline:**", ""]
        lines += [f"- `{entry}`" for entry in sorted(new)] + [""]
    else:
        lines += ["No advisories outside the committed baseline.", ""]

    lines += ["| Package | Installed | Advisories | Fixed in |", "| --- | --- | --- | --- |"]
    for name in sorted(findings, key=lambda n: (-len(findings[n]), n)):
        fixes = sorted({f for fix_versions in findings[name].values() for f in fix_versions})
        lines.append(
            f"| {name} | {versions.get(name, '?')} | {len(findings[name])} | {fixes[-1] if fixes else 'no fix listed'} |"
        )

    # Packages pip-audit could not match to a PyPI release -- the git-pinned ones, above all.
    skipped = [p for p in report.get("dependencies", []) if "skip_reason" in p]
    if skipped:
        lines += ["", "Not audited (no PyPI release to match):", ""]
        lines += [f"- `{entry['name']}` -- {entry['skip_reason']}" for entry in skipped]
    return "\n".join(lines) + "\n"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("report", nargs="?", type=argparse.FileType(), default=sys.stdin)
    parser.add_argument("--write-baseline", action="store_true", help="refresh the baseline instead of gating")
    parser.add_argument("--summary", type=pathlib.Path, help="append a Markdown summary to this file")
    args = parser.parse_args()

    report = json.load(args.report)
    findings = load_findings(report)
    current = flatten(findings)

    if args.write_baseline:
        header = [line for line in BASELINE.read_text().splitlines() if line.startswith("#")]
        BASELINE.write_text("\n".join(header + sorted(current)) + "\n")
        print(f"baseline refreshed: {len(current)} advisories (update the 'Generated' header line)")
        return 0

    known = {line.strip() for line in BASELINE.read_text().splitlines() if line.strip() and not line.startswith("#")}
    new = current - known

    summary = markdown_summary(report, findings, new)
    print(summary)
    if args.summary:
        with args.summary.open("a") as handle:
            handle.write(summary)

    if new:
        print(f"FAIL: {len(new)} advisory/advisories are new since the baseline was taken.", file=sys.stderr)
        return 1
    print(f"OK: {len(current)} advisories, all present in the baseline.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
