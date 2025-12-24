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
        
        self.skills = skills 
        for s in self.skills:
            if not s.owner_name: s.owner_name = self.name
            if not hasattr(s, 'last_used_frame'):
                s.last_used_frame = -1
        
        self.base_atk = base_atk
        self.base_hp = base_hp
        self.element = element
        self.burst_stage = str(burst_stage)
        self.character_class = character_class
        # ▼▼▼ 追加: 部隊情報 ▼▼▼
        self.squad = squad
        # ▲▲▲ 追加ここまで ▲▲▲
        
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