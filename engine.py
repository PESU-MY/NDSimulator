import os
import shutil
import random
from models import DamageProfile, Skill, WeaponConfig
from buff_manager import BuffManager
from character import Character

# --- シミュレーターエンジン (統括) ---

class NikkeSimulator:
    def __init__(self, characters, burst_rotation, enemy_element="None", enemy_core_size=3.0, enemy_size=5.0, part_break_mode=False, log_file_path="simulation_log.txt"):
        self.FPS = 60
        self.TOTAL_FRAMES = 180 * self.FPS
        
        self.characters = characters 
        self.burst_rotation = burst_rotation 
        self.burst_indices = [0, 0, 0] 
        
        self.ENEMY_DEF = 0 
        self.enemy_element = enemy_element
        self.enemy_core_size = enemy_core_size
        self.enemy_size = enemy_size
        self.part_break_mode = part_break_mode
        
        # 敵へのデバフ(全員で共有)
        self.enemy_debuffs = BuffManager()
        
        self.log_dir = "logs"
        if os.path.exists(self.log_dir):
            shutil.rmtree(self.log_dir) # 古いログを掃除
        os.makedirs(self.log_dir)
        
        self.log_handles = {}
        self.log_handles["System"] = open(os.path.join(self.log_dir, "System.txt"), 'w', encoding='utf-8')
        
        for char in self.characters:
            safe_name = "".join([c for c in char.name if c.isalnum() or c in (' ', '_', '-', '.')])
            self.log_handles[char.name] = open(os.path.join(self.log_dir, f"{safe_name}.txt"), 'w', encoding='utf-8')
            
        self.log("=== Simulation Start ===", target_name="System")
        for c in self.characters:
            self.log(f"Character: {c.name} (Atk:{c.base_atk})", target_name="System")

        self.last_burst_char_name = None
        self.burst_state = "GEN" 
        self.burst_timer = 0
        
        self.scheduled_actions = []

    def log(self, message, target_name="System"):
        if target_name in self.log_handles:
            self.log_handles[target_name].write(message + '\n')
        else:
            self.log_handles["System"].write(f"[{target_name}] {message}\n")

    def check_target_condition(self, condition, caster, target, frame):
        if not condition: return True
        if 'element' in condition and target.element != condition['element']: return False
        if 'weapon_type' in condition and target.weapon.weapon_class != condition['weapon_type']: return False
        if 'burst_stage' in condition and str(target.burst_stage) != str(condition['burst_stage']): return False
        if condition.get('is_last_burst_user'):
            if self.last_burst_char_name != target.name: return False
        if "not_has_tag" in condition:
            if target.buff_manager.has_active_tag(condition["not_has_tag"], frame): return False
        if "has_tag" in condition:
            if not target.buff_manager.has_active_tag(condition["has_tag"], frame): return False
        if "has_flag" in condition:
            if condition["has_flag"] not in target.special_flags: return False
        if "not_has_flag" in condition:
            if condition["not_has_flag"] in target.special_flags: return False
        if "stack_min" in condition or "stack_max" in condition:
            stack_name = condition.get("stack_name")
            if stack_name:
                count = target.buff_manager.get_stack_count(stack_name, frame)
                min_v = condition.get("stack_min", -999)
                max_v = condition.get("stack_max", 999)
                if not (min_v <= count <= max_v): return False
        return True

    def should_apply_skill(self, skill, frame):
        # 条件付きスキルの判定
        if skill.condition:
            if "not_has_tag" in skill.condition:
                tag = skill.condition["not_has_tag"]
                if self.enemy_debuffs.has_active_tag(tag, frame):
                     return False
            if "has_tag" in skill.condition:
                tag = skill.condition["has_tag"]
                if not self.enemy_debuffs.has_active_tag(tag, frame):
                     return False
        return True

    def apply_skill(self, skill, caster, frame, is_full_burst):
        # 同一フレーム内でのスキル多重発動を防止
        if skill.trigger_type != 'manual':
            last_frame = getattr(skill, 'last_used_frame', -1)
            if last_frame == frame:
                return 0
            skill.last_used_frame = frame

        if not self.should_apply_skill(skill, frame): return 0
        
        total_dmg = 0
        kwargs = skill.kwargs.copy()

        # ▼▼▼ 修正: cumulative_stages (段階進行) はターゲット決定・ループの前に処理する ▼▼▼
        # これにより、対象人数分だけ重複して発動するのを防ぐ
        if skill.effect_type == 'cumulative_stages':
            if skill.kwargs.get('trigger_all_stages'):
                for i, stage_data in enumerate(skill.stages):
                    if isinstance(stage_data, Skill):
                        total_dmg += self.apply_skill(stage_data, caster, frame, is_full_burst)
                    elif isinstance(stage_data, dict):
                        init_kwargs = stage_data.get('kwargs', {}).copy()
                        for k, v in stage_data.items():
                            if k not in ['name', 'trigger_type', 'trigger_value', 'effect_type', 'kwargs']:
                                init_kwargs[k] = v
                        temp_skill = Skill(
                            name=f"{skill.name}_Stage_{i}", trigger_type="manual", trigger_value=0,
                            effect_type=stage_data.get('effect_type', 'buff'), **init_kwargs
                        )
                        temp_skill.target = skill.target
                        temp_skill.target_condition = skill.target_condition
                        temp_skill.owner_name = caster.name
                        total_dmg += self.apply_skill(temp_skill, caster, frame, is_full_burst)
            else:
                skill.current_usage_count += 1
                max_apply_idx = min(len(skill.stages), skill.current_usage_count)
                for i in range(max_apply_idx):
                    stage_data = skill.stages[i]
                    if isinstance(stage_data, Skill):
                        total_dmg += self.apply_skill(stage_data, caster, frame, is_full_burst)
                    elif isinstance(stage_data, dict):
                        init_kwargs = stage_data.get('kwargs', {}).copy()
                        for k, v in stage_data.items():
                            if k not in ['name', 'trigger_type', 'trigger_value', 'effect_type', 'kwargs']:
                                init_kwargs[k] = v
                        temp_skill = Skill(
                            name=f"{skill.name}_Stage_{i}", trigger_type="manual", trigger_value=0,
                            effect_type=stage_data.get('effect_type', 'buff'), **init_kwargs
                        )
                        temp_skill.target = skill.target
                        temp_skill.target_condition = skill.target_condition
                        temp_skill.owner_name = caster.name
                        total_dmg += self.apply_skill(temp_skill, caster, frame, is_full_burst)
            
            # cumulative_stages の処理が終わったら、このスキル自体の処理は完了としてリターン
            return total_dmg
        # ▲▲▲▲▲▲

        # ターゲット決定
        targets = []
        if skill.target == 'self':
            if self.check_target_condition(skill.target_condition, caster, caster, frame):
                targets.append(caster)
        elif skill.target == 'allies':
            for char in self.characters:
                if self.check_target_condition(skill.target_condition, caster, char, frame):
                    targets.append(char)
        elif skill.target == 'enemy':
            targets.append(caster)

        if not targets and skill.effect_type == 'damage':
            targets.append(caster)

        # CT短縮はターゲットに関わらず全員に適用
        if skill.effect_type == 'cooldown_reduction':
            reduce_sec = kwargs.get('value', 0)
            reduce_frames = reduce_sec * self.FPS
            for char in self.characters:
                if char.current_cooldown > 0: char.current_cooldown = max(0, char.current_cooldown - reduce_frames)
            return 0
        
        if kwargs.get('scale_by_caster_stats'):
            ratio = kwargs.get('value', 0)
            stat_type = kwargs.get('stat_type', 'current') 
            calc_atk = caster.base_atk
            if stat_type == 'current': calc_atk = caster.get_current_atk(frame)
            if calc_atk > 0: kwargs['value'] = calc_atk * ratio

        if skill.effect_type == 'activate_flag':
            flag_name = kwargs.get('flag_name')
            for t in targets:
                t.special_flags.add(flag_name)
                self.log(f"[Flag] {t.name}: Activated {flag_name}", target_name=t.name)
            return 0

        # 効果の適用
        for target in targets:
            if skill.effect_type == 'convert_hp_to_atk':
                rate = skill.kwargs.get('value', 0)
                target.buff_manager.add_buff('conversion_hp_to_atk', rate, skill.kwargs.get('duration', 0) * self.FPS, frame, source=skill.name)
                self.log(f"[Buff] {target.name}: HP to ATK conversion ({rate})", target_name=target.name)
            
            # (cumulative_stages は上で処理済みのため、ここには記述しない)
            
            elif skill.effect_type == 'buff' or skill.effect_type == 'stack_buff':
                b_type = kwargs.get('buff_type', skill.effect_type) 
                val = kwargs.get('value', 0)
                dur = kwargs.get('duration', 0) * self.FPS
                s_name = kwargs.get('stack_name')
                tag = kwargs.get('tag')
                
                # 敵へのデバフは共有マネージャーへ
                if b_type in ['def_debuff', 'taken_dmg_debuff']:
                    if skill.effect_type == 'stack_buff':
                        self.enemy_debuffs.add_buff(b_type, val, dur, frame, source=skill.name, stack_name=s_name, max_stack=kwargs.get('max_stack', 1), tag=tag)
                    else:
                        self.enemy_debuffs.add_buff(b_type, val, dur, frame, source=skill.name, tag=tag)
                    self.log(f"[Debuff] Applied {skill.name} ({b_type}) to Enemy (Shared)", target_name=caster.name)
                else:
                    if skill.effect_type == 'stack_buff':
                        target.buff_manager.add_buff(b_type, val, dur, frame, source=skill.name, stack_name=s_name, max_stack=kwargs.get('max_stack', 1), tag=tag)
                    else:
                        target.buff_manager.add_buff(b_type, val, dur, frame, source=skill.name, tag=tag)
                    self.log(f"[Buff] Applied {skill.name} ({b_type}: {val}) to {target.name}", target_name=target.name)

            elif skill.effect_type == 'damage':
                profile = DamageProfile.create(**kwargs.get('profile', {}))
                mult = kwargs.get('multiplier', 1.0)
                loops = kwargs.get('loop_count', 1)
                skill_dmg = 0
                for _ in range(loops):
                    d, _ = caster.calculate_strict_damage(
                        mult, profile, is_full_burst, frame, 
                        self.ENEMY_DEF, self.enemy_element, self.enemy_core_size, self.enemy_size,
                        debuff_manager=self.enemy_debuffs
                    )
                    skill_dmg += d
                
                buff_debug = caster.buff_manager.get_active_buffs_debug(frame)
                self.log(f"[Skill Dmg] 時間:{frame/60:>6.2f}s | 名前:{skill.name:<25} | Dmg:{skill_dmg:10,.0f} | Hits:{loops} | Buffs:{buff_debug}", target_name=caster.name)
                
                caster.total_damage += skill_dmg
                if skill.name in caster.damage_breakdown: caster.damage_breakdown[skill.name] += skill_dmg
                else: caster.damage_breakdown[skill.name] = skill_dmg
                total_dmg += skill_dmg

            elif skill.effect_type == 'delayed_action':
                duration_sec = kwargs.get('duration', 0)
                exec_frame = frame + int(duration_sec * self.FPS)
                sub_data = skill.sub_effect
                if sub_data:
                    init_kwargs = sub_data.get('kwargs', {}).copy()
                    act_skill = Skill(
                        name=f"Delayed_{skill.name}", trigger_type="manual", trigger_value=0,
                        effect_type=sub_data.get('effect_type', 'buff'), **init_kwargs
                    )
                    act_skill.target = skill.target
                    act_skill.owner_name = caster.name
                    if 'stages' in sub_data: act_skill.stages = sub_data['stages']
                    self.scheduled_actions.append({'frame': exec_frame, 'skill': act_skill, 'caster': caster})
            
            elif skill.effect_type == 'weapon_change':
                new_weapon_data = kwargs.get('weapon_data')
                duration = kwargs.get('duration', 0)
                if new_weapon_data and target == caster:
                    target.is_weapon_changed = True
                    if 'max_ammo' in new_weapon_data:
                        target.weapon_change_ammo_specified = True
                        target.weapon = WeaponConfig(new_weapon_data)
                        target.current_max_ammo = target.weapon.max_ammo
                        target.current_ammo = target.current_max_ammo
                    else:
                        target.weapon_change_ammo_specified = False
                        temp_data = new_weapon_data.copy()
                        temp_data['max_ammo'] = target.current_max_ammo
                        target.weapon = WeaponConfig(temp_data)
                    
                    if duration > 0: target.weapon_change_end_frame = frame + (duration * self.FPS)
                    else: target.weapon_change_end_frame = 0
                    target.state = "READY"; target.state_timer = 0
                    self.log(f"[Weapon Change] {target.name} changed weapon to {target.weapon.name}", target_name=target.name)

        return total_dmg

    def update_cooldowns(self):
        for char in self.characters:
            if char.current_cooldown > 0: char.current_cooldown -= 1

    def tick_burst_state(self, frame):
        is_full_burst = (self.burst_state == "FULL")
        
        if self.burst_state == "GEN":
            self.burst_timer += 1
            if self.burst_timer >= 5 * self.FPS: 
                self.burst_state = "BURST_1"
                self.burst_timer = 0
                
        elif self.burst_state in ["BURST_1", "BURST_2", "BURST_3"]:
            stage_idx = {"BURST_1": 0, "BURST_2": 1, "BURST_3": 2}[self.burst_state]
            char_list = self.burst_rotation[stage_idx]
            
            if len(char_list) > 0:
                idx = self.burst_indices[stage_idx]
                if idx < len(char_list):
                    char = char_list[idx]
                    if char.current_cooldown <= 0:
                        base_cd = 40.0
                        if char.burst_stage in ['1', '2']: base_cd = 20.0 
                        char.current_cooldown = base_cd * self.FPS
                        
                        self.log(f"[Burst] {char.name} used Burst Stage {self.burst_state.split('_')[1]}", target_name="System")
                        self.log(f"[Burst] Activate!", target_name=char.name)
                        
                        if self.burst_state == "BURST_3":
                            self.last_burst_char_name = char.name 
                            char.process_trigger('on_burst_3_enter', 0, frame, is_full_burst, self)
                            self.process_trigger_global('on_burst_enter', frame) 
                        
                        char.process_trigger('on_use_burst_skill', 0, frame, is_full_burst, self)
                        
                        self.burst_indices[stage_idx] = (idx + 1) % len(char_list)
                        if self.burst_state == "BURST_1": self.burst_state = "BURST_2"
                        elif self.burst_state == "BURST_2": self.burst_state = "BURST_3"
                        elif self.burst_state == "BURST_3":
                            self.burst_state = "FULL"; self.burst_timer = 0
                            
        elif self.burst_state == "FULL":
            self.burst_timer += 1
            if self.burst_timer >= 10 * self.FPS: 
                self.process_trigger_global('on_burst_end', frame)
                self.burst_state = "GEN"; self.burst_timer = 0

    def process_trigger_global(self, trigger_type, frame):
        is_fb = (self.burst_state == "FULL")
        for char in self.characters:
            char.process_trigger(trigger_type, 0, frame, is_fb, self)

    def tick(self, frame):
        self.tick_burst_state(frame)
        self.update_cooldowns()
        
        executed_indices = []
        is_full_burst = (self.burst_state == "FULL")
        for i, action in enumerate(self.scheduled_actions):
            if frame >= action['frame']:
                skill = action['skill']
                caster = action['caster']
                self.apply_skill(skill, caster, frame, is_full_burst)
                executed_indices.append(i)
        for i in reversed(executed_indices): self.scheduled_actions.pop(i)
        
        for char in self.characters:
            if char.is_weapon_changed and char.weapon_change_end_frame > 0:
                if frame >= char.weapon_change_end_frame: char.revert_weapon(frame)

            char.update_max_ammo(frame)
            if frame % 60 == 0:
                damage_dot = 0
                for name, dot in list(char.active_dots.items()):
                    if frame <= dot['end_frame']:
                        total_mult = dot['multiplier'] * dot.get('count', 1)
                        profile = dot.get('profile', DamageProfile.create())
                        dmg, _ = char.calculate_strict_damage(
                            total_mult, profile, is_full_burst, frame, 
                            self.ENEMY_DEF, self.enemy_element, self.enemy_core_size, self.enemy_size,
                            debuff_manager=self.enemy_debuffs
                        )
                        damage_dot += dmg
                    else: del char.active_dots[name]
                char.total_damage += damage_dot
            
            char.process_trigger('time_interval', frame, frame, is_full_burst, self)
            char.tick_action(frame, is_full_burst, self)

    def run(self):
        try:
            self.process_trigger_global('on_start', 0)
            for frame in range(1, self.TOTAL_FRAMES + 1):
                self.tick(frame)
        finally:
            for f in self.log_handles.values():
                f.close()
        
        results = {}
        for char in self.characters:
            results[char.name] = {
                'total_damage': char.total_damage,
                'breakdown': char.damage_breakdown
            }
        return results