import os
import shutil
import random
from models import DamageProfile, Skill, WeaponConfig
from buff_manager import BuffManager
from character import Character
from engine_skills import SkillEngineMixin
from engine_burst import BurstEngineMixin

# --- シミュレーターエンジン (統括) ---

class NikkeSimulator(SkillEngineMixin, BurstEngineMixin):
    def __init__(self, characters, burst_rotation, enemy_element="None", enemy_core_size=3.0, enemy_size=5.0, part_break_mode=False, burst_charge_time=5.0, log_file_path="simulation_log.txt"):
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
        self.burst_charge_time = burst_charge_time
        
        # 敵へのデバフ(全員で共有)
        self.enemy_debuffs = BuffManager()
        
        # 1フレーム内で実行されたスキルのIDを記録するセット (多重発動防止用)
        self.executed_skill_ids = set()
        
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

    def tick(self, frame):
        self.executed_skill_ids.clear()
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
        
        # ▼▼▼ 追加: 15秒ごとの定期トリガー (900フレーム) ▼▼▼
        if frame > 0 and frame % (15 * self.FPS) == 0:
            # "trigger_value"は便宜上0
            self.process_trigger_global('interval_15s', frame)
        # ▲▲▲ 追加ここまで ▲▲▲



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
                        
                        self.log(f"[DoT] 時間:{frame/60:>6.2f}s | Source:{name} | Dmg:{dmg:10,.0f} | Stacks:{dot.get('count', 1)}", target_name=char.name)

                        damage_dot += dmg
                    else: del char.active_dots[name]
                char.total_damage += damage_dot
            
            char.process_trigger('time_interval', frame, frame, is_full_burst, self)

            # ▼▼▼ 追加: 変動間隔トリガー (variable_interval) の呼び出し ▼▼▼
            char.process_trigger('variable_interval', frame, frame, is_full_burst, self)
            # ▲▲▲ 追加ここまで ▲▲▲

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