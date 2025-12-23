import random

class CharacterSkillMixin:
    def process_trigger(self, trigger_type, val, frame, is_full_burst, simulator, delta=0):
        triggered_skills = []
        for skill in self.skills:
            if getattr(skill, 'last_used_frame', -1) == frame:
                if trigger_type not in ['pellet_hit', 'critical_hit']:
                    continue

            if skill.trigger_type == trigger_type:
                is_triggered = False
                trigger_count = 1

                if trigger_type == 'on_use_burst_skill': is_triggered = True 
                elif trigger_type == 'stack_count':
                    target_stack = skill.kwargs.get('stack_name')
                    current_count = self.buff_manager.get_stack_count(target_stack, frame)
                    prev_count = current_count - delta
                    if prev_count < skill.trigger_value <= current_count:
                        is_triggered = True
                elif trigger_type == 'part_break': is_triggered = True
                # ▼▼▼ 修正: trigger_value<=0 の除外対象に full_charge_count を追加 ▼▼▼
                elif skill.trigger_value <= 0 and trigger_type in ['shot_count', 'full_charge_count', 'time_interval', 'pellet_hit', 'critical_hit']: is_triggered = False 
                # ▲▲▲ 修正ここまで ▲▲▲
                elif trigger_type == 'shot_count' and val > 0 and val % skill.trigger_value == 0: is_triggered = True

                # ▼▼▼ 追加: フルチャージ攻撃回数トリガー ▼▼▼
                elif trigger_type == 'full_charge_count' and val > 0 and val % skill.trigger_value == 0: is_triggered = True
                # ▲▲▲ 追加ここまで ▲▲▲
                elif trigger_type == 'time_interval' and val % (skill.trigger_value * simulator.FPS) == 0: is_triggered = True
                elif trigger_type == 'ammo_empty' and val == 0: is_triggered = True
                elif trigger_type == 'on_burst_enter': is_triggered = True
                # ▼▼▼ 追加: 新規バースト段階トリガーの判定 ▼▼▼
                elif trigger_type == 'on_burst_1_enter': is_triggered = True
                elif trigger_type == 'on_burst_2_enter': is_triggered = True
                # ▲▲▲ 追加ここまで ▲▲▲
                elif trigger_type == 'on_burst_3_enter': is_triggered = True
                elif trigger_type == 'on_start': is_triggered = True
                elif trigger_type == 'on_burst_end': is_triggered = True
                
                elif trigger_type in ['pellet_hit', 'critical_hit']:
                    if skill.trigger_value > 0:
                        prev_count = (val - delta) // skill.trigger_value
                        curr_count = val // skill.trigger_value
                        count_diff = curr_count - prev_count
                        
                        if count_diff > 0:
                            is_triggered = True
                            trigger_count = count_diff

                elif trigger_type == 'on_receive_heal': is_triggered = True

                # ▼▼▼ 追加: バースト終了後からの経過時間トリガー ▼▼▼
                elif trigger_type == 'interval_after_burst_end':
                    # バースト終了記録があり、かつ現在時刻がそれより後の場合
                    if self.last_burst_end_frame > 0 and frame > self.last_burst_end_frame:
                        elapsed = frame - self.last_burst_end_frame
                        # 指定秒数（trigger_value）ごとに発動
                        interval_frames = skill.trigger_value * simulator.FPS
                        if elapsed % interval_frames == 0:
                            is_triggered = True
                # ▲▲▲ 追加ここまで ▲▲▲

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
                    for _ in range(trigger_count):
                        triggered_skills.append(skill)
        
        total_dmg = 0
        for skill in triggered_skills:
            total_dmg += simulator.apply_skill(skill, self, frame, is_full_burst)
        
        return total_dmg