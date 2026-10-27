# golden-path

The supported, automated way to onboard and run an app on the platform. An app team
declares what its app needs; this repo does the rest through reviewed pull requests.

| Part | Status |
|---|---|
| **Shared pipeline** (`.github/workflows/pipeline.yml`): gates, build, scan, push, deploy, promote | ✅ v1 |
| **Onboarding**: the "Onboard an app" issue form, Copier templates for the app repo and the GitOps folder, a workflow that opens the PRs | ✅ v1.2 |
| Per-namespace guardrails (Kyverno): walls, quota, limits, image rule | ✅ in [GitOps-Repo](https://github.com/DEVOPS-CANARY/GitOps-Repo) `platform/policies` |
| Bot identity: the `goldenpath-bot` GitHub App (short-lived tokens, no personal tokens) | ✅ onboarding and deploys (deploy keys retired); releases next |
| **Versioned releases**: Conventional Commits check, release-please release PR, tag → prod, images tagged with the version | ✅ v1.4 |
| **Automatic updates**: Renovate runs here as the App on weekdays and opens PRs in every listed repo (actions, images, charts, npm); each repo extends the shared preset `default.json` | ✅ v1.5 |

## Onboarding an app

1. Open an issue from the **Onboard an app** form: app name, repository, components,
   package manager, what it needs (Postgres, Redis, Kafka), owner, readiness ticks.
2. Add the label **preview**: the workflow renders the templates and posts every generated
   file on the issue. Fix the form if needed and preview again.
3. A platform maintainer adds the label **approved**: the workflow prepares the app
   repository (branches `develop`, `staging`, `main` if missing; the three GitHub
   Environments when the admin App below is configured), then opens two pull requests
   and links them on the issue:
   - in the app repository: `.github/workflows/pipeline.yml` (the caller), `docker/*.Dockerfile`
     and their `.dockerignore`, `.hadolint.yaml`, and `.golden-path.yml` (the answers, so
     `copier update` can bring template improvements in later as a diff);
   - in GitOps-Repo: `apps/<app>/values.yaml`, `apps/<app>/envs/uat/values.yaml` (placeholder
     digests until the first deploy) and `envs/uat/secrets/README.md` with the exact sealing
     commands.
4. The PR checklists say what is left for people: the environments if no admin App is
   configured (one script run by a repository admin), sealed secrets, database/Redis/Kafka
   credentials. Merge the GitOps PR first, then the app PR; the first merge to `develop`
   deploys to UAT.

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

**Optional: an admin App for environments.** Creating GitHub Environments and their branch
policies needs *Administration: write*, which `goldenpath-bot` deliberately does not have. A
second App holding only that permission (variable `ONBOARDING_ADMIN_APP_ID`, secret
`ONBOARDING_ADMIN_APP_KEY`) lets the workflow create `uat`, `staging` and `production` (with
the form's owner as required reviewer) through a one-hour token scoped to the one repository
being onboarded. Without it, the app PR asks a repository admin to run
`scripts/repo-environments.sh <owner/repo> <reviewer>`, the same script, by hand.

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
    branches: [develop, staging, main, "hotfix/**"]
    tags: ["v*"] # a release (merged release PR): staging's images go to production
  workflow_dispatch: # on main: the same prod deploy without a version (fallback)

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
      GOLDEN_PATH_APP_KEY: ${{ secrets.GOLDEN_PATH_APP_KEY }} # org secret: deploys write to GitOps as the platform's App
```

What the app then gets:

| When | What happens |
|---|---|
| Every PR to `develop`, `staging`, `main` | Gates: Gitleaks (secrets, whole history), Semgrep (code), Trivy (dependencies), hadolint (Dockerfiles), the app's own checks (`format:check lint typecheck test build`), image build + Trivy image scan. Nothing is pushed. |
| Push to `develop` | Gates, then the images are pushed to GHCR and **deployed to UAT** |
| Push to `hotfix/<name>` (branched from `main`) | Gates, then deployed to the **staging environment** for testing, without going through the `staging` branch |
| Push to `staging` (PR `develop` → `staging`) | The images UAT tested are **promoted to staging**, found by content, never rebuilt |
| Push to `main` (PR `staging` → `main`) | release-please keeps a **"chore(main): release X.Y.Z" PR** up to date: the next version from the commit messages, the changelog |
| Merging that release PR (tag `vX.Y.Z`) | **Prod release**: waits for approval in the `production` environment, ships exactly the digests staging runs (staging's commit must be in `main`'s history), and tags the images `vX.Y.Z` |
| *Run workflow* on `main` | The same prod deploy without a version (fallback) |

Commit messages follow [Conventional Commits](https://www.conventionalcommits.org) and are checked
on every PR: `fix:` → patch, `feat:` → minor, `feat!:` or a `BREAKING CHANGE:` footer → major;
`chore:`, `docs:`, `refactor:`… don't bump. To force a number (e.g. continue an app's existing
numbering), add a `Release-As: 1.47.0` footer to a commit on `main`. Nobody types a tag.

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

Secret `GOLDEN_PATH_APP_KEY`: an org secret, the `goldenpath-bot` App's private key. With the
org variable `GOLDEN_PATH_APP_ID`, each deploy mints a one-hour token for the GitOps repo and
commits as the App. No per-app keys. (An org without the App can still pass an SSH deploy key
as `GITOPS_DEPLOY_KEY`.)

### What the app repo must have

- Branches `develop`, `staging`, `main`; hotfixes on `hotfix/<name>` from `main`.
- One folder per component with its `package.json`, lockfile and the scripts in `checks`.
- `docker/<component>.Dockerfile`, built with the component folder as its context.
- GitHub Environments `uat` (branch `develop`), `staging` (`staging`, `hotfix/*`) and
  `production` (`main` and tags `v*`, **required reviewer**).
- In GitOps-Repo: `apps/<app>/values.yaml` and `apps/<app>/envs/<env>/values.yaml` for each
  environment, using the `rssb-app` chart, with each component's image as
  `repository: ghcr.io/<org>/<app>-<component>` followed by a `digest:` line.

The onboarding workflow creates all of this (environments: see the admin App above).

## Versions

Apps pin a **major** tag: `@v1`. A release is a tag `v1.2.3` plus the moving major tag
`v1`; only the major tag moves. Within a major, changes keep every input and convention
working (new inputs get defaults). Anything that would break a caller is a new major, and
apps move to it with a one-line change in their caller.

To release: merge to `main`, then

```sh
git tag -a v1.2.3 -m "..." && git tag -f v1 v1.2.3 && git push origin v1.2.3 && git push -f origin v1
```

## Dependency updates (Renovate)

`.github/workflows/renovate.yml` runs Renovate on weekdays as the `goldenpath-bot` App over the
repositories in `.github/renovate-global.json`. Each of them keeps a two-line `renovate.json`
that extends the shared preset [`default.json`](default.json) in this repo, so the rules live in
one place: pinned GitHub Actions and container images move by digest + version, the charts Argo
CD pins (Traefik, KEDA, Kyverno) get one PR each, minor/patch updates are grouped, every update
waits **14 days** after its release (our supply-chain rule), and security fixes skip the wait.
PRs are opened before 7am Kigali on Mondays; nothing is merged automatically.
Run it by hand: Actions → Renovate → Run workflow (log level `debug` to see why something is
or isn't proposed).

## Rules for this repo

- Every action pinned to a commit SHA; every scanner image pinned by digest.
- Inputs reach shell through environment variables, never interpolated into scripts.
- Jobs ask only for the permissions they need; the caller grants `contents: read` and
  `packages: write`, nothing more.
- `actionlint` + `shellcheck` run on every PR (`.github/workflows/lint.yml`); test locally with
  `docker run --rm -v "$PWD:/repo" -w /repo rhysd/actionlint:1.7.12`.
- No secrets, hostnames or credentials in this repo: it is public.
