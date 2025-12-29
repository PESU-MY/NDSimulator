import random
from utils import round_half_up  # ★追加

class CharacterStatsMixin:
    def get_current_atk(self, frame):
        atk_rate = self.buff_manager.get_total_value('atk_buff_rate', frame)
        atk_fixed = self.buff_manager.get_total_value('atk_buff_fixed', frame)
        hp_conv_rate = self.buff_manager.get_total_value('conversion_hp_to_atk', frame)
        if hp_conv_rate > 0:
            max_hp_rate = self.buff_manager.get_total_value('max_hp_rate', frame)
            current_max_hp = self.base_hp * (1.0 + max_hp_rate)
            atk_fixed += current_max_hp * hp_conv_rate
        return (self.base_atk * (1.0 + atk_rate)) + atk_fixed

    def calculate_strict_damage(self, mult, profile, is_full_burst, frame, enemy_def=0, enemy_element="None", enemy_core_size=3.0, enemy_size=5.0, debuff_manager=None):
        # 1. 攻撃力計算
        final_atk = self.get_current_atk(frame)
        
        # 2. 防御力・貫通計算
        # ▼▼▼ 修正: self（攻撃者）の防御デバフ参照を削除 ▼▼▼
        def_debuff = 0
        if debuff_manager:
            def_debuff = debuff_manager.get_total_value('def_debuff', frame)
        # ▲▲▲ 修正ここまで ▲▲▲
            
        # ▼▼▼ 修正: 通常攻撃の防御無視判定を追加 ▼▼▼
        # profile自体に無視フラグがある(スキル用)か、
        # またはバフマネージャーに "ignore_def_active" タグがある場合に防御無視
        is_ignoring = profile['is_ignore_def']
        if self.buff_manager.has_active_tag("ignore_def_active", frame):
            is_ignoring = True
            
        effective_def = enemy_def * (1.0 - def_debuff) if not is_ignoring else 0
        # ▲▲▲ 修正ここまで ▲▲▲
        raw_damage_diff = final_atk - effective_def
        if raw_damage_diff <= 0: return 1.0, False
        layer_atk = raw_damage_diff
        
        # 3. 武器倍率・スキル倍率
        weapon_buff = self.buff_manager.get_total_value('weapon_dmg_buff', frame) if profile['is_weapon_attack'] else 0.0
        layer_weapon = mult * (1.0 + weapon_buff)
        
        # 4. クリティカル計算 (バケット1)
        bucket_crit_bonus = 0.0
        
        # ▼▼▼ フルバースト補正 (ここを直接加算に修正) ▼▼▼
        is_fb_active = False
        if profile['burst_buff_enabled']:
            # 条件を満たしたら必ず 0.5 を足す
            if is_full_burst or profile.get('force_full_burst', False): 
                bucket_crit_bonus += 0.50
                is_fb_active = True
        # ▲▲▲
        
        # 距離ボーナス
        if profile['range_bonus_active']: bucket_crit_bonus += 0.30
        
        # 命中・コアヒット判定
        base_hit_size = self.weapon.hit_size
        hit_rate_buff = self.buff_manager.get_total_value('hit_rate_buff', frame)
        current_hit_size = max(0.01, base_hit_size * (1.0 - hit_rate_buff))
        hit_prob = min(1.0, (enemy_size / current_hit_size) ** 2)
        
        can_core_hit = profile.get('is_weapon_attack', False) or profile.get('enable_core_hit', False)
        is_core = False
        if can_core_hit:
            fixed_core_rate = self.buff_manager.get_total_value('core_hit_rate_fixed', frame)
            if fixed_core_rate > 0: core_prob = 1.0
            else: core_prob = min(1.0, (enemy_core_size / current_hit_size) ** 2)
            if core_prob > hit_prob: core_prob = hit_prob
            is_core = random.random() < (core_prob / hit_prob)

        is_hit = random.random() < hit_prob
        if not is_hit: return 0.0, False
        
        if is_core:
            core_dmg_buff = self.buff_manager.get_total_value('core_dmg_buff', frame)
            bucket_crit_bonus += (1.0 + core_dmg_buff)
            
        # クリティカル判定
        crit_rate = profile['crit_rate'] + self.buff_manager.get_total_value('crit_rate_buff', frame)
        is_crit_hit = False
        if random.random() < crit_rate or profile.get('force_critical', False):
            crit_dmg_buff = self.buff_manager.get_total_value('crit_dmg_buff', frame)
            bucket_crit_bonus += (0.50 + crit_dmg_buff)
            is_crit_hit = True
        
        # 最終的なクリティカルレイヤー倍率
        layer_crit = 1.0 + bucket_crit_bonus
        
        # 5. チャージ計算
        layer_charge = 1.0
        if profile['is_charge_attack']:
            charge_ratio_buff = self.buff_manager.get_total_value('charge_ratio_buff', frame)
            charge_dmg_buff = self.buff_manager.get_total_value('charge_dmg_buff', frame)
            layer_charge = (profile['charge_mult'] * (1.0 + charge_ratio_buff)) + charge_dmg_buff
            
        # 6. ダメージバフ計算 (バケット2)
        bucket_dmg = 0.0
        bucket_dmg += self.buff_manager.get_total_value('atk_dmg_buff', frame)
        if profile['is_part_damage']: bucket_dmg += self.buff_manager.get_total_value('part_dmg_buff', frame)
        
        is_pierce_buff = self.buff_manager.get_total_value('is_pierce', frame)
        if profile['is_pierce'] or is_pierce_buff > 0: 
            bucket_dmg += self.buff_manager.get_total_value('pierce_dmg_buff', frame)
            
        if profile['is_ignore_def']: 
            bucket_dmg += self.buff_manager.get_total_value('ignore_def_dmg_buff', frame)
            
        if profile['is_dot']: bucket_dmg += self.buff_manager.get_total_value('dot_dmg_buff', frame)
        if profile['burst_buff_enabled'] and (is_full_burst or profile.get('force_full_burst', False)):
             bucket_dmg += self.buff_manager.get_total_value('burst_dmg_buff', frame)
        
        layer_dmg = 1.0 + bucket_dmg
        
        # 7. 被ダメージデバフ
        # ▼▼▼ 修正: self（攻撃者）の被ダメデバフを参照していたのを削除 ▼▼▼
        # 以前: taken_dmg_val = self.buff_manager.get_total_value('taken_dmg_debuff', frame)
        
        taken_dmg_val = 0
        if debuff_manager:
            taken_dmg_val += debuff_manager.get_total_value('taken_dmg_debuff', frame)
        layer_taken = 1.0 + taken_dmg_val
        
        # ▲▲▲ 修正ここまで ▲▲▲
        
        # 8. その他レイヤー
        layer_split = 1.0
        if profile['is_split']: layer_split += self.buff_manager.get_total_value('split_dmg_buff', frame)
        
        layer_elem = 1.0
        advantage_map = { "Iron": "Electric", "Electric": "Water", "Water": "Fire", "Fire": "Wind", "Wind": "Iron" }
        if advantage_map.get(self.element) == enemy_element:
            elem_buff = self.buff_manager.get_total_value('elemental_buff', frame)
            layer_elem += 0.10 + elem_buff
            
        layer_special = 1.0

        # 1. 本来のスキルダメージバフ (変更なし)
        if profile.get('is_special_skill_damage', False):
            sp_buff = self.buff_manager.get_total_value('special_skill_dmg_buff', frame)
            layer_special += sp_buff
            
        # 2. チャージ攻撃時の追撃バフ (新規追加)
        # 独自のキー 'charge_additional_dmg' を参照するため、他キャラのスキルバフとは競合しない
        if profile.get('is_charge_attack', False):
            add_dmg = self.buff_manager.get_total_value('charge_additional_dmg', frame)
            layer_special += add_dmg
        # ▲▲▲ 修正ここまで ▲▲▲

        total_dmg = layer_atk * layer_weapon * layer_crit * layer_charge * layer_dmg * layer_split * layer_taken * layer_elem * layer_special
        if self.name == "ナユタ":
            if mult > 2.7:
                print(f"--- [DEBUG] Damage Calc ({self.name}) ---")
                print(f"  SkillMult: {mult:.4f}")
                print(f"  1.FinalAtk: {final_atk:.1f} (Base:{self.base_atk} + Rate:{self.buff_manager.get_total_value('atk_buff_rate', frame):.2f} + Fix:{self.buff_manager.get_total_value('atk_buff_fixed', frame):.1f})")
                print(f"  2.Split: {profile['is_pierce']} ")
                print(f"  3.CritLayer: {layer_crit:.2f} (FullBurst:{is_full_burst}, IsCrit:{is_crit_hit})")
                print(f"  4.DmgLayer : {layer_dmg:.2f} (IgnoreDefBuff:{self.buff_manager.get_total_value('atk_dmg_buff', frame):.2f}, TotalBucket:{bucket_dmg:.2f})")
                print(f"  Total: {total_dmg:,.0f}")
                print(f"----------------------------------------")
            
        # 最終計算に layer_special を乗算
        return total_dmg, is_crit_hit

    def calculate_reduced_frame(self, original_frame, rate_buff, fixed_buff):
        if rate_buff <= -1.0: return 9999
        new_frame = original_frame * (1.0 - rate_buff)
        new_frame -= fixed_buff
        return max(1, int(round_half_up(new_frame)))
    
    def calculate_reduced_frame_attack(self, original_frame, rate_buff, fixed_buff):
        if rate_buff <= -1.0: return 9999
        new_frame = original_frame / (1.0 + rate_buff)
        new_frame -= fixed_buff
        return max(1, int(round_half_up(new_frame)))

    def get_buffed_frames(self, frame_type, original_frame, frame):
        # バフ無効化のチェック
        if frame_type == 'reload' and getattr(self.weapon, 'disable_reload_buffs', False): return int(original_frame)
        if frame_type == 'charge' and self.weapon.disable_charge_buffs: return int(original_frame)
        if frame_type == 'attack' and self.weapon.disable_attack_speed_buffs: return int(original_frame)
        
        # ▼▼▼ 追加: バフ/タグによる一時的なバフ無効化チェック ▼▼▼
        # "ignore_{frame_type}_speed_buffs" タグを持つバフが有効な場合、バフ計算をスキップして元の値を返す
        # 対応タグ: 
        #   - ignore_reload_speed_buffs
        #   - ignore_charge_speed_buffs
        #   - ignore_attack_speed_buffs
        # ▼▼▼ 修正: バフ無効化チェックとホワイトリスト処理 ▼▼▼
        ignore_tag = f"ignore_{frame_type}_speed_buffs"

        # 無効化タグを持つバフが存在するかチェック
        ignore_buffs = self.buff_manager.get_buffs_by_tag(ignore_tag, frame)
        
        if ignore_buffs:
            # 無効化が有効な場合、例外的に許可するタグ(allow_tags)を収集
            allowed_tags = set()
            for b in ignore_buffs:
                # バフの定義から "allow_tags" (リスト or 文字列) を取得して追加
                # ※ kwargsはバフデータには保存されていない場合があるため、
                #    add_buff時に 'allow_tags' をバフデータとして保存させるか、
                #    ここでは簡易的にバフデータに追加属性を持たせる修正が必要。
                #    現状の add_buff 実装だと kwargs は保存されないので、
                #    JSONで指定する際はバフのパラメータとして渡す必要がある。
                
                # add_buffの修正が手間なら、ここには「allow_tags」というキーが
                # バフデータ辞書に入っている前提で動くコードを書く。
                tags = b.get('allow_tags')
                if tags:
                    if isinstance(tags, list):
                        allowed_tags.update(tags)
                    else:
                        allowed_tags.add(tags)
            
            # 許可タグがなければ固定値(バフなし)を返す
            if not allowed_tags:
                return int(original_frame)
            
            # 許可タグがある場合、それらを持つバフだけを合算して適用する
            rate = self.buff_manager.get_total_value_with_filter(f'{frame_type}_speed_rate', frame, allowed_tags)
            fixed = 0
            if frame_type in ['reload', 'charge']:
                fixed = self.buff_manager.get_total_value_with_filter(f'{frame_type}_speed_fixed', frame, allowed_tags)

            if rate <= -1.0: rate = -0.99
            
            if frame_type == 'attack':
                return self.calculate_reduced_frame_attack(original_frame, rate, fixed)
            else:
                return self.calculate_reduced_frame(original_frame, rate, fixed)

        # ▲▲▲ 修正ここまで (以下、通常の計算ロジック) ▲▲▲

        rate = self.buff_manager.get_total_value(f'{frame_type}_speed_rate', frame)
        if rate <= -1.0: rate = -0.99
        
        # 固定値バフはリロードとチャージにのみ適用
        fixed = 0
        if frame_type in ['reload', 'charge']:
            fixed = self.buff_manager.get_total_value(f'{frame_type}_speed_fixed', frame)
        
        if frame_type == 'attack':
            return self.calculate_reduced_frame_attack(original_frame, rate, fixed)
        else:
            # リロード・チャージは除算ではなく乗算短縮 + 固定値減算
            return self.calculate_reduced_frame(original_frame, rate, fixed)
    
    # ▼▼▼ 追加: 最大HP計算メソッド ▼▼▼
    def get_current_max_hp(self, frame):
        rate = self.buff_manager.get_total_value('max_hp_rate', frame)
        fixed = self.buff_manager.get_total_value('max_hp_fixed', frame)
        return self.base_hp * (1.0 + rate) + fixed
    # ▲▲▲