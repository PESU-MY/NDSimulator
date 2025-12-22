from models import DamageProfile, Skill, WeaponConfig
from utils import round_half_up

class SkillEngineMixin:
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
            
        if "self_has_tag" in condition:
            if not caster.buff_manager.has_active_tag(condition["self_has_tag"], frame): return False
        if "self_not_has_tag" in condition:
            if caster.buff_manager.has_active_tag(condition["self_not_has_tag"], frame): return False

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
        
        # ▼▼▼ 追加: 自身のスタック数を条件にする (self_stack_min) ▼▼▼
        if "self_stack_min" in condition:
            stack_name = condition.get("stack_name") # スタック名は共通
            if stack_name:
                count = caster.buff_manager.get_stack_count(stack_name, frame)
                min_v = condition["self_stack_min"]
                if count < min_v: return False
        # ▲▲▲ 追加ここまで ▲▲▲

        # ▼▼▼ 追加: バリア所持判定 (has_barrier) ▼▼▼
        if "has_barrier" in condition:
            # 現在有効な shield タイプのバフ合計値を取得
            shield_val = target.buff_manager.get_total_value('shield', frame)
            
            # 条件が true (バリアが必要) なのに値が 0 以下なら False
            if condition["has_barrier"] is True and shield_val <= 0:
                return False
            # 条件が false (バリアが無いこと) なのに値が 0 より大なら False
            elif condition["has_barrier"] is False and shield_val > 0:
                return False
        # ▲▲▲ 追加ここまで ▲▲▲

        

        return True

    def should_apply_skill(self, skill, frame, caster=None):
        if skill.condition:
            if "not_has_tag" in skill.condition:
                tag = skill.condition["not_has_tag"]
                if self.enemy_debuffs.has_active_tag(tag, frame): return False
            if "has_tag" in skill.condition:
                tag = skill.condition["has_tag"]
                if not self.enemy_debuffs.has_active_tag(tag, frame): return False
            
            if "self_has_tag" in skill.condition and caster:
                tag = skill.condition["self_has_tag"]
                if not caster.buff_manager.has_active_tag(tag, frame): return False
            if "self_not_has_tag" in skill.condition and caster:
                tag = skill.condition["self_not_has_tag"]
                if caster.buff_manager.has_active_tag(tag, frame): return False

            if skill.condition.get('is_last_burst_user'):
                if self.last_burst_char_name != skill.owner_name: return False

            # ▼▼▼ 追加: 敵の属性条件チェック ▼▼▼
            if "enemy_element" in skill.condition:
                if self.enemy_element != skill.condition["enemy_element"]:
                    return False
            
        return True

    def apply_skill(self, skill, caster, frame, is_full_burst):
        if skill.trigger_type not in ['manual', 'pellet_hit', 'critical_hit']:
            s_id = id(skill)
            if s_id in self.executed_skill_ids:
                return 0
            self.executed_skill_ids.add(s_id)

        if not self.should_apply_skill(skill, frame, caster): return 0
        
        total_dmg = 0
        kwargs = skill.kwargs.copy()

        if skill.effect_type == 'cumulative_stages':
            if skill.kwargs.get('trigger_all_stages'):
                for i, stage_data in enumerate(skill.stages):
                    # ▼▼▼ 追加: trigger_type が part_break の場合、モード設定をチェックしてスキップ ▼▼▼
                    # ステージが辞書の場合の判定
                    if isinstance(stage_data, dict):
                        t_type = stage_data.get('trigger_type')
                        if t_type == 'part_break' and not getattr(self, 'part_break_mode', False):
                            continue
                    # ステージがSkillオブジェクトの場合の判定
                    elif isinstance(stage_data, Skill):
                        if stage_data.trigger_type == 'part_break' and not getattr(self, 'part_break_mode', False):
                            continue
                    # ▲▲▲ 追加ここまで ▲▲▲
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
                        # ▼▼▼ 修正: ターゲット/条件の継承ロジック ▼▼▼
                        # ステージ設定があればそれが優先され、なければ親スキルの設定を引き継ぐ
                        if not temp_skill.target:
                            temp_skill.target = skill.target
                        if not temp_skill.target_condition:
                            temp_skill.target_condition = skill.target_condition
                        # ▲▲▲ 修正ここまで ▲▲▲
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
                        # ▼▼▼ 修正: 継承ロジック ▼▼▼
                        if not temp_skill.target:
                            temp_skill.target = skill.target
                        if not temp_skill.target_condition:
                            temp_skill.target_condition = skill.target_condition
                        # ▲▲▲ 修正ここまで ▲▲▲
                        temp_skill.target = skill.target
                        temp_skill.target_condition = skill.target_condition
                        temp_skill.owner_name = caster.name
                        total_dmg += self.apply_skill(temp_skill, caster, frame, is_full_burst)
            return total_dmg

        targets = []
        if skill.target == 'self':
            if self.check_target_condition(skill.target_condition, caster, caster, frame): targets.append(caster)
        elif skill.target == 'allies':
            # ▼▼▼ 追加: highest_atk の処理 ▼▼▼
            # 1. まず通常の条件でフィルタリング
            candidates = []
            for char in self.characters:
                if self.check_target_condition(skill.target_condition, caster, char, frame): 
                    candidates.append(char)
            
            # 2. 最高攻撃力指定のチェックとソート
            if skill.target_condition and skill.target_condition.get('type') == 'highest_atk':
                count = skill.target_condition.get('count', 1)
                # 現在の攻撃力で降順ソート
                candidates.sort(key=lambda c: c.get_current_atk(frame), reverse=True)
                # 上位N機を選択
                targets = candidates[:count]
                
                # デバッグ用ログ（必要ならコメントアウト解除）
                target_names = [t.name for t in targets]
                self.log(f"[Target] Selected Top {count} ATK: {target_names}", target_name=caster.name)
            else:
                targets = candidates
            # ▲▲▲ 追加ここまで ▲▲▲
        elif skill.target == 'enemy':
            targets.append(caster) 

        if not targets and skill.effect_type == 'damage': targets.append(caster)
        
        # ▼▼▼ 追加: フルバースト時間短縮効果 ▼▼▼
        if skill.effect_type == 'reduce_full_burst_time':
            val = kwargs.get('value', 0)
            if not hasattr(self, 'full_burst_reduction'): self.full_burst_reduction = 0.0
            self.full_burst_reduction += val
            self.log(f"[Burst] Scheduled Full Burst reduction: +{val}s (Total: {self.full_burst_reduction}s)", target_name=caster.name)
            return 0
        # ▲▲▲ 追加ここまで ▲▲▲

        if skill.effect_type == 'cooldown_reduction':
            # ... (既存コード) ...
            reduce_sec = kwargs.get('value', 0)
            reduce_frames = reduce_sec * self.FPS
            for char in self.characters:
                if char.current_cooldown > 0: char.current_cooldown = max(0, char.current_cooldown - reduce_frames)
            if reduce_sec > 0:
                self.log(f"[CT Reduce] Reduced cooldowns by {reduce_sec:.2f}s (Source: {caster.name})", target_name="System")
            return 0
        
        # ▼▼▼ 修正箇所: ステータス参照のロジック変更 ▼▼▼
        if kwargs.get('scale_by_caster_stats'):
            ratio = kwargs.get('value', 0)
            # デフォルトを 'base' とし、明示的に 'finally' が指定された場合のみ現在値を参照
            stat_type = kwargs.get('stat_type', 'base') 
            
            calc_atk = caster.base_atk
            if stat_type == 'finally': 
                calc_atk = caster.get_current_atk(frame)
                
            if calc_atk > 0: kwargs['value'] = calc_atk * ratio
        # ▲▲▲ 修正ここまで ▲▲▲

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
                self.enemy_debuffs.remove_buffs_by_tag(tag, frame) # 敵からも削除
                self.log(f"[Remove] Removed tags {tag} from targets via {skill.name}", target_name=caster.name)

        for target in targets:
            if skill.effect_type == 'ammo_charge' or skill.effect_type == 'refill_ammo':
                rate = kwargs.get('rate', 0)
                amount = round_half_up(target.current_max_ammo * rate)
                target.current_ammo = min(target.current_max_ammo, target.current_ammo + amount)
                self.log(f"[Ammo] {target.name} charged {amount} ammo (Current: {target.current_ammo})", target_name=target.name)
            
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

            # ▼▼▼ 追加: 固定値リロードの実装 ▼▼▼
            elif skill.effect_type == 'refill_ammo_fixed':
                amount = int(kwargs.get('value', 0))
                target.current_ammo = min(target.current_max_ammo, target.current_ammo + amount)
                self.log(f"[Ammo] Refilled {amount} ammo (Fixed) for {target.name}", target_name=target.name)
            # ▲▲▲▲▲▲

            # ▼▼▼ 修正: バリア (Shield) 効果の実装（タグ対応） ▼▼▼
            elif skill.effect_type == 'shield':
                value = kwargs.get('value', 1.0)
                duration = kwargs.get('duration', 0) * self.FPS
                
                # JSONで "tag" 指定があればそれを使い、なければ "barrier" をデフォルトとする
                tag_name = kwargs.get('tag', 'barrier') 
                
                target.buff_manager.add_buff(
                    'shield', value, duration, frame, 
                    source=skill.name, tag=tag_name  # ← ここを変数に変更
                )
                self.log(f"[Barrier] {target.name} applied Shield ({tag_name}) (Val:{value}, Dur:{kwargs.get('duration')}s)", target_name=target.name)
            # ▲▲▲ 修正ここまで ▲▲▲

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

                # ▼▼▼ 追加: スタック数による倍率補正処理 ▼▼▼
                # 1. 自身のバフスタック数でスケール (シンデレラ用)
                if 'copy_stack_count' in kwargs:
                    stack_name = kwargs['copy_stack_count']
                    stack_count = caster.buff_manager.get_stack_count(stack_name, frame)
                    mult *= stack_count
                    self.log(f"[Dmg Scale] Scaled by self stack '{stack_name}': x{stack_count} -> {mult:.4f}", target_name=caster.name)

                # 2. ターゲットのデバフスタック数でスケール (アスカWILLE用など)
                elif kwargs.get('scale_by_target_stack') and targets:
                    stack_name = kwargs.get('stack_name')
                    # ターゲットが複数の場合は代表して1体目、あるいは個別に計算が必要だが簡略化
                    target_stack = self.enemy_debuffs.get_stack_count(stack_name, frame)
                    mult *= target_stack
                    self.log(f"[Dmg Scale] Scaled by enemy stack '{stack_name}': x{target_stack} -> {mult:.4f}", target_name=targets[0].name)
                # ▲▲▲ 追加ここまで ▲▲▲

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
                
            # ▼▼▼ 追加: スタック数の強制設定処理 ▼▼▼
            elif skill.effect_type == 'set_stack':
                stack_name = kwargs.get('stack_name')
                val = int(kwargs.get('value', 0))
                for target in targets:
                    # BuffManagerに実装済みの set_stack_count を利用
                    target.buff_manager.set_stack_count(stack_name, val)
                    self.log(f"[Stack Set] {target.name}: {stack_name} set to {val}", target_name=target.name)
            # ▲▲▲ 追加ここまで ▲▲▲
            
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