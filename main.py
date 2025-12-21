import json
import os
from simulator import NikkeSimulator, WeaponConfig, Skill, Character
import matplotlib.pyplot as plt

# --- ヘルパー関数: JSONからキャラデータを読み込んでCharacterを作成 ---
def create_character_from_json(char_file_path, skill_level=10):
    if not os.path.exists(char_file_path):
        print(f"[Error] File not found: {char_file_path}")
        return None

    with open(char_file_path, 'r', encoding='utf-8') as f:
        char_data = json.load(f)
    
    char_name = char_data['name']
    weapon_type_str = char_data['weapon_type'].lower()
    element = char_data.get('element', 'Iron')
    stats = char_data.get('stats', {})
    char_class = char_data.get('class', 'Attacker')
    burst_stage = char_data.get('burst_stage', '3')
    
    # 武器設定
    weapon_file_path = f"weapons/{weapon_type_str}_standard.json"
    weapon_data = {}
    if os.path.exists(weapon_file_path):
        with open(weapon_file_path, 'r', encoding='utf-8') as f:
            weapon_data = json.load(f)
    else:
        weapon_data = {'weapon_type': weapon_type_str, 'name': 'Default Weapon'}

    weapon_data['name'] = f"{char_name}'s Weapon"
    weapon_data['element'] = element
    weapon_data['burst_stage'] = burst_stage
    
    for key, value in stats.items():
        if key == 'reload_time': weapon_data['reload_frames'] = int(value * 60)
        elif key == 'damage_rate': weapon_data['multiplier'] = value
        elif key == 'ammo': weapon_data['max_ammo'] = value
        else: weapon_data[key] = value

    weapon_config = WeaponConfig(weapon_data)
    
    base_atk = 25554
    base_hp = 583734
    if char_class == 'Supporter':
        base_atk = 21307
        base_hp = 647453
    elif char_class == 'Defender':
        base_atk = 17059
        base_hp = 711171
    
    if 'base_atk' in stats: base_atk = stats['base_atk']
    if 'base_hp' in stats: base_hp = stats['base_hp']

    # スキル読み込み用内部関数
    def parse_skill_data(s_data):
        init_kwargs = s_data.get('kwargs', {}).copy()
        
        # ▼▼▼ 修正: JSONのトップレベルパラメータ（condition等）もinit_kwargsにコピーする ▼▼▼
        # これがないと condition, target_condition が無視され、常時発動になってしまう
        for k, v in s_data.items():
            if k not in ['name', 'trigger_type', 'trigger_value', 'effect_type', 'kwargs', 'stages']:
                init_kwargs[k] = v
        
        # ▼▼▼ スキルレベル処理 (Lv1~10 -> index 0~9) ▼▼▼
        level_idx = max(0, min(9, skill_level - 1))
        
        # 1. トップレベルのkwargsを展開
        keys_to_process = list(init_kwargs.keys())
        for k in keys_to_process:
            if k.endswith('_list') and isinstance(init_kwargs[k], list):
                base_key = k[:-5] # "_list" を削除
                if base_key not in init_kwargs:
                    val_list = init_kwargs[k]
                    if len(val_list) > level_idx:
                        init_kwargs[base_key] = val_list[level_idx]
        
        # 2. stages 内の展開
        stages = []
        if 'stages' in s_data: 
            raw_stages = s_data['stages']
            for i, st in enumerate(raw_stages):
                st_copy = st.copy()
                st_kwargs = st.get('kwargs', {}).copy()
                
                st_keys = list(st_kwargs.keys())
                for k in st_keys:
                    if k.endswith('_list') and isinstance(st_kwargs[k], list):
                        base_key = k[:-5]
                        if base_key not in st_kwargs:
                            val_list = st_kwargs[k]
                            if len(val_list) > level_idx:
                                resolved_val = val_list[level_idx]
                                st_kwargs[base_key] = resolved_val
                                if base_key == 'multiplier':
                                    print(f"[Debug] {s_data.get('name', 'Unknown')} Stage {i}: multiplier resolved to {resolved_val}")

                st_copy['kwargs'] = st_kwargs
                stages.append(st_copy)

        return Skill(
            name=s_data.get('name', 'Unknown Skill'),
            trigger_type=s_data.get('trigger_type', 'manual'),
            trigger_value=s_data.get('trigger_value', 0),
            effect_type=s_data.get('effect_type', 'buff'),
            stages=stages,
            **init_kwargs
        )

    skills = []
    if 'skills' in char_data:
        for s_data in char_data['skills']:
            s = parse_skill_data(s_data)
            s.owner_name = char_name
            skills.append(s)
            
    if 'burst_skill' in char_data:
        b_data = char_data['burst_skill']
        b_skill = parse_skill_data(b_data)
        b_skill.owner_name = char_name
        if b_skill.trigger_type != 'on_use_burst_skill':
            b_skill.trigger_type = 'on_use_burst_skill' 
        skills.append(b_skill)

    return Character(char_name, weapon_config, skills, base_atk, base_hp, element, burst_stage, char_class)

# --- ヘルパー関数: ダミーキャラ作成 ---
def create_dummy_character(name, burst_stage, weapon_type="AR", skills=None):
    weapon_data = {'name': f"{name}_Weapon", 'weapon_type': weapon_type, 'burst_stage': str(burst_stage)}
    wc = WeaponConfig(weapon_data)
    skill_list = skills if skills else []
    return Character(name, wc, skill_list, base_atk=1, base_hp=1, element="Electric", burst_stage=burst_stage, is_dummy=False)


# === メイン処理 ===

if not os.path.exists('characters'): os.makedirs('characters')

dummy_ct_skill = Skill(
    name="Dummy B1: CT Reduction",
    trigger_type="on_use_burst_skill", 
    trigger_value=0,
    effect_type="cooldown_reduction",
    target="allies", 
    value=5.0
)

# 1. キャラクターの読み込み
print(">>> キャラクター読み込み開始")
burst3_nikke = create_character_from_json('characters/アスカ_WILLE.json', skill_level=10)
rei_nikke = create_character_from_json('characters/レイ_仮称.json', skill_level=10)
toob_nikke = create_character_from_json('characters/2B.json', skill_level=10)
print(">>> キャラクター読み込み完了\n")

# 2. ダミーキャラの作成
dummy_b1 = create_dummy_character("Dummy_B1", 1, "SMG", skills=[dummy_ct_skill])
dummy_b2 = create_dummy_character("Dummy_B2", 2, "SMG")
dummy_b3 = create_dummy_character("Dummy_B3", 3, "SMG")

# 3. 編成リスト作成 
# 例: 2B単独テスト + ダミー
all_characters = [dummy_b1, dummy_b2, burst3_nikke, rei_nikke, create_dummy_character("Dummy_5", 3, "RL")]

# 4. バーストローテーション
rotation = [
    [dummy_b1],
    [dummy_b2],
    [burst3_nikke, rei_nikke] 
]

# 5. シミュレーター初期化
sim = NikkeSimulator(
    characters=all_characters,
    burst_rotation=rotation,
    enemy_element="None", 
    enemy_core_size=3.0,
    enemy_size=100,
    part_break_mode=False,
    burst_charge_time=5.0
)

# 6. 実行
print("シミュレーションを開始します...")
results = sim.run()
print("シミュレーション終了。")

# 7. 結果表示
print("-" * 50)
total_party_damage = sum(r['total_damage'] for r in results.values())
print(f"パーティ総ダメージ: {total_party_damage:,.0f}")
print("-" * 50)

for name, res in results.items():
    if res['total_damage'] > 0:
        print(f"■ {name} - Total: {res['total_damage']:,.0f}")
        for k, v in res['breakdown'].items():
            if v > 0:
                print(f"   - {k}: {v:,.0f}")
        print("")