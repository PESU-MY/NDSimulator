import json

# --- データ定義 ---

class WeaponConfig:
    def __init__(self, data):
        self.name = data.get('name', 'Unknown Weapon')
        
        raw_type = data.get('weapon_type', 'AR')
        self.weapon_class = data.get('weapon_class', raw_type)
        
        self.type = data.get('type', 'RAPID')
        if self.weapon_class == "MG":
            self.type = "MG"
        elif self.weapon_class in ["RL", "SR"]:
            self.type = "CHARGE"
            
        self.element = data.get('element', 'Iron')
        self.burst_stage = str(data.get('burst_stage', '3')) 

        self.multiplier = data.get('multiplier', 1.0)
        self.max_ammo = data.get('max_ammo', 60)
        self.reload_frames = data.get('reload_frames', 60)
        self.windup_frames = data.get('windup_frames', 12)
        self.winddown_frames = data.get('winddown_frames', 10)
        self.pellet_count = data.get('pellet_count', 1)
        self.fire_interval = data.get('fire_interval', 5)
        self.reset_ammo_on_revert = data.get('reset_ammo_on_revert', True)
        
        default_hit_sizes = {
            "RL": 1, "SR": 1, "MG": 1,
            "SMG": 9, "AR": 6, "SG": 20
        }
        self.hit_size = data.get('hit_size', default_hit_sizes.get(self.weapon_class, 5))
        
        self.is_pierce = data.get('is_pierce', False)

        # ▼▼▼ 追加: 爆発・付着フラグの読み込み ▼▼▼
        self.is_explosive = data.get('is_explosive', False)
        self.is_sticky = data.get('is_sticky', False)
        # ▲▲▲ 追加ここまで ▲▲▲
        self.disable_reload_buffs = data.get('disable_reload_buffs', False)
        self.disable_charge_buffs = data.get('disable_charge_buffs', False)
        self.disable_attack_speed_buffs = data.get('disable_attack_speed_buffs', False)
        
        default_charge = 1.0 if self.weapon_class in ["RL", "SR"] else 0
        self.charge_time = data.get('charge_time', default_charge)
        self.charge_mult = data.get('charge_mult', 1.0)
        
        self.mg_warmup_map = []
        self.mg_max_warmup = 0
        
        if self.type == "MG":
            if 'warmup_table' not in data:
                data['warmup_table'] = [[10, 6], [10, 5], [15, 2], [9999, 1]]
            # ▼▼▼ 修正: データ形式の自動判定ロジック ▼▼▼
            # テーブルの先頭が [1, ...], [2, ...] と連番で始まっている場合、
            # 「期間(Duration)」ではなく「弾数インデックス(Shot Index)」とみなして
            # 各段階の期間を「1」として処理する
            is_index_format = False
            table = data['warmup_table']
            if len(table) >= 2 and table[0][0] == 1 and table[1][0] == 2:
                is_index_format = True

            current_sum = 0
            for val, interval in table:
                duration = val
                if is_index_format:
                    duration = 1 # 連番形式なら、各エントリは1発分とみなす
                
                self.mg_warmup_map.append({'start': current_sum, 'interval': interval})
                current_sum += duration
            
            self.mg_max_warmup = current_sum + self.windup_frames
            # ▲▲▲ 修正ここまで ▲▲▲

class DamageProfile:
    @staticmethod
    def create(**kwargs):
        profile = {
            'crit_rate': 0.15,
            'charge_mult': 1.0,
            'is_weapon_attack': False, 'range_bonus_active': False,
            'is_charge_attack': False, 'is_part_damage': False,
            'is_pierce': False, 'is_ignore_def': False,
            'is_dot': False, 'is_sticky': False, 'is_explosive': False,'is_sequential': False,
            'is_split': False, 'is_elemental': False,
            'burst_buff_enabled': True,
            'force_full_burst': False, 
            'is_skill_damage': False,
            'enable_core_hit': False,
            # ▼▼▼ 追加: 特殊スキルダメージフラグ ▼▼▼
            'is_special_skill_damage': False
        }
        if kwargs:
            profile.update(kwargs)
        return profile

class Skill:
    def __init__(self, name, trigger_type, trigger_value=0, effect_type="buff", **kwargs):
        self.name = name
        self.trigger_type = trigger_type
        self.trigger_value = trigger_value
        self.effect_type = effect_type
        self.kwargs = kwargs
        
        self.target = kwargs.get('target', 'self')
        self.target_condition = kwargs.get('target_condition', None)
        
        self.remove_tags = kwargs.get('remove_tags', [])
        self.condition = kwargs.get('condition', None)
        
        self.stages = kwargs.get('stages', [])
        self.max_stage = kwargs.get('max_stage', len(self.stages))
        
        self.sub_effect = kwargs.get('sub_effect', None)
        
        self.current_usage_count = 0
        self.owner_name = None
        
        # --- 追加: 同一フレームでの多重発動防止用 ---
        self.last_used_frame = -1

        # ▼▼▼ 追加: 最大発動回数制限 (戦闘中N回まで) ▼▼▼
        # JSONで "max_trigger_count": 1 と指定すれば、1回発動後に停止する
        self.max_trigger_count = kwargs.get('max_trigger_count', None)
        # ▲▲▲ 追加ここまで ▲▲▲