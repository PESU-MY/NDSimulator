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
                
        elif self.burst_state in ["BURST_1", "BURST_2", "BURST_3"]:
            stage_idx = {"BURST_1": 0, "BURST_2": 1, "BURST_3": 2}[self.burst_state]
            char_list = self.burst_rotation[stage_idx]
            
            if len(char_list) > 0:
                idx = self.burst_indices[stage_idx]
                if idx < len(char_list):
                    char = char_list[idx]
                    if char.current_cooldown <= 0:
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
                        
                        self.burst_indices[stage_idx] = (idx + 1) % len(char_list)
                        if self.burst_state == "BURST_1": self.burst_state = "BURST_2"
                        elif self.burst_state == "BURST_2": self.burst_state = "BURST_3"
                        elif self.burst_state == "BURST_3":
                            self.burst_state = "FULL"
                            self.burst_timer = 0
                            
                            # ▼▼▼ フルバースト時間計算 (短縮適用) ▼▼▼
                            # デフォルト10秒 - 短縮量 (下限なし、または0秒)
                            base_duration = 10.0
                            current_duration = max(0.0, base_duration - getattr(self, 'full_burst_reduction', 0.0))
                            self.current_full_burst_duration_frames = int(current_duration * self.FPS)
                            
                            if self.full_burst_reduction > 0:
                                self.log(f"[Burst] Full Burst Time shortened by {self.full_burst_reduction:.2f}s (Duration: {current_duration:.2f}s)", target_name="System")
                            # ▲▲▲ 追加ここまで ▲▲▲
                            
        elif self.burst_state == "FULL":
            self.burst_timer += 1
            # 10秒固定ではなく、計算された時間を使用
            target_duration = getattr(self, 'current_full_burst_duration_frames', 10 * self.FPS)
            
            if self.burst_timer >= target_duration: 
                self.process_trigger_global('on_burst_end', frame)
                self.burst_state = "GEN"; self.burst_timer = 0

    def process_trigger_global(self, trigger_type, frame):
        is_fb = (self.burst_state == "FULL")
        for char in self.characters:
            char.process_trigger(trigger_type, 0, frame, is_fb, self)