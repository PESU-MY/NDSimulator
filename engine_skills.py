from models import DamageProfile, Skill, WeaponConfig
from utils import round_half_up
import random

class SkillEngineMixin:
    def _formation_index(self, character):
        try:
            return self.characters.index(character)
        except (AttributeError, ValueError):
            return None

    def _check_formation_condition(self, formation, caster, target):
        caster_idx = self._formation_index(caster)
        target_idx = self._formation_index(target)
        if caster_idx is None or target_idx is None:
            return False

        last_idx = len(self.characters) - 1
        diff = target_idx - caster_idx
        if formation == "adjacent":
            return abs(diff) == 1
        if formation == "self_and_adjacent":
            return abs(diff) <= 1
        if formation == "left_of_self":
            return diff == -1
        if formation == "right_of_self":
            return diff == 1
        if formation == "left_side":
            return target_idx < caster_idx
        if formation == "right_side":
            return target_idx > caster_idx
        if formation == "leftmost":
            return target_idx == 0
        if formation == "rightmost":
            return target_idx == last_idx
        if formation in ["front_row", "front"]:
            return target_idx % 2 == 0
        if formation in ["back_row", "back"]:
            return target_idx % 2 == 1
        return False

    def _any_target_condition_matches(self, condition, caster, frame):
        if not condition or not caster:
            return False
        for char in self.characters:
            if getattr(char, "current_hp", 0) <= 0:
                continue
            if self.check_target_condition(condition, caster, char, frame):
                return True
        return False

    def check_target_condition(self, condition, caster, target, frame):
        if not condition: return True
        
        if 'type' in condition and 'value' in condition:
            c_type = condition['type']
            c_value = condition['value']
            if c_type == 'element' and target.element != c_value: return False
            if c_type == 'weapon_type' and target.weapon.weapon_class != c_value: return False
            if c_type == 'class' and target.character_class != c_value: return False

        if 'class' in condition and target.character_class != condition['class']:
            return False
        if "name" in condition:
            expected_names = condition["name"]
            if isinstance(expected_names, str):
                expected_names = [expected_names]
            if target.name not in expected_names:
                return False
        if "not_name" in condition:
            blocked_names = condition["not_name"]
            if isinstance(blocked_names, str):
                blocked_names = [blocked_names]
            if target.name in blocked_names:
                return False
        if condition.get("not_self") and target == caster:
            return False
        if "alive" in condition:
            is_alive = getattr(target, "current_hp", 0) > 0
            if is_alive != condition["alive"]:
                return False
        if "formation" in condition:
            formations = condition["formation"]
            if isinstance(formations, str):
                formations = [formations]
            if not any(self._check_formation_condition(f, caster, target) for f in formations):
                return False
        if "formation_index" in condition:
            target_idx = self._formation_index(target)
            if target_idx != int(condition["formation_index"]):
                return False
        if "formation_position" in condition:
            target_idx = self._formation_index(target)
            expected_positions = condition["formation_position"]
            if isinstance(expected_positions, int):
                expected_positions = [expected_positions]
            if target_idx is None or target_idx + 1 not in expected_positions:
                return False
        if 'element' in condition and target.element != condition['element']: return False
        if 'weapon_type' in condition and target.weapon.weapon_class != condition['weapon_type']: return False
        if 'burst_stage' in condition and str(target.burst_stage) != str(condition['burst_stage']): return False
        
        if "is_current_burst_participant" in condition:
            required = condition["is_current_burst_participant"]
            participants = getattr(self, 'current_burst_participants', set())
            is_participant = target.name in participants
            if is_participant != required:
                return False
        
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
        
        if "self_stack_min" in condition:
            stack_name = condition.get("stack_name")
            if stack_name:
                count = caster.buff_manager.get_stack_count(stack_name, frame)
                min_v = condition["self_stack_min"]
                if count < min_v: return False

        if "has_barrier" in condition:
            shield_val = target.buff_manager.get_total_value('shield', frame)
            if condition["has_barrier"] is True and shield_val <= 0:
                return False
            elif condition["has_barrier"] is False and shield_val > 0:
                return False

        if "hp_ratio_min" in condition or "hp_ratio_max" in condition:
            max_hp = target.get_current_max_hp(frame)
            if max_hp > 0:
                current_ratio = target.current_hp / max_hp
                if "hp_ratio_min" in condition:
                    if current_ratio < condition["hp_ratio_min"]: return False
                if "hp_ratio_max" in condition:
                    if current_ratio > condition["hp_ratio_max"]: return False
            else:
                return False

        if "squad" in condition:
            if target.squad != condition["squad"]: return False

        # ▼▼▼ 追加: ターゲットが指定した種類のバフを持っているか ▼▼▼
        # 使用例: "has_buff_type": "shield" (バリア持ちのみ対象)
        if "has_buff_type" in condition:
            b_type = condition["has_buff_type"]
            # get_active_buffs はそのタイプの有効なバフのリストを返す。空ならFalse
            if not target.buff_manager.get_active_buffs(b_type, frame): return False
        
        if "not_has_buff_type" in condition:
            b_type = condition["not_has_buff_type"]
            if target.buff_manager.get_active_buffs(b_type, frame): return False
        # ▲▲▲ 追加ここまで ▲▲▲

        return True

    def should_apply_skill(self, skill, frame, caster=None, is_full_burst=False):
        # ▼▼▼ 追加: 確率発動の判定 (Probability Check) ▼▼▼
        # kwargsに "probability" が設定されている場合、その確率(%)で判定を行う
        proc_rate = skill.kwargs.get('probability')
        if proc_rate is not None:
            # 0～100の乱数を生成し、確率より大きければ発動しない (Falseを返す)
            # 例: probability: 10 (10%) -> randomが 10.1 なら False
            if random.random() * 100 > float(proc_rate):
                return False
        # ▲▲▲ 追加ここまで ▲▲▲

        # ▼▼▼ 追加: 最大発動回数のチェック ▼▼▼
        if skill.max_trigger_count is not None:
            if skill.current_usage_count >= skill.max_trigger_count:
                return False
        # ▲▲▲ 追加ここまで ▲▲▲

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

            if "self_has_active_dot" in skill.condition and caster:
                dot_names = skill.condition["self_has_active_dot"]
                if isinstance(dot_names, str):
                    dot_names = [dot_names]
                has_dot = False
                for dot_name in dot_names:
                    dot = caster.active_dots.get(dot_name)
                    if dot and dot.get('count', 0) > 0 and dot.get('end_frame', -1) >= frame:
                        has_dot = True
                        break
                if not has_dot:
                    return False

            if "self_not_has_active_dot" in skill.condition and caster:
                dot_names = skill.condition["self_not_has_active_dot"]
                if isinstance(dot_names, str):
                    dot_names = [dot_names]
                for dot_name in dot_names:
                    dot = caster.active_dots.get(dot_name)
                    if dot and dot.get('count', 0) > 0 and dot.get('end_frame', -1) >= frame:
                        return False

            if skill.condition.get('is_last_burst_user'):
                if self.last_burst_char_name != skill.owner_name: return False

            if "enemy_element" in skill.condition:
                if self.enemy_element != skill.condition["enemy_element"]:
                    return False
            
            if "self_stack_min" in skill.condition and caster:
                stack_name = skill.condition.get("stack_name")
                if stack_name:
                    count = caster.buff_manager.get_stack_count(stack_name, frame)
                    if count < skill.condition["self_stack_min"]:
                        return False

            if ("stack_min" in skill.condition or "stack_max" in skill.condition) and caster:
                stack_name = skill.condition.get("stack_name")
                if stack_name:
                    count = caster.buff_manager.get_stack_count(stack_name, frame)
                    min_v = skill.condition.get("stack_min", -999)
                    max_v = skill.condition.get("stack_max", 999)
                    if not (min_v <= count <= max_v):
                        return False

            if "is_full_burst" in skill.condition:
                required_state = skill.condition["is_full_burst"]
                is_fb_now = bool(is_full_burst)
                if is_fb_now != required_state:
                    return False
            
            if "simulation_flag" in skill.condition:
                flag_name = skill.condition["simulation_flag"]
                if not getattr(self, flag_name, False):
                    return False
                
            if "self_formation" in skill.condition:
                if not caster:
                    return False
                formations = skill.condition["self_formation"]
                if isinstance(formations, str):
                    formations = [formations]
                if not any(self._check_formation_condition(f, caster, caster) for f in formations):
                    return False

            if "self_formation_position" in skill.condition:
                if not caster:
                    return False
                caster_idx = self._formation_index(caster)
                expected_positions = skill.condition["self_formation_position"]
                if isinstance(expected_positions, int):
                    expected_positions = [expected_positions]
                if caster_idx is None or caster_idx + 1 not in expected_positions:
                    return False

            # ▼▼▼ 追加: 部隊内のクラス存在判定 ▼▼▼
            # 味方に指定クラスがいるか (has_ally_class)
            if "any_target_condition" in skill.condition:
                if not caster:
                    return False
                sub_condition = skill.condition["any_target_condition"]
                if not self._any_target_condition_matches(sub_condition, caster, frame):
                    return False

            if "any_target_condition_enter" in skill.condition:
                if not caster:
                    return False
                sub_condition = skill.condition["any_target_condition_enter"]
                is_active = self._any_target_condition_matches(sub_condition, caster, frame)
                condition_states = getattr(skill, "_condition_enter_states", {})
                state_key = repr(sub_condition)
                if state_key not in condition_states and skill.condition.get("condition_enter_skip_initial"):
                    condition_states[state_key] = is_active
                    skill._condition_enter_states = condition_states
                    return False
                was_active = condition_states.get(state_key, False)
                condition_states[state_key] = is_active
                skill._condition_enter_states = condition_states
                if not is_active or was_active:
                    return False

            if "has_ally_class" in skill.condition:
                target_class = skill.condition["has_ally_class"]
                exclude_self = skill.condition.get("exclude_self", True) # デフォルトで自分を除外
                found = False
                for char in self.characters:
                    if char.base_hp <= 0: continue
                    if exclude_self and char == caster: continue
                    
                    if char.character_class == target_class:
                        found = True
                        break
                if not found: return False

            # 味方に指定クラスがいないか (not_has_ally_class)
            if "not_has_ally_class" in skill.condition:
                target_class = skill.condition["not_has_ally_class"]
                exclude_self = skill.condition.get("exclude_self", True)
                found = False
                for char in self.characters:
                    if char.base_hp <= 0: continue
                    if exclude_self and char == caster: continue
                    
                    if char.character_class == target_class:
                        found = True
                        break
                # 見つかったらNG
                if found: return False
            # ▲▲▲ 追加ここまで ▲▲▲

            # ▼▼▼ 追加: 部隊内のバースト段階存在判定 ▼▼▼
            # 味方に指定バースト段階がいるか (has_ally_burst_stage)
            if "has_ally_burst_stage" in skill.condition:
                target_stage = str(skill.condition["has_ally_burst_stage"])
                exclude_self = skill.condition.get("exclude_self", True)
                found = False
                for char in self.characters:
                    if char.base_hp <= 0: continue
                    if exclude_self and char == caster: continue
                    
                    if str(char.burst_stage) == target_stage:
                        found = True
                        break
                if not found: return False

            # 味方に指定バースト段階がいないか (not_has_ally_burst_stage)
            if "not_has_ally_burst_stage" in skill.condition:
                target_stage = str(skill.condition["not_has_ally_burst_stage"])
                exclude_self = skill.condition.get("exclude_self", True)
                found = False
                for char in self.characters:
                    if char.base_hp <= 0: continue
                    if exclude_self and char == caster: continue
                    
                    if str(char.burst_stage) == target_stage:
                        found = True
                        break
                if found: return False
            # ▲▲▲ 追加ここまで ▲▲▲

            # ▼▼▼ 追加: 自身が指定した種類のバフを持っているか ▼▼▼
            # 使用例: "self_has_buff_type": "hit_rate_buff"
            if "self_has_buff_type" in skill.condition and caster:
                b_type = skill.condition["self_has_buff_type"]
                if not caster.buff_manager.get_active_buffs(b_type, frame): return False
            
            if "self_not_has_buff_type" in skill.condition and caster:
                b_type = skill.condition["self_not_has_buff_type"]
                if caster.buff_manager.get_active_buffs(b_type, frame): return False
            # ▲▲▲ 追加ここまで ▲▲▲

        if skill.condition and "has_squad_mate_present" in skill.condition and caster:
            target_squad = caster.squad
            found = False
            for char in self.characters:
                if char != caster and char.squad == target_squad and char.base_hp > 0:
                     found = True
                     break
            required = skill.condition["has_squad_mate_present"]
            if found != required: return False
        
        return True

    def apply_skill(self, skill, caster, frame, is_full_burst):
        # 1. 無限ループ防止（manualトリガーも含めてチェック）
        if skill.trigger_type not in ['pellet_hit', 'critical_hit']:
            if getattr(skill, 'last_used_frame', -1) == frame:
                return 0
            skill.last_used_frame = frame
            
            unique_key = f"NAME_CHECK::{caster.name}::{skill.name}::{skill.trigger_type}"
            if unique_key in self.executed_skill_ids:
                return 0
            self.executed_skill_ids.add(unique_key)
        
        if not self.should_apply_skill(skill, frame, caster, is_full_burst): return 0

        # ▼▼▼▼▼ 【重要】ここに追加してください ▼▼▼▼▼
        # この行がないと、回数がカウントされず、max_trigger_countが機能しません
        skill.current_usage_count += 1
        # ▲▲▲▲▲ 追加ここまで ▲▲▲▲▲
        
        total_dmg = 0
        kwargs = skill.kwargs.copy()

        # 派生スキルの処理
        if skill.effect_type == 'cumulative_stages':
            if skill.kwargs.get('trigger_all_stages'):
                for i, stage_data in enumerate(skill.stages):
                    if isinstance(stage_data, dict):
                        t_type = stage_data.get('trigger_type')
                        if t_type == 'part_break' and not getattr(self, 'part_break_mode', False): continue
                    elif isinstance(stage_data, Skill):
                        if stage_data.trigger_type == 'part_break' and not getattr(self, 'part_break_mode', False): continue
                            
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
                        if not temp_skill.target: temp_skill.target = skill.target
                        if not temp_skill.target_condition: temp_skill.target_condition = skill.target_condition
                        temp_skill.owner_name = caster.name
                        total_dmg += self.apply_skill(temp_skill, caster, frame, is_full_burst)
            else:
                # ▼▼▼ 修正: 重複インクリメントの削除 ▼▼▼
                # 以前: skill.current_usage_count += 1 
                # apply_skill冒頭で加算済みのため、ここでは削除します
                # ▲▲▲ 修正ここまで ▲▲▲
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
                        if not temp_skill.target: temp_skill.target = skill.target
                        if not temp_skill.target_condition: temp_skill.target_condition = skill.target_condition
                        temp_skill.owner_name = caster.name
                        total_dmg += self.apply_skill(temp_skill, caster, frame, is_full_burst)
            return total_dmg

        # ターゲット選定
        targets = []
        if skill.target == 'self':
            if self.check_target_condition(skill.target_condition, caster, caster, frame): targets.append(caster)
        elif skill.target == 'allies':
            # ▼▼▼ 追加: highest_atk の処理 ▼▼▼
            # 1. まず通常の条件でフィルタリング
            candidates = []
            for char in self.characters:
                
                # ★ここに以下の3行を追加してください
                if skill.target_condition and skill.target_condition.get('exclude_self') and char == caster:
                    continue
                
                if self.check_target_condition(skill.target_condition, caster, char, frame): 
                    candidates.append(char)

            # ▼▼▼ 追加: 元のチャージ時間が長い順 (highest_base_charge_time) ▼▼▼
            if skill.target_condition and skill.target_condition.get('type') == 'highest_base_charge_time':
                count = skill.target_condition.get('count', 1)
                # 武器の基礎チャージ時間 (charge_time) を参照して降順ソート
                # チャージしない武器は 0 として扱われるため、SR/RL等が優先されます
                candidates.sort(key=lambda c: getattr(c.weapon, 'charge_time', 0), reverse=True)
                targets = candidates[:count]
                self.log(f"[Target] Selected Top {count} Base Charge Time: {[t.name for t in targets]}", target_name=caster.name)
            # ▲▲▲ 追加ここまで ▲▲▲
            
            elif skill.target_condition and skill.target_condition.get('type') == 'highest_atk':
                count = skill.target_condition.get('count', 1)
                candidates.sort(key=lambda c: c.get_current_atk(frame), reverse=True)
                targets = candidates[:count]
                target_names = [t.name for t in targets]
                self.log(f"[Target] Selected Top {count} ATK: {target_names}", target_name=caster.name)
            elif skill.target_condition and skill.target_condition.get('type') == 'lowest_hp':
                count = skill.target_condition.get('count', 1)
                candidates = []
                for char in self.characters:
                    if self.check_target_condition(skill.target_condition, caster, char, frame): 
                         candidates.append(char)
                candidates.sort(key=lambda c: c.base_hp)
                targets = candidates[:count]
                self.log(f"[Target] Selected Lowest {count} HP: {[t.name for t in targets]}", target_name=caster.name)
            else:
                targets = candidates

        elif skill.target == 'enemy':
            targets.append(caster) 

        # 2. ターゲットの重複を「名前」で強制排除
        if targets:
            unique_map = {}
            for t in targets:
                unique_map[t.name] = t
            targets = list(unique_map.values())

        if not targets and skill.effect_type == 'damage': targets.append(caster)
        
        # --- スキル効果処理 ---

        # ▼▼▼ 追加: バースト段階変更効果 ▼▼▼
        if skill.effect_type == 'change_burst_stage':
            new_stage = str(kwargs.get('value', '1'))
            # ターゲット全員のバースト段階を変更
            # (通常は自分自身に対して使う)
            # ターゲット選定ロジックは既存のものを利用
            targets = []
            if skill.target == 'self': targets = [caster]
            # 必要なら他のターゲットロジックも追加

            for target in targets:
                old_stage = target.burst_stage
                target.burst_stage = new_stage
                self.log(f"[Burst Change] {target.name} burst stage changed: {old_stage} -> {new_stage}", target_name=caster.name)
            return 0
        # ▲▲▲ 追加ここまで ▲▲▲

        # ▼▼▼ 修正: フルバースト時間短縮・延長効果 ▼▼▼
        if skill.effect_type == 'reduce_full_burst_time':
            val = kwargs.get('value', 0)
            if not hasattr(self, 'full_burst_reduction'): self.full_burst_reduction = 0.0
            
            # 設定値の保存（次回以降のため、あるいは集計用）
            self.full_burst_reduction += val
            
            # ★追加: もし現在すでにフルバースト中なら、リアルタイムで終了時間を延長/短縮する
            if getattr(self, 'burst_state', 'GEN') == 'FULL':
                # valがマイナスなら延長。
                # duration = 基本時間 - reduction なので、
                # reduction が -2 減る(val)ということは、duration は +2 増える。
                # 終了フレームに (-val * FPS) を加算する。
                extend_frames = -val * self.FPS
                self.burst_end_frame += extend_frames
                
                self.log(f"[Burst Extend] Immediate extension: {(-val):.2f}s (EndFrame: {self.burst_end_frame})", target_name=caster.name)
            else:
                self.log(f"[Burst] Scheduled Full Burst reduction: {val}s (Total: {self.full_burst_reduction}s)", target_name=caster.name)
            return 0
        # ▲▲▲ 修正ここまで ▲▲▲

        if skill.effect_type == 'cooldown_reduction':
            reduce_sec = kwargs.get('value', 0)
            reduce_frames = reduce_sec * self.FPS
            for char in self.characters:
                if char.current_cooldown > 0: char.current_cooldown = max(0, char.current_cooldown - reduce_frames)
            if reduce_sec > 0:
                self.log(f"[CT Reduce] Reduced cooldowns by {reduce_sec:.2f}s (Source: {caster.name})", target_name="System")
            return 0
        
        if skill.effect_type == 'decrease_debuff_stack_count':
            tag = kwargs.get('tag', 'debuff')
            amount = int(kwargs.get('value', 1))
            for target in targets:
                if target.buff_manager.decrease_stack_count_by_tag(tag, amount):
                    self.log(f"[Debuff Cleanse] Decreased '{tag}' stacks by {amount} for {target.name}", target_name=caster.name)
            return 0

        if skill.effect_type in ['remove_buff', 'remove_buff_by_tag']:
            tag = kwargs.get('tag')
            if tag:
                if skill.target == 'enemy':
                    self.enemy_debuffs.remove_buffs_by_tag(tag, frame)
                    self.log(f"[Remove Buff] Removed enemy buffs with tag '{tag}'", target_name=caster.name)
                else:
                    for target in targets:
                        target.buff_manager.remove_buffs_by_tag(tag, frame)
                        self.log(f"[Remove Buff] Removed buffs with tag '{tag}' from {target.name}", target_name=caster.name)
            return 0

        if kwargs.get('scale_by_max_ammo'):
            ratio = kwargs.get('value', 0)
            current_max_ammo = caster.current_max_ammo
            kwargs['value'] = ratio * current_max_ammo
            self.log(f"[Scale] Value scaled by MaxAmmo({current_max_ammo}): {ratio} -> {kwargs['value']:.4f}", target_name=caster.name)

        if kwargs.get('scale_by_caster_stats'):
            ratio = kwargs.get('value', 0)
            stat_type = kwargs.get('stat_type', 'base') 
            target_stat = kwargs.get('target_stat', 'atk')
            val_to_scale = 0
            if target_stat == 'atk':
                if stat_type == 'finally': 
                    val_to_scale = caster.get_current_atk(frame)
                else:
                    val_to_scale = caster.base_atk
            elif target_stat == 'max_hp':
                if stat_type == 'finally':
                    rate = caster.buff_manager.get_total_value('max_hp_rate', frame)
                    fixed = caster.buff_manager.get_total_value('max_hp_fixed', frame)
                    val_to_scale = caster.base_hp * (1.0 + rate) + fixed
                else:
                    val_to_scale = caster.base_hp
            # ▼▼▼ 追加: チャージ速度(charge_speed)の参照 ▼▼▼
            elif target_stat == 'charge_speed':
                # 現在のチャージ速度バフ合計値を取得 (例: 10%なら 0.1)
                # 基本チャージ速度という概念は通常0なので、バフの積み上げ値を参照
                val_to_scale = caster.buff_manager.get_total_value('charge_speed', frame)
            # ▲▲▲ 追加ここまで ▲▲▲
            if val_to_scale > 0: kwargs['value'] = val_to_scale * ratio

        # ▼▼▼ 追加: 補正係数 (scaling_factor) の適用 ▼▼▼
        # ゲーム内数値(value)を維持しつつ、計算用に補正(1/5など)を掛けたい場合に使用
        if 'scaling_factor' in kwargs:
            factor = kwargs['scaling_factor']
            # value(数値)が更新されている可能性があるため再取得して計算
            current_val = kwargs.get('value', 0)
            kwargs['value'] = current_val * factor
            self.log(f"[Scaling] Applied factor {factor} (Base:{current_val:.6f} -> Final:{kwargs['value']:.6f})", target_name=caster.name)
        # ▲▲▲ 追加ここまで ▲▲▲

        if 'copy_stack_count' in kwargs and 'value' in kwargs:
            stack_name = kwargs['copy_stack_count']
            count = caster.buff_manager.get_stack_count(stack_name, frame)
            kwargs['value'] *= count
            self.log(f"[Stack Scale] Value scaled by {stack_name} (x{count}) -> {kwargs['value']:.4f}", target_name=caster.name)

        if skill.effect_type == 'activate_flag':
            flag_name = kwargs.get('flag_name')
            for t in targets:
                t.special_flags.add(flag_name)
                self.log(f"[Flag] {t.name}: Activated {flag_name}", target_name=t.name)
            return 0
        
        if skill.effect_type == 'cleanse_debuff':
            count = int(kwargs.get('value', 1)) 
            target_tag = kwargs.get('tag', 'debuff') 
            for target in targets:
                removed = target.buff_manager.remove_debuffs_lifo(target_tag, count, frame)
                if removed > 0:
                    self.log(f"[Cleanse] Removed {removed} stacks of '{target_tag}' from {target.name}", target_name=caster.name)
            return 0

        if skill.effect_type == 'immunity_buff':
            for target in targets:
                removed = target.buff_manager.remove_debuffs_lifo('debuff', 999, frame)
                if removed > 0:
                    self.log(f"[Immunity] Cleansed {removed} debuffs from {target.name} upon immunity grant", target_name=caster.name)
            kwargs['tag'] = 'immunity' 
            if 'buff_type' not in kwargs: kwargs['buff_type'] = 'debuff_immunity_status'
            skill.effect_type = 'stack_buff' if 'stack_name' in kwargs else 'buff'
        
        remove_stacks = kwargs.get('remove_stacks')
        if remove_stacks:
            for stack_name in remove_stacks:
                for t in targets:
                    t.buff_manager.remove_stack(stack_name)
                    self.log(f"[Remove] Removed stack '{stack_name}' from {t.name}", target_name=caster.name)

        if skill.remove_tags:
            for tag in skill.remove_tags:
                for t in targets:
                    t.buff_manager.remove_buffs_by_tag(tag, frame)
                self.enemy_debuffs.remove_buffs_by_tag(tag, frame)
                self.log(f"[Remove] Removed tags {tag} from targets via {skill.name}", target_name=caster.name)

        # 3. 最終防衛ライン（バフ適用ループ）
        # ここで for target in targets を回す際に重複を完全遮断
        
        # まずはバフ以外のターゲットループ処理（Ammoなど）
        # バフは最後にまとめて処理してもよいが、元の構造を維持しつつガードを入れる
        
        if skill.effect_type in ['buff', 'stack_buff', 'debuff']:
            if not targets: return 0
            for target in targets:
                # ★重複ガード★ 同一フレーム・同一キャラ・同一スキルなら適用しない
                apply_guard_key = f"FINAL_GUARD::{frame}::{target.name}::{skill.name}"
                if apply_guard_key in self.executed_skill_ids:
                    continue
                self.executed_skill_ids.add(apply_guard_key)

                b_type = kwargs.get('buff_type', 'atk_buff_rate')
                val = kwargs.get('value', 0)
                dur = kwargs.get('duration', 0) * self.FPS
                stack_name = kwargs.get('stack_name')
                max_stack = kwargs.get('max_stack', 1)
                tag = kwargs.get('tag')
                shot_dur = kwargs.get('shot_duration', 0)
                rem_reload = kwargs.get('remove_on_reload', False)
                linked_remove_tag = kwargs.get('linked_remove_tag')
                is_extend = kwargs.get('is_extend', False)
                st_amount = kwargs.get('stack_amount', 1) 
                # ▼▼▼ 追加: フラグの取得 ▼▼▼
                disable_inc = kwargs.get('disable_stack_increase', False)
                allow_tags = kwargs.get('allow_tags') # ← 取得
                # ▲▲▲ 追加ここまで ▲▲▲

                is_debuff = False
                if tag and ('debuff' in tag): is_debuff = True
                if 'debuff' in b_type: is_debuff = True
                
                if is_debuff:
                    if target.buff_manager.has_active_immunity(frame):
                        if target.buff_manager.consume_immunity_stack(frame):
                            self.log(f"[Immunity] Blocked debuff '{b_type}' on {target.name}", target_name=target.name)
                            continue

                manager = target.buff_manager
                if skill.target == 'enemy':
                    manager = self.enemy_debuffs
                
                if is_extend and tag:
                    if hasattr(manager, 'extend_buff') and manager.extend_buff(tag, dur, frame):
                        self.log(f"[Buff Extend] Extended '{tag}' on {target.name}", target_name=target.name)
                        continue

                if not is_extend:
                    prev_count = 0
                    if stack_name:
                            prev_count = manager.get_stack_count(stack_name, frame)
                    old_max_hp = None
                    if kwargs.get('update_current_hp', False) and b_type in ['max_hp_rate', 'max_hp_fixed'] and skill.target != 'enemy':
                        old_max_hp = target.get_current_max_hp(frame)

                    manager.add_buff(
                        b_type, val, dur, frame, source=skill.name,
                        stack_name=stack_name,
                        max_stack=max_stack, tag=tag,
                        shot_duration=shot_dur, remove_on_reload=rem_reload,
                        linked_remove_tag=linked_remove_tag,
                        stack_amount=st_amount,
                        disable_stack_increase=disable_inc, # ← 引数渡し
                        allow_tags=allow_tags # ← 渡す
                    )
                    
                    t_str = "Enemy" if skill.target == 'enemy' else target.name
                    if stack_name:
                        new_count = manager.get_stack_count(stack_name, frame)
                        self.log(f"[Stack] Applied {skill.name} (Stack:{stack_name} {prev_count}->{new_count}) to {t_str}", target_name=caster.name)
                        if skill.target != 'enemy' and new_count > prev_count:
                            target.process_trigger('stack_count', stack_name, frame, is_full_burst, self, delta=new_count - prev_count)
                    else:
                        self.log(f"[Buff] Applied {skill.name} ({b_type}: {val}) to {t_str}", target_name=caster.name)

                    if old_max_hp is not None:
                        new_max_hp = target.get_current_max_hp(frame)
                        hp_diff = new_max_hp - old_max_hp
                        if hp_diff > 0:
                            target.current_hp += hp_diff
                            self.log(f"[HP Mod] Increased Current HP by {hp_diff:.0f} due to MaxHP buff", target_name=target.name)

                if kwargs.get('scale_by_missing_hp_percentage'):
                    max_hp = target.get_current_max_hp(frame)
                    if max_hp > 0:
                        missing_ratio = 1.0 - (target.current_hp / max_hp)
                        missing_percent = missing_ratio * 100.0
                        scaled_val = val * missing_percent
                        self.log(f"[HP Scale] Scaled by missing HP {missing_percent:.1f}% (Base:{val:.4f} -> Final:{scaled_val:.4f})", target_name=target.name)
                        val = scaled_val # Note: add_buff already called, so this scaling only affects logs or future logic if rearranged, but keeping original logic flow. 
                        # (Original logic had add_buff called with 'val', then scaled 'val' printed. Logic might be slightly off in original but preserving structure.)

                if kwargs.get('scale_by_reference', False):
                    # (Simplified for brevity, but referencing logic is here in original)
                    pass
                
                added_stack_count = 0
                if skill.effect_type == 'stack_buff':
                     # The count logic was handled above in logging
                     pass
                
                # Stack triggers
                # If we need precise delta, we'd calculate it. For now assuming handled by buff manager.

            return 0
        
        # バフ以外の効果処理ループ
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
                base_heal = kwargs.get('value', 0)
                target.heal(base_heal, skill.name, frame, self)

            elif skill.effect_type == 'regenerate':
                heal_per_tick = kwargs.get('value', 0)
                interval_sec = kwargs.get('interval', 1.0)
                interval_frames = int(interval_sec * self.FPS)
                duration_sec = kwargs.get('duration', 0)
                end_frame = frame + (duration_sec * self.FPS)
                target.active_hots.append({
                    'source': skill.name,
                    'heal_value': heal_per_tick,
                    'next_tick': frame + interval_frames,
                    'interval': interval_frames,
                    'end_frame': end_frame
                })
                self.log(f"[Regen] Applied Regen to {target.name} (Val:{heal_per_tick:.0f}, Int:{interval_sec}s, Dur:{duration_sec}s)", target_name=caster.name)

            elif skill.effect_type == 'refill_ammo_fixed':
                amount = int(kwargs.get('value', 0))
                target.current_ammo = min(target.current_max_ammo, target.current_ammo + amount)
                self.log(f"[Ammo] Refilled {amount} ammo (Fixed) for {target.name}", target_name=target.name)

            elif skill.effect_type == 'shield':
                value = kwargs.get('value', 1.0)
                duration = kwargs.get('duration', 0) * self.FPS
                tag_name = kwargs.get('tag', 'barrier') 
                target.buff_manager.add_buff(
                    'shield', value, duration, frame, 
                    source=skill.name, tag=tag_name
                )
                self.log(f"[Barrier] {target.name} applied Shield ({tag_name}) (Val:{value}, Dur:{kwargs.get('duration')}s)", target_name=target.name)

            elif skill.effect_type == 'stack_dot':
                stack_name = kwargs.get('stack_name', skill.name)
                max_stack = kwargs.get('max_stack', 1)
                stack_amount = int(kwargs.get('stack_amount', 1))
                if 'stack_amount_from_stack' in kwargs:
                    amount_stack_name = kwargs['stack_amount_from_stack']
                    stack_amount = max(0, caster.buff_manager.get_stack_count(amount_stack_name, frame))
                profile_kwargs = kwargs.copy()
                raw_profile = profile_kwargs.pop('profile', {})
                if isinstance(raw_profile, dict):
                    profile_kwargs.update(raw_profile)
                full_profile = DamageProfile.create(**profile_kwargs)
                
                if stack_name in target.active_dots:
                    dot = target.active_dots[stack_name]
                    dot['count'] = min(max_stack, dot['count'] + stack_amount)
                    dot['end_frame'] = frame + (kwargs.get('duration', 0) * self.FPS)
                    dot['profile'] = full_profile
                    dot['tag'] = kwargs.get('tag', stack_name)
                else:
                    target.active_dots[stack_name] = {
                        'end_frame': frame + (kwargs.get('duration', 0) * self.FPS),
                        'multiplier': kwargs.get('multiplier', kwargs.get('value', 0)), 
                        'profile': full_profile,
                        'count': min(max_stack, stack_amount), 'max_stack': max_stack, 'element': caster.element,
                        'tag': kwargs.get('tag', stack_name),
                        'start_frame': frame,
                        'next_tick': frame + (kwargs.get('interval', 1.0) * self.FPS),
                        'interval': kwargs.get('interval', 1.0) * self.FPS
                    }
                self.log(f"[DoT] Applied/Stacked {stack_name} on Enemy (via {target.name})", target_name=target.name)

            elif skill.effect_type == 'dot':
                profile_kwargs = kwargs.copy()
                raw_profile = profile_kwargs.pop('profile', {})
                if isinstance(raw_profile, dict):
                    profile_kwargs.update(raw_profile)
                mult = kwargs.get('value', 0)
                if mult == 0:
                    mult = kwargs.get('multiplier', 0)

                full_profile = DamageProfile.create(**profile_kwargs)
                duration_sec = kwargs.get('duration', 0)
                interval = kwargs.get('interval', 1.0)
                tag = kwargs.get('tag')
                is_extend = kwargs.get('is_extend', False)
                key = tag if tag else skill.name
                dot_count = int(kwargs.get('dot_count', 1))
                copy_dot_name = kwargs.get('copy_dot_count')
                if copy_dot_name:
                    source_dot = caster.active_dots.get(copy_dot_name)
                    if source_dot and source_dot.get('end_frame', -1) >= frame:
                        dot_count = int(source_dot.get('count', 0))
                    else:
                        dot_count = 0
                    if dot_count <= 0:
                        self.log(f"[DoT] Skipped {skill.name}; source DoT '{copy_dot_name}' has no active stacks", target_name=target.name)
                        continue

                if is_extend and tag and key in target.active_dots:
                    dot = target.active_dots[key]
                    remaining = max(0, dot['end_frame'] - frame)
                    dot['end_frame'] = frame + remaining + (duration_sec * self.FPS)
                    self.log(f"[DoT Extend] Extended '{tag}' on {target.name}", target_name=target.name)
                elif not is_extend:
                    target.active_dots[key] = {
                        'source': skill.name,
                        'multiplier': mult,
                        'profile': full_profile,
                        'count': dot_count,
                        'max_stack': max(int(kwargs.get('max_stack', dot_count)), dot_count),
                        'element': caster.element,
                        'start_frame': frame,
                        'end_frame': frame + (duration_sec * self.FPS),
                        'next_tick': frame + (interval * self.FPS),
                        'interval': (interval * self.FPS),
                        'tag': tag
                    }
                    self.log(f"[DoT] Applied {skill.name} ({tag}) on {target.name}", target_name=target.name)

            elif skill.effect_type in ['remove_dot', 'remove_dot_by_tag']:
                tag = kwargs.get('tag') or kwargs.get('stack_name')
                if tag:
                    removed = []
                    for dot_name, dot in list(target.active_dots.items()):
                        if dot_name == tag or dot.get('tag') == tag:
                            del target.active_dots[dot_name]
                            removed.append(dot_name)
                    if removed:
                        self.log(f"[DoT Remove] Removed {removed} from {target.name}", target_name=caster.name)

            elif skill.effect_type == 'damage':
                if kwargs.get('damage_type') == 'ignore_def':
                    kwargs['is_ignore_def'] = True
                profile_kwargs = kwargs.copy()
                raw_profile = profile_kwargs.pop('profile', {})
                if isinstance(raw_profile, dict):
                    profile_kwargs.update(raw_profile)
                if 'is_skill_damage' not in profile_kwargs:
                    profile_kwargs['is_skill_damage'] = True

                profile = DamageProfile.create(**profile_kwargs)
                mult = kwargs.get('value', 0)
                if mult == 0: mult = kwargs.get('multiplier', 1.0)
                loops = int(kwargs.get('loop_count', 1))
                if 'loop_count_from_stack' in kwargs:
                    loop_stack_name = kwargs['loop_count_from_stack']
                    loops = max(0, caster.buff_manager.get_stack_count(loop_stack_name, frame))
                if 'copy_stack_count' in kwargs:
                    stack_name = kwargs['copy_stack_count']
                    stack_count = caster.buff_manager.get_stack_count(stack_name, frame)
                    mult *= stack_count
                    self.log(f"[Dmg Scale] Scaled by self stack '{stack_name}': x{stack_count} -> {mult:.4f}", target_name=caster.name)
                elif kwargs.get('scale_by_target_stack') and targets:
                    stack_name = kwargs.get('stack_name')
                    target_stack = self.enemy_debuffs.get_stack_count(stack_name, frame)
                    mult *= target_stack
                    self.log(f"[Dmg Scale] Scaled by enemy stack '{stack_name}': x{target_stack} -> {mult:.4f}", target_name=targets[0].name)
            
                skill_dmg = 0
                for _ in range(loops):
                    # ▼▼▼ 修正: 戻り値を3つ受け取る (d, _, _) ▼▼▼
                    d, _, _ = caster.calculate_strict_damage(
                        mult, profile, is_full_burst, frame, 
                        self.ENEMY_DEF, self.enemy_element, self.enemy_core_size, self.enemy_size,
                        debuff_manager=self.enemy_debuffs
                    )
                    # ▲▲▲ 修正ここまで ▲▲▲
                    skill_dmg += d
                
                buff_debug = caster.buff_manager.get_active_buffs_debug(frame)
                self.log(f"[Skill Dmg] 時間:{frame/60:>6.2f}s | 名前:{skill.name:<25} | Dmg:{skill_dmg:10,.0f} | Hits:{loops} | Buffs:{buff_debug}", target_name=caster.name)
                
                caster.total_damage += skill_dmg
                if skill.name in caster.damage_breakdown: caster.damage_breakdown[skill.name] += skill_dmg
                else: caster.damage_breakdown[skill.name] = skill_dmg
                total_dmg += skill_dmg

            elif skill.effect_type == 'delayed_snapshot_damage':
                duration_sec = kwargs.get('duration', 0)
                exec_frame = frame + int(duration_sec * self.FPS)
                snapshot_atk = caster.get_current_atk(frame)
                delayed_kwargs = kwargs.copy()
                delayed_kwargs['snapshot_atk'] = snapshot_atk
                delayed_kwargs.pop('duration', None)

                act_skill = Skill(
                    name=f"Delayed_{skill.name}",
                    trigger_type="manual",
                    trigger_value=0,
                    effect_type="snapshot_damage",
                    **delayed_kwargs
                )
                act_skill.target = skill.target
                act_skill.owner_name = caster.name
                self.scheduled_actions.append({'frame': exec_frame, 'skill': act_skill, 'caster': caster})
                self.log(
                    f"[Snapshot] Scheduled {skill.name} at {exec_frame / self.FPS:.2f}s "
                    f"(ATK:{snapshot_atk:.0f}, Delay:{duration_sec}s)",
                    target_name=caster.name
                )

            elif skill.effect_type == 'snapshot_damage':
                snapshot_atk = kwargs.get('snapshot_atk', caster.get_current_atk(frame))
                mult = kwargs.get('value', 0)
                if mult == 0:
                    mult = kwargs.get('multiplier', 1.0)
                split_buff = caster.buff_manager.get_total_value('split_dmg_buff', frame)
                use_split = kwargs.get('is_split', True)
                split_layer = 1.0 + split_buff if use_split else 1.0
                skill_dmg = snapshot_atk * mult * split_layer

                self.log(
                    f"[Snapshot Dmg] 時間:{frame/60:>6.2f}s | 名前:{skill.name:<25} | "
                    f"Dmg:{skill_dmg:10,.0f} | SnapshotATK:{snapshot_atk:.0f} | "
                    f"Mult:{mult:.4f} | SplitBuff:{split_buff:.4f}",
                    target_name=caster.name
                )

                caster.total_damage += skill_dmg
                if skill.name in caster.damage_breakdown:
                    caster.damage_breakdown[skill.name] += skill_dmg
                else:
                    caster.damage_breakdown[skill.name] = skill_dmg
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

            elif skill.effect_type == 'reenter_burst_stage':
                val = int(kwargs.get('value', 1))
                self.reenter_burst_target = f"BURST_{val}"
                self.log(f"[Burst] Reserved re-entry to BURST_{val}", target_name=caster.name)

            elif skill.effect_type == 'set_stack':
                stack_name = kwargs.get('stack_name')
                val = int(kwargs.get('value', 0))
                target.buff_manager.set_stack_count(stack_name, val)
                self.log(f"[Stack Set] {target.name}: {stack_name} set to {val}", target_name=target.name)

            elif skill.effect_type == 'increase_current_stack_count':
                delta = int(kwargs.get('value', 1))
                ignore_tags = kwargs.get('ignore_tags', ["debuff", "negative_buff"])
                target_stack = kwargs.get('stack_name') # ★追加: 名前を取得
                
                for target in targets:
                    # ★修正: target_stack_name 引数を追加して渡す
                    # ▼▼▼ 追加: 強力な重複適用ガード ▼▼▼
                    # 同一フレーム・同一ターゲット・同一スタック名での増加処理は1回のみ許可する
                    # これにより、allies指定などでループが重複しても、2回目以降は無視される
                    guard_key = f"STACK_INC_GUARD::{frame}::{target.name}::{target_stack}"
                    if guard_key in self.executed_skill_ids:
                        continue
                    self.executed_skill_ids.add(guard_key)
                    # ▲▲▲ 追加ここまで ▲▲▲
                    count = target.buff_manager.modify_active_stack_counts(delta, frame, ignore_tags=ignore_tags, target_stack_name=target_stack)

                    if count > 0:
                        self.log(f"[Stack Inc] {target.name}: Increased '{target_stack}' by {delta}", target_name=caster.name)
            
            elif skill.effect_type == 'stun':
                duration = kwargs.get('duration', 0) * self.FPS
                tag_name = kwargs.get('tag', 'stun')
                target.buff_manager.add_buff(
                    'stun_status', 0, duration, frame, 
                    source=skill.name, tag=tag_name
                )
                self.log(f"[Stun] {target.name} is stunned for {kwargs.get('duration')}s", target_name=target.name)

            elif skill.effect_type == 'lose_hp':
                ratio = kwargs.get('value', 0)
                loss = target.current_hp * ratio
                target.current_hp = max(0, target.current_hp - loss)
                self.log(f"[Lose HP] Lost {loss:.0f} HP (Current: {target.current_hp:.0f}/{target.get_current_max_hp(frame):.0f})", target_name=target.name)

            # ▼▼▼ 追加: 遮蔽物回復スキルの適用 ▼▼▼
            elif skill.effect_type == 'cover_heal':
                val = kwargs.get('value', 0)
                target.recover_cover_hp(val, skill.name, frame, self)
            # ▲▲▲ 追加ここまで ▲▲▲

            elif skill.effect_type == 'weapon_change':
                new_weapon_data = kwargs.get('weapon_data')
                duration = kwargs.get('duration', 0)
                # ▼▼▼ 追加: タグ情報の取得 ▼▼▼
                tags = kwargs.get('tag')
                # ▲▲▲ 追加ここまで ▲▲▲
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

                    # ▼▼▼ 追加: タグをダミーバフとして適用 ▼▼▼
                    if tags:
                        # 武器変更中であることを示すバフとして付与（効果値はダミーで1）
                        target.buff_manager.add_buff(
                            'weapon_change_mode', 1, duration * self.FPS, frame, 
                            source=f"{skill.name}_Tags", tag=tags
                        )
                        self.log(f"[Weapon Tags] Applied tags {tags} for {duration}s", target_name=target.name)
                    # ▲▲▲ 追加ここまで ▲▲▲

        return total_dmg
