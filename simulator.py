import json
import math
import random
import matplotlib.pyplot as plt

def round_half_up(n):
    return math.floor(n + 0.5)

# --- 1. データ定義 ---

class WeaponConfig:
    def __init__(self, data):
        self.name = data.get('name', 'Unknown Weapon')
        self.type = data.get('type', 'RAPID')
        self.weapon_class = data.get('weapon_class', 'AR')
        self.element = data.get('element', 'Iron')
        self.multiplier = data.get('multiplier', 1.0)
        self.max_ammo = data.get('max_ammo', 60)
        self.reload_frames = data.get('reload_frames', 60)
        self.windup_frames = data.get('windup_frames', 12)
        self.winddown_frames = data.get('winddown_frames', 10)
        
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
        self.fire_interval = data.get('fire_interval', 5)
        self.mg_warmup_map = []
        self.mg_max_warmup = 0
        if self.type == "MG" and 'warmup_table' in data:
            current_sum = 0
            for idx, interval in data['warmup_table']:
                self.mg_warmup_map.append({'start': current_sum, 'interval': interval})
                current_sum += interval
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
            'enable_core_hit': False  # 追加: スキルで明示的にコアヒットさせたい場合のフラグ
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
        self.current_usage_count = 0
        self.owner_name = None

class BuffManager:
    def __init__(self):
        self.buffs = {}
        self.active_stacks = {}

    def add_buff(self, buff_type, value, duration_frames, current_frame, source=None, stack_name=None, max_stack=1, tag=None, shot_duration=0, remove_on_reload=False):
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
                stack_data['count'] = min(stack_data['max_stack'], stack_data['count'] + 1)
                stack_data['end_frame'] = current_frame + duration_frames
                stack_data['unit_value'] = value 
                stack_data['tag'] = tag
                stack_data['shot_life'] = shot_duration
                stack_data['remove_on_reload'] = remove_on_reload
                return stack_data['count']
            else:
                self.active_stacks[stack_name] = {
                    'count': 1, 'max_stack': max_stack, 'buff_type': buff_type,
                    'unit_value': value, 'end_frame': current_frame + duration_frames,
                    'tag': tag,
                    'shot_life': shot_duration,
                    'remove_on_reload': remove_on_reload
                }
                return 1
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
    def __init__(self, weapon_config, skills, burst_rotation, base_atk, base_hp=1000000, enemy_element="None", enemy_core_size=3.0, enemy_size=5.0, part_break_mode=False, character_name="Main"):
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
        
        self.weapon = weapon_config
        self.original_weapon = weapon_config 
        self.is_weapon_changed = False
        self.weapon_change_end_frame = 0 
        self.weapon_change_ammo_specified = False
        
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

    def check_target_condition(self, condition, frame):
        if not condition: return True
        my_name = self.character_name
        my_element = self.weapon.element if hasattr(self.weapon, 'element') else 'Iron'
        my_weapon = self.weapon.weapon_class
        my_atk = self.BASE_ATK
        cond_type = condition.get('type')
        cond_value = condition.get('value')
        if cond_type == "element":
            if my_element != cond_value: return False
        elif cond_type == "weapon_type":
            if my_weapon != cond_value: return False
        elif cond_type == "highest_atk":
            target_count = condition.get('count', 1)
            all_chars = []
            all_chars.append((my_name, my_atk))
            for char in self.all_burst_chars:
                if char.name != my_name:
                    all_chars.append((char.name, char.base_atk))
            all_chars.sort(key=lambda x: x[1], reverse=True)
            top_n_names = [c[0] for c in all_chars[:target_count]]
            if my_name not in top_n_names: return False
        elif cond_type == "used_burst":
            found = False
            for char in self.all_burst_chars:
                if char.name == my_name:
                    if char.has_used_burst: found = True
                    break
            if not found: return False
        return True

    def calculate_reduced_frame(self, original_frame, rate_buff, fixed_buff):
        reduction = round_half_up(original_frame * rate_buff + fixed_buff)
        new_frame = max(1, original_frame - reduction)
        return int(new_frame)

    def get_buffed_frames(self, frame_type, original_frame, current_frame):
        if frame_type == 'reload' and self.weapon.disable_reload_buffs: return int(original_frame)
        if frame_type == 'charge' and self.weapon.disable_charge_buffs: return int(original_frame)
        if frame_type == 'attack' and self.weapon.disable_attack_speed_buffs: return int(original_frame)
        
        rate = self.buff_manager.get_total_value(f'{frame_type}_speed_rate', current_frame)
        rate = min(rate, 1.0)
        
        fixed = self.buff_manager.get_total_value(f'{frame_type}_speed_fixed', current_frame)
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
        final_atk = (base_atk * (1.0 + atk_rate)) + atk_fixed
        
        def_debuff = bm.get_total_value('def_debuff', frame)
        current_def = 0 if profile['is_ignore_def'] else self.ENEMY_DEF
        effective_def = current_def * (1.0 - def_debuff)
        raw_damage_diff = final_atk - effective_def
        if raw_damage_diff <= 0: return 1.0
        
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
        
        # --- 変更: コアヒット判定条件の厳格化 ---
        # 通常攻撃、または明示的に許可されたスキルのみコアヒット判定を行う
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
        # ------------------------------------

        is_hit = random.random() < hit_prob
        if not is_hit: return 0.0
        
        if is_core:
            core_dmg_buff = bm.get_total_value('core_dmg_buff', frame)
            bucket_val += 1.0 + core_dmg_buff
            
        crit_rate = profile['crit_rate'] + bm.get_total_value('crit_rate_buff', frame)
        if random.random() < crit_rate:
            bucket_val += (0.50 + bm.get_total_value('crit_dmg_buff', frame))
            
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
        layer_dmg = bucket_dmg
        
        layer_split = 1.0
        if profile['is_split']: layer_split += bm.get_total_value('split_dmg_buff', frame)
        
        layer_taken = 1.0 + bm.get_total_value('taken_dmg_debuff', frame)
        
        layer_elem = 1.0
        advantage_map = {
            "Iron": "Electric", "Electric": "Water", "Water": "Fire", "Fire": "Wind", "Wind": "Iron"
        }
        if advantage_map.get(attacker_element) == self.enemy_element:
            elem_buff = bm.get_total_value('elemental_buff', frame)
            layer_elem += 0.10 + elem_buff
            
        return layer_atk * layer_weapon * layer_crit * layer_charge * layer_dmg * layer_split * layer_taken * layer_elem

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
        return True

    def apply_skill_effect(self, skill, frame, is_full_burst, attacker_element="None"):
        if not self.should_apply_skill(skill, frame): return 0
        if skill.target == 'allies' and skill.target_condition:
            if not self.check_target_condition(skill.target_condition, frame): return 0

        for tag in skill.remove_tags:
            self.buff_manager.remove_buffs_by_tag(tag, frame)

        dmg = 0
        
        if skill.effect_type == 'convert_hp_to_atk':
            rate = skill.kwargs.get('value', 0)
            max_hp_rate = self.buff_manager.get_total_value('max_hp_rate', frame)
            current_max_hp = self.BASE_HP * (1.0 + max_hp_rate)
            atk_increase = current_max_hp * rate
            self.buff_manager.add_buff('atk_buff_fixed', atk_increase, skill.kwargs['duration'] * self.FPS, frame, source=skill.name)
            return 0
        
        if skill.effect_type == 'cumulative_stages':
            if skill.kwargs.get('trigger_all_stages'):
                for stage_data in skill.stages:
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
                            name=f"{skill.name}_Stage", 
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
                        name="StageEffect", 
                        trigger_type="manual", 
                        trigger_value=0,
                        effect_type=stage_data.get('effect_type', 'buff'), 
                        **init_kwargs
                    )
                    temp_skill.target = skill.target
                    temp_skill.owner_name = skill.owner_name
                    dmg += self.apply_skill_effect(temp_skill, frame, is_full_burst, attacker_element)
        
        elif skill.effect_type == 'stack_buff':
            stack_name = skill.kwargs.get('stack_name', skill.name)
            max_stack = skill.kwargs.get('max_stack', 1)
            tag = skill.kwargs.get('tag')
            self.buff_manager.add_buff(skill.kwargs['buff_type'], skill.kwargs['value'], skill.kwargs['duration'] * self.FPS, frame, source=skill.name, stack_name=stack_name, max_stack=max_stack, tag=tag, shot_duration=skill.kwargs.get('shot_duration', 0), remove_on_reload=skill.kwargs.get('remove_on_reload', False))

        elif skill.effect_type == 'stack_dot':
            stack_name = skill.kwargs.get('stack_name', skill.name)
            max_stack = skill.kwargs.get('max_stack', 1)
            raw_profile = skill.kwargs.get('profile', {})
            full_profile = DamageProfile.create(**raw_profile)
            
            if stack_name in self.active_dots:
                dot = self.active_dots[stack_name]
                dot['count'] = min(max_stack, dot['count'] + 1)
                dot['end_frame'] = frame + (skill.kwargs['duration'] * self.FPS)
                dot['profile'] = full_profile
            else:
                self.active_dots[stack_name] = {
                    'end_frame': frame + (skill.kwargs['duration'] * self.FPS),
                    'multiplier': skill.kwargs['multiplier'], 
                    'profile': full_profile,
                    'count': 1, 'max_stack': max_stack, 'element': attacker_element
                }

        elif skill.effect_type == 'buff':
            tag = skill.kwargs.get('tag')
            self.buff_manager.add_buff(skill.kwargs['buff_type'], skill.kwargs['value'], skill.kwargs['duration'] * self.FPS, frame, source=skill.name, tag=tag, shot_duration=skill.kwargs.get('shot_duration', 0), remove_on_reload=skill.kwargs.get('remove_on_reload', False))
        
        elif skill.effect_type == 'damage':
            raw_profile = skill.kwargs.get('profile', {})
            full_profile = DamageProfile.create(**raw_profile)
            
            loop_count = skill.kwargs.get('loop_count', 1)
            
            if skill.kwargs.get('copy_stack_count'):
                stack_name = skill.kwargs.get('copy_stack_count')
                current_stack = self.buff_manager.get_stack_count(stack_name, frame)
                loop_count = current_stack
                
            for _ in range(loop_count):
                dmg_val = self.calculate_strict_damage(self.BASE_ATK, skill.kwargs['multiplier'], full_profile, is_full_burst, frame, attacker_element)
                dmg += dmg_val
                
            print(f"[Skill] 時間:{frame/60:>6.2f}s | 名前:{skill.name:<25} | Dmg:{dmg:10,.0f} | Hits:{loop_count}")
            
            self.total_damage += dmg
            if skill.name in self.damage_breakdown: self.damage_breakdown[skill.name] += dmg
        
        elif skill.effect_type == 'dot':
            raw_profile = skill.kwargs.get('profile', {})
            full_profile = DamageProfile.create(**raw_profile)
            self.active_dots[skill.name] = {
                'end_frame': frame + (skill.kwargs['duration'] * self.FPS),
                'multiplier': skill.kwargs['multiplier'], 
                'profile': full_profile,
                'count': 1, 'max_stack': 1, 'element': attacker_element
            }

        elif skill.effect_type == 'ammo_charge':
            charge_amount = skill.kwargs.get('fixed_value', 0)
            if self.current_ammo < self.current_max_ammo:
                self.current_ammo = min(self.current_max_ammo, self.current_ammo + charge_amount)
        elif skill.effect_type == 'weapon_change':
            new_weapon_data = skill.kwargs.get('weapon_data')
            duration = skill.kwargs.get('duration', 0)
            if new_weapon_data:
                self.is_weapon_changed = True
                self.weapon_change_ammo_specified = 'max_ammo' in new_weapon_data
                self.weapon = WeaponConfig(new_weapon_data)
                if self.weapon_change_ammo_specified:
                    self.current_max_ammo = self.weapon.max_ammo 
                    self.current_ammo = self.current_max_ammo
                if duration > 0: self.weapon_change_end_frame = frame + (duration * self.FPS)
                else: self.weapon_change_end_frame = 0
                self.state = "READY"; self.state_timer = 0
        elif skill.effect_type == 'cooldown_reduction':
            reduce_sec = skill.kwargs.get('value', 0)
            reduce_frames = reduce_sec * self.FPS
            for char in self.all_burst_chars:
                if char.current_cooldown > 0: char.current_cooldown = max(0, char.current_cooldown - reduce_frames)
        return dmg

    def revert_weapon(self, frame):
        if not self.is_weapon_changed: return
        self.weapon = self.original_weapon
        self.is_weapon_changed = False
        self.weapon_change_end_frame = 0
        if self.weapon_change_ammo_specified:
            self.update_max_ammo(frame)
            self.current_ammo = self.current_max_ammo
        else:
            self.update_max_ammo(frame)
            if self.current_ammo > self.current_max_ammo: self.current_ammo = self.current_max_ammo
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
                elif skill.trigger_value <= 0 and trigger_type in ['shot_count', 'time_interval', 'pellet_hit']: is_triggered = False 
                elif trigger_type == 'shot_count' and val > 0 and val % skill.trigger_value == 0: is_triggered = True
                elif trigger_type == 'time_interval' and val % (skill.trigger_value * self.FPS) == 0: is_triggered = True
                elif trigger_type == 'ammo_empty' and val == 0: is_triggered = True
                elif trigger_type == 'on_burst_enter': is_triggered = True
                elif trigger_type == 'on_burst_3_enter': is_triggered = True
                elif trigger_type == 'on_start': is_triggered = True
                elif trigger_type == 'pellet_hit' and val >= skill.trigger_value: is_triggered = True 
                
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
            if self.burst_timer >= 10 * self.FPS: self.burst_state = "GEN"; self.burst_timer = 0

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
            
            current_pellets = base_pellets + pellet_add
            if pellet_fixed > 0:
                current_pellets = pellet_fixed
            
            self.cumulative_pellet_hits += current_pellets
            
            dmg = self.calculate_strict_damage(self.BASE_ATK, self.weapon.multiplier, prof, is_full_burst, frame, self.weapon.element)
            
            buff_debug_str = self.buff_manager.get_active_buffs_debug(frame)
            
            print(f"[Shoot] 時間:{frame/60:>6.2f}s | 弾数:{self.current_ammo:>3}/{self.current_max_ammo:<3} | ペレット:{current_pellets:>2} | Dmg:{dmg:10,.0f} | Buffs: {buff_debug_str}")

            self.total_damage += dmg
            self.damage_breakdown['Weapon Attack'] += dmg
            damage_this_frame += dmg
            
            self.buff_manager.decrement_shot_buffs()
            
            d, t1 = self.process_trigger('shot_count', self.total_shots, frame, is_full_burst)
            damage_this_frame += d
            d, t2 = self.process_trigger('ammo_empty', self.current_ammo, frame, is_full_burst)
            damage_this_frame += d
            d, t3 = self.process_trigger('pellet_hit', self.cumulative_pellet_hits, frame, is_full_burst)
            damage_this_frame += d
            if t3:
                self.cumulative_pellet_hits = 0 
            

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
                
                if self.state_timer == 0:
                    perform_shoot()
                    self.mg_warmup_frames = min(self.weapon.mg_max_warmup, self.mg_warmup_frames + buffed_interval)
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
                if self.state_timer == 0: self.current_action_duration = self.get_buffed_frames('reload', self.weapon.reload_frames, frame)
                self.state_timer += 1
                if self.state_timer >= self.current_action_duration: 
                    self.current_ammo = self.current_max_ammo; self.state = "READY"; self.state_timer = 0
                    self.buff_manager.remove_reload_buffs()

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
        if self.is_weapon_changed and self.weapon_change_end_frame > 0:
            if frame >= self.weapon_change_end_frame: self.revert_weapon(frame)
        self.update_max_ammo(frame)
        is_full_burst = (self.burst_state == "FULL")
        damage_this_frame = 0
        if frame % 60 == 0:
            for name, dot in list(self.active_dots.items()):
                if frame <= dot['end_frame']:
                    total_mult = dot['multiplier'] * dot.get('count', 1)
                    profile = dot.get('profile')
                    if not profile: profile = DamageProfile.create()
                    
                    dmg = self.calculate_strict_damage(self.BASE_ATK, total_mult, profile, is_full_burst, frame, dot.get('element', 'None'))
                    
                    print(f"[Time {frame/60:>5.1f}s] DoT Damage: {name:<25} | Damage: {dmg:10,.0f} | Stacks: {dot.get('count', 1)}")

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