"""Compare two builds of the general role catalogue, for the person who
reviews a rebuild (scripts/build_general_catalogue.py) before it is committed.

    python scripts/compare_catalogues.py OLD_DIR NEW_DIR > compare.md
    python scripts/compare_catalogues.py --summary OLD_DIR NEW_DIR   # one line

Each folder holds role_skills_general.json and skill_taxonomy_general.json.
The report is Markdown: totals first, then per domain the roles that came in
or dropped out, and for roles in both builds the change in source postings
and the skills added or removed. Standard library only.
"""

import argparse
import json
from pathlib import Path

ROLES_FILE = "role_skills_general.json"
TAXONOMY_FILE = "skill_taxonomy_general.json"


def load(folder: Path) -> tuple[dict[tuple[str, str], dict], dict[str, list[str]]]:
    roles = json.loads((folder / ROLES_FILE).read_text(encoding="utf-8"))
    taxonomy = json.loads((folder / TAXONOMY_FILE).read_text(encoding="utf-8"))
    return {(r["domain"], r["role"]): r for r in roles}, taxonomy


def postings(role: dict) -> str:
    return f"{role.get('source_postings', 0):,}"


def summary(old_dir: Path, new_dir: Path) -> str:
    """The totals of report() in one line, for the end-of-run email."""
    old, old_tax = load(old_dir)
    new, new_tax = load(new_dir)
    kept = [k for k in new if k in old]
    changed = [k for k in kept if old[k]["skills"] != new[k]["skills"]]
    reordered = [k for k in changed if set(old[k]["skills"]) == set(new[k]["skills"])]
    return (
        f"{len(new)} roles (was {len(old)}): {len(new) - len(kept)} came in, {len(old) - len(kept)} dropped out, "
        f"{len(changed)} skill lists changed ({len(reordered)} only reordered); taxonomy {len(old_tax):,} -> "
        f"{len(new_tax):,} skills (+{len(set(new_tax) - set(old_tax))} / -{len(set(old_tax) - set(new_tax))})"
    )


def report(old_dir: Path, new_dir: Path) -> str:
    old, old_tax = load(old_dir)
    new, new_tax = load(new_dir)
    domains = list(dict.fromkeys([d for d, _ in old] + [d for d, _ in new]))
    kept = [k for k in new if k in old]
    changed = [k for k in kept if old[k]["skills"] != new[k]["skills"]]
    same_set = [k for k in changed if set(old[k]["skills"]) == set(new[k]["skills"])]

    out = [
        "# Role catalogue: old build vs new build",
        "",
        "| | Old | New |",
        "|---|---|---|",
        f"| Roles | {len(old)} | {len(new)} |",
        f"| Skills in the taxonomy | {len(old_tax)} | {len(new_tax)} |",
        f"| Source postings, all roles | {sum(r.get('source_postings', 0) for r in old.values()):,}"
        f" | {sum(r.get('source_postings', 0) for r in new.values()):,} |",
        "",
        f"- Roles in both builds: {len(kept)}; came in: {len(new) - len(kept)}; dropped out: {len(old) - len(kept)}",
        f"- Roles whose skill list changed: {len(changed)} ({len(same_set)} of them only reordered)",
        f"- Taxonomy skills added: {len(set(new_tax) - set(old_tax))}; removed: {len(set(old_tax) - set(new_tax))}",
    ]

    for domain in domains:
        came_in = [k for k in new if k[0] == domain and k not in old]
        dropped = [k for k in old if k[0] == domain and k not in new]
        roles = [k for k in kept if k[0] == domain]
        out += ["", f"## {domain}", ""]
        if came_in:
            out.append("Came in: " + ", ".join(f"{k[1]} ({postings(new[k])})" for k in came_in))
        if dropped:
            out.append("Dropped out: " + ", ".join(f"{k[1]} ({postings(old[k])})" for k in dropped))
        if came_in or dropped:
            out.append("")
        out += ["| Role | Postings old → new | Skills added | Skills removed |", "|---|---|---|---|"]
        for k in roles:
            added = [s for s in new[k]["skills"] if s not in old[k]["skills"]]
            removed = [s for s in old[k]["skills"] if s not in new[k]["skills"]]
            note = "reordered" if not added and not removed and old[k]["skills"] != new[k]["skills"] else ""
            out.append(
                f"| {k[1]} | {postings(old[k])} → {postings(new[k])} | {', '.join(added) or note} | {', '.join(removed)} |"
            )
        for k in came_in:
            out.append(f"| {k[1]} (new) | → {postings(new[k])} | {', '.join(new[k]['skills'])} | |")
    return "\n".join(out) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--summary", action="store_true", help="print the totals in one line")
    parser.add_argument("old_dir", type=Path)
    parser.add_argument("new_dir", type=Path)
    args = parser.parse_args()
    if args.summary:
        print(summary(args.old_dir, args.new_dir))
    else:
        print(report(args.old_dir, args.new_dir), end="")


if __name__ == "__main__":
    main()
