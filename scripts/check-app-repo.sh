#!/usr/bin/env bash
# Checks that an app repository matches the onboarding answers before anything
# is rendered for it: each component folder exists, has a package.json and the
# lockfile of the chosen package manager. Catches the most common form slip
# (npm chosen, yarn.lock in the repo), which otherwise fails the first pipeline
# run in three places. Usage: check-app-repo.sh <owner/repo> <answers.json>
# Needs GH_TOKEN able to read the repository. Exit 1 with the problems listed.
set -euo pipefail
repository=$1 answers=$2
pm=$(jq -r .package_manager "$answers")
case "$pm" in yarn) lock=yarn.lock; other=package-lock.json ;; *) lock=package-lock.json; other=yarn.lock ;; esac
problems=()
for component in backend frontend; do
  [ "$(jq -r ".$component" "$answers")" != "not-needed" ] || continue
  if ! names=$(gh api "repos/$repository/contents/$component" --jq '.[].name' 2>/dev/null); then
    problems+=("folder \`$component/\` not found in $repository")
    continue
  fi
  grep -qx package.json <<<"$names" || problems+=("\`$component/package.json\` missing")
  if ! grep -qx "$lock" <<<"$names"; then
    hint=""
    grep -qx "$other" <<<"$names" && hint=" (it has \`$other\`: choose the other package manager, or switch the app)"
    problems+=("\`$component/$lock\` missing, but package manager \`$pm\` was chosen$hint")
  fi
done
if [ ${#problems[@]} -gt 0 ]; then
  printf '%s\n' "${problems[@]}"
  exit 1
fi
echo "$repository matches the answers (package manager $pm)"
