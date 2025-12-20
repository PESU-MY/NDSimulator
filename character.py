import random
from utils import round_half_up
from models import DamageProfile, Skill
from buff_manager import BuffManager

# --- キャラクタークラス ---

class Character:
    def __init__(self, name, weapon_config, skills, base_atk, base_hp, element, burst_stage, character_class="Attacker", is_dummy=False):
        self.name = name
        self.weapon = weapon_config
        
        # ▼▼▼ 修正箇所: ここで self.skills を先に定義します ▼▼▼
        self.skills = skills 
        for s in self.skills:
            if not s.owner_name: s.owner_name = self.name
        # ▲▲▲▲▲▲
            
        self.base_atk = base_atk
        self.base_hp = base_hp
        self.element = element
        self.burst_stage = str(burst_stage)
        self.character_class = character_class
        
        self.is_dummy = is_dummy

        self.buff_manager = BuffManager()
        
        # 追加: engine.pyで属性エラーにならないよう初期化
        self.skill = None 
        # もしバーストスキルがskillsに含まれているなら、それをself.skillに割り当てる簡易対応
        for s in self.skills:
            if s.trigger_type == 'on_use_burst_skill' and s.name.find('Burst') != -1:
                self.skill = s
        
        self.state = "READY"
        self.state_timer = 0
        self.current_ammo = self.weapon.max_ammo
        self.current_max_ammo = self.weapon.max_ammo
        self.current_cooldown = 0
        self.current_action_duration = 0
        
        self.mg_warmup_frames = 0
        self.mg_decay_rate = self.weapon.mg_max_warmup / 68.0 if self.weapon.type == "MG" else 0
        
        self.total_damage = 0
        self.total_shots = 0
        self.cumulative_pellet_hits = 0 
        self.cumulative_crit_hits = 0 
        self.damage_breakdown = {'Weapon Attack': 0}
        
        self.active_dots = {}
        self.special_flags = set()
        
        def register_breakdown(skill_obj):
            if skill_obj.effect_type in ['damage', 'dot']:
                self.damage_breakdown[skill_obj.name] = 0
            if skill_obj.effect_type == 'cumulative_stages':
                for stage in skill_obj.stages:
                    if isinstance(stage, Skill): register_breakdown(stage)
        for s in self.skills: register_breakdown(s)
        
        self.original_weapon = self.weapon
        self.is_weapon_changed = False
        self.weapon_change_end_frame = 0
        self.weapon_change_ammo_specified = False

    def get_current_atk(self, frame):
        atk_rate = self.buff_manager.get_total_value('atk_buff_rate', frame)
        atk_fixed = self.buff_manager.get_total_value('atk_buff_fixed', frame)
        hp_conv_rate = self.buff_manager.get_total_value('conversion_hp_to_atk', frame)
        if hp_conv_rate > 0:
            max_hp_rate = self.buff_manager.get_total_value('max_hp_rate', frame)
            current_max_hp = self.base_hp * (1.0 + max_hp_rate)
            atk_fixed += current_max_hp * hp_conv_rate
        return (self.base_atk * (1.0 + atk_rate)) + atk_fixed

    # 修正: calculate_strict_damage に debuff_manager 引数を追加 (前回の提案通り)
    def calculate_strict_damage(self, mult, profile, is_full_burst, frame, enemy_def=0, enemy_element="None", enemy_core_size=3.0, enemy_size=5.0, debuff_manager=None):
        final_atk = self.get_current_atk(frame)
        
        def_debuff = self.buff_manager.get_total_value('def_debuff', frame)
        if debuff_manager:
            def_debuff += debuff_manager.get_total_value('def_debuff', frame)
            
        effective_def = enemy_def * (1.0 - def_debuff) if not profile['is_ignore_def'] else 0
        raw_damage_diff = final_atk - effective_def
        if raw_damage_diff <= 0: return 1.0, False
        layer_atk = raw_damage_diff
        
        weapon_buff = self.buff_manager.get_total_value('weapon_dmg_buff', frame) if profile['is_weapon_attack'] else 0.0
        layer_weapon = mult * (1.0 + weapon_buff)
        
        bucket_val = 1.0
        if profile['burst_buff_enabled']:
            if is_full_burst or profile.get('force_full_burst', False): bucket_val += 0.50
        if profile['range_bonus_active']: bucket_val += 0.30
        
        base_hit_size = self.weapon.hit_size
        hit_rate_buff = self.buff_manager.get_total_value('hit_rate_buff', frame)
        current_hit_size = max(0.01, base_hit_size * (1.0 - hit_rate_buff))
        
        hit_prob = min(1.0, (enemy_size / current_hit_size) ** 2)
        
        can_core_hit = profile.get('is_weapon_attack', False) or profile.get('enable_core_hit', False)
        is_core = False
        if can_core_hit:
            fixed_core_rate = self.buff_manager.get_total_value('core_hit_rate_fixed', frame)
            if fixed_core_rate > 0: core_prob = 1.0
            else: core_prob = min(1.0, (enemy_core_size / current_hit_size) ** 2)
            if core_prob > hit_prob: core_prob = hit_prob
            is_core = random.random() < (core_prob / hit_prob)

        is_hit = random.random() < hit_prob
        if not is_hit: return 0.0, False
        
        if is_core:
            core_dmg_buff = self.buff_manager.get_total_value('core_dmg_buff', frame)
            bucket_val += 1.0 + core_dmg_buff
            
        crit_rate = profile['crit_rate'] + self.buff_manager.get_total_value('crit_rate_buff', frame)
        is_crit_hit = False
        if random.random() < crit_rate:
            bucket_val += (0.50 + self.buff_manager.get_total_value('crit_dmg_buff', frame))
            is_crit_hit = True
        layer_crit = bucket_val
        
        layer_charge = 1.0
        if profile['is_charge_attack']:
            charge_ratio_buff = self.buff_manager.get_total_value('charge_ratio_buff', frame)
            charge_dmg_buff = self.buff_manager.get_total_value('charge_dmg_buff', frame)
            layer_charge = (profile['charge_mult'] * (1.0 + charge_ratio_buff)) + charge_dmg_buff
            
        bucket_dmg = 1.0
        bucket_dmg += self.buff_manager.get_total_value('atk_dmg_buff', frame)
        if profile['is_part_damage']: bucket_dmg += self.buff_manager.get_total_value('part_dmg_buff', frame)
        
        is_pierce_buff = self.buff_manager.get_total_value('is_pierce', frame)
        if profile['is_pierce'] or is_pierce_buff > 0: 
            bucket_dmg += self.buff_manager.get_total_value('pierce_dmg_buff', frame)
            
        if profile['is_ignore_def']: bucket_dmg += self.buff_manager.get_total_value('ignore_def_dmg_buff', frame)
        if profile['is_dot']: bucket_dmg += self.buff_manager.get_total_value('dot_dmg_buff', frame)
        if profile['burst_buff_enabled'] and (is_full_burst or profile.get('force_full_burst', False)):
             bucket_dmg += self.buff_manager.get_total_value('burst_dmg_buff', frame)
        
        # 被ダメージデバフの合算
        taken_dmg_val = self.buff_manager.get_total_value('taken_dmg_debuff', frame)
        if debuff_manager:
            taken_dmg_val += debuff_manager.get_total_value('taken_dmg_debuff', frame)
        layer_taken = 1.0 + taken_dmg_val

        layer_dmg = bucket_dmg
        
        layer_split = 1.0
        if profile['is_split']: layer_split += self.buff_manager.get_total_value('split_dmg_buff', frame)
        
        layer_elem = 1.0
        advantage_map = { "Iron": "Electric", "Electric": "Water", "Water": "Fire", "Fire": "Wind", "Wind": "Iron" }
        if advantage_map.get(self.element) == enemy_element:
            elem_buff = self.buff_manager.get_total_value('elemental_buff', frame)
            layer_elem += 0.10 + elem_buff
            
        return layer_atk * layer_weapon * layer_crit * layer_charge * layer_dmg * layer_split * layer_taken * layer_elem, is_crit_hit

    def calculate_reduced_frame(self, original_frame, rate_buff, fixed_buff):
        if rate_buff <= -1.0: return 9999
        new_frame = original_frame / (1.0 + rate_buff)
        new_frame -= fixed_buff
        return max(1, int(new_frame))

    def get_buffed_frames(self, frame_type, original_frame, frame):
        if frame_type == 'reload':
            fixed_val = self.buff_manager.get_total_value('reload_speed_fixed_value', frame)
            if fixed_val > 0: return int(original_frame / (1.0 + fixed_val))
            if self.weapon.disable_reload_buffs: return int(original_frame)
        if frame_type == 'charge' and self.weapon.disable_charge_buffs: return int(original_frame)
        if frame_type == 'attack' and self.weapon.disable_attack_speed_buffs: return int(original_frame)
        
        rate = self.buff_manager.get_total_value(f'{frame_type}_speed_rate', frame)
        if rate <= -1.0: rate = -0.99
        fixed = self.buff_manager.get_total_value(f'{frame_type}_speed_fixed', frame)
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
            if self.current_ammo > self.current_max_ammo: self.current_ammo = self.current_max_ammo
        self.state = "READY"; self.state_timer = 0

    def process_trigger(self, trigger_type, val, frame, is_full_burst, simulator):
        triggered_skills = []
        for skill in self.skills:
            # --- 追加: 同一フレームでの多重発動チェック ---
            if skill.last_used_frame == frame:
                continue
            # ----------------------------------------
            if skill.trigger_type == trigger_type:
                is_triggered = False
                if trigger_type == 'on_use_burst_skill': is_triggered = True 
                elif trigger_type == 'stack_count':
                    target_stack = skill.kwargs.get('stack_name')
                    current_count = self.buff_manager.get_stack_count(target_stack, frame)
                    if current_count >= skill.trigger_value: is_triggered = True
                elif trigger_type == 'part_break': is_triggered = True
                elif skill.trigger_value <= 0 and trigger_type in ['shot_count', 'time_interval', 'pellet_hit', 'critical_hit']: is_triggered = False 
                elif trigger_type == 'shot_count' and val > 0 and val % skill.trigger_value == 0: is_triggered = True
                elif trigger_type == 'time_interval' and val % (skill.trigger_value * simulator.FPS) == 0: is_triggered = True
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
                        if interval and val % interval == 0: is_triggered = True
                
                if is_triggered and 'probability' in skill.kwargs:
                    prob = skill.kwargs['probability']
                    if random.random() * 100 > prob: is_triggered = False

                if is_triggered:
                    triggered_skills.append(skill)
        
        total_dmg = 0
        for skill in triggered_skills:
            # 発動記録を更新
            skill.last_used_frame = frame
            total_dmg += simulator.apply_skill(skill, self, frame, is_full_burst)
        
        return total_dmg

    def tick_action(self, frame, is_full_burst, simulator):
        if self.is_dummy: return 0  # ダミーキャラは行動計算しない
        
        damage_this_frame = 0
        if self.weapon.type == "MG" and self.state != "SHOOTING" and self.state != "READY": 
            self.mg_warmup_frames -= self.mg_decay_rate
            self.mg_warmup_frames = max(0, self.mg_warmup_frames)

        def perform_shoot():
            nonlocal damage_this_frame
            self.total_shots += 1
            self.current_ammo -= 1
            
            force_fb = getattr(self.weapon, 'force_full_burst', False)
            if isinstance(self.weapon, dict): force_fb = self.weapon.get('force_full_burst', False)
            
            prof = DamageProfile.create(
                is_weapon_attack=True, 
                is_charge_attack=(self.weapon.type in ["RL", "SR", "CHARGE"]), 
                charge_mult=self.weapon.charge_mult if self.weapon.type in ["RL", "SR", "CHARGE"] else 1.0, 
                force_full_burst=force_fb, is_pierce=self.weapon.is_pierce
            )
            base_pellets = 10 if self.weapon.weapon_class == "SG" else 1
            pellet_add = self.buff_manager.get_total_value('pellet_count_add', frame)
            pellet_fixed = self.buff_manager.get_total_value('pellet_count_fixed', frame)
            base_pellets_from_config = getattr(self.weapon, 'pellet_count', 1)
            current_pellets = base_pellets_from_config + pellet_add
            if pellet_fixed > 0: current_pellets = pellet_fixed
            current_pellets = int(max(1, current_pellets))
            per_pellet_multiplier = self.weapon.multiplier / current_pellets

            total_shot_dmg = 0
            hit_count = 0
            crit_count = 0
            
            for _ in range(current_pellets):
                dmg, is_crit = self.calculate_strict_damage(
                    per_pellet_multiplier, prof, is_full_burst, frame, 
                    enemy_def=simulator.ENEMY_DEF, enemy_element=simulator.enemy_element,
                    enemy_core_size=simulator.enemy_core_size, enemy_size=simulator.enemy_size,
                    debuff_manager=simulator.enemy_debuffs 
                )
                total_shot_dmg += dmg
                if dmg > 0: hit_count += 1
                if is_crit: crit_count += 1
            
            self.cumulative_pellet_hits += hit_count
            self.cumulative_crit_hits += crit_count
            
            self.total_damage += total_shot_dmg
            self.damage_breakdown['Weapon Attack'] += total_shot_dmg
            damage_this_frame += total_shot_dmg
            
            self.buff_manager.decrement_shot_buffs()
            
            # --- ログ出力（詳細） ---
            buff_debug_str = self.buff_manager.get_active_buffs_debug(frame)
            simulator.log(f"[Shoot] 時間:{frame/60:>6.2f}s | 弾数:{self.current_ammo:>3}/{self.current_max_ammo:<3} | Dmg:{total_shot_dmg:10,.0f} | Buffs: {buff_debug_str}", target_name=self.name)
            # ---------------------

            damage_this_frame += self.process_trigger('shot_count', self.total_shots, frame, is_full_burst, simulator)
            damage_this_frame += self.process_trigger('ammo_empty', self.current_ammo, frame, is_full_burst, simulator)
            damage_this_frame += self.process_trigger('pellet_hit', self.cumulative_pellet_hits, frame, is_full_burst, simulator)
            damage_this_frame += self.process_trigger('critical_hit', self.cumulative_crit_hits, frame, is_full_burst, simulator)
            
            if self.cumulative_pellet_hits >= 9999: self.cumulative_pellet_hits = 0 

        if self.weapon.type in ["RL", "SR", "CHARGE"]:
            # --- RL/SR のロジック修正 ---
            if self.state == "READY":
                if self.state_timer == 0:
                    # windup_frames を正しく取得
                    self.current_action_duration = self.get_buffed_frames('attack', self.weapon.windup_frames, frame)
                
                self.state_timer += 1
                if self.state_timer >= self.current_action_duration:
                    self.state = "CHARGING"
                    self.state_timer = 0
                    
            elif self.state == "CHARGING":
                if self.state_timer == 0:
                    # charge_time が 0 の場合の安全策 (最低1フレーム)
                    base_frames = max(1, self.weapon.charge_time * simulator.FPS)
                    self.current_action_duration = self.get_buffed_frames('charge', base_frames, frame)
                    
                self.state_timer += 1
                if self.state_timer >= self.current_action_duration:
                    self.state = "SHOOTING"
                    self.state_timer = 0
                    
            elif self.state == "SHOOTING":
                # 発射処理
                perform_shoot()
                self.state = "WINDDOWN"
                self.state_timer = 0
                
            elif self.state == "WINDDOWN":
                if self.state_timer == 0:
                    self.current_action_duration = self.get_buffed_frames('attack', self.weapon.winddown_frames, frame)
                
                self.state_timer += 1
                if self.state_timer >= self.current_action_duration:
                    self.state_timer = 0
                    if self.is_weapon_changed and self.current_ammo <= 0:
                        self.revert_weapon(frame)
                    else:
                        self.state = "RELOADING" if self.current_ammo <= 0 else "READY"
                        
            elif self.state == "RELOADING":
                if self.state_timer == 0:
                    self.current_action_duration = self.get_buffed_frames('reload', self.weapon.reload_frames, frame)
                    simulator.log(f"[Action] Reloading... ({self.current_action_duration} frames)", target_name=self.name)
                
                self.state_timer += 1
                if self.state_timer >= self.current_action_duration:
                    self.current_ammo = self.current_max_ammo
                    self.state = "READY"
                    self.state_timer = 0
                    self.buff_manager.remove_reload_buffs()
                    simulator.log(f"[Action] Reload Complete. Ammo: {self.current_ammo}", target_name=self.name)

        elif self.weapon.type == "MG":
            if self.state == "READY":
                if self.state_timer == 0: self.current_action_duration = self.get_buffed_frames('attack', self.weapon.windup_frames, frame)
                self.mg_warmup_frames = min(self.weapon.mg_max_warmup, self.mg_warmup_frames + 1)
                self.state_timer += 1
                if self.state_timer >= self.current_action_duration: 
                    self.state = "SHOOTING"; self.state_timer = 0 
                    if self.mg_warmup_frames < self.weapon.windup_frames: self.mg_warmup_frames = self.weapon.windup_frames
            elif self.state == "SHOOTING":
                original_interval = self.get_mg_interval()
                buffed_interval = self.get_buffed_frames('attack', original_interval, frame)
                forced_interval = self.buff_manager.get_total_value('force_fire_interval', frame)
                if forced_interval > 0: buffed_interval = int(forced_interval)
                
                if self.state_timer == 0:
                    perform_shoot()
                    warmup_speed = 1.0 + self.buff_manager.get_total_value('mg_warmup_speed', frame)
                    if warmup_speed < 0: warmup_speed = 0
                    increment = warmup_speed
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
                    simulator.log(f"[Action] Reloading... ({self.current_action_duration} frames)", target_name=self.name)
                self.state_timer += 1
                if self.state_timer >= self.current_action_duration: 
                    self.current_ammo = self.current_max_ammo; self.state = "READY"; self.state_timer = 0
                    self.buff_manager.remove_reload_buffs()
                    simulator.log(f"[Action] Reload Complete. Ammo: {self.current_ammo}", target_name=self.name)

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