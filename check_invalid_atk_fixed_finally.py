import argparse
import json
from pathlib import Path


def iter_json_files(paths):
    for raw_path in paths:
        path = Path(raw_path)
        if path.is_file() and path.suffix.lower() == ".json":
            yield path
        elif path.is_dir():
            yield from sorted(path.rglob("*.json"))


def find_invalid_atk_fixed_finally(node, path="$"):
    if isinstance(node, dict):
        kwargs = node.get("kwargs") if isinstance(node.get("kwargs"), dict) else {}
        if (
            kwargs.get("buff_type") == "atk_buff_fixed"
            and kwargs.get("target_stat") == "atk"
            and kwargs.get("stat_type") == "finally"
        ):
            yield {
                "path": path,
                "name": node.get("name", ""),
                "effect_type": node.get("effect_type", ""),
                "effect_no": kwargs.get("effect_no", ""),
            }

        for key, value in node.items():
            yield from find_invalid_atk_fixed_finally(value, f"{path}.{key}")
    elif isinstance(node, list):
        for index, value in enumerate(node):
            yield from find_invalid_atk_fixed_finally(value, f"{path}[{index}]")


def main():
    parser = argparse.ArgumentParser(
        description=(
            'Find JSON entries where "atk_buff_fixed" scales from final ATK. '
            'Fixed ATK buffs should not use target_stat=atk with stat_type=finally.'
        )
    )
    parser.add_argument(
        "paths",
        nargs="*",
        default=["characters"],
        help="JSON files or directories to inspect. Defaults to characters/.",
    )
    args = parser.parse_args()

    findings = []
    read_errors = []
    for json_path in iter_json_files(args.paths):
        try:
            with json_path.open("r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception as exc:
            read_errors.append(
                {
                    "file": str(json_path),
                    "error": f"{type(exc).__name__}: {exc}",
                }
            )
            continue

        for finding in find_invalid_atk_fixed_finally(data):
            finding["file"] = str(json_path)
            findings.append(finding)

    if not findings and not read_errors:
        print("OK: atk_buff_fixed with target_stat=atk and stat_type=finally was not found.")
        return

    if findings:
        print(f"Found {len(findings)} invalid definition(s):")
    for item in findings:
        details = []
        if item.get("name"):
            details.append(f"name={item['name']}")
        if item.get("effect_type"):
            details.append(f"effect_type={item['effect_type']}")
        if item.get("effect_no") != "":
            details.append(f"effect_no={item['effect_no']}")
        suffix = f" ({', '.join(details)})" if details else ""
        print(f"- {item['file']} :: {item['path']}{suffix}")

    if read_errors:
        print(f"Skipped {len(read_errors)} unreadable JSON file(s):")
        for item in read_errors:
            print(f"- {item['file']} :: {item['error']}")


if __name__ == "__main__":
    main()
