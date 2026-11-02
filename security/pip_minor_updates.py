#!/usr/bin/env python3
"""Report pip packages pinned in pyproject.toml that have a newer release in their own major.

Scope is deliberately narrow: this answers "is there a minor or patch release waiting for something
we pin?" and nothing else. It does not look at advisories, and it does not consider majors -- those
are excluded by the pip policy in .github/dependabot.yml, so reporting them would be reporting work
nothing is allowed to do automatically.

Only exact `==` pins can be compared, since a range has no single current version to measure
against. Everything else is listed as unchecked rather than silently dropped.

Two honest limits, both of which cost a false positive rather than a miss:

  * Availability is not installability. Another pinned package can cap the one being updated --
    djangorestframework-gis pinned djangorestframework below its own fix at one point -- so taking
    a reported update may mean moving the capping pin too.
  * A pin can be tied to something outside PyPI. GDAL is the standing example: the sdist builds
    against the system libgdal, so its version is set by the base image's Ubuntu release and not
    chosen here. Those live in security/pip-update-ignore.txt with a reason.

Usage:
    python3 security/pip_minor_updates.py [--pyproject pyproject.toml] [--summary "$GITHUB_STEP_SUMMARY"]

Exits 1 when an update is available, 0 when every comparable pin is current.
"""

import argparse
import concurrent.futures
import json
import pathlib
import re
import sys
import tomllib
import urllib.error
import urllib.request

PYPI = "https://pypi.org/pypi/{}/json"
IGNORE_FILE = pathlib.Path(__file__).with_name("pip-update-ignore.txt")

# A release we would never pin on purpose. PEP 440 pre-release and dev spellings.
PRERELEASE = re.compile(r"(a|b|rc|alpha|beta|dev|pre|post)", re.IGNORECASE)
EXACT_PIN = re.compile(r"^\s*([A-Za-z0-9][A-Za-z0-9._-]*)\s*==\s*([^\s,;\[\]]+)\s*$")


def version_key(version):
    """PEP 440-lite ordering on the leading numeric release components.

    Sorting these as strings puts "9.0.3" above "13.0.0" and "26.3.1" above "26.10.1", which is
    exactly the kind of wrong answer that is hard to notice in a table.
    """
    parts = []
    for chunk in re.split(r"[.+-]", version.strip()):
        match = re.match(r"^(\d+)", chunk)
        if not match:
            break
        parts.append(int(match.group(1)))
    return tuple(parts) or (0,)


def is_final(version):
    """True for a plain numeric release: 5.2.18 yes, 5.2rc1 / 1.0.dev0 / 2.0b1 no."""
    return re.fullmatch(r"[0-9]+(\.[0-9]+)*", version.strip()) is not None


def read_ignores():
    """-> {canonical_name: reason}. Lines are `name: reason`, `#` comments ignored."""
    ignores = {}
    if not IGNORE_FILE.exists():
        return ignores
    for line in IGNORE_FILE.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        name, _, reason = line.partition(":")
        ignores[canonical(name)] = reason.strip() or "no reason recorded"
    return ignores


def canonical(name):
    """PEP 503 normalisation, so Pillow/pillow and foo_bar/foo-bar compare equal."""
    return re.sub(r"[-_.]+", "-", name.strip()).lower()


def read_pins(path):
    """-> (pins, unchecked) from [project].dependencies.

    pins is [(name, version)] for exact `==` requirements; unchecked is the raw text of everything
    else, which has no single version to compare and so cannot be judged either way.
    """
    data = tomllib.loads(path.read_text())
    pins, unchecked = [], []
    for requirement in data.get("project", {}).get("dependencies", []):
        # An environment marker makes the requirement conditional; the pin itself still reads fine.
        base = requirement.split(";", 1)[0]
        match = EXACT_PIN.match(base)
        if match and is_final(match.group(2)):
            pins.append((match.group(1), match.group(2)))
        else:
            unchecked.append(requirement.strip())
    return pins, unchecked


def latest_in_major(name, pinned, timeout=20):
    """-> (latest_final_release_in_the_pinned_major, error). Exactly one of the two is None."""
    try:
        with urllib.request.urlopen(PYPI.format(name), timeout=timeout) as response:
            payload = json.load(response)
    except urllib.error.HTTPError as exc:
        return None, f"HTTP {exc.code}"
    except Exception as exc:  # noqa: BLE001 -- a probe failure must not read as "up to date"
        return None, type(exc).__name__

    major = version_key(pinned)[:1]
    candidates = [
        version
        for version, files in payload.get("releases", {}).items()
        if files and is_final(version) and not PRERELEASE.search(version) and version_key(version)[:1] == major
    ]
    if not candidates:
        return None, "no final release in this major"
    return max(candidates, key=version_key), None


def check(pins, ignores, workers=12):
    """-> (updates, current, ignored, errors). Queries PyPI concurrently; order is restored after."""
    updates, current, ignored, errors = [], [], [], []
    to_query = []
    for name, pinned in pins:
        if canonical(name) in ignores:
            ignored.append((name, pinned, ignores[canonical(name)]))
        else:
            to_query.append((name, pinned))

    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(latest_in_major, n, v): (n, v) for n, v in to_query}
        for future in concurrent.futures.as_completed(futures):
            name, pinned = futures[future]
            latest, error = future.result()
            if error:
                errors.append((name, pinned, error))
            elif version_key(latest) > version_key(pinned):
                updates.append((name, pinned, latest))
            else:
                current.append((name, pinned))

    updates.sort(key=lambda row: row[0].lower())
    errors.sort(key=lambda row: row[0].lower())
    ignored.sort(key=lambda row: row[0].lower())
    return updates, current, ignored, errors


def markdown_summary(updates, current, ignored, errors, unchecked):
    lines = ["## pip: minor and patch updates", ""]
    if updates:
        lines += [f"**{len(updates)} pinned package(s) have a newer release in their own major.**", ""]
        lines += ["| Package | Pinned | Latest in major |", "| --- | --- | --- |"]
        lines += [f"| {name} | `{pinned}` | `{latest}` |" for name, pinned, latest in updates]
        lines += [""]
    else:
        lines += [f"Every comparable pin is current ({len(current)} checked).", ""]

    if errors:
        lines += [
            f"**{len(errors)} package(s) could not be checked.** Treated as a failure: a probe that "
            "did not answer is not evidence of being up to date.",
            "",
            "| Package | Pinned | Problem |",
            "| --- | --- | --- |",
        ]
        lines += [f"| {name} | `{pinned}` | {why} |" for name, pinned, why in errors]
        lines += [""]

    if ignored:
        lines += [
            f"<details><summary>{len(ignored)} pin(s) excluded by "
            "<code>security/pip-update-ignore.txt</code></summary>",
            "",
            "| Package | Pinned | Why |",
            "| --- | --- | --- |",
        ]
        lines += [f"| {name} | `{pinned}` | {why} |" for name, pinned, why in ignored]
        lines += ["", "</details>", ""]

    if unchecked:
        lines += [
            f"<details><summary>{len(unchecked)} requirement(s) not pinned with <code>==</code>, "
            "so not comparable</summary>",
            "",
        ]
        lines += [f"- `{requirement}`" for requirement in unchecked]
        lines += ["", "</details>", ""]

    lines += [
        "Majors are out of scope by design: the pip policy in `.github/dependabot.yml` ignores "
        "`version-update:semver-major`, so a major is a scheduled migration rather than something "
        "this check can ask for.",
    ]
    return "\n".join(lines) + "\n"


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--pyproject", type=pathlib.Path, default=pathlib.Path("pyproject.toml"))
    parser.add_argument("--summary", type=pathlib.Path, help="append a Markdown summary to this file")
    args = parser.parse_args()

    pins, unchecked = read_pins(args.pyproject)
    ignores = read_ignores()
    updates, current, ignored, errors = check(pins, ignores)

    summary = markdown_summary(updates, current, ignored, errors, unchecked)
    print(summary)
    if args.summary:
        with args.summary.open("a") as handle:
            handle.write(summary)

    if updates or errors:
        if updates:
            print(f"FAIL: {len(updates)} pinned package(s) have a minor/patch update available.", file=sys.stderr)
        if errors:
            print(f"FAIL: {len(errors)} pinned package(s) could not be checked.", file=sys.stderr)
        return 1

    print(f"OK: {len(current)} pin(s) current, {len(ignored)} ignored, {len(unchecked)} not comparable.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
