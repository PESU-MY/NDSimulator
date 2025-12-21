from models import DamageProfile, Skill, WeaponConfig
from utils import round_half_up

class SkillEngineMixin:
    # ... (既存の check_target_condition, should_apply_skill は変更なし) ...
    def check_target_condition(self, condition, caster, target, frame):
        if not condition: return True
        
        if 'type' in condition and 'value' in condition:
            c_type = condition['type']
            c_value = condition['value']
            if c_type == 'element' and target.element != c_value: return False
            if c_type == 'weapon_type' and target.weapon.weapon_class != c_value: return False
            if c_type == 'class' and target.character_class != c_value: return False

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
        if skill.condition:
            if "not_has_tag" in skill.condition:
                tag = skill.condition["not_has_tag"]
                if self.enemy_debuffs.has_active_tag(tag, frame):
                     return False
            if "has_tag" in skill.condition:
                tag = skill.condition["has_tag"]
                if not self.enemy_debuffs.has_active_tag(tag, frame):
                     return False
            if skill.condition.get('is_last_burst_user'):
                if self.last_burst_char_name != skill.owner_name:
                    return False
        return True

    def apply_skill(self, skill, caster, frame, is_full_burst):
        if skill.trigger_type not in ['manual', 'pellet_hit', 'critical_hit']:
            s_id = id(skill)
            if s_id in self.executed_skill_ids:
                return 0
            self.executed_skill_ids.add(s_id)

        if not self.should_apply_skill(skill, frame): return 0
        
        total_dmg = 0
        kwargs = skill.kwargs.copy()

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
            return total_dmg

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

        if skill.effect_type == 'cooldown_reduction':
            reduce_sec = kwargs.get('value', 0)
            reduce_frames = reduce_sec * self.FPS
            for char in self.characters:
                if char.current_cooldown > 0: char.current_cooldown = max(0, char.current_cooldown - reduce_frames)
            if reduce_sec > 0:
                self.log(f"[CT Reduce] Reduced cooldowns by {reduce_sec:.2f}s (Source: {caster.name})", target_name="System")
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

        if skill.remove_tags:
            for tag in skill.remove_tags:
                for t in targets:
                    t.buff_manager.remove_buffs_by_tag(tag, frame)
                self.enemy_debuffs.remove_buffs_by_tag(tag, frame)
                self.log(f"[Remove] Removed tags {tag} from targets via {skill.name}", target_name=caster.name)

        for target in targets:
            # ▼▼▼ 新規追加: 弾丸チャージ (rate指定) ▼▼▼
            if skill.effect_type == 'ammo_charge' or skill.effect_type == 'refill_ammo':
                rate = kwargs.get('rate', 0)
                amount = round_half_up(target.current_max_ammo * rate)
                target.current_ammo = min(target.current_max_ammo, target.current_ammo + amount)
                self.log(f"[Ammo] {target.name} charged {amount} ammo (Current: {target.current_ammo})", target_name=target.name)
            
            # ▼▼▼ 新規追加: 残弾数強制変更 (value指定) ▼▼▼
            elif skill.effect_type == 'set_current_ammo':
                val = int(kwargs.get('value', 0))
                target.current_ammo = max(0, min(target.current_max_ammo, val))
                self.log(f"[Ammo] {target.name} ammo set to {target.current_ammo}", target_name=target.name)

            elif skill.effect_type == 'convert_hp_to_atk':
                rate = skill.kwargs.get('value', 0)
                target.buff_manager.add_buff('conversion_hp_to_atk', rate, skill.kwargs.get('duration', 0) * self.FPS, frame, source=skill.name)
                self.log(f"[Buff] {target.name}: HP to ATK conversion ({rate})", target_name=target.name)
            
            elif skill.effect_type == 'heal':
                heal_val = kwargs.get('value', 0)
                self.log(f"[Heal] {caster.name} healed {target.name} (Val: {heal_val})", target_name=target.name)
                target.process_trigger('on_receive_heal', heal_val, frame, is_full_burst, self)

            elif skill.effect_type == 'buff' or skill.effect_type == 'stack_buff':
                b_type = kwargs.get('buff_type', skill.effect_type) 
                val = kwargs.get('value', 0)
                dur = kwargs.get('duration', 0) * self.FPS
                s_name = kwargs.get('stack_name')
                tag = kwargs.get('tag')
                shot_dur = kwargs.get('shot_duration', 0)
                rem_reload = kwargs.get('remove_on_reload', False)
                st_amount = kwargs.get('stack_amount', 1)
                
                added_stack_count = 0
                if b_type in ['def_debuff', 'taken_dmg_debuff']:
                    if skill.effect_type == 'stack_buff':
                        self.enemy_debuffs.add_buff(b_type, val, dur, frame, source=skill.name, stack_name=s_name, max_stack=kwargs.get('max_stack', 1), tag=tag, shot_duration=shot_dur, remove_on_reload=rem_reload, stack_amount=st_amount)
                    else:
                        self.enemy_debuffs.add_buff(b_type, val, dur, frame, source=skill.name, tag=tag, shot_duration=shot_dur, remove_on_reload=rem_reload)
                    self.log(f"[Debuff] Applied {skill.name} ({b_type}) to Enemy (Shared)", target_name=caster.name)
                else:
                    if skill.effect_type == 'stack_buff':
                        prev_count = target.buff_manager.get_stack_count(s_name, frame)
                        target.buff_manager.add_buff(b_type, val, dur, frame, source=skill.name, stack_name=s_name, max_stack=kwargs.get('max_stack', 1), tag=tag, shot_duration=shot_dur, remove_on_reload=rem_reload, stack_amount=st_amount)
                        new_count = target.buff_manager.get_stack_count(s_name, frame)
                        added_stack_count = new_count - prev_count
                    else:
                        target.buff_manager.add_buff(b_type, val, dur, frame, source=skill.name, tag=tag, shot_duration=shot_dur, remove_on_reload=rem_reload)
                    self.log(f"[Buff] Applied {skill.name} ({b_type}: {val}) to {target.name}", target_name=target.name)
                
                if added_stack_count > 0:
                    target.process_trigger('stack_count', 0, frame, is_full_burst, self, delta=added_stack_count)

            elif skill.effect_type == 'stack_dot':
                stack_name = skill.kwargs.get('stack_name', skill.name)
                max_stack = skill.kwargs.get('max_stack', 1)
                raw_profile = skill.kwargs.get('profile', {})
                full_profile = DamageProfile.create(**raw_profile)
                
                if stack_name in target.active_dots:
                    dot = target.active_dots[stack_name]
                    dot['count'] = min(max_stack, dot['count'] + 1)
                    dot['end_frame'] = frame + (skill.kwargs.get('duration', 0) * self.FPS)
                    dot['profile'] = full_profile
                else:
                    target.active_dots[stack_name] = {
                        'end_frame': frame + (skill.kwargs.get('duration', 0) * self.FPS),
                        'multiplier': skill.kwargs['multiplier'], 
                        'profile': full_profile,
                        'count': 1, 'max_stack': max_stack, 'element': caster.element
                    }
                self.log(f"[DoT] Applied/Stacked {stack_name} on Enemy (via {target.name})", target_name=target.name)

            elif skill.effect_type == 'dot':
                raw_profile = skill.kwargs.get('profile', {})
                full_profile = DamageProfile.create(**raw_profile)
                target.active_dots[skill.name] = {
                    'end_frame': frame + (skill.kwargs.get('duration', 0) * self.FPS),
                    'multiplier': skill.kwargs['multiplier'], 
                    'profile': full_profile,
                    'count': 1, 'max_stack': 1, 'element': caster.element
                }
                self.log(f"[DoT] Applied {skill.name} on Enemy (via {target.name})", target_name=target.name)

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