import random

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
        final_atk = self.get_current_atk(frame)
        
        def_debuff = self.buff_manager.get_total_value('def_debuff', frame)
        if debuff_manager:
            def_debuff += debuff_manager.get_total_value('def_debuff', frame)
            
        effective_def = enemy_def * (1.0 - def_debuff) if not profile['is_ignore_def'] else 0
        raw_damage_diff = final_atk - effective_def
        if raw_damage_diff <= 0: return 1.0, False
        layer_atk = raw_damage_diff
        
        weapon_buff = self.buff_manager.get_total_value('weapon_dmg_buff', frame) if profile['is_weapon_attack'] else 0.0
        layer_weapon = mult * (1.0 + weapon_buff)
        
        bucket_val = 1.0
        if profile['burst_buff_enabled']:
            if is_full_burst or profile.get('force_full_burst', False): bucket_val += 0.50
        if profile['range_bonus_active']: bucket_val += 0.30
        
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
            bucket_val += 1.0 + core_dmg_buff
            
        crit_rate = profile['crit_rate'] + self.buff_manager.get_total_value('crit_rate_buff', frame)
        is_crit_hit = False
        if random.random() < crit_rate:
            bucket_val += (0.50 + self.buff_manager.get_total_value('crit_dmg_buff', frame))
            is_crit_hit = True
        layer_crit = bucket_val
        
        layer_charge = 1.0
        if profile['is_charge_attack']:
            charge_ratio_buff = self.buff_manager.get_total_value('charge_ratio_buff', frame)
            charge_dmg_buff = self.buff_manager.get_total_value('charge_dmg_buff', frame)
            layer_charge = (profile['charge_mult'] * (1.0 + charge_ratio_buff)) + charge_dmg_buff
            
        bucket_dmg = 1.0
        bucket_dmg += self.buff_manager.get_total_value('atk_dmg_buff', frame)
        if profile['is_part_damage']: bucket_dmg += self.buff_manager.get_total_value('part_dmg_buff', frame)
        
        is_pierce_buff = self.buff_manager.get_total_value('is_pierce', frame)
        if profile['is_pierce'] or is_pierce_buff > 0: 
            bucket_dmg += self.buff_manager.get_total_value('pierce_dmg_buff', frame)
            
        if profile['is_ignore_def']: bucket_dmg += self.buff_manager.get_total_value('ignore_def_dmg_buff', frame)
        if profile['is_dot']: bucket_dmg += self.buff_manager.get_total_value('dot_dmg_buff', frame)
        if profile['burst_buff_enabled'] and (is_full_burst or profile.get('force_full_burst', False)):
             bucket_dmg += self.buff_manager.get_total_value('burst_dmg_buff', frame)
        
        taken_dmg_val = self.buff_manager.get_total_value('taken_dmg_debuff', frame)
        if debuff_manager:
            taken_dmg_val += debuff_manager.get_total_value('taken_dmg_debuff', frame)
        layer_taken = 1.0 + taken_dmg_val
        
        layer_dmg = bucket_dmg
        layer_split = 1.0
        if profile['is_split']: layer_split += self.buff_manager.get_total_value('split_dmg_buff', frame)
        
        layer_elem = 1.0
        advantage_map = { "Iron": "Electric", "Electric": "Water", "Water": "Fire", "Fire": "Wind", "Wind": "Iron" }
        if advantage_map.get(self.element) == enemy_element:
            elem_buff = self.buff_manager.get_total_value('elemental_buff', frame)
            layer_elem += 0.10 + elem_buff
            
        return layer_atk * layer_weapon * layer_crit * layer_charge * layer_dmg * layer_split * layer_taken * layer_elem, is_crit_hit

    def calculate_reduced_frame(self, original_frame, rate_buff, fixed_buff):
        if rate_buff <= -1.0: return 9999
        new_frame = original_frame * (1.0 - rate_buff)
        new_frame -= fixed_buff
        return max(1, int(new_frame))
    
    def calculate_reduced_frame_attack(self, original_frame, rate_buff, fixed_buff):
        if rate_buff <= -1.0: return 9999
        new_frame = original_frame / (1.0 + rate_buff)
        new_frame -= fixed_buff
        return max(1, int(new_frame))

    def get_buffed_frames(self, frame_type, original_frame, frame):
        if frame_type == 'reload':
            fixed_val = self.buff_manager.get_total_value('reload_speed_fixed_value', frame)
            if fixed_val > 0: return int(original_frame / (1.0 + fixed_val))
            if self.weapon.disable_reload_buffs: return int(original_frame)
        
        if frame_type == 'charge' and self.weapon.disable_charge_buffs: return int(original_frame)
        if frame_type == 'attack' and self.weapon.disable_attack_speed_buffs: return int(original_frame)
        
        rate = self.buff_manager.get_total_value(f'{frame_type}_speed_rate', frame)
        if rate <= -1.0: rate = -0.99
        fixed = self.buff_manager.get_total_value(f'{frame_type}_speed_fixed', frame)
        
        if frame_type == 'attack':
            return self.calculate_reduced_frame_attack(original_frame, rate, fixed)
        else:
            return self.calculate_reduced_frame(original_frame, rate, fixed)