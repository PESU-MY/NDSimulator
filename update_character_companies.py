import argparse
import csv
import json
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parent
CHARACTER_DIR = ROOT_DIR / "characters"
MANUFACTURER_CSV = ROOT_DIR / "資料" / "nikke_manufacturers_ja.csv"


def normalize_name(value):
    return (
        str(value or "")
        .replace("\ufeff", "")
        .replace("：", ":")
        .replace("・", "")
        .replace(" ", "")
        .replace("_", "")
        .lower()
        .strip()
    )


def load_company_lookup(path):
    lookup = {}
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            company = (row.get("manufacturer_ja") or "").strip()
            if not company:
                continue
            for key in (row.get("japanese_name"), row.get("english_name")):
                normalized = normalize_name(key)
                if normalized:
                    lookup[normalized] = company
    return lookup


def load_json(path):
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def ordered_with_company(data, company):
    updated = {}
    inserted = False

    for key, value in data.items():
        if key == "company":
            continue
        if key == "squad" and not inserted:
            updated["company"] = company
            inserted = True
        updated[key] = value

    if not inserted:
        rebuilt = {}
        for key, value in updated.items():
            if key == "stats" and not inserted:
                rebuilt["company"] = company
                inserted = True
            rebuilt[key] = value
        updated = rebuilt

    if not inserted:
        updated["company"] = company

    return updated


def dump_json(path, data):
    text = json.dumps(data, ensure_ascii=False, indent=2)
    path.write_text(text + "\n", encoding="utf-8")


def find_company(data, path, lookup):
    candidates = [
        data.get("name"),
        path.stem,
        path.name.removesuffix(".json"),
    ]

    expanded_candidates = []
    for candidate in candidates:
        if not candidate:
            continue
        text = str(candidate)
        expanded_candidates.append(text)
        for suffix in ("_宝物", " 宝物"):
            if text.endswith(suffix):
                expanded_candidates.append(text[: -len(suffix)])
        for separator in ("：", ":"):
            if separator in text:
                expanded_candidates.append(text.split(separator, 1)[0])

    for candidate in expanded_candidates:
        company = lookup.get(normalize_name(candidate))
        if company:
            return company
    return None


def update_companies(write=False):
    lookup = load_company_lookup(MANUFACTURER_CSV)
    matched = []
    unchanged = []
    unmatched = []

    for path in sorted(CHARACTER_DIR.glob("*.json"), key=lambda p: p.name):
        try:
            data = load_json(path)
        except Exception as exc:
            unmatched.append((path.name, f"JSON読み込み失敗: {type(exc).__name__}: {exc}"))
            continue

        company = find_company(data, path, lookup)
        if not company:
            unmatched.append((path.name, data.get("name", path.stem)))
            continue

        if data.get("company") == company:
            unchanged.append((path.name, company))
            continue

        matched.append((path.name, data.get("company"), company))
        if write:
            dump_json(path, ordered_with_company(data, company))

    return matched, unchanged, unmatched


def main():
    parser = argparse.ArgumentParser(
        description="characters/*.json に nikke_manufacturers_ja.csv の company を追加します。"
    )
    parser.add_argument("--write", action="store_true", help="実際にJSONを書き換えます。未指定ならdry-runです。")
    args = parser.parse_args()

    matched, unchanged, unmatched = update_companies(write=args.write)
    mode = "WRITE" if args.write else "DRY-RUN"
    print(f"[{mode}] update={len(matched)} unchanged={len(unchanged)} unmatched={len(unmatched)}")

    if matched:
        print("\n[update]")
        for file_name, before, after in matched:
            before_text = before if before else "-"
            print(f"{file_name}: {before_text} -> {after}")

    if unmatched:
        print("\n[unmatched]")
        for file_name, name in unmatched:
            print(f"{file_name}: {name}")


if __name__ == "__main__":
    main()
