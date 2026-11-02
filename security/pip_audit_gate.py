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
import re
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


def version_key(version):
    """PEP 440-lite ordering: the leading numeric release components.

    Sorting fix versions as plain strings puts "9.0.3" after "13.0.0", which is how this report
    used to end up naming a major as the fix for a package whose own branch had a backport.
    """
    parts = []
    for chunk in re.split(r"[.+-]", version.strip()):
        match = re.match(r"^(\d+)", chunk)
        if not match:
            break
        parts.append(int(match.group(1)))
    return tuple(parts) or (0,)


def classify_fixes(installed, advisories):
    """Split a package's advisories by whether a same-major upgrade can clear them.

    .github/dependabot.yml restricts pip to minor and patch updates, so the version this report
    puts forward has to stay inside the installed major -- otherwise it reads as an instruction
    nothing in the pipeline will carry out. pip-audit often lists a backport alongside the next
    major (pillow: 12.2.0, 12.3.0, 13.0.0), and the backport is the one that is actionable here.

    -> (in_policy_target, cleared, major_target, needs_major, unfixed)
    """
    major = version_key(installed)[:1]
    in_policy, crossing, unfixed = [], [], 0
    for fix_versions in advisories.values():
        if not fix_versions:
            unfixed += 1
            continue
        same_major = [f for f in fix_versions if version_key(f)[:1] == major]
        if same_major:
            in_policy.append(min(same_major, key=version_key))
        else:
            crossing.append(min(fix_versions, key=version_key))
    return (
        max(in_policy, key=version_key) if in_policy else None,
        len(in_policy),
        max(crossing, key=version_key) if crossing else None,
        len(crossing),
        unfixed,
    )


def classify_new(findings, versions, new):
    """Split the new advisories by whether the pip policy can act on them at all.

    Failing on every new advisory id made sense while any fix was fair game. Against the
    minor/patch-only pip policy it does not: an advisory whose only fix is a major leaves the audit
    red with nothing anyone is allowed to merge to clear it, so the gate ends up demanding an action
    the policy forbids, every run, forever. Red then stops meaning anything.

    Failing only on the actionable group restores the signal -- a red audit means "there is a patch
    waiting". The rest are still reported on every run, in the table and in the summary below it, so
    nothing drops out of sight; they are a scheduling decision, not a build failure.

    "Actionable" means a same-major fix exists, not that it installs unaided: another pinned
    package may cap the one being fixed, as djangorestframework-gis and geonode-dynamic-rest both
    capped djangorestframework below its fix. Clearing it then means bumping the capping package
    too, which stays inside the policy as long as that bump is itself minor or patch.

    -> (actionable, needs_major, unfixed), each a sorted list of "package:advisory" keys.
    """
    actionable, needs_major, unfixed = [], [], []
    for key in new:
        name, _, advisory = key.partition(":")
        fixes = findings.get(name, {}).get(advisory, [])
        installed = versions.get(name, "")
        major = version_key(installed)[:1] if installed else None
        if not fixes:
            unfixed.append(key)
        elif major and any(version_key(f)[:1] == major for f in fixes):
            actionable.append(key)
        else:
            needs_major.append(key)
    return sorted(actionable), sorted(needs_major), sorted(unfixed)


def markdown_summary(report, findings, groups):
    actionable, needs_major, unfixed_new = groups
    versions = {p["name"]: p.get("version", "?") for p in report.get("dependencies", [])}
    lines = ["## pip-audit", ""]
    if actionable:
        lines += [f"**{len(actionable)} new advisory/advisories with a fix inside the pip policy:**", ""]
        lines += [f"- `{entry}`" for entry in actionable] + [""]
    elif needs_major or unfixed_new:
        lines += ["No new advisory has an in-policy fix, so the gate passes.", ""]
    else:
        lines += ["No advisories outside the committed baseline.", ""]

    if needs_major:
        lines += [
            f"<details><summary>{len(needs_major)} new advisory/advisories needing a major "
            "(reported, not gated)</summary>",
            "",
        ]
        lines += [f"- `{entry}`" for entry in needs_major]
        lines += ["", "</details>", ""]

    if unfixed_new:
        lines += [
            f"<details><summary>{len(unfixed_new)} new advisory/advisories with no fix published"
            "</summary>",
            "",
        ]
        lines += [f"- `{entry}`" for entry in unfixed_new]
        lines += ["", "</details>", ""]

    # Capped to the installed major on purpose: see classify_fixes. The major column is kept
    # visible rather than dropped -- those advisories are real, and hiding them would turn a
    # policy about *how* upgrades land into a gap in what the audit reports.
    lines += [
        "Fix versions are capped to the installed major, matching the pip policy in "
        "`.github/dependabot.yml`. **In-policy fix** is what a minor/patch upgrade can take now; "
        "**needs major** is a migration to schedule, and nothing opens it automatically.",
        "",
        "| Package | Installed | Advisories | In-policy fix | Clears | Needs major |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    for name in sorted(findings, key=lambda n: (-len(findings[n]), n)):
        installed = versions.get(name, "?")
        total = len(findings[name])
        target, cleared, major_target, needs_major, unfixed = classify_fixes(installed, findings[name])
        notes = []
        if needs_major:
            notes.append(f"{major_target} (for {needs_major})")
        if unfixed:
            notes.append(f"{unfixed} with no fix listed")
        lines.append(
            f"| {name} | {installed} | {total} "
            f"| {target or '--'} | {cleared}/{total} | {', '.join(notes) or '--'} |"
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
    versions = {p["name"]: p.get("version", "?") for p in report.get("dependencies", [])}
    actionable, needs_major, unfixed_new = classify_new(findings, versions, new)

    summary = markdown_summary(report, findings, (actionable, needs_major, unfixed_new))
    print(summary)
    if args.summary:
        with args.summary.open("a") as handle:
            handle.write(summary)

    if actionable:
        print(
            f"FAIL: {len(actionable)} new advisory/advisories have a fix within the installed major.",
            file=sys.stderr,
        )
        return 1

    parked = len(needs_major) + len(unfixed_new)
    if parked:
        print(
            f"OK: {len(current)} advisories, none newly actionable. "
            f"{len(needs_major)} new need a major and {len(unfixed_new)} have no fix published -- "
            "listed above, and not gated on."
        )
    else:
        print(f"OK: {len(current)} advisories, all present in the baseline.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
