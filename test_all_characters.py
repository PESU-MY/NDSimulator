import argparse
import copy
import csv
import json
import traceback
from pathlib import Path

from simulator import Character, NikkeSimulator, Skill, WeaponConfig


UNIVERSAL_BURST_STAGES = {"∀", "ALL", "all", "*"}


def create_character_from_json(char_file_path, skill_level=10):
    char_file_path = Path(char_file_path)
    with char_file_path.open("r", encoding="utf-8") as f:
        char_data = json.load(f)

    char_name = char_data["name"]
    weapon_type_str = char_data["weapon_type"].lower()
    element = char_data.get("element", "Iron")
    stats = char_data.get("stats", {})
    char_class = char_data.get("class", "Attacker")
    burst_stage = str(char_data.get("burst_stage", "3"))
    squad = char_data.get("squad", "Unknown")

    weapon_file_path = Path("weapons") / f"{weapon_type_str}_standard.json"
    if weapon_file_path.exists():
        with weapon_file_path.open("r", encoding="utf-8") as f:
            weapon_data = json.load(f)
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

        for k, v in s_data.items():
            if k not in ["name", "trigger_type", "trigger_value", "effect_type", "kwargs", "stages"]:
                init_kwargs[k] = copy.deepcopy(v)

        level_idx = max(0, min(9, skill_level - 1))

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


def create_dummy_character(name, burst_stage, weapon_type="SMG", skills=None):
    weapon_data = {
        "name": f"{name}_Weapon",
        "weapon_type": weapon_type,
        "burst_stage": str(burst_stage),
    }
    return Character(
        name,
        WeaponConfig(weapon_data),
        skills if skills else [],
        base_atk=1,
        base_hp=1,
        element="Electric",
        burst_stage=str(burst_stage),
        is_dummy=False,
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
        name = "装弾数100%バフ",
        trigger_type="on_start", 
        trigger_value=0,
        effect_type = "buff",
        buff_type = "max_ammo_rate",
        target = "allies",
        value = 1,
        duration = 999,
    )

def get_burst_cooldown(character):
    if getattr(character, "burst_skill_cooldown", None) is not None:
        return float(character.burst_skill_cooldown)
    return 20.0 if str(character.burst_stage) in ["1", "2"] else 40.0


def make_party_and_rotation(target):
    raw_target_stage = str(target.burst_stage)
    target_stage = "3" if raw_target_stage in UNIVERSAL_BURST_STAGES else raw_target_stage
    if target_stage not in ["1", "2", "3"]:
        raise ValueError(f"Unsupported burst_stage: {raw_target_stage}")

    dummy_b1 = create_dummy_character("Dummy_B1", "1", "SMG", skills=[create_dummy_ct_skill()])
    dummy_b2 = create_dummy_character("Dummy_B2", "2", "SMG")
    dummy_b3_primary = create_dummy_character("Dummy_B3_Primary", "3", "SG")
    dummy_b3_rotation = create_dummy_character("Dummy_B3_Rotation", "3", "SG")
    dummy_b3_filler = create_dummy_character("Dummy_B3_Filler", "3", "SG", skills=[create_dummy_ammo_skill()])

    cooldown = get_burst_cooldown(target)

    if abs(cooldown - 20.0) < 0.001:
        if target_stage == "1":
            party = [target, dummy_b2, dummy_b3_primary, dummy_b3_rotation, dummy_b3_filler]
            rotation = [[target], [dummy_b2], [dummy_b3_primary, dummy_b3_rotation]]
        elif target_stage == "2":
            party = [dummy_b1, target, dummy_b3_primary, dummy_b3_rotation, dummy_b3_filler]
            rotation = [[dummy_b1], [target], [dummy_b3_primary, dummy_b3_rotation]]
        else:
            party = [dummy_b1, dummy_b2, target, dummy_b3_rotation, dummy_b3_filler]
            rotation = [[dummy_b1], [dummy_b2], [target]]
        policy = "20s: target replaces same-stage dummy"
    elif abs(cooldown - 40.0) < 0.001:
        if target_stage == "1":
            partner = create_dummy_character(
                "Dummy_B1_Rotation",
                "1",
                "SMG",
                skills=[create_dummy_ct_skill()],
            )
            party = [target, partner, dummy_b2, dummy_b3_primary, dummy_b3_rotation]
            rotation = [[target, partner], [dummy_b2], [dummy_b3_primary, dummy_b3_rotation]]
        elif target_stage == "2":
            partner = create_dummy_character("Dummy_B2_Rotation", "2", "SMG")
            party = [dummy_b1, target, partner, dummy_b3_primary, dummy_b3_rotation]
            rotation = [[dummy_b1], [target, partner], [dummy_b3_primary, dummy_b3_rotation]]
        else:
            party = [dummy_b1, dummy_b2, target, dummy_b3_rotation, dummy_b3_filler]
            rotation = [[dummy_b1], [dummy_b2], [target, dummy_b3_rotation]]
        policy = "40s: target and same-stage dummy rotate"
    else:
        if target_stage == "1":
            party = [target, dummy_b2, dummy_b3_primary, dummy_b3_rotation, dummy_b3_filler]
            rotation = [[target], [dummy_b2], [dummy_b3_primary, dummy_b3_rotation]]
        elif target_stage == "2":
            party = [dummy_b1, target, dummy_b3_primary, dummy_b3_rotation, dummy_b3_filler]
            rotation = [[dummy_b1], [target], [dummy_b3_primary, dummy_b3_rotation]]
        else:
            party = [dummy_b1, dummy_b2, target, dummy_b3_rotation, dummy_b3_filler]
            rotation = [[dummy_b1], [dummy_b2], [target, dummy_b3_rotation]]
        policy = f"{cooldown:g}s: default stage rotation"

    if raw_target_stage in UNIVERSAL_BURST_STAGES:
        policy = f"{policy} (universal burst tested as stage {target_stage})"

    return party, rotation, cooldown, policy


def run_one_character(char_file, args):
    target = create_character_from_json(char_file, skill_level=args.skill_level)
    party, rotation, cooldown, policy = make_party_and_rotation(target)

    sim = NikkeSimulator(
        characters=party,
        burst_rotation=rotation,
        enemy_element=args.enemy_element,
        enemy_core_size=args.enemy_core_size,
        enemy_size=args.enemy_size,
        part_break_mode=args.part_break_mode,
        burst_charge_time=args.burst_charge_time,
    )
    sim.special_mode = args.special_mode

    try:
        results = sim.run()
    finally:
        if hasattr(sim, "hp_log_handle") and not sim.hp_log_handle.closed:
            sim.hp_log_handle.close()

    target_result = results.get(target.name, {"total_damage": 0, "breakdown": {}})
    party_damage = sum(r["total_damage"] for r in results.values())

    return {
        "file": Path(char_file).name,
        "name": target.name,
        "burst_stage": target.burst_stage,
        "cooldown_time": cooldown,
        "rotation_policy": policy,
        "target_damage": target_result["total_damage"],
        "party_damage": party_damage,
        "status": "OK",
        "error": "",
    }


def iter_character_files(args):
    files = sorted(Path(args.characters_dir).glob("*.json"), key=lambda p: p.name)
    if args.name_contains:
        files = [p for p in files if args.name_contains in p.stem]
    if args.limit is not None:
        files = files[: args.limit]
    return files


def main():
    parser = argparse.ArgumentParser(description="Run one standard damage test for every character JSON.")
    parser.add_argument("--characters-dir", default="characters")
    parser.add_argument("--output", default="test_results/all_character_damage.csv")
    parser.add_argument("--skill-level", type=int, default=10)
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--name-contains", default=None)
    parser.add_argument("--enemy-element", default="None")
    parser.add_argument("--enemy-core-size", type=float, default=3.0)
    parser.add_argument("--enemy-size", type=float, default=100.0)
    parser.add_argument("--burst-charge-time", type=float, default=5.0)
    parser.add_argument("--part-break-mode", action="store_true")
    parser.add_argument("--special-mode", action="store_true")
    parser.add_argument("--quiet", action="store_true")
    args = parser.parse_args()

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    rows = []
    files = iter_character_files(args)

    for idx, char_file in enumerate(files, start=1):
        if not args.quiet:
            print(f"[{idx}/{len(files)}] {char_file.name}")
        try:
            row = run_one_character(char_file, args)
        except Exception as exc:
            row = {
                "file": char_file.name,
                "name": "",
                "burst_stage": "",
                "cooldown_time": "",
                "rotation_policy": "",
                "target_damage": 0,
                "party_damage": 0,
                "status": "ERROR",
                "error": f"{type(exc).__name__}: {exc}\n{traceback.format_exc()}",
            }
        rows.append(row)

    fieldnames = [
        "file",
        "name",
        "burst_stage",
        "cooldown_time",
        "rotation_policy",
        "target_damage",
        "party_damage",
        "status",
        "error",
    ]
    with output_path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    ok_count = sum(1 for row in rows if row["status"] == "OK")
    error_count = len(rows) - ok_count
    total_damage = sum(float(row["target_damage"] or 0) for row in rows if row["status"] == "OK")

    print(f"Done: {ok_count} OK, {error_count} ERROR")
    print(f"Total target damage sum: {total_damage:,.0f}")
    print(f"Output: {output_path}")


if __name__ == "__main__":
    main()
