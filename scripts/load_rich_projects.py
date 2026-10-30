#!/usr/bin/env python3
"""Load reviewed rich-project values from a proposals CSV into the API.

    python scripts/load_rich_projects.py proposals.csv --base-url http://127.0.0.1:3600/api
    python scripts/load_rich_projects.py proposals.csv --base-url http://127.0.0.1:3600/api --force

By default a field is only written if it is blank on the project right now.
--force writes every non-empty proposed value, even over an existing one.
Output names fields only, never values.
Stops the whole run if a row's project_id differs from the database's id for that name.
"""
import argparse
import csv
import json
import sys

import httpx

FIELDS = {
    "proposed_display_name": "display_name",
    "proposed_description": "description",
    "proposed_url": "url",
    "proposed_college_and_department_id": "college_and_department_id",
    "proposed_fos_id": "fos_id",
}


def is_blank(field, project):
    value = project.get(field)
    if value is None:
        return True
    if isinstance(value, str):
        if not value.strip():
            return True
        # display_name is backfilled to name, so equal-to-name means never set
        if field == "display_name" and value == project.get("name"):
            return True
    return False


def same_value(field, proposed, current):
    # the API stores bare-host urls with a trailing slash, so compare ignoring it
    if field == "url" and current:
        return proposed.rstrip("/") == current.rstrip("/")
    return proposed == current


def build_body(row, project, force):
    body = {}
    for column, field in FIELDS.items():
        raw = (row.get(column) or "").strip()
        if not raw:
            continue
        value = int(raw) if field == "college_and_department_id" else raw
        if same_value(field, value, project.get(field)):
            continue
        # url is always eligible: the proposal only exists when the old one was missing or dead
        if force or field == "url" or is_blank(field, project):
            body[field] = value
    return body


def csv_project_id(row):
    try:
        return int((row.get("project_id") or "").strip())
    except ValueError:
        return None


def abort_on_id_mismatch(name, csv_id, api_id):
    bar = "!" * 64
    shown = csv_id if csv_id is not None else "(blank or not a number)"
    print(
        f"\n{bar}\nPROJECT ID MISMATCH - STOPPING THE RUN\n"
        f"  project:        {name}\n"
        f"  CSV project_id: {shown}\n"
        f"  database id:    {api_id}\n"
        "The CSV does not match this database. Nothing was written for this row\n"
        f"or any after it; earlier rows were already processed.\n{bar}",
        file=sys.stderr,
        flush=True,
    )
    sys.exit(2)


def error_keys(response):
    try:
        return sorted({str(d["loc"][-1]) for d in response.json()["detail"]})
    except Exception:
        return []


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("csv_path")
    parser.add_argument("--base-url", required=True, help="API base, e.g. http://127.0.0.1:3600/api")
    parser.add_argument("--force", action="store_true", help="overwrite existing values")
    args = parser.parse_args()

    base = args.base_url.rstrip("/")
    tally = {"wrote": 0, "unchanged": 0, "not found": 0, "errors": 0}

    def report(name, message, outcome):
        tally[outcome] += 1
        print(f"{name}: {message}", flush=True)

    with open(args.csv_path, newline="", encoding="utf-8-sig") as f, httpx.Client(timeout=30) as client:
        for row in csv.DictReader(f):
            name = (row.get("name") or "").strip()
            if not name:
                continue
            try:
                response = client.get(f"{base}/projects", params={"name": f"eq.{name}"})
                response.raise_for_status()
                matches = response.json()
                if not matches:
                    report(name, "not found", "not found")
                    continue
                project = matches[0]
                csv_id = csv_project_id(row)
                if csv_id != project["id"]:
                    abort_on_id_mismatch(name, csv_id, project["id"])
                body = build_body(row, project, args.force)
                if not body:
                    report(name, "nothing to write", "unchanged")
                    continue
                response = client.put(f"{base}/projects/{project['id']}", json=body)
                response.raise_for_status()
                report(name, "wrote " + ", ".join(body), "wrote")
            except httpx.HTTPStatusError as e:
                keys = error_keys(e.response)
                suffix = f" ({', '.join(keys)})" if keys else ""
                report(name, f"HTTP {e.response.status_code}{suffix}", "errors")
            except httpx.HTTPError as e:
                report(name, type(e).__name__, "errors")
            except json.JSONDecodeError:
                report(name, "response was not JSON", "errors")
            except ValueError:
                report(name, "non-numeric college_and_department_id, skipped", "errors")

    print("done: " + ", ".join(f"{count} {label}" for label, count in tally.items()))
    sys.exit(1 if tally["errors"] else 0)


if __name__ == "__main__":
    main()
