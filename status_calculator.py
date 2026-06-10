from pathlib import Path


STATUS_DIR = Path(__file__).resolve().parent / "status"

CLASS_FILE_MAP = {
    "Attacker": "火力型",
    "火力型": "火力型",
    "Defender": "防御型",
    "防御型": "防御型",
    "Supporter": "支援型",
    "支援型": "支援型",
}

CLASS_RESEARCH_KEYS = {
    "火力型": ("Attacker", "火力型"),
    "防御型": ("Defender", "防御型"),
    "支援型": ("Supporter", "支援型"),
}

COMPANY_ALIASES = {
    "Elysion": ("Elysion", "エリシオン"),
    "エリシオン": ("Elysion", "エリシオン"),
    "Missilis": ("Missilis", "ミシリス"),
    "ミシリス": ("Missilis", "ミシリス"),
    "Tetra": ("Tetra", "テトラ"),
    "テトラ": ("Tetra", "テトラ"),
    "Pilgrim": ("Pilgrim", "ピルグリム"),
    "ピルグリム": ("Pilgrim", "ピルグリム"),
    "Abnormal": ("Abnormal", "アブノーマル"),
    "アブノーマル": ("Abnormal", "アブノーマル"),
}

PART_FILE_MAP = {
    "head": "頭",
    "body": "胴",
    "arms": "腕",
    "legs": "足",
}

STATUS_CACHE = {}


def _read_rows(path):
    cache_key = str(path.resolve())
    stat = path.stat()
    cached = STATUS_CACHE.get(cache_key)
    if cached and cached["mtime_ns"] == stat.st_mtime_ns:
        return cached["rows"]

    rows = []
    with path.open("r", encoding="utf-8") as handle:
        for raw_line in handle:
            line = raw_line.strip()
            if not line:
                continue
            rows.append([part.strip() for part in line.split(",")])
    STATUS_CACHE[cache_key] = {"mtime_ns": stat.st_mtime_ns, "rows": rows}
    return rows


def _num(value, default=0.0):
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _int(value, default=0):
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return default


def _lookup_level(path, level, has_tier=False, tier=None):
    if not path.exists():
        return (0.0, 0.0)

    level = _int(level)
    candidates = []
    for row in _read_rows(path):
        if has_tier:
            if len(row) < 4 or str(row[0]) != str(tier):
                continue
            row_level = _int(row[1])
            hp = _num(row[2])
            atk = _num(row[3])
        else:
            if len(row) < 3:
                continue
            row_level = _int(row[0])
            hp = _num(row[1])
            atk = _num(row[2])
        candidates.append((row_level, hp, atk))

    if not candidates:
        return (0.0, 0.0)

    candidates.sort(key=lambda item: item[0])
    lower_or_equal = [item for item in candidates if item[0] <= level]
    row = lower_or_equal[-1] if lower_or_equal else candidates[0]
    return (row[1], row[2])


def _read_per_level(path):
    if not path.exists():
        return (0.0, 0.0)
    rows = _read_rows(path)
    if not rows or len(rows[0]) < 2:
        return (0.0, 0.0)
    row = rows[0]
    return (_num(row[0]), _num(row[1]))


def _limit_break_fixed_bonus(settings):
    path = STATUS_DIR / "凸固定ステータス" / "凸固定ステータス.txt"
    return _read_per_level(path)


def _class_file_name(character_class):
    return CLASS_FILE_MAP.get(str(character_class), "火力型")


def _research_level(settings, group, keys):
    levels = settings.get(group, {})
    if not isinstance(levels, dict):
        return 0
    for key in keys:
        if key in levels:
            return _int(levels.get(key))
    return 0


def _company_research_level(settings, company):
    aliases = COMPANY_ALIASES.get(str(company), (str(company),))
    return _research_level(settings, "companyResearchLevels", aliases)


def _class_research_level(settings, class_file_name):
    keys = CLASS_RESEARCH_KEYS.get(class_file_name, (class_file_name,))
    return _research_level(settings, "classResearchLevels", keys)


def _equipment_bonus(class_file_name, settings):
    equipment = settings.get("equipment", {})
    if not isinstance(equipment, dict):
        return (0.0, 0.0)

    total_hp = 0.0
    total_atk = 0.0
    for part_key, part_name in PART_FILE_MAP.items():
        part = equipment.get(part_key, {})
        if not isinstance(part, dict):
            continue
        tier = part.get("tier", "T10")
        level = _int(part.get("level", 0))
        path = STATUS_DIR / "装備ステータス" / f"{class_file_name}_{part_name}.txt"
        hp, atk = _lookup_level(path, level, has_tier=True, tier=tier)
        total_hp += hp
        total_atk += atk
    return (total_hp, total_atk)


def _collection_bonus(settings):
    rarity = str(settings.get("collectionRarity") or "").strip()
    if not rarity or rarity.lower() == "none":
        return (0.0, 0.0)
    path = STATUS_DIR / "コレクションステータス" / f"{rarity}.txt"
    return _lookup_level(path, settings.get("collectionLevel", 0))


def _cube_bonus(settings):
    level = _int(settings.get("cubeLevel", 0))
    if level <= 0:
        return (0.0, 0.0)
    path = STATUS_DIR / "キューブステータス" / "キューブステータス.txt"
    return _lookup_level(path, level)


def _research_bonus(class_file_name, company, settings):
    class_hp, class_atk = _read_per_level(STATUS_DIR / "研究レベル補正" / "クラス研究.txt")
    company_hp, company_atk = _read_per_level(STATUS_DIR / "研究レベル補正" / "企業研究.txt")
    common_hp, common_atk = _read_per_level(STATUS_DIR / "研究レベル補正" / "共通研究.txt")

    class_level = _class_research_level(settings, class_file_name)
    company_level = _company_research_level(settings, company)
    common_level = _int(settings.get("commonResearchLevel", 0))

    return (
        class_hp * class_level + company_hp * company_level + common_hp * common_level,
        class_atk * class_level + company_atk * company_level + common_atk * common_level,
    )


def calculate_character_base_stats(character_class, company, settings):
    class_file_name = _class_file_name(character_class)
    level = _int(settings.get("level", 400), 400)
    limit_break = max(0, min(10, _int(settings.get("limitBreak", 3), 3)))
    fixed_hp, fixed_atk = _limit_break_fixed_bonus(settings)

    base_path = STATUS_DIR / "基礎ステータス" / f"{class_file_name}.txt"
    base_hp, base_atk = _lookup_level(base_path, level)

    hp = base_hp
    atk = base_atk
    first_limit_breaks = min(limit_break, 3)
    hp += ((base_hp * 0.02) + fixed_hp) * first_limit_breaks
    atk += ((base_atk * 0.02) + fixed_atk) * first_limit_breaks

    bond_path = STATUS_DIR / "好感度補正" / f"{class_file_name}.txt"
    bond_hp, bond_atk = _lookup_level(bond_path, settings.get("bondLevel", 0))
    research_hp, research_atk = _research_bonus(class_file_name, company, settings)

    hp += bond_hp + research_hp
    atk += bond_atk + research_atk

    three_limit_hp = hp
    three_limit_atk = atk
    if limit_break > 3:
        extra_rate = 0.02 * (limit_break - 3)
        hp = three_limit_hp * (1.0 + extra_rate)
        atk = three_limit_atk * (1.0 + extra_rate)

    equipment_hp, equipment_atk = _equipment_bonus(class_file_name, settings)
    collection_hp, collection_atk = _collection_bonus(settings)
    cube_hp, cube_atk = _cube_bonus(settings)

    hp += equipment_hp + collection_hp + cube_hp
    atk += equipment_atk + collection_atk + cube_atk

    return {
        "base_hp": int(round(hp)),
        "base_atk": int(round(atk)),
    }
