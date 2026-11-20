# Releasing Zcall for Omarchy

The plugin version lives in `VERSION` and `manifest.json`. A release tag must agree with both. Release assets are generated from that exact Git commit; the current working tree is not copied into an archive.

## Routine iteration

Run the local checks after a meaningful change:

```sh
python3 scripts/check.py
```

For a change to CLI calls or library flows, set `ZCALLD_TEST_BINARY` to an absolute executable path. Those integration tests use a temporary home and do not start a gateway service. A bar or Omarchy API change also needs the installed Omarchy validator and `python3 scripts/validate-qml.py`.

The **Manual checks** workflow is available through workflow dispatch. Ordinary pushes do not trigger a CI run.

## Bump and publish

For a version-only working diff:

```sh
python3 scripts/bump.py patch
```

For the complete release operation, start from a clean, pushed `main`:

```sh
python3 scripts/bump.py patch --release
```

The command updates both version files, runs checks, commits them, creates an annotated tag and pushes the branch and tag atomically. `minor`, `major` and an exact version are supported. The first release can tag the current version with `python3 scripts/bump.py 0.1.0 --release`.

The tag workflow checks the source, creates a reproducible tar.gz archive and SHA256SUMS, publishes a GitHub release and optionally publishes the AUR recipe. Version tags and existing assets are immutable. A retry compares existing assets byte for byte before continuing; it never uses an overwrite flag.

If a push fails after the local tag is created, inspect the remote branch and tag before retrying. Do not move an already published tag. Fix a published issue in the next version.

## AUR publication

Repository configuration:

| Name | Kind | Purpose |
| --- | --- | --- |
| `AUR_SSH_KEY` | Secret | Maintainer key with access to the AUR package |
| `AUR_KNOWN_HOSTS` | Secret | Previously verified `aur.archlinux.org` host entry |
| `AUR_PUBLISH` | Variable, `true` | Enables the publication step |

The publisher creates temporary private SSH files, uses strict host verification and removes those files on exit. It does not discover or trust new host keys during a release.

`scripts/release.py --ref v0.1.0` generates `dist/aur/PKGBUILD` and `dist/aur/.SRCINFO` using the archive's SHA256. The package is architecture independent, installs no service and runs no home-directory hooks. The backend package remains a separate dependency.

Before a packaging change is released, use Arch's actual tools:

```sh
python3 scripts/release.py --ref HEAD
cd dist/aur
makepkg --printsrcinfo
makepkg --cleanbuild
```

Compare the printed source information with the generated `.SRCINFO`. A maintainer can use `--nodeps` only for an isolated package build when the upcoming zcalld version is not yet installed; this does not authorize installing a package with unsatisfied dependencies.

## Downstream coordination

After publishing, update zcalld's `apps/zcall-omarchy` submodule to the released commit and record the package version. A change to the zcalld JSON CLI contract must be coordinated with this frontend and tested with a real new binary before updating the minimum backend version.
