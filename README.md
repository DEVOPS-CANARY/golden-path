# golden-path

The supported, automated way to onboard and run an app on the platform. An app team
declares what its app needs; this repo does the rest through reviewed pull requests.

| Part | Status |
|---|---|
| **Shared pipeline** (`.github/workflows/pipeline.yml`): gates, build, scan, push, deploy, promote | ✅ v1 |
| **Onboarding**: the "Onboard an app" issue form, Copier templates for the app repo and the GitOps folder, a workflow that opens the PRs | ✅ v1.2 |
| Per-namespace guardrails (Kyverno): walls, quota, limits, image rule | ✅ in [GitOps-Repo](https://github.com/DEVOPS-CANARY/GitOps-Repo) `platform/policies` |
| Bot identity: the `goldenpath-bot` GitHub App (short-lived tokens, no personal tokens) | ✅ for onboarding; deploys and releases next |
| Versioned releases, automatic updates (Renovate) | planned |

## Onboarding an app

1. Open an issue from the **Onboard an app** form: app name, repository, components,
   package manager, what it needs (Postgres, Redis, Kafka), owner, readiness ticks.
2. Add the label **preview**: the workflow renders the templates and posts every generated
   file on the issue. Fix the form if needed and preview again.
3. A platform maintainer adds the label **approved**: the workflow opens two pull requests
   and links them on the issue:
   - in the app repository: `.github/workflows/pipeline.yml` (the caller), `docker/*.Dockerfile`
     and their `.dockerignore`, `.hadolint.yaml`, and `.golden-path.yml` (the answers, so
     `copier update` can bring template improvements in later as a diff);
   - in GitOps-Repo: `apps/<app>/values.yaml`, `apps/<app>/envs/uat/values.yaml` (placeholder
     digests until the first deploy) and `envs/uat/secrets/README.md` with the exact sealing
     commands.
4. The PR checklists say what is left for people: branches and GitHub Environments, the
   `GITOPS_DEPLOY_KEY` secret, sealed secrets, database/Redis/Kafka credentials. Merge the
   GitOps PR first, then the app PR; the first merge to `develop` deploys to UAT.

What the templates produce is what logistics runs today: the same pipeline caller, the
same Dockerfile structure (multi-stage, pinned base by digest, non-root, no package
managers at runtime, migrations from the image), the same chart values shape.

**The onboarding App**: the workflow writes to other repos as the GitHub App `goldenpath-bot`
(installed on the org's repos, permissions *Contents* and *Pull requests* read & write). Its
App ID is the repository variable `ONBOARDING_APP_ID`, its private key the secret
`ONBOARDING_APP_KEY` (set with `gh secret set ONBOARDING_APP_KEY < key.pem`, then delete the
file). Each run mints a token that lives one hour and only covers the two repositories it
touches; commits are authored by `goldenpath-bot[bot]`. Without the App, **preview** works and
**approved** stops with a message on the issue.

By hand, without the form (needs [Copier](https://copier.readthedocs.io) 9.18+):

```sh
copier copy --trust --data template=app-repo   gh:DEVOPS-CANARY/golden-path ../my-app       # answers asked interactively
copier copy --trust --data template=gitops-app gh:DEVOPS-CANARY/golden-path ../GitOps-Repo
copier update --trust      # later, inside ../my-app: template changes since its version, as a diff
```

Every PR to this repo renders both templates for the sample apps in `templates/tests/` and
checks the output exactly as the pipeline would (hadolint, actionlint, the chart, kubeconform).

The platform pieces an app relies on, and where they live:

| Repo | Holds |
|---|---|
| **golden-path** (this repo) | How an app is built, checked, deployed and onboarded |
| [helm-charts](https://github.com/DEVOPS-CANARY/helm-charts) | How an app runs in the cluster (the `rssb-app` chart) |
| [GitOps-Repo](https://github.com/DEVOPS-CANARY/GitOps-Repo) | What runs where: values per app per environment, sealed secrets |
| App repos | Code, Dockerfiles, and one short workflow that calls the pipeline |

## Using the pipeline

An app repo keeps this one file, `.github/workflows/pipeline.yml`:

```yaml
name: Pipeline

on:
  pull_request:
    branches: [develop, staging, main]
  push:
    branches: [develop, staging, "hotfix/**"]
  workflow_dispatch: # on main: release to production

permissions:
  contents: read

concurrency:
  group: pipeline-${{ github.ref }}
  cancel-in-progress: ${{ github.event_name == 'pull_request' }} # superseded PR runs stop; deploys always finish

jobs:
  pipeline:
    uses: DEVOPS-CANARY/golden-path/.github/workflows/pipeline.yml@v1
    permissions:
      contents: read
      packages: write # push images to GHCR
    with:
      app: logistics
      components: '["backend", "frontend"]'
    secrets:
      GITOPS_DEPLOY_KEY: ${{ secrets.GITOPS_DEPLOY_KEY }}
```

What the app then gets:

| When | What happens |
|---|---|
| Every PR to `develop`, `staging`, `main` | Gates: Gitleaks (secrets, whole history), Semgrep (code), Trivy (dependencies), hadolint (Dockerfiles), the app's own checks (`format:check lint typecheck test build`), image build + Trivy image scan. Nothing is pushed. |
| Push to `develop` | Gates, then the images are pushed to GHCR and **deployed to UAT** |
| Push to `hotfix/<name>` (branched from `main`) | Gates, then deployed to the **staging environment** for testing, without going through the `staging` branch |
| Push to `staging` (PR `develop` → `staging`) | The images UAT tested are **promoted to staging**, found by content, never rebuilt |
| *Run workflow* on `main` (after PR `staging` → `main`) | **Prod release**: waits for approval in the `production` environment and only accepts the exact digests staging runs |

Deploys are GitOps commits: the pipeline writes the new image digests into
`apps/<app>/envs/<env>/values.yaml` in GitOps-Repo, and Argo CD rolls them out. CI never
touches the cluster.

### Inputs

| Input | Required | Default | Meaning |
|---|---|---|---|
| `app` | yes | | Product name, lowercase: image prefix `ghcr.io/<org>/<app>-<component>`, GitOps folder `apps/<app>` |
| `components` | yes | | JSON list of components, each a folder with a `package.json` and a `docker/<component>.Dockerfile` |
| `node-version` | | `22` | Node major used for the checks (Dockerfiles pin their own) |
| `package-manager` | | `npm` | `npm` or `yarn` (installs from the lockfile, exactly) |
| `checks` | | `format:check lint typecheck test build` | `package.json` scripts run on every component, in order |
| `dockerfile-dir` | | `docker` | Folder holding `<component>.Dockerfile` |
| `gitops-repo` | | `DEVOPS-CANARY/GitOps-Repo` | Where deploys are committed |

Secret `GITOPS_DEPLOY_KEY`: an SSH deploy key with write access to the GitOps repo.

### What the app repo must have

- Branches `develop`, `staging`, `main`; hotfixes on `hotfix/<name>` from `main`.
- One folder per component with its `package.json`, lockfile and the scripts in `checks`.
- `docker/<component>.Dockerfile`, built with the component folder as its context.
- GitHub Environments `uat` (branch `develop`), `staging` (`staging`, `hotfix/*`) and
  `production` (`main` only, **required reviewer**), plus the secret `GITOPS_DEPLOY_KEY`.
- In GitOps-Repo: `apps/<app>/values.yaml` and `apps/<app>/envs/<env>/values.yaml` for each
  environment, using the `rssb-app` chart, with each component's image as
  `repository: ghcr.io/<org>/<app>-<component>` followed by a `digest:` line.

The onboarding template (next step) creates all of this.

## Versions

Apps pin a **major** tag: `@v1`. A release is a tag `v1.2.3` plus the moving major tag
`v1`; only the major tag moves. Within a major, changes keep every input and convention
working (new inputs get defaults). Anything that would break a caller is a new major, and
apps move to it with a one-line change in their caller.

To release: merge to `main`, then

```sh
git tag -a v1.2.3 -m "..." && git tag -f v1 v1.2.3 && git push origin v1.2.3 && git push -f origin v1
```

## Rules for this repo

- Every action pinned to a commit SHA; every scanner image pinned by digest.
- Inputs reach shell through environment variables, never interpolated into scripts.
- Jobs ask only for the permissions they need; the caller grants `contents: read` and
  `packages: write`, nothing more.
- `actionlint` + `shellcheck` run on every PR (`.github/workflows/lint.yml`); test locally with
  `docker run --rm -v "$PWD:/repo" -w /repo rhysd/actionlint:1.7.12`.
- No secrets, hostnames or credentials in this repo: it is public.
