from models import Skill
from buff_manager import BuffManager
from character_stats import CharacterStatsMixin
from character_skill import CharacterSkillMixin
from character_action import CharacterActionMixin

# --- キャラクタークラス ---

class Character(CharacterStatsMixin, CharacterSkillMixin, CharacterActionMixin):
    def __init__(self, name, weapon_config, skills, base_atk, base_hp, element, burst_stage, character_class="Attacker", squad="Unknown", is_dummy=False):
        self.name = name
        self.weapon = weapon_config
        
        # ▼▼▼ 正しい重複排除ブロック（残す） ▼▼▼
        self.skills = []
        seen_skills = set()
        for s in skills:
            # 名前とトリガーが完全に一致するものだけを重複とみなす
            unique_key = (s.name, s.trigger_type)
            if unique_key not in seen_skills:
                self.skills.append(s)
                seen_skills.add(unique_key)
        
        # ▼▼▼ 削除するブロック（ここを削除してください！） ▼▼▼
        # unique_skills = {}
        # for s in skills:
        #     if s.name not in unique_skills:
        #         unique_skills[s.name] = s
        # self.skills = list(unique_skills.values())
        # ▲▲▲▲▲▲
        
        self.base_atk = base_atk
        self.base_hp = base_hp
        self.element = element
        self.burst_stage = str(burst_stage)
        self.character_class = character_class
        # ▼▼▼ 追加: 部隊情報 ▼▼▼
        self.squad = squad
        # ▲▲▲ 追加ここまで ▲▲▲

        # ▼▼▼ 追加: スキルの重複排除 ▼▼▼
        # スキル名が同じものは1つだけ残す
        unique_skills = {}
        for s in skills:
            # 同じ名前のスキルが既にあればスキップ（あるいは上書き）
            if s.name not in unique_skills:
                unique_skills[s.name] = s
        self.skills = list(unique_skills.values())
        # ▲▲▲
        
        self.is_dummy = is_dummy

        self.buff_manager = BuffManager()
        
        self.skill = None 
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
        # ▼▼▼ 追加: フルチャージ攻撃回数の累積カウンタ ▼▼▼
        self.cumulative_full_charge_count = 0
        # ▲▲▲ 追加ここまで ▲▲▲
        self.damage_breakdown = {'Weapon Attack': 0}
        
        self.active_dots = {}
        self.special_flags = set()

        # ▼▼▼ 追加: リジェネ(HoT)の管理用リスト ▼▼▼
        self.active_hots = []

        # 初期状態ではバフなし最大HPとする
        self.current_hp = self.base_hp
        # ▲▲▲

        
        # ▼▼▼ 追加: 自身のバースト(Full Burst)が終了した時刻 ▼▼▼
        self.last_burst_end_frame = -1
        # ▲▲▲ 追加ここまで ▲▲▲

        def register_breakdown(skill_obj):
            if skill_obj.effect_type in ['damage', 'dot']:
                self.damage_breakdown[skill_obj.name] = 0
            if skill_obj.effect_type == 'cumulative_stages':
                for stage in skill_obj.stages:
                    if isinstance(stage, Skill): register_breakdown(stage)

        # ▼▼▼ 追加: バーストスキルのクールタイム設定を保持 ▼▼▼
        self.burst_skill_cooldown = None
        for s in self.skills:
            if s.trigger_type == 'on_use_burst_skill':
                # JSONのパラメータはkwargsに入っている
                cd = s.kwargs.get('cooldown_time') or s.kwargs.get('cooldown')
                if cd is not None:
                    self.burst_skill_cooldown = float(cd)
        # ▲▲▲ 追加ここまで ▲▲▲
        
        self.original_weapon = self.weapon
        self.is_weapon_changed = False
        self.weapon_change_end_frame = 0
        self.weapon_change_ammo_specified = False

    def heal(self, amount, source_name, frame, simulator):
        heal_rate = self.buff_manager.get_total_value('heal_effectiveness_buff', frame)
        final_heal = amount * (1.0 + heal_rate)
        if final_heal <= 0: return 0
        
        max_hp = self.get_current_max_hp(frame)
        overflow_rate = self.buff_manager.get_total_value('max_hp_overflow', frame)
        cap_hp = max_hp * (1.0 + overflow_rate)
        
        prev_hp = self.current_hp
        self.current_hp = min(cap_hp, self.current_hp + final_heal)
        actual_heal = self.current_hp - prev_hp
        
        # ▼▼▼ 修正: HPが増えなくても(0でも)トリガーを発火させる ▼▼▼
        # ログは回復が発生したことを記録
        simulator.log(f"[Heal] {self.name} received heal (Val: {final_heal:.0f} -> Actual: {actual_heal:.0f}) (Src: {source_name}, HP: {self.current_hp:.0f}/{max_hp:.0f})", target_name=self.name)
        
        is_fb = (simulator.burst_state == "FULL")
        self.process_trigger('on_receive_heal', actual_heal, frame, is_fb, simulator)
        # ▲▲▲
        #     
        return actual_heal
    # ▲▲▲