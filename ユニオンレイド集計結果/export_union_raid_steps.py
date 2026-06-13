from __future__ import annotations

import argparse
import csv
import re
import sys
import unicodedata
from collections import defaultdict
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from lxml import html

BASE_URL = "https://oooooo.rip"
DEFAULT_RAID = "40"
DEFAULT_SERVERS = ("global", "jp", "kr", "na", "sea")
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/136.0.0.0 Safari/537.36"
)

STEP_LABEL_RE = re.compile(
    r"^Step\s+(?P<number>\d+)\s+-\s+(?P<name>.+?)\s+\(Weakness:\s*(?P<weakness>.+?)\)$"
)
LB_RE = re.compile(r"LB\s*(\d+)")
LV_RE = re.compile(r"Lv\s*([\d,]+)")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Download Union Raid leaderboard pages from oooooo.rip and "
            "export one CSV per Step for the selected servers."
        )
    )
    parser.add_argument(
        "--raid",
        default=DEFAULT_RAID,
        help="Union Raid number in the site URL. Default: %(default)s",
    )
    parser.add_argument(
        "--servers",
        nargs="+",
        default=list(DEFAULT_SERVERS),
        help=f"Servers to export. Default: {' '.join(DEFAULT_SERVERS)}",
    )
    parser.add_argument(
        "--output-dir",
        default="output",
        help="Directory where CSV files will be written. Default: %(default)s",
    )
    return parser.parse_args()


def fetch_html(url: str) -> str:
    request = Request(url, headers={"User-Agent": USER_AGENT})
    with urlopen(request, timeout=60) as response:
        return response.read().decode("utf-8")


def clean_text(value: str) -> str:
    return " ".join(value.replace("\xa0", " ").split())


def direct_text(element: Any) -> str:
    return clean_text("".join(element.xpath("./text()")))


def parse_step_label(raw_label: str) -> dict[str, str]:
    normalized_label = raw_label.replace("\u2014", "-").replace("\u2013", "-")
    match = STEP_LABEL_RE.match(normalized_label)
    if not match:
        raise ValueError(f"Could not parse step label: {raw_label!r}")
    return match.groupdict()


def extract_lb(stats_text: str) -> str:
    match = LB_RE.search(stats_text)
    if not match:
        return ""
    return f"LB{int(match.group(1)):02d}"


def extract_level(stats_text: str) -> str:
    match = LV_RE.search(stats_text)
    if not match:
        return ""
    return match.group(1).replace(",", "")


def slugify_step_name(step_name: str) -> str:
    replacements = {"∞": "infinity"}
    text = step_name
    for source, target in replacements.items():
        text = text.replace(source, target)
    normalized = unicodedata.normalize("NFKD", text)
    ascii_text = normalized.encode("ascii", "ignore").decode("ascii").lower()
    slug = re.sub(r"[^a-z0-9]+", "-", ascii_text).strip("-")
    return slug or "step"


def parse_team(team_cell: Any) -> tuple[str, list[dict[str, str]]]:
    members: list[dict[str, str]] = []
    team_level = ""

    for unit in team_cell.xpath('.//span[contains(@class, "ur-team-unit")]'):
        name = clean_text("".join(unit.xpath("./span[1]//text()")))
        stats_text = clean_text("".join(unit.xpath("./span[2]//text()")))
        lb = extract_lb(stats_text)
        level = extract_level(stats_text)
        if not team_level and level:
            team_level = level
        members.append(
            {
                "name": name,
                "lb": lb,
                "level": level,
            }
        )

    return team_level, members


def build_team_summary(members: list[dict[str, str]]) -> str:
    return ", ".join(
        f"{member['name']} {member['lb']}".strip() for member in members if member["name"]
    )


def parse_server_page(server: str, raid: str, page_html: str) -> dict[int, dict[str, Any]]:
    document = html.fromstring(page_html)
    step_rows: dict[int, list[dict[str, str]]] = defaultdict(list)
    step_meta: dict[int, dict[str, str]] = {}

    guilds = document.xpath('//details[contains(@class, "ur-guild")]')
    for guild in guilds:
        summary_nodes = guild.xpath('./summary[contains(@class, "ur-guild-summary")]')
        if not summary_nodes:
            continue

        summary = summary_nodes[0]
        summary_divs = summary.xpath("./div")
        if len(summary_divs) < 3:
            continue

        union_rank = direct_text(summary_divs[0])
        union_name = direct_text(summary_divs[1])
        union_id = clean_text(
            "".join(summary_divs[1].xpath('.//span[contains(@class, "ur-sub-id")]/text()'))
        )

        for step in guild.xpath('.//details[contains(@class, "ur-step")]'):
            step_title_nodes = step.xpath('.//span[contains(@class, "ur-step-label")]')
            if not step_title_nodes:
                continue

            step_label = clean_text("".join(step_title_nodes[0].xpath("./text()")))
            parsed_step = parse_step_label(step_label)
            step_number = int(parsed_step["number"])
            step_meta.setdefault(
                step_number,
                {
                    "step_name": parsed_step["name"],
                    "weakness": parsed_step["weakness"],
                },
            )

            rows = step.xpath('.//table[contains(@class, "ur-step-table")]/tbody/tr')
            for hit_index, row in enumerate(rows, start=1):
                cells = row.xpath("./td")
                if len(cells) < 5:
                    continue

                utc = clean_text("".join(cells[0].xpath(".//text()")))
                raid_lv = direct_text(cells[1]).replace(",", "")
                player_name = direct_text(cells[2])
                player_id = clean_text(
                    "".join(cells[2].xpath('.//span[contains(@class, "ur-sub-id")]/text()'))
                )
                team_level, team_members = parse_team(cells[3])
                damage = direct_text(cells[4]).replace(",", "")
                damage_classes = cells[4].attrib.get("class", "")
                is_kill = "Yes" if "ur-damage-kill" in damage_classes else "No"

                record: dict[str, str] = {
                    "Raid": raid,
                    "Server": server.upper(),
                    "Union Rank": union_rank,
                    "Union Name": union_name,
                    "Union ID": union_id,
                    "Step Number": str(step_number),
                    "Step Name": parsed_step["name"],
                    "Weakness": parsed_step["weakness"],
                    "Union Hit Order": str(hit_index),
                    "UTC": utc,
                    "Raid Lv": raid_lv,
                    "Team Lv": team_level,
                    "Player Name": player_name,
                    "Player ID": player_id,
                    "Team (Name+LB)": build_team_summary(team_members),
                    "Damage": damage,
                    "Kill Hit": is_kill,
                }

                for index in range(5):
                    member = team_members[index] if index < len(team_members) else None
                    member_number = index + 1
                    record[f"Team {member_number} Name"] = member["name"] if member else ""
                    record[f"Team {member_number} LB"] = member["lb"] if member else ""

                step_rows[step_number].append(record)

    return {
        step_number: {
            "meta": step_meta[step_number],
            "rows": rows,
        }
        for step_number, rows in sorted(step_rows.items())
    }


def csv_fieldnames() -> list[str]:
    fields = [
        "Raid",
        "Server",
        "Union Rank",
        "Union Name",
        "Union ID",
        "Step Number",
        "Step Name",
        "Weakness",
        "Union Hit Order",
        "UTC",
        "Raid Lv",
        "Team Lv",
        "Player Name",
        "Player ID",
    ]
    for member_number in range(1, 6):
        fields.append(f"Team {member_number} Name")
        fields.append(f"Team {member_number} LB")
    fields.extend(
        [
            "Team (Name+LB)",
            "Damage",
            "Kill Hit",
        ]
    )
    return fields


def write_server_csvs(
    server: str,
    step_data: dict[int, dict[str, Any]],
    output_dir: Path,
) -> list[Path]:
    server_dir = output_dir / server
    server_dir.mkdir(parents=True, exist_ok=True)
    fieldnames = csv_fieldnames()
    written_files: list[Path] = []

    for step_number, payload in step_data.items():
        meta = payload["meta"]
        rows = payload["rows"]
        slug = slugify_step_name(meta["step_name"])
        file_path = server_dir / f"step_{step_number:02d}_{slug}.csv"

        with file_path.open("w", newline="", encoding="utf-8-sig") as handle:
            writer = csv.DictWriter(handle, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(rows)

        written_files.append(file_path)

    return written_files


def export_server(server: str, raid: str, output_dir: Path) -> list[Path]:
    url = f"{BASE_URL}/ur{raid}/{server.lower()}/"
    print(f"[INFO] Fetching {url}", file=sys.stderr)
    page_html = fetch_html(url)
    step_data = parse_server_page(server=server, raid=raid, page_html=page_html)
    if not step_data:
        raise ValueError(f"No step data found for server {server!r}")
    written_files = write_server_csvs(server.lower(), step_data, output_dir)
    print(
        f"[INFO] Wrote {len(written_files)} step files for {server.upper()}",
        file=sys.stderr,
    )
    return written_files


def main() -> int:
    args = parse_args()
    output_dir = Path(args.output_dir).resolve()

    try:
        output_dir.mkdir(parents=True, exist_ok=True)
        total_files = 0
        for server in args.servers:
            written_files = export_server(server=server, raid=args.raid, output_dir=output_dir)
            total_files += len(written_files)
    except (HTTPError, URLError) as exc:
        print(f"[ERROR] Failed to fetch leaderboard page: {exc}", file=sys.stderr)
        return 1
    except Exception as exc:  # pragma: no cover - defensive guard for CLI use.
        print(f"[ERROR] {exc}", file=sys.stderr)
        return 1

    print(f"[INFO] Export completed. Files written: {total_files}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
