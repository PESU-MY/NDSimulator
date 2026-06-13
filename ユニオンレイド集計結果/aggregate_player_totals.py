from __future__ import annotations

import argparse
import csv
import sys
from collections import Counter
from pathlib import Path

DEFAULT_SERVERS = ("global", "jp", "kr", "na", "sea")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Aggregate step CSV files by Player ID and write one player total "
            "CSV per server."
        )
    )
    parser.add_argument(
        "--input-dir",
        default="output",
        help="Directory that contains server subdirectories with step CSV files.",
    )
    parser.add_argument(
        "--output-dir",
        default="player_totals",
        help="Directory where aggregated player total CSV files will be written.",
    )
    parser.add_argument(
        "--servers",
        nargs="+",
        default=list(DEFAULT_SERVERS),
        help=f"Servers to aggregate. Default: {' '.join(DEFAULT_SERVERS)}",
    )
    return parser.parse_args()


def parse_int(value: str) -> int:
    text = (value or "").replace(",", "").strip()
    if not text:
        return 0
    return int(text)


def choose_most_common(counter: Counter[str]) -> str:
    if not counter:
        return ""
    return counter.most_common(1)[0][0]


def choose_max_numeric(values: set[str]) -> str:
    numeric_values = [parse_int(value) for value in values if (value or "").strip()]
    if not numeric_values:
        return ""
    return str(max(numeric_values))


def aggregate_server(server: str, input_root: Path) -> tuple[list[dict[str, str]], int]:
    server_dir = input_root / server.lower()
    step_files = sorted(server_dir.glob("step_*.csv"))
    if not step_files:
        raise FileNotFoundError(f"No step CSV files found in {server_dir}")

    player_totals: dict[str, dict[str, object]] = {}
    hit_count = 0

    for step_file in step_files:
        with step_file.open("r", newline="", encoding="utf-8-sig") as handle:
            reader = csv.DictReader(handle)
            for row in reader:
                player_id = (row.get("Player ID") or "").strip()
                if not player_id:
                    continue

                hit_count += 1
                damage = parse_int(row.get("Damage", "0"))
                player_name = (row.get("Player Name") or "").strip()
                union_id = (row.get("Union ID") or "").strip()
                union_name = (row.get("Union Name") or "").strip()
                server_name = (row.get("Server") or server.upper()).strip()
                raid = (row.get("Raid") or "").strip()
                team_level = (row.get("Team Lv") or "").strip()

                entry = player_totals.setdefault(
                    player_id,
                    {
                        "raid_counter": Counter(),
                        "server_counter": Counter(),
                        "player_name_counter": Counter(),
                        "union_id_counter": Counter(),
                        "union_name_counter": Counter(),
                        "team_levels": set(),
                        "total_damage": 0,
                        "hit_count": 0,
                        "kill_hit_count": 0,
                    },
                )

                entry["raid_counter"][raid] += 1
                entry["server_counter"][server_name] += 1
                entry["player_name_counter"][player_name] += 1
                entry["union_id_counter"][union_id] += 1
                entry["union_name_counter"][union_name] += 1
                if team_level:
                    entry["team_levels"].add(team_level)
                entry["total_damage"] += damage
                entry["hit_count"] += 1
                if (row.get("Kill Hit") or "").strip().lower() == "yes":
                    entry["kill_hit_count"] += 1

    output_rows: list[dict[str, str]] = []
    for player_id, entry in player_totals.items():
        output_rows.append(
            {
                "Raid": choose_most_common(entry["raid_counter"]),
                "Server": choose_most_common(entry["server_counter"]),
                "Player ID": player_id,
                "Player Name": choose_most_common(entry["player_name_counter"]),
                "Union ID": choose_most_common(entry["union_id_counter"]),
                "Union Name": choose_most_common(entry["union_name_counter"]),
                "Team Lv": choose_max_numeric(entry["team_levels"]),
                "Total Damage": str(entry["total_damage"]),
                "Hit Count": str(entry["hit_count"]),
                "Kill Hit Count": str(entry["kill_hit_count"]),
            }
        )

    output_rows.sort(
        key=lambda row: (
            -parse_int(row["Total Damage"]),
            -parse_int(row["Hit Count"]),
            row["Player ID"],
        )
    )
    return output_rows, hit_count


def write_server_totals(server: str, rows: list[dict[str, str]], output_root: Path) -> Path:
    server_dir = output_root / server.lower()
    server_dir.mkdir(parents=True, exist_ok=True)
    output_file = server_dir / "player_totals.csv"
    fieldnames = [
        "Raid",
        "Server",
        "Player ID",
        "Player Name",
        "Union ID",
        "Union Name",
        "Team Lv",
        "Total Damage",
        "Hit Count",
        "Kill Hit Count",
    ]

    with output_file.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    return output_file


def main() -> int:
    args = parse_args()
    input_root = Path(args.input_dir).resolve()
    output_root = Path(args.output_dir).resolve()
    output_root.mkdir(parents=True, exist_ok=True)

    try:
        total_output_files = 0
        total_hits = 0
        for server in args.servers:
            print(f"[INFO] Aggregating {server.upper()} from {input_root}", file=sys.stderr)
            rows, hit_count = aggregate_server(server, input_root)
            output_file = write_server_totals(server, rows, output_root)
            total_output_files += 1
            total_hits += hit_count
            print(
                f"[INFO] Wrote {len(rows)} player totals to {output_file}",
                file=sys.stderr,
            )
    except Exception as exc:  # pragma: no cover - defensive guard for CLI use.
        print(f"[ERROR] {exc}", file=sys.stderr)
        return 1

    print(
        f"[INFO] Aggregation completed. Files written: {total_output_files}, "
        f"hits processed: {total_hits}",
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
