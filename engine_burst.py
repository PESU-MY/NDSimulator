class BurstEngineMixin:
    def update_cooldowns(self):
        for char in self.characters:
            if char.current_cooldown > 0: char.current_cooldown -= 1

    def tick_burst_state(self, frame):
        is_full_burst = (self.burst_state == "FULL")
        
        if self.burst_state == "GEN":
            self.burst_timer += 1
            # バースト終了時に短縮効果をリセット
            self.full_burst_reduction = 0.0 
            
            if self.burst_timer >= self.burst_charge_time * self.FPS: 
                self.burst_state = "BURST_1"
                self.burst_timer = 0
                # ▼▼▼ 追加: バースト1段階突入トリガー ▼▼▼
                self.process_trigger_global('on_burst_1_enter', frame)
                # ▲▲▲
                
        elif self.burst_state in ["BURST_1", "BURST_2", "BURST_3"]:
            stage_idx = {"BURST_1": 0, "BURST_2": 1, "BURST_3": 2}[self.burst_state]
            char_list = self.burst_rotation[stage_idx]
            
            if len(char_list) > 0:
                idx = self.burst_indices[stage_idx]
                # ▼▼▼ 修正: バースト発動試行ループ (気絶スキップ対応) ▼▼▼
                # 現在のインデックスから開始し、リストを一巡するまで試行
                start_idx = idx
                target_char = None
                
                for i in range(len(char_list)):
                    current_check_idx = (start_idx + i) % len(char_list)
                    candidate = char_list[current_check_idx]
                    
                    # クールダウン中ならスキップ
                    if candidate.current_cooldown > 0:
                        continue
                        
                    # ▼▼▼ 追加: 気絶チェック ▼▼▼
                    if candidate.buff_manager.has_active_tag("stun", frame):
                        # 気絶中はスキップ
                        continue
                    # ▲▲▲ 追加ここまで ▲▲▲
                    
                    # 発動可能なキャラが見つかった
                    target_char = candidate
                    # インデックスを更新 (次は、今回発動したキャラの次から)
                    self.burst_indices[stage_idx] = (current_check_idx + 1) % len(char_list)
                    break
                
                if target_char:
                    char = target_char
                    base_cd = 40.0
                    if char.burst_stage in ['1', '2']: base_cd = 20.0 
                    char.current_cooldown = base_cd * self.FPS
                    
                    self.log(f"[Burst] {char.name} used Burst Stage {self.burst_state.split('_')[1]}", target_name="System")
                    self.log(f"[Burst] Activate!", target_name=char.name)
                    
                    if self.burst_state == "BURST_3":
                        self.last_burst_char_name = char.name 
                        char.process_trigger('on_burst_3_enter', 0, frame, is_full_burst, self)
                        self.process_trigger_global('on_burst_3_enter', frame)
                        self.process_trigger_global('on_burst_enter', frame) 
                    
                    char.process_trigger('on_use_burst_skill', 0, frame, is_full_burst, self)
                    
                    # 状態遷移
                    if getattr(self, 'reenter_burst_target', None):
                        self.burst_state = self.reenter_burst_target
                        self.log(f"[Burst] Re-entered {self.burst_state} by effect", target_name="System")
                        self.reenter_burst_target = None 
                    else:
                        if self.burst_state == "BURST_1": 
                            self.burst_state = "BURST_2"
                            # ▼▼▼ 追加: バースト2段階突入トリガー ▼▼▼
                            self.process_trigger_global('on_burst_2_enter', frame)
                            # ▲▲▲ 追加ここまで ▲▲▲
                        elif self.burst_state == "BURST_2": 
                            self.burst_state = "BURST_3"
                        elif self.burst_state == "BURST_3":
                            self.burst_state = "FULL"
                            self.burst_timer = 0
                            # ... (フルバースト処理) ...
                            base_duration = 10.0
                            current_duration = max(0.0, base_duration - getattr(self, 'full_burst_reduction', 0.0))
                            self.current_full_burst_duration_frames = int(current_duration * self.FPS)
                            if self.full_burst_reduction > 0:
                                self.log(f"[Burst] Full Burst Time shortened by {self.full_burst_reduction:.2f}s", target_name="System")
                # ▲▲▲ 修正ここまで ▲▲▲
                            
        elif self.burst_state == "FULL":
            self.burst_timer += 1
            # 10秒固定ではなく、計算された時間を使用
            target_duration = getattr(self, 'current_full_burst_duration_frames', 10 * self.FPS)
            
            if self.burst_timer >= target_duration: 
                self.process_trigger_global('on_burst_end', frame)

                # ▼▼▼ 追加: バーストIII発動者の「バースト終了時刻」を更新 ▼▼▼
                if self.last_burst_char_name:
                    for char in self.characters:
                        if char.name == self.last_burst_char_name:
                            char.last_burst_end_frame = frame
                            self.log(f"[Burst] Recorded burst end time for {char.name} at frame {frame}", target_name="System")
                            break
                # ▲▲▲ 追加ここまで ▲▲▲
                
                self.burst_state = "GEN"; self.burst_timer = 0

    def process_trigger_global(self, trigger_type, frame):
        is_fb = (self.burst_state == "FULL")
        for char in self.characters:
            char.process_trigger(trigger_type, 0, frame, is_fb, self)