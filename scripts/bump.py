#!/usr/bin/env python3
"""Bump the two version files; --release checks, commits, tags and atomically pushes."""
import argparse
import json
from pathlib import Path
import re
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("version", help="patch, minor, major, or an exact numeric version")
parser.add_argument("--release", action="store_true")
args = parser.parse_args()

def git(*arguments, capture=False):
    result = subprocess.run(["git", *arguments], cwd=ROOT, check=True,
                            stdout=subprocess.PIPE if capture else None, text=True)
    return result.stdout.strip() if capture else None

current = (ROOT / "VERSION").read_text().strip()
parts = [int(value) for value in current.split(".")]
if args.version in ("major", "minor", "patch"):
    index = ("major", "minor", "patch").index(args.version)
    parts[index] += 1
    for following in range(index + 1, 3):
        parts[following] = 0
    version = ".".join(map(str, parts))
else:
    version = args.version
if not re.fullmatch(r"(?:0|[1-9]\d*)\.(?:0|[1-9]\d*)\.(?:0|[1-9]\d*)", version):
    parser.error("expected a numeric semantic version")
if tuple(map(int, version.split("."))) < tuple(map(int, current.split("."))):
    parser.error("version cannot go backwards")
tag = "v" + version
if args.release:
    if git("status", "--porcelain", capture=True):
        parser.error("--release requires a clean working tree")
    if git("branch", "--show-current", capture=True) != "main":
        parser.error("--release requires the main branch")
    git("fetch", "--quiet", "origin", "main")
    if git("rev-parse", "HEAD", capture=True) != git("rev-parse", "origin/main", capture=True):
        parser.error("push or integrate main before releasing")
    if git("tag", "--list", tag, capture=True):
        parser.error("the release tag already exists locally")
    if git("ls-remote", "--tags", "origin", "refs/tags/" + tag, capture=True):
        parser.error("the release tag already exists remotely")
manifest_path = ROOT / "manifest.json"
manifest = json.loads(manifest_path.read_text())
manifest["version"] = version
(ROOT / "VERSION").write_text(version + "\n")
manifest_path.write_text(json.dumps(manifest, indent=2) + "\n")
subprocess.run([sys.executable, str(ROOT / "scripts/check.py")], cwd=ROOT, check=True)
if args.release:
    if version != current:
        git("add", "VERSION", "manifest.json")
        git("commit", "-m", "release: v" + version)
    elif git("status", "--porcelain", capture=True):
        parser.error("canonical version formatting changed; commit it before tagging")
    git("tag", "-a", tag, "-m", "Zcall for Omarchy " + version)
    git("push", "--atomic", "origin", "HEAD:refs/heads/main", "refs/tags/" + tag)
    print("Published tag " + tag + "; the formal release workflow will build and publish it.")
else:
    print("Updated VERSION and manifest.json to " + version + ". Review and commit the diff.")
