#!/usr/bin/env bash
set -euo pipefail
recipe_dir=${1:?usage: publish-aur.sh RECIPE_DIRECTORY}
: "${AUR_SSH_KEY:?AUR_SSH_KEY is required}"
: "${AUR_KNOWN_HOSTS:?AUR_KNOWN_HOSTS is required}"
test -f "$recipe_dir/PKGBUILD"
test -f "$recipe_dir/.SRCINFO"
temporary=$(mktemp -d)
trap 'rm -rf "$temporary"' EXIT
umask 077
printf '%s\n' "$AUR_SSH_KEY" > "$temporary/key"
printf '%s\n' "$AUR_KNOWN_HOSTS" > "$temporary/known_hosts"
unset AUR_SSH_KEY AUR_KNOWN_HOSTS
ssh-keygen -F aur.archlinux.org -f "$temporary/known_hosts" >/dev/null
export GIT_SSH_COMMAND="ssh -i $temporary/key -o IdentitiesOnly=yes -o StrictHostKeyChecking=yes -o UserKnownHostsFile=$temporary/known_hosts"
git clone ssh://aur@aur.archlinux.org/zcall-omarchy.git "$temporary/aur"
cp "$recipe_dir/PKGBUILD" "$temporary/aur/PKGBUILD"
cp "$recipe_dir/.SRCINFO" "$temporary/aur/.SRCINFO"
git -C "$temporary/aur" add PKGBUILD .SRCINFO
if git -C "$temporary/aur" diff --cached --quiet; then
  printf '%s\n' 'AUR already has this exact recipe.'
  exit 0
fi
git -C "$temporary/aur" -c user.name='LIghtJUNction release automation' \
  -c user.email='41898282+github-actions[bot]@users.noreply.github.com' \
  commit -m "Update zcall-omarchy $(sed -n 's/^[[:space:]]*pkgver = //p' "$recipe_dir/.SRCINFO")"
git -C "$temporary/aur" push origin HEAD:master
