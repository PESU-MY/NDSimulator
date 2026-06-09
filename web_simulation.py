import copy
import json
import math
import re
import time
from pathlib import Path

from simulator import Character, NikkeSimulator, Skill, WeaponConfig


ROOT_DIR = Path(__file__).resolve().parent
CHARACTER_DIR = ROOT_DIR / "characters"
WEAPON_DIR = ROOT_DIR / "weapons"
UNIVERSAL_BURST_STAGES = {"∀", "ALL", "all", "*"}
DETAIL_SECONDS = 180


DUMMY_DEFINITIONS = {
    "dummy_b1": {
        "name": "Dummy_B1",
        "label": "Dummy B1",
        "burst_stage": "1",
        "weapon_type": "SMG",
    },
    "dummy_b2": {
        "name": "Dummy_B2",
        "label": "Dummy B2",
        "burst_stage": "2",
        "weapon_type": "SMG",
    },
    "dummy_b2_rotation": {
        "name": "Dummy_B2_Rotation",
        "label": "Dummy B2 Rotation",
        "burst_stage": "2",
        "weapon_type": "SMG",
    },
    "dummy_b3": {
        "name": "Dummy_B3",
        "label": "Dummy B3",
        "burst_stage": "3",
        "weapon_type": "SG",
    },
    "dummy_b3_2": {
        "name": "Dummy_B3_2",
        "label": "Dummy B3 2",
        "burst_stage": "3",
        "weapon_type": "SG",
    },
}

ADDITIONAL_BUFF_DEFINITIONS = {
    "cooldown_reduction": {
        "label": "CT短縮",
        "unit": "sec",
        "effect_type": "cooldown_reduction",
        "trigger_type": "on_burst_enter",
        "value_mode": "seconds",
    },
    "max_ammo_rate": {
        "label": "装弾数バフ",
        "unit": "percent",
        "effect_type": "buff",
        "trigger_type": "on_start",
        "buff_type": "max_ammo_rate",
        "value_mode": "percent",
    },
    "reload_speed_rate": {
        "label": "リロード速度バフ",
        "unit": "percent",
        "effect_type": "buff",
        "trigger_type": "on_start",
        "buff_type": "reload_speed_rate",
        "value_mode": "percent",
    },
    "elemental_buff": {
        "label": "有利コードダメージバフ",
        "unit": "percent",
        "effect_type": "buff",
        "trigger_type": "on_start",
        "buff_type": "elemental_buff",
        "value_mode": "percent",
    },
}

BUFF_BUCKET_ORDER = [
    "攻撃力",
    "武器倍率",
    "クリティカル/コア",
    "チャージ",
    "ダメージバフ",
    "被ダメージ",
    "分配/有利コード/特殊",
    "行動/弾管理",
    "耐久/回復",
    "状態/フラグ",
    "その他バフ",
]

BUFF_BUCKET_MAP = {
    "atk_buff_rate": "攻撃力",
    "atk_buff_fixed": "攻撃力",
    "conversion_hp_to_atk": "攻撃力",
    "weapon_dmg_buff": "武器倍率",
    "crit_rate_buff": "クリティカル/コア",
    "crit_dmg_buff": "クリティカル/コア",
    "core_dmg_buff": "クリティカル/コア",
    "core_hit_rate_fixed": "クリティカル/コア",
    "hit_rate_buff": "クリティカル/コア",
    "charge_ratio_buff": "チャージ",
    "charge_dmg_buff": "チャージ",
    "charge_speed_overflow_charge_dmg_rate": "チャージ",
    "charge_additional_dmg": "チャージ",
    "atk_dmg_buff": "ダメージバフ",
    "part_dmg_buff": "ダメージバフ",
    "pierce_dmg_buff": "ダメージバフ",
    "explosive_dmg_buff": "ダメージバフ",
    "sticky_dmg_buff": "ダメージバフ",
    "ignore_def_dmg_buff": "ダメージバフ",
    "dot_dmg_buff": "ダメージバフ",
    "burst_dmg_buff": "ダメージバフ",
    "sequential_dmg_buff": "ダメージバフ",
    "enemy_wide_burst_dmg_buff": "ダメージバフ",
    "taken_dmg_debuff": "被ダメージ",
    "split_dmg_buff": "分配/有利コード/特殊",
    "elemental_buff": "分配/有利コード/特殊",
    "special_skill_dmg_buff": "分配/有利コード/特殊",
    "max_ammo_rate": "行動/弾管理",
    "max_ammo_fixed": "行動/弾管理",
    "reload_speed_rate": "行動/弾管理",
    "reload_speed_fixed": "行動/弾管理",
    "attack_speed_rate": "行動/弾管理",
    "attack_speed_fixed": "行動/弾管理",
    "charge_speed_rate": "行動/弾管理",
    "charge_speed_fixed": "行動/弾管理",
    "charge_speed": "行動/弾管理",
    "charge_time_cut": "行動/弾管理",
    "charge_time_fixed": "行動/弾管理",
    "max_hp_rate": "耐久/回復",
    "max_hp_fixed": "耐久/回復",
    "shield": "耐久/回復",
    "distribute_heal_buff": "耐久/回復",
    "is_ignore_def": "状態/フラグ",
    "is_pierce": "状態/フラグ",
    "is_explosive": "状態/フラグ",
    "is_sticky": "状態/フラグ",
    "is_sequential": "状態/フラグ",
}


def _buff_bucket_for(effect):
    return BUFF_BUCKET_MAP.get(str(effect), "その他バフ")


class TimelineNikkeSimulator(NikkeSimulator):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._current_frame = 0
        self.damage_series = {char.name: [0.0 for _ in range(DETAIL_SECONDS)] for char in self.characters}
        self.burst_events = {char.name: [] for char in self.characters}
        self.buff_timeline = {char.name: [] for char in self.characters}
        self._open_buff_intervals = {char.name: {} for char in self.characters}

    def log(self, message, target_name="System"):
        super().log(message, target_name=target_name)
        match = re.match(r"\[Burst\] (.+) used Burst Stage ([123])", message)
        if not match:
            return

        char_name = match.group(1)
        if char_name not in self.burst_events:
            return
        self.burst_events[char_name].append(
            {
                "time": round(self._current_frame / self.FPS, 3),
                "frame": int(self._current_frame),
                "stage": match.group(2),
            }
        )

    def tick(self, frame):
        self._current_frame = frame
        before_damage = {char.name: char.total_damage for char in self.characters}
        super().tick(frame)

        second_index = min(DETAIL_SECONDS - 1, max(0, (frame - 1) // self.FPS))
        for char in self.characters:
            delta = char.total_damage - before_damage.get(char.name, 0)
            if delta:
                self.damage_series[char.name][second_index] += float(delta)

        if frame % self.FPS == 0:
            self._record_buff_snapshot(frame)

    def run(self):
        try:
            self._current_frame = 0
            before_damage = {char.name: char.total_damage for char in self.characters}
            self.process_trigger_global("on_start", 0)
            for char in self.characters:
                delta = char.total_damage - before_damage.get(char.name, 0)
                if delta:
                    self.damage_series[char.name][0] += float(delta)
            self._record_buff_snapshot(0)

            for frame in range(1, self.TOTAL_FRAMES + 1):
                self.tick(frame)
        finally:
            self._close_all_buff_intervals(self.TOTAL_FRAMES)
            for f in self.log_handles.values():
                f.close()
            if hasattr(self, "hp_log_handle") and not self.hp_log_handle.closed:
                self.hp_log_handle.close()

        results = {}
        for char in self.characters:
            results[char.name] = {
                "total_damage": char.total_damage,
                "breakdown": char.damage_breakdown,
            }
        return results

    def _record_buff_snapshot(self, frame):
        now = round(frame / self.FPS, 3)
        for char in self.characters:
            current = self._active_buff_entries(char, frame)
            open_map = self._open_buff_intervals[char.name]

            for key in list(open_map.keys()):
                if key not in current:
                    interval = open_map.pop(key)
                    expected_end = interval.get("expectedEnd", now)
                    interval["end"] = min(now, expected_end) if expected_end <= now else now
                    if interval["end"] > interval["start"]:
                        self.buff_timeline[char.name].append(interval)

            for key, entry in current.items():
                if key not in open_map:
                    entry["start"] = max(0.0, min(now, entry.get("start", now)))
                    open_map[key] = entry
                else:
                    open_map[key].update(
                        {
                            "value": entry["value"],
                            "count": entry.get("count", 1),
                            "effect": entry["effect"],
                            "bucket": entry.get("bucket", "その他バフ"),
                            "expectedEnd": entry.get("expectedEnd"),
                        }
                    )

    def _close_all_buff_intervals(self, frame):
        end_time = round(frame / self.FPS, 3)
        for char_name, open_map in self._open_buff_intervals.items():
            for interval in open_map.values():
                expected_end = interval.get("expectedEnd", end_time)
                interval["end"] = min(end_time, expected_end)
                if interval["end"] > interval["start"]:
                    self.buff_timeline[char_name].append(interval)
            open_map.clear()

    def _active_buff_entries(self, char, frame):
        entries = {}
        aggregates = {}

        def tag_text(tag):
            if isinstance(tag, list):
                return ", ".join(str(t) for t in tag)
            return "" if tag is None else str(tag)

        def add_aggregate(kind, name, effect, value, start_frame, end_frame, tag="", count=1):
            key = (
                kind,
                name,
                effect,
                round(float(value), 8),
                int(count),
                tag,
            )
            if key not in aggregates:
                aggregates[key] = {
                    "kind": kind,
                    "name": name,
                    "effect": effect,
                    "bucket": _buff_bucket_for(effect),
                    "value": float(value),
                    "count": int(count),
                    "tag": tag,
                    "start": round(start_frame / self.FPS, 3),
                    "expectedEnd": round(min(end_frame, self.TOTAL_FRAMES) / self.FPS, 3),
                }
            else:
                aggregates[key]["value"] += float(value)
                aggregates[key]["count"] += int(count)

        for buff_type, buff_list in char.buff_manager.buffs.items():
            for buff in buff_list:
                if buff.get("end_frame", -1) < frame and buff.get("shot_life", 0) <= 0:
                    continue
                source = buff.get("source") or buff_type
                add_aggregate(
                    "buff",
                    str(source),
                    str(buff_type),
                    buff.get("val", 0),
                    buff.get("start_frame", frame),
                    buff.get("end_frame", self.TOTAL_FRAMES),
                    tag_text(buff.get("tag")),
                )

        for stack_name, stack in char.buff_manager.active_stacks.items():
            if stack.get("count", 0) <= 0:
                continue
            if stack.get("end_frame", -1) < frame and stack.get("shot_life", 0) <= 0:
                continue
            count = int(stack.get("count", 1))
            unit_value = float(stack.get("unit_value", 0))
            add_aggregate(
                "stack",
                str(stack_name),
                str(stack.get("buff_type", "stack")),
                unit_value * count,
                stack.get("start_frame", frame),
                stack.get("end_frame", self.TOTAL_FRAMES),
                tag_text(stack.get("tag")),
                count=count,
            )

        for key, entry in aggregates.items():
            entry["key"] = "|".join(str(part) for part in key)
            entries[entry["key"]] = entry
        return entries


def _read_json(path):
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def _character_path(file_name):
    path = (CHARACTER_DIR / file_name).resolve()
    if path.parent != CHARACTER_DIR.resolve() or path.suffix.lower() != ".json":
        raise ValueError(f"Invalid character file: {file_name}")
    if not path.exists():
        raise FileNotFoundError(f"Character file not found: {file_name}")
    return path


def _extract_burst_cooldown(char_data):
    burst_data = char_data.get("burst_skill", {})
    kwargs = burst_data.get("kwargs", {})
    cooldown = (
        kwargs.get("cooldown_time")
        or kwargs.get("cooldown")
        or burst_data.get("cooldown_time")
        or burst_data.get("cooldown")
    )
    if cooldown is not None:
        return float(cooldown)

    burst_stage = str(char_data.get("burst_stage", "3"))
    return 20.0 if burst_stage in {"1", "2"} else 40.0


def list_character_catalog():
    characters = []
    for path in sorted(CHARACTER_DIR.glob("*.json"), key=lambda p: p.name):
        try:
            data = _read_json(path)
            characters.append(
                {
                    "kind": "character",
                    "file": path.name,
                    "name": data.get("name", path.stem),
                    "burstStage": str(data.get("burst_stage", "3")),
                    "cooldownTime": _extract_burst_cooldown(data),
                    "weaponType": data.get("weapon_type", ""),
                    "element": data.get("element", "None"),
                    "class": data.get("class", "Attacker"),
                    "squad": data.get("squad", "Unknown"),
                }
            )
        except Exception as exc:
            characters.append(
                {
                    "kind": "character",
                    "file": path.name,
                    "name": path.stem,
                    "burstStage": "",
                    "cooldownTime": "",
                    "weaponType": "",
                    "element": "",
                    "class": "",
                    "squad": "",
                    "error": f"{type(exc).__name__}: {exc}",
                }
            )

    dummies = []
    for dummy_id, definition in DUMMY_DEFINITIONS.items():
        dummies.append(
            {
                "kind": "dummy",
                "id": dummy_id,
                "name": definition["label"],
                "burstStage": definition["burst_stage"],
                "cooldownTime": 20.0 if definition["burst_stage"] in {"1", "2"} else 40.0,
                "weaponType": definition["weapon_type"],
                "element": "Electric",
                "class": "Dummy",
                "squad": "Dummy",
            }
        )

    return {"characters": characters, "dummies": dummies}


def create_character_from_json(file_name, skill_level=10):
    char_file_path = _character_path(file_name)
    char_data = _read_json(char_file_path)

    char_name = char_data["name"]
    weapon_type_str = char_data["weapon_type"].lower()
    element = char_data.get("element", "Iron")
    stats = char_data.get("stats", {})
    char_class = char_data.get("class", "Attacker")
    burst_stage = str(char_data.get("burst_stage", "3"))
    squad = char_data.get("squad", "Unknown")

    weapon_file_path = WEAPON_DIR / f"{weapon_type_str}_standard.json"
    if weapon_file_path.exists():
        weapon_data = _read_json(weapon_file_path)
    else:
        weapon_data = {"weapon_type": weapon_type_str, "name": "Default Weapon"}

    weapon_data["name"] = f"{char_name}'s Weapon"
    weapon_data["element"] = element
    weapon_data["burst_stage"] = burst_stage

    for key, value in stats.items():
        if key == "reload_time":
            weapon_data["reload_frames"] = int(value * 60)
        elif key == "damage_rate":
            weapon_data["multiplier"] = value
        elif key == "ammo":
            weapon_data["max_ammo"] = value
        else:
            weapon_data[key] = value

    weapon_config = WeaponConfig(weapon_data)

    base_atk = 25554
    base_hp = 583734
    if char_class == "Supporter":
        base_atk = 21307
        base_hp = 647453
    elif char_class == "Defender":
        base_atk = 17059
        base_hp = 711171

    if "base_atk" in stats:
        base_atk = stats["base_atk"]
    if "base_hp" in stats:
        base_hp = stats["base_hp"]

    def parse_skill_data(s_data):
        init_kwargs = copy.deepcopy(s_data.get("kwargs", {}))

        for key, value in s_data.items():
            if key not in ["name", "trigger_type", "trigger_value", "effect_type", "kwargs", "stages"]:
                init_kwargs[key] = copy.deepcopy(value)

        level_idx = max(0, min(9, int(skill_level) - 1))

        def resolve_variable_params(value):
            if isinstance(value, dict):
                for k in list(value.keys()):
                    if k.endswith("_list") and isinstance(value[k], list):
                        base_key = k[:-5]
                        if len(value[k]) > level_idx:
                            value[base_key] = value[k][level_idx]
                    elif k == "value" and isinstance(value[k], list):
                        if len(value[k]) > level_idx:
                            value["value"] = value[k][level_idx]
                    else:
                        resolve_variable_params(value[k])
            elif isinstance(value, list):
                for item in value:
                    resolve_variable_params(item)

        resolve_variable_params(init_kwargs)

        effect_type = s_data.get("effect_type", "buff")
        if effect_type in ["ammo_charge", "refill_ammo"]:
            if "value" in init_kwargs and "rate" not in init_kwargs:
                init_kwargs["rate"] = init_kwargs["value"]

        stages = []
        for st in s_data.get("stages", []):
            st_copy = copy.deepcopy(st)
            resolve_variable_params(st_copy)

            st_kwargs = st_copy.get("kwargs", {})
            if st_copy.get("effect_type") in ["ammo_charge", "refill_ammo"]:
                if "value" in st_kwargs and "rate" not in st_kwargs:
                    st_kwargs["rate"] = st_kwargs["value"]
            st_copy["kwargs"] = st_kwargs
            stages.append(st_copy)

        final_trigger_value = init_kwargs.pop("trigger_value", s_data.get("trigger_value", 0))

        return Skill(
            name=s_data.get("name", "Unknown Skill"),
            trigger_type=s_data.get("trigger_type", "manual"),
            trigger_value=final_trigger_value,
            effect_type=effect_type,
            stages=stages,
            **init_kwargs,
        )

    skills = []
    for s_data in char_data.get("skills", []):
        skill = parse_skill_data(s_data)
        skill.owner_name = char_name
        skills.append(skill)

    if "burst_skill" in char_data:
        burst_skill = parse_skill_data(char_data["burst_skill"])
        burst_skill.owner_name = char_name
        if burst_skill.trigger_type != "on_use_burst_skill":
            burst_skill.trigger_type = "on_use_burst_skill"
        skills.append(burst_skill)

    return Character(
        char_name,
        weapon_config,
        skills,
        base_atk,
        base_hp,
        element,
        burst_stage,
        char_class,
        squad=squad,
    )


def create_dummy_ct_skill():
    return Skill(
        name="Dummy B1: CT Reduction",
        trigger_type="on_burst_enter",
        trigger_value=0,
        effect_type="cooldown_reduction",
        target="allies",
        value=5.0,
    )


def create_dummy_ammo_skill():
    return Skill(
        name="装弾数100%バフ",
        trigger_type="on_start",
        trigger_value=0,
        effect_type="buff",
        buff_type="max_ammo_rate",
        target="allies",
        value=1,
        duration=999,
    )


def create_dummy_from_id(dummy_id):
    definition = DUMMY_DEFINITIONS.get(dummy_id)
    if definition is None:
        raise ValueError(f"Unknown dummy id: {dummy_id}")

    weapon_data = {
        "name": f"{definition['name']}_Weapon",
        "weapon_type": definition["weapon_type"],
        "burst_stage": definition["burst_stage"],
    }
    return Character(
        definition["name"],
        WeaponConfig(weapon_data),
        [],
        base_atk=1,
        base_hp=1,
        element="Electric",
        burst_stage=definition["burst_stage"],
        is_dummy=False,
    )


def _coerce_buff_value(raw_value):
    try:
        value = float(raw_value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(value):
        return None
    return max(0.0, value)


def create_additional_buff_skill(buff_request):
    if not isinstance(buff_request, dict) or not buff_request.get("enabled", True):
        return None

    buff_type = buff_request.get("type")
    definition = ADDITIONAL_BUFF_DEFINITIONS.get(buff_type)
    if definition is None:
        return None

    raw_value = _coerce_buff_value(buff_request.get("value"))
    if raw_value is None:
        return None

    value = raw_value / 100 if definition["value_mode"] == "percent" else raw_value
    kwargs = {
        "name": f"追加バフ: {definition['label']}",
        "trigger_type": definition["trigger_type"],
        "trigger_value": 0,
        "effect_type": definition["effect_type"],
        "target": "allies",
        "value": value,
    }
    if definition["effect_type"] == "buff":
        kwargs.update(
            {
                "buff_type": definition["buff_type"],
                "duration": 999,
            }
        )
    return Skill(**kwargs)


def apply_additional_buffs(characters, buff_requests):
    if not characters or not isinstance(buff_requests, list):
        return

    caster = characters[0]
    for buff_request in buff_requests:
        skill = create_additional_buff_skill(buff_request)
        if skill is None:
            continue
        skill.owner_name = caster.name
        caster.skills.append(skill)


def apply_crust_operation_mode(simulator, mode):
    simulator.crust_maillard_mode = mode == "maillard"
    simulator.crust_blanching_mode = mode == "blanching"

    for char in simulator.characters:
        if char.name != "クラスト":
            continue

        if mode == "maillard":
            char.weapon.charge_time = 1 / simulator.FPS
            char.weapon.charge_mult = 1.0
        elif mode == "blanching":
            char.weapon.charge_time = 2.0
            char.weapon.charge_mult = 2.5


def _create_selected_character(selection, skill_level):
    if not selection:
        return None
    kind = selection.get("kind")
    if kind == "character":
        return create_character_from_json(selection.get("file", ""), skill_level=skill_level)
    if kind == "dummy":
        return create_dummy_from_id(selection.get("id", ""))
    raise ValueError(f"Unsupported formation selection: {kind}")


def _auto_stage_for_char(char):
    stage = str(char.burst_stage)
    if stage in UNIVERSAL_BURST_STAGES:
        return "3"
    if stage in {"1", "2", "3"}:
        return stage
    return None


def _build_rotation(rotation_request, slot_map):
    burst_rotation = []
    for stage in ["1", "2", "3"]:
        stage_chars = []
        for raw_slot in rotation_request.get(stage, []):
            try:
                slot_index = int(raw_slot)
            except (TypeError, ValueError):
                continue
            if slot_index in slot_map:
                stage_chars.append(slot_map[slot_index])
        if not stage_chars:
            raise ValueError(f"バースト{stage}のローテーションが空です")
        burst_rotation.append(stage_chars)
    return burst_rotation


def _auto_rotation(slot_map):
    rotation = {"1": [], "2": [], "3": []}
    for slot_index, char in slot_map.items():
        stage = _auto_stage_for_char(char)
        if stage:
            rotation[stage].append(slot_index)
    return rotation


def _float_option(options, key, default):
    value = options.get(key, default)
    if value in ("", None):
        return default
    return float(value)


def _int_option(options, key, default):
    value = options.get(key, default)
    if value in ("", None):
        return default
    return int(value)


def run_web_simulation(payload):
    started = time.perf_counter()
    options = payload.get("options", {})
    include_details = not bool(options.get("summaryOnly", False))
    skill_level = max(1, min(10, _int_option(options, "skillLevel", 10)))

    formation = payload.get("formation", [])
    if not formation:
        raise ValueError("編成が空です")

    characters = []
    slot_map = {}
    seen_names = set()
    for slot_index, selection in enumerate(formation):
        char = _create_selected_character(selection, skill_level)
        if char is None:
            continue
        if char.name in seen_names:
            raise ValueError(f"同じキャラクター名が複数入っています: {char.name}")
        seen_names.add(char.name)
        characters.append(char)
        slot_map[slot_index] = char

    if not characters:
        raise ValueError("有効な編成メンバーがありません")

    apply_additional_buffs(characters, options.get("additionalBuffs", []))

    rotation_request = payload.get("rotation") or _auto_rotation(slot_map)
    burst_rotation = _build_rotation(rotation_request, slot_map)

    simulator_class = TimelineNikkeSimulator if include_details else NikkeSimulator
    sim = simulator_class(
        characters=characters,
        burst_rotation=burst_rotation,
        enemy_element=options.get("enemyElement", "None"),
        enemy_core_size=_float_option(options, "enemyCoreSize", 3.0),
        enemy_size=_float_option(options, "enemySize", 100.0),
        part_break_mode=bool(options.get("partBreakMode", False)),
        burst_charge_time=_float_option(options, "burstChargeTime", 5.0),
        enemy_count=_int_option(options, "enemyCount", 1),
    )
    sim.special_mode = bool(options.get("specialMode", False))
    apply_crust_operation_mode(sim, options.get("crustOperationMode") or None)

    results = sim.run()

    result_rows = []
    for char in characters:
        result = results.get(char.name, {"total_damage": 0, "breakdown": {}})
        breakdown = [
            {
                "source": source,
                "damage": float(damage),
                "count": int(getattr(char, "damage_hit_counts", {}).get(source, 0)),
                "averageDamage": (
                    float(damage) / getattr(char, "damage_hit_counts", {}).get(source, 0)
                    if getattr(char, "damage_hit_counts", {}).get(source, 0)
                    else 0.0
                ),
                "sourceType": getattr(char, "damage_source_types", {}).get(source, "スキル"),
            }
            for source, damage in result.get("breakdown", {}).items()
            if float(damage) != 0.0
        ]
        breakdown.sort(key=lambda row: row["damage"], reverse=True)
        result_rows.append(
            {
                "name": char.name,
                "burstStage": str(char.burst_stage),
                "totalDamage": float(result.get("total_damage", 0)),
                "breakdown": breakdown,
                "damageSeries": (
                    sim.damage_series.get(char.name, [0.0 for _ in range(DETAIL_SECONDS)])
                    if include_details else []
                ),
                "buffTimeline": sim.buff_timeline.get(char.name, []) if include_details else [],
                "burstEvents": sim.burst_events.get(char.name, []) if include_details else [],
            }
        )

    total_party_damage = sum(row["totalDamage"] for row in result_rows)
    rotation_summary = {
        str(index + 1): [char.name for char in stage_chars]
        for index, stage_chars in enumerate(burst_rotation)
    }

    return {
        "status": "ok",
        "elapsedSeconds": time.perf_counter() - started,
        "totalPartyDamage": total_party_damage,
        "totalAllyAmmoConsumed": int(getattr(sim, "total_ally_ammo_consumed", 0)),
        "rotation": rotation_summary,
        "results": result_rows,
    }
