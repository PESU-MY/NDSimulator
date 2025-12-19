import matplotlib.pyplot as plt
import random
import math

# --- 1. 定数・データ定義 ---

# MGの発射間隔テーブル (射撃回数 -> 必要フレーム)
# 35発目以降は1Fになるように定義
MG_SHOT_TABLE = [
    (1, 24), (2, 13), (3, 10), (4, 8), (5, 7), (6, 6), (7, 5), (8, 5), (9, 4), (10, 4), 
    (11, 4), (12, 3), (13, 3), (14, 3), (15, 3), (16, 3), (17, 3), (18, 2), (19, 2), (20, 2), 
    (21, 2), (22, 2), (23, 2), (24, 2), (25, 2), (26, 2), (27, 2), (28, 2), (29, 2), (30, 2), 
    (31, 2), (32, 2), (33, 2), (34, 2), 
    # 【修正】ここから1Fを追加
    (35, 1)
]

# 累計フレーム(射撃準備除く)から射撃間隔を引くためのマップを作成
MG_WARMUP_MAP = []
current_sum = 0
for idx, interval in MG_SHOT_TABLE:
    MG_WARMUP_MAP.append({'start': current_sum, 'interval': interval})
    current_sum += interval
    
# ウォームアップ最大値 (154F = 射撃準備12F + 射撃累計142F)
# テーブル最後の35発目(1F)に到達するまでの時間
MG_MAX_WARMUP_TIME = 154

class WeaponConfig:
    def __init__(self, name, w_type, multiplier, max_ammo, reload_frames, windup_frames, winddown_frames, charge_time=0):
        self.name = name
        self.type = w_type # "RL", "SR", "MG", "AR", "SMG", "SG"
        self.multiplier = multiplier
        self.max_ammo = max_ammo
        self.base_reload = reload_frames
        self.base_windup = windup_frames
        self.base_winddown = winddown_frames
        self.base_charge_time = charge_time

class DamageProfile:
    @staticmethod
    def create(**kwargs):
        profile = {
            'hit_rate': 1.0, 'core_hit_rate': 0.0, 'crit_rate': 0.15,
            'charge_mult': 1.0,
            'is_weapon_attack': False, 'range_bonus_active': False,
            'is_charge_attack': False, 'is_part_damage': False,
            'is_pierce': False, 'is_ignore_def': False,
            'is_dot': False, 'is_sticky': False, 'is_explosive': False,
            'is_split': False, 'is_elemental': False,
            'burst_buff_enabled': True,
            'force_full_burst': False, 
        }
        profile.update(kwargs)
        return profile

class Skill:
    def __init__(self, name, trigger_type, trigger_value, effect_type, **kwargs):
        self.name = name
        self.trigger_type = trigger_type
        self.trigger_value = trigger_value
        self.effect_type = effect_type
        self.kwargs = kwargs

class BuffManager:
    def __init__(self):
        self.buffs = {}

    def add_buff(self, buff_type, value, duration_frames, current_frame, source=None):
        if buff_type not in self.buffs: self.buffs[buff_type] = []
        
        existing_buff = None
        if source is not None:
            for b in self.buffs[buff_type]:
                if b.get('source') == source:
                    existing_buff = b
                    break
        
        if existing_buff:
            existing_buff['end_frame'] = current_frame + duration_frames
            existing_buff['val'] = value 
        else:
            self.buffs[buff_type].append({
                'val': value, 
                'end_frame': current_frame + duration_frames,
                'source': source
            })

    def get_total_value(self, buff_type, current_frame):
        if buff_type not in self.buffs: return 0.0
        valid_buffs = [b for b in self.buffs[buff_type] if b['end_frame'] >= current_frame]
        self.buffs[buff_type] = valid_buffs
        return sum(b['val'] for b in valid_buffs)
    
    def get_active_buffs(self, buff_type, current_frame):
        if buff_type not in self.buffs: return []
        valid_buffs = [b for b in self.buffs[buff_type] if b['end_frame'] >= current_frame]
        self.buffs[buff_type] = valid_buffs
        return [b['val'] for b in valid_buffs]

class BurstCharacter:
    def __init__(self, name, stage, cooldown_sec, skill=None):
        self.name = name
        self.stage = stage 
        self.base_cooldown = cooldown_sec
        self.current_cooldown = 0 
        self.skill = skill 

# --- 2. シミュレーションエンジン ---

def round_half_up(n):
    return math.floor(n + 0.5)

class NikkeSimulator:
    def __init__(self, weapon_config, skills, burst_rotation):
        self.FPS = 60
        self.TOTAL_FRAMES = 180 * self.FPS
        
        self.BASE_ATK = 21307
        self.ENEMY_DEF = 0 
        
        # 武器設定
        self.weapon = weapon_config
        self.current_max_ammo = self.weapon.max_ammo
        self.current_ammo = self.current_max_ammo
        
        self.skills = skills
        self.buff_manager = BuffManager()
        self.burst_rotation = burst_rotation
        self.burst_indices = [0, 0, 0] 
        self.all_burst_chars = []
        for stage_list in burst_rotation:
            for char in stage_list:
                self.all_burst_chars.append(char)

        # ステート管理
        self.state = "READY"
        self.state_timer = 0
        self.burst_state = "GEN" 
        self.burst_timer = 0
        self.current_action_duration = 0
        
        # MG用ステート
        self.mg_warmup_frames = 0
        self.mg_decay_rate = 154.0 / 68.0 # 68Fで最大(154)から0へ
        
        self.total_shots = 0
        self.total_damage = 0
        self.active_dots = {}
        self.liter_stack_count = 0
        
        self.damage_breakdown = {'Weapon Attack': 0}
        for s in skills:
            if s.effect_type in ['damage', 'dot']:
                self.damage_breakdown[s.name] = 0
        for char in self.all_burst_chars:
            if char.skill and char.skill.effect_type in ['damage', 'dot']:
                self.damage_breakdown[char.skill.name] = 0

        self.history = {'frame': [], 'damage': [], 'current_ammo': [], 'max_ammo': [], 'warmup': []}
        for char in self.all_burst_chars:
            self.history[f'ct_{char.name}'] = []

    def calculate_reduced_frame(self, original_frame, rate_buff, fixed_buff):
        reduction = round_half_up(original_frame * rate_buff + fixed_buff)
        new_frame = max(1, original_frame - reduction)
        return int(new_frame)

    def get_buffed_frames(self, frame_type, original_frame, current_frame):
        rate = self.buff_manager.get_total_value(f'{frame_type}_speed_rate', current_frame)
        fixed = self.buff_manager.get_total_value(f'{frame_type}_speed_fixed', current_frame)
        return self.calculate_reduced_frame(original_frame, rate, fixed)

    def update_max_ammo(self, frame):
        rate_buffs = self.buff_manager.get_active_buffs('max_ammo_rate', frame)
        fixed_buff_sum = self.buff_manager.get_total_value('max_ammo_fixed', frame)
        added_ammo = sum([round_half_up(self.weapon.max_ammo * rate) for rate in rate_buffs])
        self.current_max_ammo = int(self.weapon.max_ammo + added_ammo + fixed_buff_sum)
        if self.current_ammo > self.current_max_ammo:
            self.current_ammo = self.current_max_ammo

    # MGの発射間隔を取得
    def get_mg_interval(self):
        # 射撃準備時間(BaseWindup)を除いた有効射撃時間
        effective_time = max(0, self.mg_warmup_frames - self.weapon.base_windup)
        
        target_interval = 1 # デフォルト最大レート(1F)
        
        # テーブルを走査して現在のwarmup時間に対応するintervalを探す
        # マップは昇順なので、effective_time が start より小さければ、その直前の区間...
        # というより、「この区間より前」なので、ループ内で条件に合致した時点で確定させる
        
        # MG_WARMUP_MAP は [(start=0, int=24), (start=24, int=13), ...]
        # 例: time=10 -> start=24より小さい -> 該当なし(最初の24F区間)
        
        # 逆転の発想: 
        # テーブルの最後の要素から見て、effective_time が start 以上ならその interval
        # これが一番簡単
        
        found = False
        for entry in reversed(MG_WARMUP_MAP):
            if effective_time >= entry['start']:
                target_interval = entry['interval']
                found = True
                break
        
        if not found:
            # テーブルの最初より前（ありえないはずだが）
            target_interval = MG_WARMUP_MAP[0]['interval']
            
        return target_interval

    def calculate_strict_damage(self, base_atk, mult, profile, is_full_burst, frame):
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
            if is_full_burst or profile.get('force_full_burst', False):
                bucket_val += 0.50
        if profile['range_bonus_active']: bucket_val += 0.30
        if random.random() < profile['crit_rate']:
            bucket_val += (0.50 + bm.get_total_value('crit_dmg_buff', frame))
        if random.random() < profile['core_hit_rate']:
            core_buff = bm.get_total_value('core_dmg_buff', frame)
            bucket_val += (1.0 + core_buff)
        layer_crit = bucket_val
        
        layer_charge = 1.0
        if profile['is_charge_attack']:
            charge_ratio_buff = bm.get_total_value('charge_ratio_buff', frame)
            charge_dmg_buff = bm.get_total_value('charge_dmg_buff', frame)
            layer_charge = (profile['charge_mult'] * (1.0 + charge_ratio_buff)) + charge_dmg_buff
            
        bucket_dmg = 1.0
        bucket_dmg += bm.get_total_value('atk_dmg_buff', frame)
        if profile['is_part_damage']: bucket_dmg += bm.get_total_value('part_dmg_buff', frame)
        if profile['is_pierce']: bucket_dmg += bm.get_total_value('pierce_dmg_buff', frame)
        if profile['is_ignore_def']: bucket_dmg += bm.get_total_value('ignore_def_dmg_buff', frame)
        if profile['is_dot']: bucket_dmg += bm.get_total_value('dot_dmg_buff', frame)
        if profile['burst_buff_enabled'] and (is_full_burst or profile.get('force_full_burst', False)):
             bucket_dmg += bm.get_total_value('burst_dmg_buff', frame)
        layer_dmg = bucket_dmg
        
        layer_split = 1.0
        if profile['is_split']: layer_split += bm.get_total_value('split_dmg_buff', frame)
            
        layer_taken = 1.0 + bm.get_total_value('taken_dmg_debuff', frame)
        layer_elem = 1.0 + (bm.get_total_value('elemental_buff', frame) if profile['is_elemental'] else 0)
        
        return layer_atk * layer_weapon * layer_crit * layer_charge * layer_dmg * layer_split * layer_taken * layer_elem

    def apply_skill_effect(self, skill, frame, is_full_burst):
        dmg = 0
        if skill.effect_type == 'buff':
            self.buff_manager.add_buff(skill.kwargs['buff_type'], skill.kwargs['value'], skill.kwargs['duration'] * self.FPS, frame, source=skill.name)
        elif skill.effect_type == 'damage':
            dmg = self.calculate_strict_damage(self.BASE_ATK, skill.kwargs['multiplier'], skill.kwargs['profile'], is_full_burst, frame)
            self.total_damage += dmg
            self.damage_breakdown[skill.name] += dmg
        elif skill.effect_type == 'dot':
            self.active_dots[skill.name] = {'end_frame': frame + (skill.kwargs['duration'] * self.FPS), 'multiplier': skill.kwargs['multiplier'], 'profile': skill.kwargs['profile']}
        elif skill.effect_type == 'ammo_charge':
            charge_amount = skill.kwargs.get('fixed_value', 0)
            if self.current_ammo < self.current_max_ammo:
                self.current_ammo = min(self.current_max_ammo, self.current_ammo + charge_amount)
        return dmg

    def process_trigger(self, trigger_type, val, frame, is_full_burst):
        total_dmg = 0
        triggered_skills = []
        for skill in self.skills:
            if skill.trigger_type == trigger_type:
                is_triggered = False
                if skill.trigger_value <= 0 and trigger_type in ['shot_count', 'time_interval']: is_triggered = False 
                elif trigger_type == 'shot_count' and val > 0 and val % skill.trigger_value == 0: is_triggered = True
                elif trigger_type == 'time_interval' and val % (skill.trigger_value * self.FPS) == 0: is_triggered = True
                elif trigger_type == 'ammo_empty' and val == 0: is_triggered = True
                elif trigger_type == 'on_burst_enter' and trigger_type == trigger_type: is_triggered = True
                elif trigger_type == 'on_start': is_triggered = True
                if is_triggered: triggered_skills.append(skill)
        
        for skill in triggered_skills:
            if skill.effect_type == 'buff': total_dmg += self.apply_skill_effect(skill, frame, is_full_burst)
        for skill in triggered_skills:
            if skill.effect_type != 'buff': total_dmg += self.apply_skill_effect(skill, frame, is_full_burst)
        return total_dmg

    def update_cooldowns(self):
        for char in self.all_burst_chars:
            if char.current_cooldown > 0: char.current_cooldown -= 1

    def tick_burst_state(self, frame):
        is_full_burst = (self.burst_state == "FULL")
        if self.burst_state == "GEN":
            self.burst_timer += 1
            if self.burst_timer >= 5 * self.FPS:
                self.burst_state = "BURST_1"
                self.burst_timer = 0
        elif self.burst_state == "BURST_1":
            char_list = self.burst_rotation[0]
            idx = self.burst_indices[0]
            char = char_list[idx]
            if char.current_cooldown <= 0:
                char.current_cooldown = char.base_cooldown * self.FPS
                if char.skill: self.apply_skill_effect(char.skill, frame, is_full_burst)
                self.burst_indices[0] = (idx + 1) % len(char_list)
                self.burst_state = "BURST_2"
        elif self.burst_state == "BURST_2":
            char_list = self.burst_rotation[1]
            idx = self.burst_indices[1]
            char = char_list[idx]
            if char.current_cooldown <= 0:
                char.current_cooldown = char.base_cooldown * self.FPS
                if char.skill: self.apply_skill_effect(char.skill, frame, is_full_burst)
                self.burst_indices[1] = (idx + 1) % len(char_list)
                self.burst_state = "BURST_3"
        elif self.burst_state == "BURST_3":
            char_list = self.burst_rotation[2]
            idx = self.burst_indices[2]
            char = char_list[idx]
            if char.current_cooldown <= 0:
                char.current_cooldown = char.base_cooldown * self.FPS
                if char.skill: self.apply_skill_effect(char.skill, frame, is_full_burst)
                self.burst_indices[2] = (idx + 1) % len(char_list)
                self.burst_state = "FULL"
                self.burst_timer = 0
                self.liter_stack_count = min(3, self.liter_stack_count + 1)
                reduce_sec = 0.0
                if self.liter_stack_count >= 1: reduce_sec += 2.34
                if self.liter_stack_count >= 2: reduce_sec += 2.70
                if self.liter_stack_count >= 3: reduce_sec += 3.17
                reduce_frames = reduce_sec * self.FPS
                for c in self.all_burst_chars:
                    if c.current_cooldown > 0: c.current_cooldown = max(0, c.current_cooldown - reduce_frames)
                self.process_trigger('on_burst_enter', 0, frame, True)
        elif self.burst_state == "FULL":
            self.burst_timer += 1
            if self.burst_timer >= 10 * self.FPS:
                self.burst_state = "GEN"
                self.burst_timer = 0

    def tick_weapon_action(self, frame, is_full_burst):
        damage_this_frame = 0
        
        # MGのWarmup減衰 (射撃してない場合)
        if self.weapon.type == "MG" and self.state != "SHOOTING" and self.state != "READY": 
            self.mg_warmup_frames -= self.mg_decay_rate
            self.mg_warmup_frames = max(0, self.mg_warmup_frames)

        # === 武器種別ステートマシン ===
        
        # 1. RL / SR
        if self.weapon.type in ["RL", "SR"]:
            if self.state == "READY":
                if self.state_timer == 0:
                    self.current_action_duration = self.get_buffed_frames('attack', self.weapon.base_windup, frame)
                self.state_timer += 1
                if self.state_timer >= self.current_action_duration:
                    self.state = "CHARGING"
                    self.state_timer = 0
            elif self.state == "CHARGING":
                if self.state_timer == 0:
                    self.current_action_duration = self.get_buffed_frames('charge', self.weapon.base_charge_time, frame)
                self.state_timer += 1
                if self.state_timer >= self.current_action_duration:
                    self.state = "SHOOTING"
                    self.state_timer = 0
            elif self.state == "SHOOTING":
                self.total_shots += 1
                self.current_ammo -= 1
                prof = DamageProfile.create(is_weapon_attack=True, range_bonus_active=False, core_hit_rate=1.0, is_charge_attack=True, charge_mult=2.5) 
                dmg = self.calculate_strict_damage(self.BASE_ATK, self.weapon.multiplier, prof, is_full_burst, frame)
                self.total_damage += dmg
                self.damage_breakdown['Weapon Attack'] += dmg
                damage_this_frame += dmg
                damage_this_frame += self.process_trigger('shot_count', self.total_shots, frame, is_full_burst)
                damage_this_frame += self.process_trigger('ammo_empty', self.current_ammo, frame, is_full_burst)
                self.state = "WINDDOWN"
                self.state_timer = 0
            elif self.state == "WINDDOWN":
                if self.state_timer == 0:
                    self.current_action_duration = self.get_buffed_frames('attack', self.weapon.base_winddown, frame)
                self.state_timer += 1
                if self.state_timer >= self.current_action_duration:
                    self.state_timer = 0
                    self.state = "RELOADING" if self.current_ammo <= 0 else "READY"
            elif self.state == "RELOADING":
                if self.state_timer == 0:
                    self.current_action_duration = self.get_buffed_frames('reload', self.weapon.base_reload, frame)
                self.state_timer += 1
                if self.state_timer >= self.current_action_duration:
                    self.current_ammo = self.current_max_ammo
                    self.state = "READY"
                    self.state_timer = 0

        # 2. MG
        elif self.weapon.type == "MG":
            if self.state == "READY":
                if self.state_timer == 0:
                    self.current_action_duration = self.get_buffed_frames('attack', self.weapon.base_windup, frame)
                
                # 準備中もWarmupを加算
                self.mg_warmup_frames += 1
                self.mg_warmup_frames = min(MG_MAX_WARMUP_TIME, self.mg_warmup_frames)

                self.state_timer += 1
                if self.state_timer >= self.current_action_duration:
                    self.state = "SHOOTING"
                    self.state_timer = 0 
            
            elif self.state == "SHOOTING":
                interval = self.get_mg_interval()
                
                if self.state_timer == 0:
                    self.total_shots += 1
                    self.current_ammo -= 1
                    
                    prof = DamageProfile.create(is_weapon_attack=True, range_bonus_active=True, core_hit_rate=1.0)
                    dmg = self.calculate_strict_damage(self.BASE_ATK, self.weapon.multiplier, prof, is_full_burst, frame)
                    self.total_damage += dmg
                    self.damage_breakdown['Weapon Attack'] += dmg
                    damage_this_frame += dmg
                    
                    damage_this_frame += self.process_trigger('shot_count', self.total_shots, frame, is_full_burst)
                    damage_this_frame += self.process_trigger('ammo_empty', self.current_ammo, frame, is_full_burst)
                    
                    # 撃った分の時間をWarmupに加算 (間隔分進む)
                    self.mg_warmup_frames += interval
                    self.mg_warmup_frames = min(MG_MAX_WARMUP_TIME, self.mg_warmup_frames)
                    
                    if self.current_ammo <= 0:
                        self.state = "WINDDOWN"
                        self.state_timer = 0
                    else:
                        self.state_timer = interval - 1 
                        if self.state_timer < 0: self.state_timer = 0
                else:
                    # インターバル待ち
                    self.state_timer -= 1

            elif self.state == "WINDDOWN":
                if self.state_timer == 0:
                    self.current_action_duration = self.get_buffed_frames('attack', self.weapon.base_winddown, frame)
                self.state_timer += 1
                if self.state_timer >= self.current_action_duration:
                    self.state_timer = 0
                    self.state = "RELOADING" 
                
            elif self.state == "RELOADING":
                if self.state_timer == 0:
                    self.current_action_duration = self.get_buffed_frames('reload', self.weapon.base_reload, frame)
                self.state_timer += 1
                if self.state_timer >= self.current_action_duration:
                    self.current_ammo = self.current_max_ammo
                    self.state = "READY"
                    self.state_timer = 0

        # 3. SMG / AR / SG (固定レート)
        else: 
            # 簡易実装
            fire_interval = 3 
            if self.state == "READY":
                if self.state_timer == 0: self.current_action_duration = self.get_buffed_frames('attack', self.weapon.base_windup, frame)
                self.state_timer += 1
                if self.state_timer >= self.current_action_duration: self.state = "SHOOTING"; self.state_timer = 0
            elif self.state == "SHOOTING":
                if self.state_timer == 0:
                    self.total_shots += 1
                    self.current_ammo -= 1
                    prof = DamageProfile.create(is_weapon_attack=True, range_bonus_active=True, core_hit_rate=1.0)
                    dmg = self.calculate_strict_damage(self.BASE_ATK, self.weapon.multiplier, prof, is_full_burst, frame)
                    self.total_damage += dmg
                    self.damage_breakdown['Weapon Attack'] += dmg
                    damage_this_frame += dmg
                    damage_this_frame += self.process_trigger('shot_count', self.total_shots, frame, is_full_burst)
                    damage_this_frame += self.process_trigger('ammo_empty', self.current_ammo, frame, is_full_burst)
                    if self.current_ammo <= 0: self.state = "WINDDOWN"; self.state_timer = 0
                    else: self.state_timer = fire_interval - 1
                else: self.state_timer -= 1
            elif self.state == "WINDDOWN":
                if self.state_timer == 0: self.current_action_duration = self.get_buffed_frames('attack', self.weapon.base_winddown, frame)
                self.state_timer += 1
                if self.state_timer >= self.current_action_duration: self.state_timer=0; self.state = "RELOADING"
            elif self.state == "RELOADING":
                if self.state_timer == 0: self.current_action_duration = self.get_buffed_frames('reload', self.weapon.base_reload, frame)
                self.state_timer += 1
                if self.state_timer >= self.current_action_duration: self.current_ammo = self.current_max_ammo; self.state = "READY"; self.state_timer=0

        return damage_this_frame

    def tick(self, frame):
        self.tick_burst_state(frame)
        self.update_cooldowns()
        self.update_max_ammo(frame)
        
        is_full_burst = (self.burst_state == "FULL")
        damage_this_frame = 0

        # DoT
        if frame % 60 == 0:
            for name, dot in list(self.active_dots.items()):
                if frame <= dot['end_frame']:
                    dmg = self.calculate_strict_damage(self.BASE_ATK, dot['multiplier'], dot['profile'], is_full_burst, frame)
                    self.total_damage += dmg
                    self.damage_breakdown[name] += dmg
                    damage_this_frame += dmg
                else:
                    del self.active_dots[name]

        damage_this_frame += self.process_trigger('time_interval', frame, frame, is_full_burst)
        
        # Weapon Action
        damage_this_frame += self.tick_weapon_action(frame, is_full_burst)

        self.history['frame'].append(frame/60)
        self.history['damage'].append(damage_this_frame)
        self.history['current_ammo'].append(self.current_ammo)
        self.history['max_ammo'].append(self.current_max_ammo)
        self.history['warmup'].append(self.mg_warmup_frames) 
        for char in self.all_burst_chars:
            self.history[f'ct_{char.name}'].append(char.current_cooldown / 60)

    def run(self):
        self.process_trigger('on_start', 0, 0, False)
        for frame in range(1, self.TOTAL_FRAMES + 1):
            self.tick(frame)
        self.plot_results()
        return self.damage_breakdown

    def plot_results(self):
        fig, (ax1, ax2, ax3, ax4) = plt.subplots(4, 1, figsize=(10, 12), sharex=True)
        ax1.plot(self.history['frame'], self.history['damage'], color='blue', linewidth=0.3, alpha=0.5)
        ax1.set_title('Damage History')
        
        ax2.plot(self.history['frame'], self.history['max_ammo'], color='green', linestyle='--')
        ax2.plot(self.history['frame'], self.history['current_ammo'], color='orange')
        ax2.set_title('Ammo History')
        
        for char in self.all_burst_chars:
            ax3.plot(self.history['frame'], self.history[f'ct_{char.name}'], label=f'{char.name}')
        ax3.set_title('Burst CT')
        ax3.legend()
        
        if self.weapon.type == "MG":
            ax4.plot(self.history['frame'], self.history['warmup'], color='purple')
            ax4.set_title('MG Warmup State')
            ax4.set_ylabel('Warmup Frames')
        
        plt.tight_layout()
        plt.show()

# --- 実行 ---

# 1. 武器設定 (MG)
mg_config = WeaponConfig(
    name="Machine Gun",
    w_type="MG",
    multiplier=0.0557, # 5.57%
    max_ammo=300,
    reload_frames=150,
    windup_frames=12,
    winddown_frames=10
)

# 2. バースト設定
liter_skill = Skill("Liter Burst", "manual", 0, "buff",
    buff_type='atk_buff_rate', value=0.66, duration=5)
b1_liter = BurstCharacter("Liter", 1, 20, liter_skill)
b2_char = BurstCharacter("B2", 2, 20, None)
b3_a = BurstCharacter("B3_A", 3, 40, None)
b3_b = BurstCharacter("B3_B", 3, 40, None)
burst_rotation = [ [b1_liter], [b2_char], [b3_a, b3_b] ]

# 3. その他のスキル
s_atk_passive = Skill("Passive ATK", "on_start", 0, "buff",
    buff_type='atk_buff_rate', value=0.20, duration=999999)

# 実行
sim = NikkeSimulator(mg_config, [s_atk_passive], burst_rotation)
breakdown = sim.run()

print("【MGシミュレーション結果】")
print(f"総発射回数: {sim.total_shots}回")
for name, val in breakdown.items():
    print(f"{name.ljust(25)}: {val:12,.0f}")