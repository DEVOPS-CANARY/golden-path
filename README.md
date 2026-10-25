# golden-path

The supported, automated way to onboard and run an app on the platform. An app team
declares what its app needs; this repo does the rest through reviewed pull requests.

| Part | Status |
|---|---|
| **Shared pipeline** (`.github/workflows/pipeline.yml`): gates, build, scan, push, deploy, promote | ✅ v1 |
| Onboarding form + templates (app repo, GitOps folder) | next |
| Per-namespace guardrails (Kyverno), bot identity, automatic updates (Renovate) | planned |

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
