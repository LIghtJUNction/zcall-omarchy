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

The **Bump version** workflow also accepts patch, minor or major through GitHub's Run workflow interface. It runs the same checks and atomic branch/tag push, then explicitly dispatches Release. This dispatch is required because a tag pushed with GITHUB_TOKEN does not itself trigger another push workflow.


For a version-only working diff:

```sh
python3 scripts/bump.py patch
```

For the complete release operation, start from a clean, pushed `main`:

```sh
python3 scripts/bump.py patch --release
```

The command updates both version files, runs checks, commits them, creates an annotated tag and pushes the branch and tag atomically. `minor`, `major` and an exact version are supported. The first release can tag the current version with `python3 scripts/bump.py 0.1.0 --release`.

The tag workflow checks the source, creates a reproducible tar archive and SHA256SUMS, publishes a GitHub release and optionally publishes the AUR recipe. The source-info release asset is explicitly named zcall-omarchy.SRCINFO because GitHub renames leading-dot asset names; the AUR checkout still uses the required .SRCINFO filename. Version tags and existing assets are immutable. A retry compares existing assets byte for byte before continuing; it never uses an overwrite flag.

Before publication, a failed check or confirmed failed atomic push restores only this operation's version files and removes its new local tag/commit. Unrelated files are preserved. If the remote cannot be checked, local state is retained for review. Once a remote tag exists, it is immutable: resume Release with that tag instead of rolling it back. Fix a published issue in the next version.

Source archives use plain tar with a fixed file-mode mask. This keeps their checksum independent of the installed compression-library version.

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
