#!/usr/bin/env python3
"""Bump versions; --release checks, commits, tags and atomically pushes."""
import argparse
import json
import os
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
start = None
if args.release:
    if git("status", "--porcelain", capture=True):
        parser.error("--release requires a clean working tree")
    if git("branch", "--show-current", capture=True) != "main":
        parser.error("--release requires the main branch")
    git("fetch", "--quiet", "origin", "main")
    start = git("rev-parse", "HEAD", capture=True)
    if start != git("rev-parse", "origin/main", capture=True):
        parser.error("push or integrate main before releasing")
    if git("tag", "--list", tag, capture=True):
        parser.error("the release tag already exists locally")
    if git("ls-remote", "--tags", "origin", "refs/tags/" + tag, capture=True):
        parser.error("the release tag already exists remotely")

original = {name: (ROOT / name).read_bytes() for name in ("VERSION", "manifest.json")}
manifest = json.loads(original["manifest.json"])
manifest["version"] = version
updated = {"VERSION": (version + "\n").encode(),
           "manifest.json": (json.dumps(manifest, indent=2) + "\n").encode()}
created_commit = start
created_tag = None
push_attempted = False

def restore_local():
    # An uncertain network result must never cause a published tag to be
    # removed. Only roll back after the remote confirms our tag is absent.
    if push_attempted:
        try:
            advertised = git("ls-remote", "--tags", "origin", "refs/tags/" + tag, capture=True)
        except subprocess.CalledProcessError:
            print("Remote publication could not be checked; local commit and tag were retained.", file=sys.stderr)
            return
        if advertised:
            print("The remote tag exists; it is immutable. Resume the Release workflow for " + tag + ".", file=sys.stderr)
            return
    if args.release:
        head = git("rev-parse", "HEAD", capture=True)
        if head not in {start, created_commit}:
            print("HEAD changed concurrently; local state was retained for review.", file=sys.stderr)
            return
        if created_tag and git("rev-parse", "refs/tags/" + tag, capture=True) == created_tag:
            git("tag", "-d", tag)
        if head != start:
            git("reset", "--soft", start)
    for name, before in original.items():
        if args.release:
            git("restore", "--source", start, "--staged", "--", name)
        path = ROOT / name
        if path.read_bytes() == updated[name]:
            path.write_bytes(before)
        elif path.read_bytes() != before:
            print(name + " changed concurrently; its working copy was preserved.", file=sys.stderr)
    print("Unpublished version changes were rolled back; unrelated files were preserved.", file=sys.stderr)

try:
    for name, content in updated.items():
        (ROOT / name).write_bytes(content)
    subprocess.run([sys.executable, str(ROOT / "scripts/check.py")], cwd=ROOT, check=True)
    if args.release:
        if version != current:
            git("add", "VERSION", "manifest.json")
            git("commit", "-m", "release: v" + version)
            created_commit = git("rev-parse", "HEAD", capture=True)
        elif git("status", "--porcelain", capture=True):
            raise RuntimeError("canonical version formatting changed; commit it before tagging")
        git("tag", "-a", tag, "-m", "Zcall for Omarchy " + version)
        created_tag = git("rev-parse", "refs/tags/" + tag, capture=True)
        push_attempted = True
        git("push", "--atomic", "origin", "HEAD:refs/heads/main", "refs/tags/" + tag)
        print("Published immutable tag " + tag + ".")
        if "GITHUB_ACTIONS" in os.environ:
            print("The Bump workflow must explicitly dispatch release.yml for this tag.")
        else:
            print("The tag-triggered Release workflow will publish the assets.")
    else:
        print("Updated VERSION and manifest.json to " + version + ". Review and commit the diff.")
except (OSError, RuntimeError, subprocess.CalledProcessError) as error:
    restore_local()
    print("Version operation failed: " + str(error), file=sys.stderr)
    raise SystemExit(1)
