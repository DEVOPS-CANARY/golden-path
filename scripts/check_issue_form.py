"""Checks a GitHub Issue Form: valid YAML and the rules GitHub enforces silently.

GitHub ignores a form it cannot parse and shows a blank issue instead, with no
error anywhere. This fails CI instead. Usage: check_issue_form.py <form.yml>...
"""
import sys

import yaml

TYPES = {"markdown", "input", "textarea", "dropdown", "checkboxes"}


def check(path):
    with open(path, encoding="utf-8") as fh:
        form = yaml.safe_load(fh)
    problems = []
    for key in ("name", "description", "body"):
        if not form.get(key):
            problems.append(f"missing top-level '{key}'")
    body = form.get("body") or []
    ids, labels = [], []
    for n, block in enumerate(body, 1):
        kind = block.get("type")
        attrs = block.get("attributes") or {}
        if kind not in TYPES:
            problems.append(f"body[{n}]: unknown type {kind!r}")
            continue
        if kind == "markdown":
            if not attrs.get("value"):
                problems.append(f"body[{n}]: markdown needs a value")
            continue
        if not attrs.get("label"):
            problems.append(f"body[{n}]: {kind} needs a label")
        labels.append(attrs.get("label"))
        if block.get("id"):
            ids.append(block["id"])
        if kind == "dropdown":
            opts = attrs.get("options") or []
            if not opts:
                problems.append(f"body[{n}]: dropdown needs options")
            # GitHub refuses an option named "none" or "n/a" (the docs only
            # mention it for dropdowns with a default; tested: it is always).
            reserved = {str(o).strip().lower() for o in opts} & {"none", "n/a"}
            if reserved:
                problems.append(f"body[{n}]: dropdown has a reserved option {sorted(reserved)}")
        if kind == "checkboxes":
            opts = attrs.get("options") or []
            if not opts or any(not o.get("label") for o in opts):
                problems.append(f"body[{n}]: every checkbox needs a label")
    if not any(b.get("type") != "markdown" for b in body):
        problems.append("the form needs at least one field besides markdown")
    for name, items in (("id", ids), ("label", labels)):
        dup = sorted({x for x in items if items.count(x) > 1})
        if dup:
            problems.append(f"duplicate {name}s: {dup}")
    return problems


def main(paths):
    failed = False
    for path in paths:
        try:
            problems = check(path)
        except yaml.YAMLError as err:
            problems = [f"invalid YAML: {err}"]
        if problems:
            failed = True
            print(f"{path}:")
            for p in problems:
                print(f"  - {p}")
        else:
            print(f"{path}: ok")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
