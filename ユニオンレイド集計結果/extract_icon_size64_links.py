from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path
from urllib.request import Request, urlopen

from lxml import html

DEFAULT_URL = "https://wiki3.jp/nikke/page/202"
DEFAULT_SUBSTRING = "icon_size64"
DEFAULT_OUTPUT_DIR = "icon_links"
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/136.0.0.0 Safari/537.36"
)
URL_ATTRS = ("href", "src", "data-src", "data-original")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Fetch a web page and extract URLs whose attribute value contains "
            "the target substring."
        )
    )
    parser.add_argument(
        "--url",
        default=DEFAULT_URL,
        help="Target page URL. Default: %(default)s",
    )
    parser.add_argument(
        "--substring",
        default=DEFAULT_SUBSTRING,
        help="Case-insensitive substring to search for. Default: %(default)s",
    )
    parser.add_argument(
        "--output-dir",
        default=DEFAULT_OUTPUT_DIR,
        help="Directory to write CSV/TXT output files. Default: %(default)s",
    )
    return parser.parse_args()


def fetch_html(url: str) -> str:
    request = Request(url, headers={"User-Agent": USER_AGENT})
    with urlopen(request, timeout=60) as response:
        return response.read().decode("utf-8")


def clean_text(value: str) -> str:
    return " ".join((value or "").replace("\xa0", " ").split())


def extract_matches(page_html: str, needle: str) -> list[dict[str, str]]:
    document = html.fromstring(page_html)
    needle_lower = needle.lower()
    rows: list[dict[str, str]] = []

    for element in document.iter():
        for attr_name in URL_ATTRS:
            raw_value = element.attrib.get(attr_name)
            if not raw_value:
                continue
            if needle_lower not in raw_value.lower():
                continue

            parent_anchor = element if element.tag == "a" else element.getparent()
            while parent_anchor is not None and parent_anchor.tag != "a":
                parent_anchor = parent_anchor.getparent()

            page_link = parent_anchor.attrib.get("href", "") if parent_anchor is not None else ""
            label = clean_text("".join(parent_anchor.itertext())) if parent_anchor is not None else ""

            rows.append(
                {
                    "matched_url": raw_value,
                    "attribute": attr_name,
                    "tag": element.tag,
                    "page_link": page_link,
                    "label": label,
                }
            )

    return rows


def write_occurrences(rows: list[dict[str, str]], output_dir: Path) -> Path:
    output_file = output_dir / "icon_size64_occurrences.csv"
    fieldnames = ["matched_url", "attribute", "tag", "page_link", "label"]

    with output_file.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    return output_file


def write_unique_urls(rows: list[dict[str, str]], output_dir: Path) -> Path:
    output_file = output_dir / "icon_size64_unique_urls.txt"
    unique_urls = sorted({row["matched_url"] for row in rows})

    with output_file.open("w", encoding="utf-8") as handle:
        for url in unique_urls:
            handle.write(f"{url}\n")

    return output_file


def main() -> int:
    args = parse_args()
    output_dir = Path(args.output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    try:
        print(f"[INFO] Fetching {args.url}", file=sys.stderr)
        page_html = fetch_html(args.url)
        rows = extract_matches(page_html, args.substring)
        if not rows:
            print("[ERROR] No matching URLs were found.", file=sys.stderr)
            return 1

        occurrences_file = write_occurrences(rows, output_dir)
        unique_urls_file = write_unique_urls(rows, output_dir)
    except Exception as exc:  # pragma: no cover - CLI guard.
        print(f"[ERROR] {exc}", file=sys.stderr)
        return 1

    unique_count = len({row["matched_url"] for row in rows})
    print(f"[INFO] Occurrences: {len(rows)}", file=sys.stderr)
    print(f"[INFO] Unique URLs: {unique_count}", file=sys.stderr)
    print(f"[INFO] Wrote {occurrences_file}", file=sys.stderr)
    print(f"[INFO] Wrote {unique_urls_file}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
