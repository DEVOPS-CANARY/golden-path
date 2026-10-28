#!/usr/bin/env bash
# Creates the GitHub Environments the shared pipeline deploys to, idempotently:
#   uat         branch develop
#   staging     branches staging and hotfix/*
#   production  branch main and tags v*, with one required reviewer
#
# Needs Administration: write on the repository: run it as a repository admin
# (`gh auth login`), or let the onboarding workflow run it with the optional
# admin App's token (README, "Optional: an admin App for environments").
#
# Usage: scripts/repo-environments.sh <owner/repo> <reviewer>
#   reviewer: a GitHub user handle, or org/team-slug for a team
set -euo pipefail

repo=${1:?usage: repo-environments.sh <owner/repo> <reviewer>}
reviewer=${2:?usage: repo-environments.sh <owner/repo> <reviewer>}

if [[ "$reviewer" == */* ]]; then
  reviewer_type=Team
  reviewer_id=$(gh api "orgs/${reviewer%%/*}/teams/${reviewer#*/}" --jq .id)
else
  reviewer_type=User
  reviewer_id=$(gh api "users/$reviewer" --jq .id)
fi

# environment <name> <reviewed: yes|no> <type:pattern>...
environment() {
  local name=$1 reviewed=$2
  shift 2
  local body='{"deployment_branch_policy":{"protected_branches":false,"custom_branch_policies":true}'
  if [ "$reviewed" = yes ]; then
    body="$body,\"reviewers\":[{\"type\":\"$reviewer_type\",\"id\":$reviewer_id}]"
  fi
  printf '%s}' "$body" | gh api -X PUT "repos/$repo/environments/$name" --input - --silent
  local existing
  existing=$(gh api "repos/$repo/environments/$name/deployment-branch-policies" \
    --jq '.branch_policies[] | "\(.type):\(.name)"')
  local policy
  for policy in "$@"; do
    if grep -qxF "$policy" <<< "$existing"; then continue; fi
    gh api -X POST "repos/$repo/environments/$name/deployment-branch-policies" \
      -f name="${policy#*:}" -f type="${policy%%:*}" --silent
  done
  if [ "$reviewed" = yes ]; then
    echo "environment $name: $* (reviewer: $reviewer)"
  else
    echo "environment $name: $*"
  fi
}

environment uat no branch:develop
environment staging no branch:staging 'branch:hotfix/*'
environment production yes branch:main 'tag:v*'
