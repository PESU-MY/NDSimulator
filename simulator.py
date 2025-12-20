import json
import math
import random
import matplotlib.pyplot as plt
import os

def round_half_up(n):
    return math.floor(n + 0.5)

# --- 1. データ定義 ---

class WeaponConfig:
    def __init__(self, data):
        self.name = data.get('name', 'Unknown Weapon')
        
        raw_type = data.get('weapon_type', 'AR')
        self.weapon_class = data.get('weapon_class', raw_type)
        
        self.type = data.get('type', 'RAPID')
        if self.weapon_class == "MG":
            self.type = "MG"
        elif self.weapon_class in ["RL", "SR"]:
            self.type = "CHARGE"
            
        self.element = data.get('element', 'Iron')
        
        # --- 追加: バースト段階の読み込み ---
        # "1", "2", "3" などの文字列または数値を受け取る
        self.burst_stage = str(data.get('burst_stage', '3')) 
        # -------------------------------

        self.multiplier = data.get('multiplier', 1.0)
        self.max_ammo = data.get('max_ammo', 60)
        self.reload_frames = data.get('reload_frames', 60)
        self.windup_frames = data.get('windup_frames', 12)
        self.winddown_frames = data.get('winddown_frames', 10)
        self.pellet_count = data.get('pellet_count', 1)
        self.fire_interval = data.get('fire_interval', 5)
        self.reset_ammo_on_revert = data.get('reset_ammo_on_revert', True)
        
        default_hit_sizes = {
            "RL": 1, "SR": 1, "MG": 1,
            "SMG": 9, "AR": 6, "SG": 20
        }
        self.hit_size = data.get('hit_size', default_hit_sizes.get(self.weapon_class, 5))
        
        self.is_pierce = data.get('is_pierce', False)
        self.disable_reload_buffs = data.get('disable_reload_buffs', False)
        self.disable_charge_buffs = data.get('disable_charge_buffs', False)
        self.disable_attack_speed_buffs = data.get('disable_attack_speed_buffs', False)
        self.charge_time = data.get('charge_time', 0)
        self.charge_mult = data.get('charge_mult', 1.0)
        
        self.mg_warmup_map = []
        self.mg_max_warmup = 0
        
        if self.type == "MG":
            if 'warmup_table' not in data:
                data['warmup_table'] = [
                    [10, 6],
                    [10, 5],
                    [15, 2],
                    [9999, 1] 
                ]
            
            current_sum = 0
            for count, interval in data['warmup_table']:
                self.mg_warmup_map.append({'start': current_sum, 'interval': interval})
                current_sum += count 
            self.mg_max_warmup = current_sum + self.windup_frames

    @classmethod
    def load_from_file(cls, filepath):
        with open(filepath, 'r', encoding='utf-8') as f:
            data = json.load(f)
        return cls(data)

class DamageProfile:
    @staticmethod
    def create(**kwargs):
        profile = {
            'crit_rate': 0.15,
            'charge_mult': 1.0,
            'is_weapon_attack': False, 'range_bonus_active': False,
            'is_charge_attack': False, 'is_part_damage': False,
            'is_pierce': False, 'is_ignore_def': False,
            'is_dot': False, 'is_sticky': False, 'is_explosive': False,
            'is_split': False, 'is_elemental': False,
            'burst_buff_enabled': True,
            'force_full_burst': False, 
            'is_skill_damage': False,
            'enable_core_hit': False 
        }
        if kwargs:
            profile.update(kwargs)
        return profile

class Skill:
    def __init__(self, name, trigger_type, trigger_value=0, effect_type="buff", **kwargs):
        self.name = name
        self.trigger_type = trigger_type
        self.trigger_value = trigger_value
        self.effect_type = effect_type
        self.kwargs = kwargs
        
        self.target = kwargs.get('target', 'self')
        self.target_condition = kwargs.get('target_condition', None)
        
        self.remove_tags = kwargs.get('remove_tags', [])
        self.condition = kwargs.get('condition', None)
        
        self.stages = kwargs.get('stages', [])
        self.max_stage = kwargs.get('max_stage', len(self.stages))
        
        self.sub_effect = kwargs.get('sub_effect', None)
        
        self.current_usage_count = 0
        self.owner_name = None

class BuffManager:
    def __init__(self):
        self.buffs = {}
        self.active_stacks = {}

    def add_buff(self, buff_type, value, duration_frames, current_frame, source=None, stack_name=None, max_stack=1, tag=None, shot_duration=0, remove_on_reload=False, stack_amount=1):
        buff_data = {
            'val': value, 
            'end_frame': current_frame + duration_frames, 
            'source': source,
            'tag': tag,
            'shot_life': shot_duration,
            'remove_on_reload': remove_on_reload
        }

        if stack_name:
            if stack_name in self.active_stacks:
                stack_data = self.active_stacks[stack_name]
                stack_data['count'] = min(stack_data['max_stack'], stack_data['count'] + stack_amount)
                stack_data['end_frame'] = current_frame + duration_frames
                stack_data['unit_value'] = value 
                stack_data['tag'] = tag
                stack_data['shot_life'] = shot_duration
                stack_data['remove_on_reload'] = remove_on_reload
                return stack_data['count']
            else:
                self.active_stacks[stack_name] = {
                    'count': min(max_stack, stack_amount), 'max_stack': max_stack, 'buff_type': buff_type,
                    'unit_value': value, 'end_frame': current_frame + duration_frames,
                    'tag': tag,
                    'shot_life': shot_duration,
                    'remove_on_reload': remove_on_reload
                }
                return stack_amount
        else:
            if buff_type not in self.buffs: self.buffs[buff_type] = []
            existing_buff = None
            if source is not None:
                for b in self.buffs[buff_type]:
                    if b.get('source') == source:
                        existing_buff = b
                        break
            if existing_buff:
                existing_buff.update(buff_data)
            else:
                self.buffs[buff_type].append(buff_data)
            return 1

    def set_stack_count(self, stack_name, count, max_stack=100):
        if stack_name in self.active_stacks:
            self.active_stacks[stack_name]['count'] = min(self.active_stacks[stack_name]['max_stack'], count)
        else:
            self.active_stacks[stack_name] = {
                'count': min(max_stack, count), 'max_stack': max_stack, 'buff_type': 'counter',
                'unit_value': 0, 'end_frame': 99999999, 'tag': None, 'shot_life': 0, 'remove_on_reload': False
            }

    def remove_buffs_by_tag(self, tag, current_frame):
        if not tag: return
        for buff_type in self.buffs:
            self.buffs[buff_type] = [b for b in self.buffs[buff_type] if b.get('tag') != tag]
        keys_to_remove = [k for k, v in self.active_stacks.items() if v.get('tag') == tag]
        for k in keys_to_remove:
            del self.active_stacks[k]

    def remove_reload_buffs(self):
        for buff_type in self.buffs:
            self.buffs[buff_type] = [b for b in self.buffs[buff_type] if not b.get('remove_on_reload', False)]
        keys_to_remove = [k for k, v in self.active_stacks.items() if v.get('remove_on_reload', False)]
        for k in keys_to_remove:
            del self.active_stacks[k]

    def has_active_tag(self, tag, current_frame):
        if not tag: return False
        for buff_list in self.buffs.values():
            for b in buff_list:
                if b.get('tag') == tag and (b['end_frame'] >= current_frame or b['shot_life'] > 0):
                    return True
        for stack in self.active_stacks.values():
            if stack.get('tag') == tag and (stack['end_frame'] >= current_frame or stack['shot_life'] > 0):
                return True
        return False

    def get_total_value(self, buff_type, current_frame):
        total = 0.0
        if buff_type in self.buffs:
            valid_buffs = [b for b in self.buffs[buff_type] if b['end_frame'] >= current_frame or b['shot_life'] > 0]
            self.buffs[buff_type] = valid_buffs
            total += sum(b['val'] for b in valid_buffs)
            
        expired_stacks = []
        for name, stack in self.active_stacks.items():
            if stack['end_frame'] < current_frame and stack['shot_life'] <= 0:
                expired_stacks.append(name)
                continue
            if stack['buff_type'] == buff_type:
                total += stack['unit_value'] * stack['count']
        for name in expired_stacks: del self.active_stacks[name]
        return total
    
    def get_active_buffs(self, buff_type, current_frame):
        vals = []
        if buff_type in self.buffs:
            valid_buffs = [b for b in self.buffs[buff_type] if b['end_frame'] >= current_frame or b['shot_life'] > 0]
            self.buffs[buff_type] = valid_buffs
            vals.extend([b['val'] for b in valid_buffs])
        for name, stack in list(self.active_stacks.items()):
            if stack['end_frame'] >= current_frame or stack['shot_life'] > 0:
                if stack['buff_type'] == buff_type:
                    for _ in range(stack['count']): vals.append(stack['unit_value'])
            else: del self.active_stacks[name]
        return vals
    
    def get_stack_count(self, stack_name, current_frame):
        if stack_name in self.active_stacks:
            stack = self.active_stacks[stack_name]
            if stack['end_frame'] >= current_frame or stack['shot_life'] > 0: return stack['count']
            else: del self.active_stacks[stack_name]
        return 0

    def decrement_shot_buffs(self):
        for buff_type in self.buffs:
            for b in self.buffs[buff_type]:
                if b['shot_life'] > 0:
                    b['shot_life'] -= 1
        for name, stack in self.active_stacks.items():
            if stack['shot_life'] > 0:
                stack['shot_life'] -= 1
    
    def get_active_buffs_debug(self, current_frame):
        parts = []
        for b_type, b_list in self.buffs.items():
            active_list = [b for b in b_list if b['end_frame'] >= current_frame or b['shot_life'] > 0]
            if active_list:
                total = sum(b['val'] for b in active_list)
                parts.append(f"{b_type}:{total:.2f}")
        for name, stack in self.active_stacks.items():
            if stack['end_frame'] >= current_frame or stack['shot_life'] > 0:
                val = stack['unit_value'] * stack['count']
                parts.append(f"[{name} x{stack['count']} (Val:{val:.2f})]")
        return " | ".join(parts) if parts else "None"

class BurstCharacter:
    def __init__(self, name, stage, cooldown_sec, skill=None, element="Iron", weapon_type="AR", base_atk=10000, base_hp=1000000):
        self.name = name
        self.stage = stage 
        self.base_cooldown = cooldown_sec
        self.current_cooldown = 0 
        self.skill = skill
        self.element = element
        self.weapon_type = weapon_type
        self.base_atk = base_atk
        self.base_hp = base_hp
        self.has_used_burst = False
        if self.skill:
            self.skill.owner_name = self.name

# --- 2. シミュレーションエンジン ---

class NikkeSimulator:
    def __init__(self, weapon_config, skills, burst_rotation, base_atk, base_hp=1000000, enemy_element="None", enemy_core_size=3.0, enemy_size=5.0, part_break_mode=False, character_name="Main", log_file_path="simulation_log.txt"):
        self.FPS = 60
        self.TOTAL_FRAMES = 180 * self.FPS
        
        self.BASE_ATK = base_atk
        self.BASE_HP = base_hp
        self.ENEMY_DEF = 0 
        self.enemy_element = enemy_element
        
        self.enemy_core_size = enemy_core_size
        self.enemy_size = enemy_size
        
        self.part_break_mode = part_break_mode
        self.character_name = character_name
        
        self.log_file_path = log_file_path
        with open(self.log_file_path, 'w', encoding='utf-8') as f:
            f.write("=== Simulation Start ===\n")
        
        self.weapon = weapon_config
        self.original_weapon = weapon_config 
        self.is_weapon_changed = False
        self.weapon_change_end_frame = 0 
        self.weapon_change_ammo_specified = False
        
        self.log(f"[Config] Weapon: {self.weapon.name}")
        self.log(f"[Config] Type: {self.weapon.type} (Class: {self.weapon.weapon_class})")
        self.log(f"[Config] Max Ammo: {self.weapon.max_ammo}")
        self.log(f"[Config] Fire Interval (RAPID default): {self.weapon.fire_interval}")
        if self.weapon.type == "MG":
            self.log(f"[Config] MG Warmup Table: {len(self.weapon.mg_warmup_map)} stages")
            if len(self.weapon.mg_warmup_map) > 0:
                first = self.weapon.mg_warmup_map[0]
                self.log(f"[Config] Initial Interval: {first['interval']}F")
        
        self.current_max_ammo = self.weapon.max_ammo
        self.current_ammo = self.current_max_ammo
        
        self.skills = skills
        for s in self.skills: 
            if not s.owner_name: s.owner_name = self.character_name

        self.buff_manager = BuffManager()
        self.burst_rotation = burst_rotation
        self.burst_indices = [0, 0, 0] 
        self.all_burst_chars = []
        for stage_list in burst_rotation:
            for char in stage_list:
                self.all_burst_chars.append(char)
        
        self.last_burst_char_name = None

        self.state = "READY"
        self.state_timer = 0
        self.burst_state = "GEN" 
        self.burst_timer = 0
        self.current_action_duration = 0
        
        self.mg_warmup_frames = 0
        self.mg_decay_rate = self.weapon.mg_max_warmup / 68.0 if self.weapon.type == "MG" else 0
        
        self.total_shots = 0
        self.total_damage = 0
        self.active_dots = {}
        self.cumulative_pellet_hits = 0 
        self.cumulative_crit_hits = 0 
        
        self.scheduled_actions = []
        
        self.damage_breakdown = {'Weapon Attack': 0}
        
        def register_breakdown(skill_obj):
            if skill_obj.effect_type in ['damage', 'dot']:
                self.damage_breakdown[skill_obj.name] = 0
            if skill_obj.effect_type == 'cumulative_stages':
                for stage in skill_obj.stages:
                    if isinstance(stage, Skill): register_breakdown(stage)

        for s in skills: register_breakdown(s)
        for char in self.all_burst_chars:
            if char.skill: register_breakdown(char.skill)

        self.history = {'frame': [], 'damage': [], 'current_ammo': [], 'max_ammo': [], 'warmup': []}
        for char in self.all_burst_chars:
            self.history[f'ct_{char.name}'] = []

    def log(self, message):
        print(message)
        with open(self.log_file_path, 'a', encoding='utf-8') as f:
            f.write(message + '\n')

    def get_character_stats(self, name):
        if name == self.character_name or name == 'Main':
             return self.BASE_ATK, self.BASE_HP
        for char in self.all_burst_chars:
            if char.name == name:
                return char.base_atk, char.base_hp
        return 0, 0

    def check_target_condition(self, condition, frame):
        if not condition: return True
        
        my_name = self.character_name
        my_element = self.weapon.element if hasattr(self.weapon, 'element') else 'Iron'
        my_weapon = self.weapon.weapon_class
        my_atk = self.BASE_ATK
        
        # --- 変更: 複合条件チェック ---
        # 1つでも不一致があれば False を返す
        
        # 属性
        if 'element' in condition:
            if my_element != condition['element']: return False
            
        # 武器種
        if 'weapon_type' in condition:
            if my_weapon != condition['weapon_type']: return False
            
        # バースト段階 (メインキャラのバースト段階)
        if 'burst_stage' in condition:
            # メインキャラのバースト段階は self.weapon.burst_stage に格納されている想定
            my_stage = getattr(self.weapon, 'burst_stage', '0')
            if str(my_stage) != str(condition['burst_stage']): return False

        # 直前のバースト使用者か
        if condition.get('is_last_burst_user'):
            if self.last_burst_char_name != my_name: return False
            
        # クラス
        if 'class' in condition:
            # 現状Mainのクラスは持っていないが、必要ならWeaponConfigに追加
            pass 

        # タグ関連
        if "not_has_tag" in condition:
            tag = condition["not_has_tag"]
            if self.buff_manager.has_active_tag(tag, frame): return False
        if "has_tag" in condition:
            tag = condition["has_tag"]
            if not self.buff_manager.has_active_tag(tag, frame): return False
            
        # スタック数
        if "stack_min" in condition or "stack_max" in condition:
            stack_name = condition.get("stack_name")
            if stack_name:
                count = self.buff_manager.get_stack_count(stack_name, frame)
                min_v = condition.get("stack_min", -999)
                max_v = condition.get("stack_max", 999)
                if not (min_v <= count <= max_v): return False
        
        # 従来の 'type' 指定の互換性維持 (念のため)
        if 'type' in condition:
            if condition['type'] == 'element' and my_element != condition['value']: return False
            if condition['type'] == 'weapon_type' and my_weapon != condition['value']: return False
            # ... 他のタイプも必要に応じて
            
        return True

    def calculate_reduced_frame(self, original_frame, rate_buff, fixed_buff):
        if rate_buff <= -1.0: return 9999
        new_frame = original_frame * (1.0 - rate_buff)
        new_frame -= fixed_buff
        return max(1, int(new_frame))
    
    def calculate_reduced_frame_attack(self, original_frame, rate_buff, fixed_buff):
        if rate_buff <= -1.0: return 9999
        new_frame = original_frame / (1.0 + rate_buff)
        new_frame -= fixed_buff
        return max(1, int(new_frame))

    def get_buffed_frames(self, frame_type, original_frame, current_frame):
        if frame_type == 'reload':
            fixed_val = self.buff_manager.get_total_value('reload_speed_fixed_value', current_frame)
            if fixed_val > 0:
                return int(original_frame / (1.0 + fixed_val))
            if self.weapon.disable_reload_buffs: return int(original_frame)
        
        if frame_type == 'charge' and self.weapon.disable_charge_buffs: return int(original_frame)
        if frame_type == 'attack' and self.weapon.disable_attack_speed_buffs: return int(original_frame)
        
        rate = self.buff_manager.get_total_value(f'{frame_type}_speed_rate', current_frame)
        rate = min(rate, 1.0)
        
        fixed = self.buff_manager.get_total_value(f'{frame_type}_speed_fixed', current_frame)

        if frame_type == 'attack':
            return self.calculate_reduced_frame_attack(original_frame, rate, fixed)
        else:
            return self.calculate_reduced_frame(original_frame, rate, fixed)
            

    def update_max_ammo(self, frame):
        rate_buffs = self.buff_manager.get_active_buffs('max_ammo_rate', frame)
        fixed_buff_sum = self.buff_manager.get_total_value('max_ammo_fixed', frame)
        added_ammo = sum([round_half_up(self.weapon.max_ammo * rate) for rate in rate_buffs])
        self.current_max_ammo = int(self.weapon.max_ammo + added_ammo + fixed_buff_sum)
        if self.current_ammo > self.current_max_ammo: self.current_ammo = self.current_max_ammo

    def get_mg_interval(self):
        effective_time = max(0, self.mg_warmup_frames - self.weapon.windup_frames)
        target_interval = 1 
        for entry in reversed(self.weapon.mg_warmup_map):
            if effective_time >= entry['start']: target_interval = entry['interval']; break
        return target_interval

    def calculate_strict_damage(self, base_atk, mult, profile, is_full_burst, frame, attacker_element="None"):
        bm = self.buff_manager
        
        atk_rate = bm.get_total_value('atk_buff_rate', frame)
        atk_fixed = bm.get_total_value('atk_buff_fixed', frame)
        
        hp_conv_rate = bm.get_total_value('conversion_hp_to_atk', frame)
        if hp_conv_rate > 0:
            max_hp_rate = bm.get_total_value('max_hp_rate', frame)
            current_max_hp = self.BASE_HP * (1.0 + max_hp_rate)
            atk_fixed += current_max_hp * hp_conv_rate

        final_atk = (base_atk * (1.0 + atk_rate)) + atk_fixed
        
        def_debuff = bm.get_total_value('def_debuff', frame)
        current_def = 0 if profile['is_ignore_def'] else self.ENEMY_DEF
        effective_def = current_def * (1.0 - def_debuff)
        raw_damage_diff = final_atk - effective_def
        if raw_damage_diff <= 0: return 1.0, False
        
        layer_atk = raw_damage_diff
        
        weapon_buff = bm.get_total_value('weapon_dmg_buff', frame) if profile['is_weapon_attack'] else 0.0
        layer_weapon = mult * (1.0 + weapon_buff)
        
        bucket_val = 1.0
        if profile['burst_buff_enabled']:
            if is_full_burst or profile.get('force_full_burst', False): bucket_val += 0.50
        if profile['range_bonus_active']: bucket_val += 0.30
        
        base_hit_size = self.weapon.hit_size
        hit_rate_buff = bm.get_total_value('hit_rate_buff', frame)
        current_hit_size = max(0.01, base_hit_size * (1.0 - hit_rate_buff))
        
        hit_prob = min(1.0, (self.enemy_size / current_hit_size) ** 2)
        
        can_core_hit = profile.get('is_weapon_attack', False) or profile.get('enable_core_hit', False)
        
        is_core = False
        if can_core_hit:
            fixed_core_rate = bm.get_total_value('core_hit_rate_fixed', frame)
            if fixed_core_rate > 0:
                core_prob = 1.0
            else:
                core_prob = min(1.0, (self.enemy_core_size / current_hit_size) ** 2)
                
            if core_prob > hit_prob: core_prob = hit_prob
            is_core = random.random() < (core_prob / hit_prob)

        is_hit = random.random() < hit_prob
        if not is_hit: return 0.0, False
        
        if is_core:
            core_dmg_buff = bm.get_total_value('core_dmg_buff', frame)
            bucket_val += 1.0 + core_dmg_buff
            
        crit_rate = profile['crit_rate'] + bm.get_total_value('crit_rate_buff', frame)
        is_crit_hit = False
        if random.random() < crit_rate:
            bucket_val += (0.50 + bm.get_total_value('crit_dmg_buff', frame))
            is_crit_hit = True
            
        layer_crit = bucket_val
        
        layer_charge = 1.0
        if profile['is_charge_attack']:
            charge_ratio_buff = bm.get_total_value('charge_ratio_buff', frame)
            charge_dmg_buff = bm.get_total_value('charge_dmg_buff', frame)
            layer_charge = (profile['charge_mult'] * (1.0 + charge_ratio_buff)) + charge_dmg_buff
            
        bucket_dmg = 1.0
        bucket_dmg += bm.get_total_value('atk_dmg_buff', frame)
        if profile['is_part_damage']: bucket_dmg += bm.get_total_value('part_dmg_buff', frame)
        
        is_pierce_buff = bm.get_total_value('is_pierce', frame)
        if profile['is_pierce'] or is_pierce_buff > 0: 
            bucket_dmg += bm.get_total_value('pierce_dmg_buff', frame)
            
        if profile['is_ignore_def']: bucket_dmg += bm.get_total_value('ignore_def_dmg_buff', frame)
        if profile['is_dot']: bucket_dmg += bm.get_total_value('dot_dmg_buff', frame)
        if profile['burst_buff_enabled'] and (is_full_burst or profile.get('force_full_burst', False)):
             bucket_dmg += bm.get_total_value('burst_dmg_buff', frame)
        
        taken_dmg_val = bm.get_total_value('taken_dmg_debuff', frame)
        layer_taken = 1.0 + taken_dmg_val
        
        layer_dmg = bucket_dmg
        
        layer_split = 1.0
        if profile['is_split']: layer_split += bm.get_total_value('split_dmg_buff', frame)
        
        layer_elem = 1.0
        advantage_map = {
            "Iron": "Electric", "Electric": "Water", "Water": "Fire", "Fire": "Wind", "Wind": "Iron"
        }
        if advantage_map.get(attacker_element) == self.enemy_element:
            elem_buff = bm.get_total_value('elemental_buff', frame)
            layer_elem += 0.10 + elem_buff
            
        return layer_atk * layer_weapon * layer_crit * layer_charge * layer_dmg * layer_split * layer_taken * layer_elem, is_crit_hit

    def should_apply_skill(self, skill, frame):
        is_target_valid = True
        if skill.target == 'self':
            if skill.owner_name != 'Main' and skill.owner_name != self.character_name: 
                is_target_valid = False
        if not is_target_valid: return False

        if skill.condition:
            if "not_has_tag" in skill.condition:
                tag = skill.condition["not_has_tag"]
                if self.buff_manager.has_active_tag(tag, frame):
                    return False
            if "has_tag" in skill.condition:
                tag = skill.condition["has_tag"]
                if not self.buff_manager.has_active_tag(tag, frame):
                    return False
            if "stack_min" in skill.condition or "stack_max" in skill.condition:
                stack_name = skill.condition.get("stack_name")
                if stack_name:
                    count = self.buff_manager.get_stack_count(stack_name, frame)
                    min_v = skill.condition.get("stack_min", -999)
                    max_v = skill.condition.get("stack_max", 999)
                    if not (min_v <= count <= max_v):
                        return False
        return True

    def apply_skill_effect(self, skill, frame, is_full_burst, attacker_element="None"):
        if not self.should_apply_skill(skill, frame): return 0
        if skill.target == 'allies' and skill.target_condition:
            if not self.check_target_condition(skill.target_condition, frame): return 0

        for tag in skill.remove_tags:
            self.buff_manager.remove_buffs_by_tag(tag, frame)

        dmg = 0
        
        kwargs = skill.kwargs.copy()
        
        if kwargs.get('scale_by_caster_stats'):
            owner_name = skill.owner_name
            base_atk, base_hp = self.get_character_stats(owner_name)
            
            ratio = kwargs.get('value', 0)
            stat_type = kwargs.get('stat_type', 'current') 
            
            calc_atk = base_atk
            if stat_type == 'current' and (owner_name == self.character_name or owner_name == 'Main'):
                 atk_rate = self.buff_manager.get_total_value('atk_buff_rate', frame)
                 atk_fixed = self.buff_manager.get_total_value('atk_buff_fixed', frame)
                 calc_atk = (base_atk * (1.0 + atk_rate)) + atk_fixed
            
            if calc_atk > 0:
                kwargs['value'] = calc_atk * ratio

        if skill.effect_type == 'convert_hp_to_atk':
            rate = skill.kwargs.get('value', 0)
            self.buff_manager.add_buff('conversion_hp_to_atk', rate, skill.kwargs.get('duration', 0) * self.FPS, frame, source=skill.name)
            return 0
        
        if skill.effect_type == 'cumulative_stages':
            if skill.kwargs.get('trigger_all_stages'):
                for i, stage_data in enumerate(skill.stages):
                    if isinstance(stage_data, Skill):
                        stage_data.target = skill.target
                        stage_data.owner_name = skill.owner_name
                        dmg += self.apply_skill_effect(stage_data, frame, is_full_burst, attacker_element)
                    elif isinstance(stage_data, dict):
                        init_kwargs = stage_data.get('kwargs', {}).copy()
                        for k, v in stage_data.items():
                            if k not in ['name', 'trigger_type', 'trigger_value', 'effect_type', 'kwargs']:
                                init_kwargs[k] = v
                        
                        temp_skill = Skill(
                            name=f"{skill.name}_Stage_{i}", 
                            trigger_type="manual", 
                            trigger_value=0,
                            effect_type=stage_data.get('effect_type', 'buff'), 
                            **init_kwargs
                        )
                        temp_skill.target = skill.target
                        temp_skill.owner_name = skill.owner_name
                        dmg += self.apply_skill_effect(temp_skill, frame, is_full_burst, attacker_element)
                return dmg

            skill.current_usage_count += 1
            max_apply_idx = min(len(skill.stages), skill.current_usage_count)
            for i in range(max_apply_idx):
                stage_data = skill.stages[i]
                if isinstance(stage_data, Skill):
                    stage_data.target = skill.target
                    stage_data.owner_name = skill.owner_name
                    dmg += self.apply_skill_effect(stage_data, frame, is_full_burst, attacker_element)
                elif isinstance(stage_data, dict):
                    init_kwargs = stage_data.get('kwargs', {}).copy()
                    for k, v in stage_data.items():
                        if k not in ['name', 'trigger_type', 'trigger_value', 'effect_type', 'kwargs']:
                            init_kwargs[k] = v
                    
                    temp_skill = Skill(
                        name=f"{skill.name}_Stage_{i}", 
                        trigger_type="manual", 
                        trigger_value=0,
                        effect_type=stage_data.get('effect_type', 'buff'), 
                        **init_kwargs
                    )
                    temp_skill.target = skill.target
                    temp_skill.owner_name = skill.owner_name
                    dmg += self.apply_skill_effect(temp_skill, frame, is_full_burst, attacker_element)
        
        elif skill.effect_type == 'stack_buff':
            stack_name = kwargs.get('stack_name', skill.name)
            max_stack = kwargs.get('max_stack', 1)
            stack_amount = kwargs.get('stack_amount', 1)
            tag = kwargs.get('tag')
            self.buff_manager.add_buff(kwargs['buff_type'], kwargs['value'], kwargs.get('duration', 0) * self.FPS, frame, source=skill.name, stack_name=stack_name, max_stack=max_stack, tag=tag, shot_duration=kwargs.get('shot_duration', 0), remove_on_reload=kwargs.get('remove_on_reload', False), stack_amount=stack_amount)

        elif skill.effect_type == 'stack_dot':
            stack_name = kwargs.get('stack_name', skill.name)
            max_stack = kwargs.get('max_stack', 1)
            raw_profile = kwargs.get('profile', {})
            full_profile = DamageProfile.create(**raw_profile)
            
            if stack_name in self.active_dots:
                dot = self.active_dots[stack_name]
                dot['count'] = min(max_stack, dot['count'] + 1)
                dot['end_frame'] = frame + (kwargs.get('duration', 0) * self.FPS)
                dot['profile'] = full_profile
            else:
                self.active_dots[stack_name] = {
                    'end_frame': frame + (kwargs.get('duration', 0) * self.FPS),
                    'multiplier': kwargs['multiplier'], 
                    'profile': full_profile,
                    'count': 1, 'max_stack': max_stack, 'element': attacker_element
                }

        elif skill.effect_type == 'buff':
            tag = kwargs.get('tag')
            if kwargs['buff_type'] == 'barrier': tag = 'barrier'
            
            self.buff_manager.add_buff(kwargs['buff_type'], kwargs['value'], kwargs.get('duration', 0) * self.FPS, frame, source=skill.name, tag=tag, shot_duration=kwargs.get('shot_duration', 0), remove_on_reload=kwargs.get('remove_on_reload', False))
            
            if kwargs['buff_type'] in ['dummy_heal', 'barrier']:
                if kwargs['buff_type'] == 'dummy_heal':
                    self.process_trigger('on_receive_heal', 0, frame, is_full_burst, attacker_char=None)
        
        elif skill.effect_type == 'damage':
            raw_profile = kwargs.get('profile', {})
            full_profile = DamageProfile.create(**raw_profile)
            
            loop_count = kwargs.get('loop_count', 1)
            multiplier = kwargs['multiplier']
            
            if kwargs.get('scale_by_target_stack'):
                stack_name = kwargs.get('stack_name')
                stack_count = self.buff_manager.get_stack_count(stack_name, frame)
                multiplier = multiplier * stack_count
            
            if kwargs.get('copy_stack_count'):
                stack_name = kwargs.get('copy_stack_count')
                current_stack = self.buff_manager.get_stack_count(stack_name, frame)
                loop_count = current_stack
                
            for _ in range(loop_count):
                dmg_val, _ = self.calculate_strict_damage(self.BASE_ATK, multiplier, full_profile, is_full_burst, frame, attacker_element)
                dmg += dmg_val
                
            self.log(f"[Skill] 時間:{frame/60:>6.2f}s | 名前:{skill.name:<25} | Dmg:{dmg:10,.0f} | Hits:{loop_count}")
            
            self.total_damage += dmg
            if skill.name in self.damage_breakdown: self.damage_breakdown[skill.name] += dmg
        
        elif skill.effect_type == 'dot':
            raw_profile = kwargs.get('profile', {})
            full_profile = DamageProfile.create(**raw_profile)
            self.active_dots[skill.name] = {
                'end_frame': frame + (kwargs.get('duration', 0) * self.FPS),
                'multiplier': kwargs['multiplier'], 
                'profile': full_profile,
                'count': 1, 'max_stack': 1, 'element': attacker_element
            }

        elif skill.effect_type == 'ammo_charge':
            charge_amount = kwargs.get('fixed_value', 0)
            if 'rate' in kwargs:
                charge_amount = int(self.current_max_ammo * kwargs['rate'])
            
            if self.current_ammo < self.current_max_ammo:
                self.current_ammo = min(self.current_max_ammo, self.current_ammo + charge_amount)
        
        elif skill.effect_type == 'weapon_change':
            new_weapon_data = kwargs.get('weapon_data')
            duration = kwargs.get('duration', 0)
            if new_weapon_data:
                self.is_weapon_changed = True
                
                if 'max_ammo' in new_weapon_data:
                    self.weapon_change_ammo_specified = True
                    self.weapon = WeaponConfig(new_weapon_data)
                    self.current_max_ammo = self.weapon.max_ammo
                    self.current_ammo = self.current_max_ammo
                else:
                    self.weapon_change_ammo_specified = False
                    temp_data = new_weapon_data.copy()
                    temp_data['max_ammo'] = self.current_max_ammo
                    self.weapon = WeaponConfig(temp_data)
                
                if duration > 0: self.weapon_change_end_frame = frame + (duration * self.FPS)
                else: self.weapon_change_end_frame = 0
                self.state = "READY"; self.state_timer = 0
        elif skill.effect_type == 'cooldown_reduction':
            reduce_sec = kwargs.get('value', 0)
            reduce_frames = reduce_sec * self.FPS
            for char in self.all_burst_chars:
                if char.current_cooldown > 0: char.current_cooldown = max(0, char.current_cooldown - reduce_frames)
        elif skill.effect_type == 'set_stack':
            stack_name = kwargs.get('stack_name')
            count = kwargs.get('value', 0)
            if stack_name:
                self.buff_manager.set_stack_count(stack_name, count)
        elif skill.effect_type == 'set_current_ammo':
            val = kwargs.get('value', 0)
            self.current_ammo = val
            self.log(f"[Effect] Ammo set to {val}")
            if self.current_ammo == 0:
                self.state = "RELOADING"
                self.state_timer = 0
                self.log("[State] Force Reloading started.")
        elif skill.effect_type == 'delayed_action':
            duration_sec = kwargs.get('duration', 0)
            exec_frame = frame + int(duration_sec * self.FPS)
            
            sub_data = skill.sub_effect
            if sub_data:
                init_kwargs = sub_data.get('kwargs', {}).copy()
                act_skill = Skill(
                    name=f"Delayed_{skill.name}", 
                    trigger_type="manual", trigger_value=0,
                    effect_type=sub_data.get('effect_type', 'buff'), 
                    **init_kwargs
                )
                act_skill.target = skill.target
                act_skill.owner_name = skill.owner_name
                
                if 'stages' in sub_data:
                    act_skill.stages = sub_data['stages']
                
                self.scheduled_actions.append({
                    'frame': exec_frame,
                    'skill': act_skill
                })
        return dmg

    def revert_weapon(self, frame):
        if not self.is_weapon_changed: return
        
        should_reset = getattr(self.weapon, 'reset_ammo_on_revert', True)
        
        self.weapon = self.original_weapon
        self.is_weapon_changed = False
        self.weapon_change_end_frame = 0
        
        self.update_max_ammo(frame)
        
        if self.weapon_change_ammo_specified and should_reset:
            self.current_ammo = self.current_max_ammo
        else:
            if self.current_ammo > self.current_max_ammo:
                self.current_ammo = self.current_max_ammo
                
        self.state = "READY"; self.state_timer = 0

    def process_trigger(self, trigger_type, val, frame, is_full_burst, attacker_char=None):
        total_dmg = 0
        attacker_element = attacker_char.element if attacker_char else self.weapon.element
        check_skills = []
        check_skills.extend(self.skills)
        if attacker_char and attacker_char.skill: check_skills.append(attacker_char.skill)

        triggered_skills = []
        for skill in check_skills:
            if skill.trigger_type == trigger_type:
                is_triggered = False
                if trigger_type == 'on_use_burst_skill':
                    if attacker_char and skill.owner_name == attacker_char.name: is_triggered = True
                elif trigger_type == 'stack_count':
                    target_stack = skill.kwargs.get('stack_name')
                    current_count = self.buff_manager.get_stack_count(target_stack, frame)
                    if current_count >= skill.trigger_value: is_triggered = True
                elif trigger_type == 'part_break': 
                    is_triggered = True
                elif skill.trigger_value <= 0 and trigger_type in ['shot_count', 'time_interval', 'pellet_hit', 'critical_hit']: is_triggered = False 
                elif trigger_type == 'shot_count' and val > 0 and val % skill.trigger_value == 0: is_triggered = True
                elif trigger_type == 'time_interval' and val % (skill.trigger_value * self.FPS) == 0: is_triggered = True
                elif trigger_type == 'ammo_empty' and val == 0: is_triggered = True
                elif trigger_type == 'on_burst_enter': is_triggered = True
                elif trigger_type == 'on_burst_3_enter': is_triggered = True
                elif trigger_type == 'on_start': is_triggered = True
                elif trigger_type == 'on_burst_end': is_triggered = True
                elif trigger_type == 'pellet_hit' and val >= skill.trigger_value: is_triggered = True 
                elif trigger_type == 'critical_hit' and val >= skill.trigger_value: is_triggered = True
                elif trigger_type == 'on_receive_heal': is_triggered = True 
                elif trigger_type == 'variable_interval':
                    intervals = skill.kwargs.get('intervals', {})
                    stack_name = skill.kwargs.get('stack_name')
                    if stack_name:
                        current_stack = self.buff_manager.get_stack_count(stack_name, frame)
                        interval = intervals.get(str(current_stack))
                        if interval and val % interval == 0:
                            is_triggered = True
                
                if is_triggered: triggered_skills.append(skill)
        
        for skill in triggered_skills:
            total_dmg += self.apply_skill_effect(skill, frame, is_full_burst, attacker_element)
            
        return total_dmg, len(triggered_skills) > 0

    def update_cooldowns(self):
        for char in self.all_burst_chars:
            if char.current_cooldown > 0: char.current_cooldown -= 1

    def tick_burst_state(self, frame):
        is_full_burst = (self.burst_state == "FULL")
        if self.burst_state == "GEN":
            self.burst_timer += 1
            if self.burst_timer >= 5 * self.FPS: self.burst_state = "BURST_1"; self.burst_timer = 0
        elif self.burst_state in ["BURST_1", "BURST_2", "BURST_3"]:
            stage_idx = {"BURST_1": 0, "BURST_2": 1, "BURST_3": 2}[self.burst_state]
            char_list = self.burst_rotation[stage_idx]
            idx = self.burst_indices[stage_idx]
            char = char_list[idx]
            if char.current_cooldown <= 0:
                char.current_cooldown = char.base_cooldown * self.FPS
                char.has_used_burst = True
                
                if self.burst_state == "BURST_3":
                    self.process_trigger('on_burst_3_enter', 0, frame, is_full_burst, attacker_char=char)
                    self.last_burst_char_name = char.name
                
                if char.skill: self.apply_skill_effect(char.skill, frame, is_full_burst, char.element)
                self.process_trigger('on_use_burst_skill', 0, frame, is_full_burst, attacker_char=char)
                self.burst_indices[stage_idx] = (idx + 1) % len(char_list)
                if self.burst_state == "BURST_1": self.burst_state = "BURST_2"
                elif self.burst_state == "BURST_2": self.burst_state = "BURST_3"
                elif self.burst_state == "BURST_3":
                    self.burst_state = "FULL"; self.burst_timer = 0
                    self.process_trigger('on_burst_enter', 0, frame, True)
        elif self.burst_state == "FULL":
            self.burst_timer += 1
            if self.burst_timer >= 10 * self.FPS: 
                self.process_trigger('on_burst_end', 0, frame, False)
                self.burst_state = "GEN"; self.burst_timer = 0

    def tick_weapon_action(self, frame, is_full_burst):
        damage_this_frame = 0
        if self.weapon.type == "MG" and self.state != "SHOOTING" and self.state != "READY": 
            self.mg_warmup_frames -= self.mg_decay_rate
            self.mg_warmup_frames = max(0, self.mg_warmup_frames)

        def perform_shoot(interval_mult=1):
            nonlocal damage_this_frame
            self.total_shots += 1
            self.current_ammo -= 1
            force_fb = getattr(self.weapon, 'force_full_burst', False)
            if isinstance(self.weapon, dict): force_fb = self.weapon.get('force_full_burst', False)
            
            prof = DamageProfile.create(
                is_weapon_attack=True, range_bonus_active=False, 
                is_charge_attack=(self.weapon.type in ["RL", "SR", "CHARGE"]), 
                charge_mult=self.weapon.charge_mult if self.weapon.type in ["RL", "SR", "CHARGE"] else 1.0, 
                force_full_burst=force_fb, is_pierce=self.weapon.is_pierce
            )
            
            base_pellets = 10 if self.weapon.weapon_class == "SG" else 1
            pellet_add = self.buff_manager.get_total_value('pellet_count_add', frame)
            pellet_fixed = self.buff_manager.get_total_value('pellet_count_fixed', frame)
            
            base_pellets_from_config = getattr(self.weapon, 'pellet_count', 1)
            
            current_pellets = base_pellets_from_config + pellet_add
            if pellet_fixed > 0:
                current_pellets = pellet_fixed
            
            current_pellets = int(max(1, current_pellets))
            
            per_pellet_multiplier = self.weapon.multiplier / current_pellets

            total_shot_dmg = 0
            hit_count = 0
            crit_count = 0
            
            for _ in range(current_pellets):
                dmg, is_crit = self.calculate_strict_damage(self.BASE_ATK, per_pellet_multiplier, prof, is_full_burst, frame, self.weapon.element)
                
                total_shot_dmg += dmg
                if dmg > 0:
                    hit_count += 1
                if is_crit:
                    crit_count += 1
            
            self.cumulative_pellet_hits += hit_count
            self.cumulative_crit_hits += crit_count
            
            buff_debug_str = self.buff_manager.get_active_buffs_debug(frame)
            
            self.log(f"[Shoot] 時間:{frame/60:>6.2f}s | 弾数:{self.current_ammo:>3}/{self.current_max_ammo:<3} | ペレット:{current_pellets:>2} (Hit:{hit_count}) | Dmg:{total_shot_dmg:10,.0f} | Buffs: {buff_debug_str}")

            self.total_damage += total_shot_dmg
            self.damage_breakdown['Weapon Attack'] += total_shot_dmg
            damage_this_frame += total_shot_dmg
            
            self.buff_manager.decrement_shot_buffs()
            
            d, t1 = self.process_trigger('shot_count', self.total_shots, frame, is_full_burst)
            damage_this_frame += d
            d, t2 = self.process_trigger('ammo_empty', self.current_ammo, frame, is_full_burst)
            damage_this_frame += d
            d, t3 = self.process_trigger('pellet_hit', self.cumulative_pellet_hits, frame, is_full_burst)
            damage_this_frame += d
            d, t4 = self.process_trigger('critical_hit', self.cumulative_crit_hits, frame, is_full_burst)
            damage_this_frame += d
            if t3:
                self.cumulative_pellet_hits = 0 
            if t4:
                self.cumulative_crit_hits = 0
            

        if self.weapon.type in ["RL", "SR", "CHARGE"]:
            if self.state == "READY":
                if self.state_timer == 0: self.current_action_duration = self.get_buffed_frames('attack', self.weapon.windup_frames, frame)
                self.state_timer += 1
                if self.state_timer >= self.current_action_duration: self.state = "CHARGING"; self.state_timer = 0
            elif self.state == "CHARGING":
                if self.state_timer == 0: self.current_action_duration = self.get_buffed_frames('charge', self.weapon.charge_time, frame)
                self.state_timer += 1
                if self.state_timer >= self.current_action_duration: self.state = "SHOOTING"; self.state_timer = 0
            elif self.state == "SHOOTING":
                perform_shoot()
                self.state = "WINDDOWN"; self.state_timer = 0
            elif self.state == "WINDDOWN":
                if self.state_timer == 0: self.current_action_duration = self.get_buffed_frames('attack', self.weapon.winddown_frames, frame)
                self.state_timer += 1
                if self.state_timer >= self.current_action_duration:
                    self.state_timer = 0
                    if self.is_weapon_changed and self.current_ammo <= 0: self.revert_weapon(frame)
                    else: self.state = "RELOADING" if self.current_ammo <= 0 else "READY"
            elif self.state == "RELOADING":
                if self.state_timer == 0: self.current_action_duration = self.get_buffed_frames('reload', self.weapon.reload_frames, frame)
                self.state_timer += 1
                if self.state_timer >= self.current_action_duration:
                    self.current_ammo = self.current_max_ammo; self.state = "READY"; self.state_timer = 0
                    self.buff_manager.remove_reload_buffs()

        elif self.weapon.type == "MG":
            if self.state == "READY":
                if self.state_timer == 0: self.current_action_duration = self.get_buffed_frames('attack', self.weapon.windup_frames, frame)
                self.mg_warmup_frames = min(self.weapon.mg_max_warmup, self.mg_warmup_frames + 1)
                self.state_timer += 1
                if self.state_timer >= self.current_action_duration: self.state = "SHOOTING"; self.state_timer = 0 
            elif self.state == "SHOOTING":
                original_interval = self.get_mg_interval()
                buffed_interval = self.get_buffed_frames('attack', original_interval, frame)
                
                # --- 追加: 強制発射間隔バフの確認 ---
                forced_interval = self.buff_manager.get_total_value('force_fire_interval', frame)
                if forced_interval > 0:
                    buffed_interval = int(forced_interval)
                # --------------------------------
                
                if self.state_timer == 0:
                    perform_shoot()
                    
                    # --- 変更点: MG立ち上げ速度バフの適用 ---
                    warmup_speed = 1.0 + self.buff_manager.get_total_value('mg_warmup_speed', frame)
                    if warmup_speed < 0: warmup_speed = 0 # 負の値は停止とする
                    increment = warmup_speed
                    # ------------------------------------
                    
                    self.mg_warmup_frames = min(self.weapon.mg_max_warmup, self.mg_warmup_frames + increment)
                    if self.current_ammo <= 0: self.state = "WINDDOWN"; self.state_timer = 0
                    else: self.state_timer = max(0, buffed_interval - 1)
                else: self.state_timer -= 1
            elif self.state == "WINDDOWN":
                if self.state_timer == 0: self.current_action_duration = self.get_buffed_frames('attack', self.weapon.winddown_frames, frame)
                self.state_timer += 1
                if self.state_timer >= self.current_action_duration: 
                    self.state_timer = 0
                    if self.is_weapon_changed and self.current_ammo <= 0: self.revert_weapon(frame)
                    else: self.state = "RELOADING"
            elif self.state == "RELOADING":
                if self.state_timer == 0:
                    self.current_action_duration = self.get_buffed_frames('reload', self.weapon.reload_frames, frame)
                    self.log(f"[Action] Reloading... ({self.current_action_duration} frames)")
                
                self.state_timer += 1
                if self.state_timer >= self.current_action_duration: 
                    self.current_ammo = self.current_max_ammo
                    self.state = "READY"
                    self.state_timer = 0
                    self.buff_manager.remove_reload_buffs()
                    self.log(f"[Action] Reload Complete. Ammo: {self.current_ammo}")

        else: 
            if self.state == "READY":
                if self.state_timer == 0: self.current_action_duration = self.get_buffed_frames('attack', self.weapon.windup_frames, frame)
                self.state_timer += 1
                if self.state_timer >= self.current_action_duration: self.state = "SHOOTING"; self.state_timer = 0
            elif self.state == "SHOOTING":
                if self.state_timer == 0:
                    perform_shoot()
                    if self.current_ammo <= 0: self.state = "WINDDOWN"; self.state_timer = 0
                    else:
                        original_interval = self.weapon.fire_interval
                        buffed_interval = self.get_buffed_frames('attack', original_interval, frame)
                        self.state_timer = max(0, buffed_interval - 1)
                else: self.state_timer -= 1
            elif self.state == "WINDDOWN":
                if self.state_timer == 0: self.current_action_duration = self.get_buffed_frames('attack', self.weapon.winddown_frames, frame)
                self.state_timer += 1
                if self.state_timer >= self.current_action_duration:
                    self.state_timer=0
                    if self.is_weapon_changed and self.current_ammo <= 0: self.revert_weapon(frame)
                    else: self.state = "RELOADING"
            elif self.state == "RELOADING":
                if self.state_timer == 0: self.current_action_duration = self.get_buffed_frames('reload', self.weapon.reload_frames, frame)
                self.state_timer += 1
                if self.state_timer >= self.current_action_duration: self.current_ammo = self.current_max_ammo; self.state = "READY"; self.state_timer=0
                self.buff_manager.remove_reload_buffs()

        return damage_this_frame

    def tick(self, frame):
        self.tick_burst_state(frame)
        self.update_cooldowns()
        
        executed_indices = []
        is_full_burst = (self.burst_state == "FULL")
        for i, action in enumerate(self.scheduled_actions):
            if frame >= action['frame']:
                skill = action['skill']
                self.apply_skill_effect(skill, frame, is_full_burst, self.weapon.element)
                executed_indices.append(i)
        
        for i in reversed(executed_indices):
            self.scheduled_actions.pop(i)
        
        if self.is_weapon_changed and self.weapon_change_end_frame > 0:
            if frame >= self.weapon_change_end_frame: self.revert_weapon(frame)
        self.update_max_ammo(frame)
        damage_this_frame = 0
        if frame % 60 == 0:
            for name, dot in list(self.active_dots.items()):
                if frame <= dot['end_frame']:
                    total_mult = dot['multiplier'] * dot.get('count', 1)
                    profile = dot.get('profile')
                    if not profile: profile = DamageProfile.create()
                    
                    dmg, _ = self.calculate_strict_damage(self.BASE_ATK, total_mult, profile, is_full_burst, frame, dot.get('element', 'None'))
                    
                    self.log(f"[Time {frame/60:>5.1f}s] DoT Damage: {name:<25} | Damage: {dmg:10,.0f} | Stacks: {dot.get('count', 1)}")

                    self.total_damage += dmg
                    if name in self.damage_breakdown: self.damage_breakdown[name] += dmg
                    damage_this_frame += dmg
                else: del self.active_dots[name]
        
        d, t = self.process_trigger('stack_count', 0, frame, is_full_burst)
        damage_this_frame += d
        
        if self.part_break_mode and frame % 60 == 0:
            d, t = self.process_trigger('part_break', 0, frame, is_full_burst)
            damage_this_frame += d
            
        d, t = self.process_trigger('time_interval', frame, frame, is_full_burst)
        damage_this_frame += d
        
        d, t = self.process_trigger('variable_interval', frame, frame, is_full_burst)
        damage_this_frame += d
        
        damage_this_frame += self.tick_weapon_action(frame, is_full_burst)
        self.history['frame'].append(frame/60)
        self.history['damage'].append(damage_this_frame)
        self.history['current_ammo'].append(self.current_ammo)
        self.history['max_ammo'].append(self.current_max_ammo)
        self.history['warmup'].append(self.mg_warmup_frames) 
        for char in self.all_burst_chars: self.history[f'ct_{char.name}'].append(char.current_cooldown / 60)

    def run(self):
        self.process_trigger('on_start', 0, 0, False)
        for frame in range(1, self.TOTAL_FRAMES + 1): self.tick(frame)
        return self.damage_breakdown