#!/usr/bin/env python3
"""Build a reproducible archive and a pinned, standard AUR recipe."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess

ROOT = Path(__file__).resolve().parents[1]
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--ref", default="HEAD", help="HEAD or a numeric vMAJOR.MINOR.PATCH tag")
parser.add_argument("--output", type=Path, default=ROOT / "dist")
args = parser.parse_args()
if args.ref != "HEAD" and not re.fullmatch(r"v(?:0|[1-9]\d*)\.(?:0|[1-9]\d*)\.(?:0|[1-9]\d*)", args.ref):
    parser.error("ref must be HEAD or a numeric release tag")

def git(*arguments):
    return subprocess.check_output(["git", *arguments], cwd=ROOT)

commit = git("rev-parse", "--verify", args.ref + "^{commit}").decode().strip()
version = git("show", commit + ":VERSION").decode().strip()
if not re.fullmatch(r"(?:0|[1-9]\d*)\.(?:0|[1-9]\d*)\.(?:0|[1-9]\d*)", version):
    raise SystemExit("Invalid VERSION in selected commit")
manifest = json.loads(git("show", commit + ":manifest.json"))
if manifest["version"] != version or (args.ref != "HEAD" and args.ref != "v" + version):
    raise SystemExit("Tag, VERSION and plugin manifest must agree")
name = "zcall-omarchy-" + version
# A plain tar keeps release bytes independent of the host's zlib variant.
# The complete frontend source is small; no compressor or container is needed.
archive = git("-c", "tar.umask=0022", "archive", "--format=tar", "--prefix=" + name + "/", commit)
sha = hashlib.sha256(archive).hexdigest()
args.output.mkdir(parents=True, exist_ok=True)
(args.output / (name + ".tar")).write_bytes(archive)
(args.output / "SHA256SUMS").write_text(sha + "  " + name + ".tar\n")
aur = args.output / "aur"
aur.mkdir(exist_ok=True)
for template, target in (("PKGBUILD.in", "PKGBUILD"), ("SRCINFO.in", ".SRCINFO")):
    source = git("show", commit + ":packaging/" + template).decode()
    (aur / target).write_text(source.replace("@VERSION@", version).replace("@SHA256@", sha))
(args.output / "zcall-omarchy.SRCINFO").write_bytes((aur / ".SRCINFO").read_bytes())
record = {"project": "zcall-omarchy", "version": version, "commit": commit,
          "archive": name + ".tar", "sha256": sha}
(args.output / "release.json").write_text(json.dumps(record, indent=2) + "\n")
print(json.dumps(record))
