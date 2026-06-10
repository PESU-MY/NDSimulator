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


def find_missing_stack_names(node, path="$"):
    if isinstance(node, dict):
        effect_type = node.get("effect_type")
        kwargs = node.get("kwargs") if isinstance(node.get("kwargs"), dict) else {}
        if effect_type == "stack_buff" and not kwargs.get("stack_name"):
            yield {
                "path": path,
                "name": node.get("name", ""),
                "buff_type": kwargs.get("buff_type", ""),
                "effect_no": kwargs.get("effect_no", ""),
            }

        for key, value in node.items():
            yield from find_missing_stack_names(value, f"{path}.{key}")
    elif isinstance(node, list):
        for index, value in enumerate(node):
            yield from find_missing_stack_names(value, f"{path}[{index}]")


def main():
    parser = argparse.ArgumentParser(
        description='Find JSON entries with "effect_type": "stack_buff" but no kwargs.stack_name.'
    )
    parser.add_argument(
        "paths",
        nargs="*",
        default=["characters"],
        help="JSON files or directories to inspect. Defaults to characters/.",
    )
    args = parser.parse_args()

    findings = []
    for json_path in iter_json_files(args.paths):
        try:
            with json_path.open("r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception as exc:
            findings.append(
                {
                    "file": str(json_path),
                    "path": "$",
                    "name": "",
                    "buff_type": "",
                    "effect_no": "",
                    "error": f"{type(exc).__name__}: {exc}",
                }
            )
            continue

        for finding in find_missing_stack_names(data):
            finding["file"] = str(json_path)
            findings.append(finding)

    if not findings:
        print("OK: stack_buff without stack_name was not found.")
        return

    print(f"Found {len(findings)} issue(s):")
    for item in findings:
        if item.get("error"):
            print(f"- {item['file']} :: {item['error']}")
            continue

        details = []
        if item.get("name"):
            details.append(f"name={item['name']}")
        if item.get("buff_type"):
            details.append(f"buff_type={item['buff_type']}")
        if item.get("effect_no") != "":
            details.append(f"effect_no={item['effect_no']}")
        suffix = f" ({', '.join(details)})" if details else ""
        print(f"- {item['file']} :: {item['path']}{suffix}")


if __name__ == "__main__":
    main()
