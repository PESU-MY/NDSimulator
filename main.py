import json
import os
from simulator import NikkeSimulator, WeaponConfig, Skill, BurstCharacter
import matplotlib.pyplot as plt
import numpy as np

# --- 日本語フォントの設定 ---
plt.rcParams['font.family'] = 'MS Gothic'

def load_character_full_setup(char_file_path):
    with open(char_file_path, 'r', encoding='utf-8') as f:
        char_data = json.load(f)
    
    char_name = char_data['name']
    weapon_type_str = char_data['weapon_type'].lower()
    element = char_data.get('element', 'Iron')
    stats = char_data['stats']
    char_class = char_data.get('class', 'Attacker')
    
    # 武器情報の読み込み
    weapon_file_path = f"weapons/{weapon_type_str}_standard.json"
    if os.path.exists(weapon_file_path):
        with open(weapon_file_path, 'r', encoding='utf-8') as f:
            weapon_data = json.load(f)
    
    # 基本項目の設定
    weapon_data['name'] = f"{char_name}'s {weapon_data['weapon_class']}"
    weapon_data['element'] = element
    
    # --- 修正: stats内の全パラメータでweapon_dataを更新 ---
    for key, value in stats.items():
        if key == 'reload_time':
            weapon_data['reload_frames'] = int(value * 60)
        elif key == 'damage_rate':
            weapon_data['multiplier'] = value
        elif key == 'core_hit_rate':
            # core_hit_rate はWeaponConfigから削除されたため無視する
            pass 
        else:
            # hit_size などのパラメータはそのまま上書き
            weapon_data[key] = value
    # -------------------------------------------------------
    
    weapon_config = WeaponConfig(weapon_data)
    
    # クラスごとの基礎ステータス設定
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

    def parse_skill_data(s_data):
        init_kwargs = s_data.get('kwargs', {}).copy()
        for k, v in s_data.items():
            if k not in ['name', 'trigger_type', 'trigger_value', 'effect_type', 'kwargs', 'stages']:
                init_kwargs[k] = v
        
        stages = []
        if 'stages' in s_data:
            for stage in s_data['stages']:
                stages.append(stage)
        
        return Skill(
            name=s_data['name'],
            trigger_type=s_data['trigger_type'],
            trigger_value=s_data.get('trigger_value', 0),
            effect_type=s_data['effect_type'],
            stages=stages,
            **init_kwargs
        )

    passive_skills = []
    if 'skills' in char_data:
        for s_data in char_data['skills']:
            s = parse_skill_data(s_data)
            s.owner_name = char_name
            passive_skills.append(s)
            
    burst_skill = None
    if 'burst_skill' in char_data:
        burst_skill = parse_skill_data(char_data['burst_skill'])
        burst_skill.owner_name = char_name

    return {
        "name": char_name, "base_atk": base_atk, "base_hp": base_hp, "element": element,
        "weapon_config": weapon_config, "passive_skills": passive_skills, "burst_skill": burst_skill
    }

if not os.path.exists('characters'): os.makedirs('characters')

# ドロシーの読み込み (命中率仕様変更の確認用)
nikke_setup = load_character_full_setup('characters/アイン.json')

# --- 追加: 常時バーストCT短縮スキル ---
passive_cd_reduction = Skill(
    name="Passive: CD Reduction",
    trigger_type="on_burst_enter", 
    trigger_value=0,
    effect_type="cooldown_reduction",
    target="allies",
    value=5.0,  # 5秒短縮
    owner_name="System"
)

# バースト編成
b1 = BurstCharacter("B1", 1, 20, None, element="Wind", weapon_type="SMG", base_atk=15000)
b2 = BurstCharacter("B2", 2, 20, None, element="Water", weapon_type="AR", base_atk=18000)
b3_nikke = BurstCharacter(
    nikke_setup['name'], 
    3, 
    40, 
    nikke_setup['burst_skill'], 
    element=nikke_setup['element'],
    weapon_type="SG",
    base_atk=nikke_setup['base_atk'],
    base_hp=nikke_setup['base_hp']
)
b3_dummy = BurstCharacter("B3_Dummy", 3, 40, None, element="Fire", weapon_type="MG", base_atk=10000)

rotation = [[b1], [b2], [b3_nikke, b3_dummy]]

sim = NikkeSimulator(
    weapon_config=nikke_setup['weapon_config'],
    skills=nikke_setup['passive_skills']+[passive_cd_reduction],
    burst_rotation=rotation,
    base_atk=nikke_setup['base_atk'],
    base_hp=nikke_setup['base_hp'],
    enemy_element="None", 
    enemy_core_size=3.0, # コアサイズ指定
    enemy_size=100,      # 敵サイズ指定
    character_name=nikke_setup['name']
)

breakdown = sim.run()

print(f"キャラクター: {nikke_setup['name']}")
print(f"基礎攻撃力: {sim.BASE_ATK}")
print(f"総ダメージ: {sim.total_damage:,.0f}")
print("【ダメージ内訳】")
for name, val in breakdown.items():
    if val > 0:
        print(f"{name.ljust(35)}: {val:12,.0f}")

duration_seconds = sim.TOTAL_FRAMES / sim.FPS
overall_dps = sim.total_damage / duration_seconds
print(f"経過時間: {duration_seconds:.1f} 秒")
print(f"平均DPS: {overall_dps:,.0f}")

time_axis = sim.history['frame']
damage_per_frame = sim.history['damage']
cumulative_damage = np.cumsum(damage_per_frame)

plt.figure(figsize=(12, 6))
plt.plot(time_axis, cumulative_damage, label='総ダメージ (累積)', color='red', linewidth=1.5)
plt.xlabel('時間 (秒)')
plt.ylabel('総ダメージ')
plt.title(f'総ダメージ推移: {nikke_setup["name"]}')
plt.grid(True, alpha=0.3)
plt.legend()
plt.tight_layout()
plt.show()