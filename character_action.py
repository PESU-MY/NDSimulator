from models import DamageProfile
from utils import round_half_up

class CharacterActionMixin:
    def update_max_ammo(self, frame):
        rate_buffs = self.buff_manager.get_active_buffs('max_ammo_rate', frame)
        fixed_buff_sum = self.buff_manager.get_total_value('max_ammo_fixed', frame)
        added_ammo = sum([round_half_up(self.weapon.max_ammo * rate) for rate in rate_buffs])
        self.current_max_ammo = int(self.weapon.max_ammo + added_ammo + fixed_buff_sum)
        if self.current_ammo > self.current_max_ammo: self.current_ammo = self.current_max_ammo

    def get_mg_interval(self):
        effective_time = max(0, self.mg_warmup_frames - self.weapon.windup_frames)
        target_interval = 1 
        for entry in reversed(self.weapon.mg_warmup_map):
            if effective_time >= entry['start']: target_interval = entry['interval']; break
        return target_interval
    
    def revert_weapon(self, frame):
        if not self.is_weapon_changed: return
        should_reset = getattr(self.weapon, 'reset_ammo_on_revert', True)
        self.weapon = self.original_weapon
        self.is_weapon_changed = False
        self.weapon_change_end_frame = 0
        self.update_max_ammo(frame)
        if self.weapon_change_ammo_specified and should_reset:
            self.current_ammo = self.current_max_ammo
        else:
            if self.current_ammo > self.current_max_ammo: self.current_ammo = self.current_max_ammo
        self.state = "READY"; self.state_timer = 0

    def tick_action(self, frame, is_full_burst, simulator):
        if self.is_dummy: return 0
        
        # ▼▼▼ 追加: 気絶(Stun)判定 ▼▼▼
        # "stun" タグを持つバフが有効な場合、行動不能として処理をスキップ
        if self.buff_manager.has_active_tag("stun", frame):
            # ログ出力（頻繁に出過ぎる場合は調整）
            if frame % 60 == 0:
                simulator.log(f"[Stun] {self.name} is stunned and cannot act.", target_name=self.name)
            return 0
        # ▲▲▲ 追加ここまで ▲▲▲
        
        damage_this_frame = 0
        if self.weapon.type == "MG" and self.state != "SHOOTING" and self.state != "READY": 
            self.mg_warmup_frames -= self.mg_decay_rate
            self.mg_warmup_frames = max(0, self.mg_warmup_frames)

        def perform_shoot():
            nonlocal damage_this_frame
            self.total_shots += 1
            self.current_ammo -= 1
            
            force_fb = getattr(self.weapon, 'force_full_burst', False)
            if isinstance(self.weapon, dict): force_fb = self.weapon.get('force_full_burst', False)
            
            prof = DamageProfile.create(
                is_weapon_attack=True, 
                is_charge_attack=(self.weapon.type in ["RL", "SR", "CHARGE"]), 
                charge_mult=self.weapon.charge_mult if self.weapon.type in ["RL", "SR", "CHARGE"] else 1.0, 
                force_full_burst=force_fb, is_pierce=self.weapon.is_pierce
            )
            base_pellets = 10 if self.weapon.weapon_class == "SG" else 1
            pellet_add = self.buff_manager.get_total_value('pellet_count_add', frame)
            pellet_fixed = self.buff_manager.get_total_value('pellet_count_fixed', frame)
            base_pellets_from_config = getattr(self.weapon, 'pellet_count', 1)
            current_pellets = base_pellets_from_config + pellet_add
            if pellet_fixed > 0: current_pellets = pellet_fixed
            current_pellets = int(max(1, current_pellets))
            per_pellet_multiplier = self.weapon.multiplier / current_pellets

            total_shot_dmg = 0
            hit_count = 0
            crit_count = 0
            
            for _ in range(current_pellets):
                # ▼▼▼ 修正: 戻り値を3つ (dmg, is_crit, is_core) で受け取る ▼▼▼
                dmg, is_crit, is_core = self.calculate_strict_damage(
                    per_pellet_multiplier, prof, is_full_burst, frame, 
                    enemy_def=simulator.ENEMY_DEF, enemy_element=simulator.enemy_element,
                    enemy_core_size=simulator.enemy_core_size, enemy_size=simulator.enemy_size,
                    debuff_manager=simulator.enemy_debuffs 
                )
                # ▲▲▲ 修正ここまで ▲▲▲
                total_shot_dmg += dmg
                if dmg > 0: hit_count += 1
                if is_crit: crit_count += 1

                # ▼▼▼ 追加: コアヒットカウント ▼▼▼
                if is_core: core_hit_count += 1
                # ▲▲▲
            
            self.cumulative_pellet_hits += hit_count
            self.cumulative_crit_hits += crit_count

            # ▼▼▼ 追加: 累計コアヒット数の加算 (未定義なら初期化) ▼▼▼
            if not hasattr(self, 'cumulative_core_hits'): self.cumulative_core_hits = 0
            self.cumulative_core_hits += core_hit_count
            # ▲▲▲
            
            self.total_damage += total_shot_dmg
            self.damage_breakdown['Weapon Attack'] += total_shot_dmg
            damage_this_frame += total_shot_dmg
            
            self.buff_manager.decrement_shot_buffs()
            
            buff_debug_str = self.buff_manager.get_active_buffs_debug(frame)
            simulator.log(f"[Shoot] 時間:{frame/60:>6.2f}s | 弾数:{self.current_ammo:>3}/{self.current_max_ammo:<3} | Pellets:{current_pellets:>2} | Dmg:{total_shot_dmg:10,.0f} | Buffs: {buff_debug_str}", target_name=self.name)
            
            damage_this_frame += self.process_trigger('shot_count', self.total_shots, frame, is_full_burst, simulator)
            damage_this_frame += self.process_trigger('ammo_empty', self.current_ammo, frame, is_full_burst, simulator)
            damage_this_frame += self.process_trigger('pellet_hit', self.cumulative_pellet_hits, frame, is_full_burst, simulator, delta=hit_count)
            damage_this_frame += self.process_trigger('critical_hit', self.cumulative_crit_hits, frame, is_full_burst, simulator, delta=crit_count)

            # ▼▼▼ 追加: core_hit トリガーの発火 ▼▼▼
            damage_this_frame += self.process_trigger('core_hit', self.cumulative_core_hits, frame, is_full_burst, simulator, delta=core_hit_count)
            # ▲▲▲ 追加ここまで ▲▲▲
            
            # ▼▼▼ 追加: フルチャージ攻撃判定とトリガー処理 ▼▼▼
            # 現状のシミュ仕様では、SR/RL/CHARGEタイプは必ずチャージ時間を経て発射されるため、常にフルチャージ扱いとする。
            # 将来タップ撃ちを実装する場合は、ここでチャージ率などを判定する。
            if self.weapon.type in ["RL", "SR", "CHARGE"]:
                self.cumulative_full_charge_count += 1
                damage_this_frame += self.process_trigger('full_charge_count', self.cumulative_full_charge_count, frame, is_full_burst, simulator)
            # ▲▲▲ 追加ここまで ▲▲▲

            # ▼▼▼ 追加: ドレイン(攻撃回復)処理 ▼▼▼
            # "drain" バフが付与されている場合、与ダメージの n% を回復
            drain_rate = self.buff_manager.get_total_value('drain', frame)
            if drain_rate > 0 and total_shot_dmg > 0:
                heal_amount = total_shot_dmg * drain_rate
                # healメソッドを呼び出す (simulatorへの参照が必要)
                self.heal(heal_amount, "Drain", frame, simulator)
            # ▲▲▲


        if self.weapon.type in ["RL", "SR", "CHARGE"]:
            if self.state == "READY":
                if self.state_timer == 0: self.current_action_duration = self.get_buffed_frames('attack', self.weapon.windup_frames, frame)
                self.state_timer += 1
                if self.state_timer >= self.current_action_duration: self.state = "CHARGING"; self.state_timer = 0
            elif self.state == "CHARGING":
                if self.state_timer == 0:
                    base_frames = max(1, self.weapon.charge_time * simulator.FPS)
                    self.current_action_duration = self.get_buffed_frames('charge', base_frames, frame)
                self.state_timer += 1
                if self.state_timer >= self.current_action_duration: self.state = "SHOOTING"; self.state_timer = 0
            elif self.state == "SHOOTING":
                perform_shoot()
                self.state = "WINDDOWN"; self.state_timer = 0
            elif self.state == "WINDDOWN":
                if self.state_timer == 0: self.current_action_duration = self.get_buffed_frames('attack', self.weapon.winddown_frames, frame)
                self.state_timer += 1
                if self.state_timer >= self.current_action_duration:
                    self.state_timer = 0
                    if self.is_weapon_changed and self.current_ammo <= 0: self.revert_weapon(frame)
                    else: self.state = "RELOADING" if self.current_ammo <= 0 else "READY"
            elif self.state == "RELOADING":
                if self.state_timer == 0:
                    self.current_action_duration = self.get_buffed_frames('reload', self.weapon.reload_frames, frame)
                    simulator.log(f"[Action] Reloading... ({self.current_action_duration} frames)", target_name=self.name)
                self.state_timer += 1
                if self.state_timer >= self.current_action_duration:
                    self.current_ammo = self.current_max_ammo; self.state = "READY"; self.state_timer = 0
                    self.buff_manager.remove_reload_buffs()
                    simulator.log(f"[Action] Reload Complete. Ammo: {self.current_ammo}", target_name=self.name)
                    # ▼▼▼ 追加: リロード完了トリガー ▼▼▼
                    damage_this_frame += self.process_trigger('reload_complete', 0, frame, is_full_burst, simulator)
                    # ▲▲▲
                    

        elif self.weapon.type == "MG":
            if self.state == "READY":
                if self.state_timer == 0: self.current_action_duration = self.get_buffed_frames('attack', self.weapon.windup_frames, frame)
                self.mg_warmup_frames = min(self.weapon.mg_max_warmup, self.mg_warmup_frames + 1)
                self.state_timer += 1
                if self.state_timer >= self.current_action_duration: 
                    self.state = "SHOOTING"; self.state_timer = 0 
                    if self.mg_warmup_frames < self.weapon.windup_frames: self.mg_warmup_frames = self.weapon.windup_frames
            elif self.state == "SHOOTING":
                original_interval = self.get_mg_interval()
                buffed_interval = self.get_buffed_frames('attack', original_interval, frame)
                forced_interval = self.buff_manager.get_total_value('force_fire_interval', frame)
                if forced_interval > 0: buffed_interval = int(forced_interval)
                
                if self.state_timer == 0:
                    perform_shoot()
                    warmup_speed = 1.0 + self.buff_manager.get_total_value('mg_warmup_speed', frame)
                    if warmup_speed < 0: warmup_speed = 0 # 安全策
                    increment = warmup_speed
                    self.mg_warmup_frames = min(self.weapon.mg_max_warmup, self.mg_warmup_frames + increment)
                    if self.current_ammo <= 0: self.state = "WINDDOWN"; self.state_timer = 0
                    else: self.state_timer = max(0, buffed_interval - 1)
                else: self.state_timer -= 1
            elif self.state == "WINDDOWN":
                if self.state_timer == 0: self.current_action_duration = self.get_buffed_frames('attack', self.weapon.winddown_frames, frame)
                self.state_timer += 1
                if self.state_timer >= self.current_action_duration: 
                    self.state_timer = 0
                    if self.is_weapon_changed and self.current_ammo <= 0: self.revert_weapon(frame)
                    else: self.state = "RELOADING"
            elif self.state == "RELOADING":
                if self.state_timer == 0:
                    self.current_action_duration = self.get_buffed_frames('reload', self.weapon.reload_frames, frame)
                    simulator.log(f"[Action] Reloading... ({self.current_action_duration} frames)", target_name=self.name)
                self.state_timer += 1
                if self.state_timer >= self.current_action_duration: 
                    self.current_ammo = self.current_max_ammo; self.state = "READY"; self.state_timer = 0
                    self.buff_manager.remove_reload_buffs()
                    simulator.log(f"[Action] Reload Complete. Ammo: {self.current_ammo}", target_name=self.name)
                    # ▼▼▼ 追加: リロード完了トリガー ▼▼▼
                    damage_this_frame += self.process_trigger('reload_complete', 0, frame, is_full_burst, simulator)
                    # ▲▲▲
                    

        else: 
            if self.state == "READY":
                if self.state_timer == 0: self.current_action_duration = self.get_buffed_frames('attack', self.weapon.windup_frames, frame)
                self.state_timer += 1
                if self.state_timer >= self.current_action_duration: self.state = "SHOOTING"; self.state_timer = 0
            elif self.state == "SHOOTING":
                if self.state_timer == 0:
                    perform_shoot()
                    if self.current_ammo <= 0: self.state = "WINDDOWN"; self.state_timer = 0
                    else:
                        original_interval = self.weapon.fire_interval
                        buffed_interval = self.get_buffed_frames('attack', original_interval, frame)
                        self.state_timer = max(0, buffed_interval - 1)
                else: self.state_timer -= 1
            elif self.state == "WINDDOWN":
                if self.state_timer == 0: self.current_action_duration = self.get_buffed_frames('attack', self.weapon.winddown_frames, frame)
                self.state_timer += 1
                if self.state_timer >= self.current_action_duration:
                    self.state_timer=0
                    if self.is_weapon_changed and self.current_ammo <= 0: self.revert_weapon(frame)
                    else: self.state = "RELOADING"
            elif self.state == "RELOADING":
                if self.state_timer == 0: self.current_action_duration = self.get_buffed_frames('reload', self.weapon.reload_frames, frame)
                self.state_timer += 1
                # ▼▼▼ 修正: if文をブロック化し、処理を中に含める ▼▼▼
                if self.state_timer >= self.current_action_duration:
                    self.current_ammo = self.current_max_ammo
                    self.state = "READY"
                    self.state_timer = 0
                    
                    self.buff_manager.remove_reload_buffs()

                    # ▼▼▼ 追加: リロード完了トリガー ▼▼▼
                    damage_this_frame += self.process_trigger('reload_complete', 0, frame, is_full_burst, simulator)
                    # ▲▲▲

        
        return damage_this_frame