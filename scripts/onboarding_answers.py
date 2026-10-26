"""Turn the body of an "Onboard an app" issue into the answers file both
templates read (Copier --data-file).

GitHub renders an issue form as Markdown: "### <Label>" followed by the value,
checkboxes as "- [x] Option". Usage:
    python scripts/onboarding_answers.py <issue-body.md> > answers.yml
Exits 1 with a readable message when a value is invalid, so the workflow can
post it back on the issue.
"""
import json
import re
import sys

NAME = re.compile(r"^[a-z][a-z0-9-]{0,30}$")
REPO = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")

# Form label -> answer key (labels as in .github/ISSUE_TEMPLATE/onboard-app.yml)
FIELDS = {
    "App name": "app",
    "GitHub repository": "repository",
    "Backend": "backend",
    "Backend port": "backend_port",
    "Backend database layer": "backend_orm",
    "Frontend": "frontend",
    "Background worker (name)": "worker",
    "Worker command": "worker_command",
    "Package manager": "package_manager",
    "The app needs": "needs",
    "Owner": "owner",
}


def sections(body: str) -> dict:
    out, key = {}, None
    for line in body.splitlines():
        if line.startswith("### "):
            key = line[4:].strip()
            out[key] = []
        elif key is not None:
            out[key].append(line)
    return {k: "\n".join(v).strip() for k, v in out.items()}


def fail(msg: str):
    print(f"invalid form: {msg}", file=sys.stderr)
    sys.exit(1)


def main(path: str):
    body = open(path, encoding="utf-8").read()
    raw = {FIELDS[k]: v for k, v in sections(body).items() if k in FIELDS}
    get = lambda k, d="": (raw.get(k, d) or d).strip()
    empty = {"", "_No response_", "None"}

    app = get("app")
    if not NAME.match(app):
        fail(f"app name '{app}' must be lowercase letters, digits and '-'")
    repository = get("repository")
    if not REPO.match(repository):
        fail(f"repository '{repository}' must be owner/name")
    backend = get("backend", "nestjs")
    frontend = get("frontend", "nextjs")
    if backend == "none" and frontend == "none":
        fail("an app needs at least a backend or a frontend")
    worker = "" if get("worker") in empty else get("worker")
    if worker and not NAME.match(worker):
        fail(f"worker name '{worker}' must be lowercase letters, digits and '-'")
    if worker and backend == "none":
        fail("a worker runs the backend image, so it needs a backend")
    port = get("backend_port", "3001")
    if not port.isdigit() or not 1 <= int(port) <= 65535:
        fail(f"backend port '{port}' is not a port number")
    needs = raw.get("needs", "")

    answers = {
        "app": app,
        "repository": repository,
        "backend": backend,
        "backend_port": int(port),
        "backend_orm": get("backend_orm", "prisma"),
        "frontend": frontend,
        "worker": worker,
        "worker_command": get("worker_command", "node dist/worker.js") or "node dist/worker.js",
        "package_manager": get("package_manager", "npm"),
        "needs_postgres": "[x] PostgreSQL" in needs,
        "needs_redis": "[x] Redis" in needs,
        "needs_kafka": "[x] Kafka" in needs,
        "owner": get("owner"),
    }
    # YAML-compatible JSON: Copier reads it as a data file.
    print(json.dumps(answers, indent=2))


if __name__ == "__main__":
    main(sys.argv[1])
