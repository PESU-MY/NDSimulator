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
        
        # ▼▼▼ 修正: スキルリストの重複排除処理を追加 ▼▼▼
        # 同じ名前、同じトリガータイプのスキルが複数ある場合、1つに絞る
        unique_skills = {}
        for s in skills:
            # キーを (スキル名, トリガータイプ) にすることで、同名でもトリガーが違う場合は維持
            key = (s.name, s.trigger_type)
            if key not in unique_skills:
                unique_skills[key] = s
            else:
                # 既に存在する場合、こちらのオブジェクトを採用するか、あるいは無視する
                # 基本的にJSON定義のミスで重複している場合は無視でよい
                pass
        
        self.skills = list(unique_skills.values())
        # ▲▲▲ 修正ここまで ▲▲▲
        
       
        
        self.base_atk = base_atk
        self.base_hp = base_hp

        # ▼▼▼ 追加: 遮蔽物HPの初期化 ▼▼▼
        # 一般的に遮蔽物HPは本体HPと同等とみなす（別途定義がない場合）
        self.cover_hp = self.base_hp
        self.max_cover_hp = self.base_hp

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

    # ▼▼▼ 修正: healメソッド (引数 is_distributed を追加) ▼▼▼
    def heal(self, amount, source_name, frame, simulator, is_distributed=False):
        # 1. 回復分配ロジック (Distribution Logic)
        # 自身が分配バフを持っており、かつこれが「分配後の回復」でない場合に発動
        dist_val = self.buff_manager.get_total_value('distribute_heal_buff', frame)
        
        if dist_val > 0 and not is_distributed:
            # 分配対象者の収集と総バフ量の計算
            targets = []
            total_dist_val = 0
            
            # simulator経由で全キャラを走査
            for char in simulator.characters:
                if char.base_hp <= 0: continue # 戦闘不能者は除外（仕様によるが通常は回復しない）
                
                c_val = char.buff_manager.get_total_value('distribute_heal_buff', frame)
                if c_val > 0:
                    targets.append((char, c_val))
                    total_dist_val += c_val
            
            # 分配実行
            if total_dist_val > 0:
                simulator.log(f"[Heal Dist] Distributing {amount:.0f} heal among {len(targets)} targets (Total Buff: {total_dist_val})", target_name=self.name)
                
                for t_char, t_val in targets:
                    # 配分計算: (個人のバフ量 / 全体のバフ量) * 回復量
                    ratio = t_val / total_dist_val
                    share_amount = amount * ratio
                    
                    # 再帰呼び出し (is_distributed=True で無限ループ防止 & トリガー阻止)
                    t_char.heal(share_amount, source_name, frame, simulator, is_distributed=True)
                
                # 元の回復処理は分配に置き換わったため終了
                return 0

        # 2. 通常の回復処理 (Normal Heal)
        heal_rate = self.buff_manager.get_total_value('heal_effectiveness_buff', frame)
        final_heal = amount * (1.0 + heal_rate)
        if final_heal <= 0: return 0
        
        max_hp = self.get_current_max_hp(frame)
        overflow_rate = self.buff_manager.get_total_value('max_hp_overflow', frame)
        cap_hp = max_hp * (1.0 + overflow_rate)
        
        prev_hp = self.current_hp
        self.current_hp = min(cap_hp, self.current_hp + final_heal)
        actual_heal = self.current_hp - prev_hp
        
        # ログ出力
        dist_tag = " (Distributed)" if is_distributed else ""
        simulator.log(f"[Heal{dist_tag}] {self.name} received heal (Val: {final_heal:.0f} -> Actual: {actual_heal:.0f}) (Src: {source_name}, HP: {self.current_hp:.0f}/{max_hp:.0f})", target_name=self.name)
        
        # 3. トリガー発火判定
        # 分配された回復ではトリガーを発動しない
        if not is_distributed:
            is_fb = (simulator.burst_state == "FULL")
            self.process_trigger('on_receive_heal', actual_heal, frame, is_fb, simulator)
            
        return actual_heal
    # ▲▲▲ 修正ここまで ▲▲▲
    # ▼▼▼ 追加: 遮蔽物HP回復メソッド ▼▼▼
    def recover_cover_hp(self, value, source_name, frame, simulator):
        # 遮蔽物が既に破壊されている(0以下)場合は回復不能とする（「復活」スキルでない限り）
        if self.cover_hp <= 0:
            return 0
            
        # 値が2.0以下なら割合回復、それ以上なら固定値回復と判定
        heal_amount = 0
        if value <= 2.0:
            heal_amount = self.max_cover_hp * value
        else:
            heal_amount = value
            
        prev_cover_hp = self.cover_hp
        self.cover_hp = min(self.max_cover_hp, self.cover_hp + heal_amount)
        actual_heal = self.cover_hp - prev_cover_hp
        
        # ▼▼▼ 修正: if actual_heal > 0: の条件を削除し、回復量が0でも処理を通す ▼▼▼
        # 以前: if actual_heal > 0:
        
        # ログ出力（回復量が0でも「受けた」事実は残す）
        simulator.log(f"[Cover Heal] {self.name} cover repaired (Val: {heal_amount:.0f} -> Actual: {actual_heal:.0f}) (Src: {source_name}, CoverHP: {self.cover_hp:.0f}/{self.max_cover_hp:.0f})", target_name=self.name)
        
        # トリガー発火
        is_fb = (simulator.burst_state == "FULL")
        self.process_trigger('on_receive_cover_heal', actual_heal, frame, is_fb, simulator)
            
        return actual_heal
    # ▲▲▲ 修正ここまで ▲▲▲