import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import json

# --- 定数・辞書定義 ---

WEAPON_TYPES = {
    "AR": "AR (アサルトライフル)",
    "SMG": "SMG (サブマシンガン)",
    "SG": "SG (ショットガン)",
    "MG": "MG (マシンガン)",
    "SR": "SR (スナイパーライフル)",
    "RL": "RL (ロケットランチャー)"
}

ELEMENTS = {
    "Fire": "Fire (灼熱)",
    "Water": "Water (水冷)",
    "Wind": "Wind (風圧)",
    "Electric": "Electric (電撃)",
    "Iron": "Iron (鉄甲)"
}

CLASSES = {
    "Attacker": "Attacker (火力型)",
    "Defender": "Defender (防御型)",
    "Supporter": "Supporter (支援型)"
}

TRIGGER_TYPES = {
    "manual": "manual (手動/バースト発動)",
    "shot_count": "shot_count (攻撃回数/○回命中)",
    "pellet_hit": "pellet_hit (ペレット命中数/SG用)",
    "time_interval": "time_interval (時間経過/○秒ごと)",
    "on_burst_enter": "on_burst_enter (フルバースト突入時)",
    "on_burst_3_enter": "on_burst_3_enter (バーストIII突入時)",
    "on_use_burst_skill": "on_use_burst_skill (バーストスキル使用時)",
    "on_start": "on_start (戦闘開始時)",
    "ammo_empty": "ammo_empty (最後の弾丸命中時)",
    "part_break": "part_break (部位破壊時)",
    "stack_count": "stack_count (スタック数到達時)"
}

EFFECT_TYPES = {
    "damage": "damage (ダメージを与える)",
    "buff": "buff (バフを付与)",
    "stack_buff": "stack_buff (スタック型バフ)",
    "cumulative_stages": "cumulative_stages (段階/一括発動スキル)",
    "cooldown_reduction": "cooldown_reduction (CD短縮)",
    "convert_hp_to_atk": "convert_hp_to_atk (HP変換攻撃力UP)",
    "weapon_change": "weapon_change (武器変更/SWなど)",
    "ammo_charge": "ammo_charge (弾丸チャージ)",
    "dot": "dot (持続ダメージ)"
}

TARGETS = {
    "self": "self (自分)",
    "allies": "allies (味方全体)",
    "enemy": "enemy (敵/対象)",
    "lowest_hp": "lowest_hp (HP最低の味方)"
}

# Kwargsのキー候補
KWARGS_KEYS = [
    "buff_type", "value", "duration", "shot_duration",
    "multiplier", "loop_count", "trigger_all_stages",
    "scale_by_caster_stats", "stat_type",
    "max_stack", "stack_name", "remove_on_reload",
    "target_condition"
]

# バフの種類（buff_typeの選択肢）
BUFF_TYPES = [
    "atk_buff_rate", "atk_buff_fixed", "atk_dmg_buff",
    "crit_rate_buff", "crit_dmg_buff",
    "reload_speed_rate", "max_ammo_rate",
    "charge_speed_rate", "charge_dmg_buff",
    "def_buff_rate", "hit_rate_buff",
    "pierce_dmg_buff", "core_dmg_buff", "part_dmg_buff",
    "elemental_buff",
    "dummy_heal", "dummy_effect"  # ダミー用
]

# --- UIクラス ---

class ScrollableFrame(ttk.Frame):
    def __init__(self, container, *args, **kwargs):
        super().__init__(container, *args, **kwargs)
        canvas = tk.Canvas(self)
        scrollbar = ttk.Scrollbar(self, orient="vertical", command=canvas.yview)
        self.scrollable_frame = ttk.Frame(canvas)

        self.scrollable_frame.bind(
            "<Configure>",
            lambda e: canvas.configure(scrollregion=canvas.bbox("all"))
        )

        canvas.create_window((0, 0), window=self.scrollable_frame, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)

        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

class KwargsRow(ttk.Frame):
    """Kwargsの1行分を管理するウィジェット"""
    def __init__(self, parent, key="", val="", delete_callback=None):
        super().__init__(parent)
        self.delete_callback = delete_callback
        
        # Key Selection
        self.cb_key = ttk.Combobox(self, values=KWARGS_KEYS, width=23)
        self.cb_key.set(key)
        self.cb_key.pack(side="left")
        self.cb_key.bind("<<ComboboxSelected>>", self.on_key_changed)
        self.cb_key.bind("<KeyRelease>", self.on_key_changed)

        # Value Container (Entry or Combobox)
        self.val_frame = ttk.Frame(self)
        self.val_frame.pack(side="left", padx=2)
        
        self.val_widget = None
        self.create_val_widget(val)

        # Delete Button
        btn_del = ttk.Button(self, text="x", width=3, command=self.delete)
        btn_del.pack(side="left", padx=2)

        # 初期化時にウィジェット状態を更新
        self.on_key_changed()

    def create_val_widget(self, initial_val=""):
        if self.val_widget:
            self.val_widget.destroy()
        
        key = self.cb_key.get()
        
        if key == "buff_type":
            self.val_widget = ttk.Combobox(self.val_frame, values=BUFF_TYPES, width=23)
            self.val_widget.set(str(initial_val))
        elif key in ["trigger_all_stages", "scale_by_caster_stats", "remove_on_reload"]:
            self.val_widget = ttk.Combobox(self.val_frame, values=["true", "false"], width=23)
            current = str(initial_val).lower()
            self.val_widget.set("true" if current == "true" else "false" if current == "false" else "")
        else:
            self.val_widget = ttk.Entry(self.val_frame, width=25)
            self.val_widget.insert(0, str(initial_val))
            
        self.val_widget.pack(fill="x")

    def on_key_changed(self, event=None):
        """Keyが変わったらValueのウィジェットタイプを切り替える"""
        current_key = self.cb_key.get()
        current_val = self.val_widget.get()
        
        # 特定のキーの場合のみウィジェットを再生成
        # (無限ループ防止のため、タイプが違うときだけ再生成するのが理想だが簡易実装)
        is_combobox = isinstance(self.val_widget, ttk.Combobox)
        needs_combobox = (current_key == "buff_type" or 
                          current_key in ["trigger_all_stages", "scale_by_caster_stats", "remove_on_reload"])
        
        # buff_typeの場合、中身がBUFF_TYPESか確認
        if current_key == "buff_type":
            if not is_combobox:
                self.create_val_widget(current_val)
            elif self.val_widget['values'] != tuple(BUFF_TYPES): # 値候補が違う場合
                self.create_val_widget(current_val)
        elif needs_combobox:
             if not is_combobox:
                 self.create_val_widget(current_val)
             elif self.val_widget['values'] != ("true", "false"):
                 self.create_val_widget(current_val)
        else:
            if is_combobox:
                self.create_val_widget(current_val)

    def delete(self):
        if self.delete_callback:
            self.delete_callback(self)

    def get_data(self):
        k = self.cb_key.get().strip()
        v_str = self.val_widget.get().strip()
        
        if not k: return None, None
        
        # 型変換
        if v_str.lower() == "true":
            v = True
        elif v_str.lower() == "false":
            v = False
        else:
            try:
                if "." in v_str:
                    v = float(v_str)
                else:
                    v = int(v_str)
            except ValueError:
                v = v_str
        return k, v

class KwargsEditor(ttk.Frame):
    def __init__(self, parent):
        super().__init__(parent)
        self.rows = []
        
        header = ttk.Frame(self)
        header.pack(fill="x")
        ttk.Label(header, text="パラメータ名 (Key)", width=25).pack(side="left")
        ttk.Label(header, text="値 (Value)", width=25).pack(side="left")
        ttk.Button(header, text="+ 追加", command=self.add_row, width=8).pack(side="left", padx=5)

        self.container = ttk.Frame(self)
        self.container.pack(fill="x", pady=2)

    def add_row(self, key="", val=""):
        row = KwargsRow(self.container, key, val, self.delete_row)
        row.pack(fill="x", pady=1)
        self.rows.append(row)

    def delete_row(self, row_widget):
        if row_widget in self.rows:
            self.rows.remove(row_widget)
        row_widget.destroy()

    def get_data(self):
        data = {}
        for row in self.rows:
            k, v = row.get_data()
            if k is not None:
                data[k] = v
        return data

class StageEditor(ttk.LabelFrame):
    def __init__(self, parent, index):
        super().__init__(parent, text=f"Stage {index+1} 設定", padding=5)
        
        frame_top = ttk.Frame(self)
        frame_top.pack(fill="x")
        
        ttk.Label(frame_top, text="Effect Type:").pack(side="left")
        self.cb_effect = ttk.Combobox(frame_top, values=[f"{k} : {v}" for k, v in EFFECT_TYPES.items()], width=40)
        self.cb_effect.pack(side="left", padx=5)
        self.cb_effect.set("buff : buff (バフを付与)") 

        ttk.Label(frame_top, text="Target:").pack(side="left", padx=5)
        self.cb_target = ttk.Combobox(frame_top, values=[f"{k} : {v}" for k, v in TARGETS.items()], width=20)
        self.cb_target.pack(side="left")
        
        ttk.Label(self, text="Stage Parameters (kwargs):").pack(anchor="w", pady=(5, 0))
        self.kwargs_editor = KwargsEditor(self)
        self.kwargs_editor.pack(fill="x", padx=10)
        
        self.var_skill_dmg = tk.BooleanVar(value=False)
        ttk.Checkbutton(self, text="スキルダメージ扱い (is_skill_damage)", variable=self.var_skill_dmg).pack(anchor="w")

        ttk.Button(self, text="このステージを削除", command=self.destroy).pack(anchor="e", pady=5)

    def get_data(self):
        effect_raw = self.cb_effect.get().split(" : ")[0]
        target_raw = self.cb_target.get().split(" : ")[0] if self.cb_target.get() else None
        
        data = {
            "effect_type": effect_raw,
            "kwargs": self.kwargs_editor.get_data()
        }
        if target_raw:
            data["target"] = target_raw
            
        if self.var_skill_dmg.get():
            if "profile" not in data["kwargs"]:
                data["kwargs"]["profile"] = {}
            if isinstance(data["kwargs"]["profile"], dict):
                data["kwargs"]["profile"]["is_skill_damage"] = True
            
        return data

class SkillTab(ttk.Frame):
    def __init__(self, parent, default_name=""):
        super().__init__(parent)
        
        # --- Basic Info ---
        f_basic = ttk.LabelFrame(self, text="基本情報", padding=5)
        f_basic.pack(fill="x", pady=5)
        
        grid_opts = {'padx': 5, 'pady': 2, 'sticky': 'w'}
        
        ttk.Label(f_basic, text="スキル名:").grid(row=0, column=0, **grid_opts)
        self.ent_name = ttk.Entry(f_basic, width=40)
        self.ent_name.insert(0, default_name)
        self.ent_name.grid(row=0, column=1, **grid_opts)
        
        ttk.Label(f_basic, text="トリガー(Trigger):").grid(row=1, column=0, **grid_opts)
        self.cb_trigger = ttk.Combobox(f_basic, values=[f"{k} : {v}" for k, v in TRIGGER_TYPES.items()], width=40)
        self.cb_trigger.grid(row=1, column=1, **grid_opts)
        
        ttk.Label(f_basic, text="トリガー値(Value):").grid(row=2, column=0, **grid_opts)
        self.ent_trig_val = ttk.Entry(f_basic, width=10)
        self.ent_trig_val.insert(0, "0")
        self.ent_trig_val.grid(row=2, column=1, **grid_opts)
        
        ttk.Label(f_basic, text="クールダウン(秒):").grid(row=3, column=0, **grid_opts)
        self.ent_cd = ttk.Entry(f_basic, width=10)
        self.ent_cd.insert(0, "0")
        self.ent_cd.grid(row=3, column=1, **grid_opts)

        # --- Main Effect Info ---
        f_effect = ttk.LabelFrame(self, text="メイン効果 / 親設定", padding=5)
        f_effect.pack(fill="x", pady=5)
        
        ttk.Label(f_effect, text="効果タイプ(Effect):").grid(row=0, column=0, **grid_opts)
        self.cb_effect = ttk.Combobox(f_effect, values=[f"{k} : {v}" for k, v in EFFECT_TYPES.items()], width=40)
        self.cb_effect.grid(row=0, column=1, **grid_opts)
        self.cb_effect.set("cumulative_stages : cumulative_stages (段階/一括発動スキル)")
        
        ttk.Label(f_effect, text="対象(Target):").grid(row=1, column=0, **grid_opts)
        self.cb_target = ttk.Combobox(f_effect, values=[f"{k} : {v}" for k, v in TARGETS.items()], width=20)
        self.cb_target.grid(row=1, column=1, **grid_opts)
        self.cb_target.set("self : self (自分)")

        # --- Kwargs ---
        f_kwargs = ttk.LabelFrame(self, text="スキルパラメータ (kwargs)", padding=5)
        f_kwargs.pack(fill="x", pady=5)
        self.main_kwargs = KwargsEditor(f_kwargs)
        self.main_kwargs.pack(fill="x")
        
        # 便利ボタン
        btn_frame = ttk.Frame(f_kwargs)
        btn_frame.pack(anchor="e")
        ttk.Button(btn_frame, text="一括発動(All Stages)追加", 
                   command=lambda: self.main_kwargs.add_row("trigger_all_stages", "true")).pack(side="right", padx=2)
        ttk.Button(btn_frame, text="攻撃力固定値バフ(Caster Base)", 
                   command=lambda: [self.main_kwargs.add_row("buff_type", "atk_buff_fixed"), 
                                    self.main_kwargs.add_row("scale_by_caster_stats", "true"),
                                    self.main_kwargs.add_row("stat_type", "base")]).pack(side="right", padx=2)
        ttk.Button(btn_frame, text="ダミー効果(効果なし)", 
                   command=lambda: [self.main_kwargs.add_row("buff_type", "dummy_effect"), 
                                    self.main_kwargs.add_row("value", "0")]).pack(side="right", padx=2)

        # --- Stages ---
        self.f_stages = ttk.LabelFrame(self, text="Stages (効果詳細リスト)", padding=5)
        self.f_stages.pack(fill="both", expand=True, pady=5)
        
        btn_add_stage = ttk.Button(self.f_stages, text="+ ステージ効果を追加", command=self.add_stage)
        btn_add_stage.pack(anchor="nw", pady=2)
        
        self.stages_container = ttk.Frame(self.f_stages)
        self.stages_container.pack(fill="both", expand=True)

    def add_stage(self):
        idx = len(self.stages_container.winfo_children())
        stage = StageEditor(self.stages_container, idx)
        stage.pack(fill="x", pady=2)

    def get_data(self):
        trig_raw = self.cb_trigger.get().split(" : ")[0]
        try: trig_val = float(self.ent_trig_val.get())
        except: trig_val = 0
        try: cd_val = float(self.ent_cd.get())
        except: cd_val = 0
        
        eff_raw = self.cb_effect.get().split(" : ")[0]
        tgt_raw = self.cb_target.get().split(" : ")[0]
        
        skill_data = {
            "name": self.ent_name.get(),
            "trigger_type": trig_raw,
            "trigger_value": int(trig_val) if trig_val.is_integer() else trig_val,
            "effect_type": eff_raw,
            "target": tgt_raw,
            "kwargs": self.main_kwargs.get_data(),
            "stages": []
        }
        
        if cd_val > 0:
            skill_data["cooldown"] = cd_val
            
        for child in self.stages_container.winfo_children():
            if isinstance(child, StageEditor):
                skill_data["stages"].append(child.get_data())
                
        return skill_data

class Application(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("NIKKE Simulator JSON Maker v3")
        self.geometry("900x850")
        
        main_scroll = ScrollableFrame(self)
        main_scroll.pack(fill="both", expand=True)
        self.content = main_scroll.scrollable_frame
        
        # --- Character Info ---
        info_frame = ttk.LabelFrame(self.content, text="キャラクター基本情報", padding=10)
        info_frame.pack(fill="x", padx=10, pady=5)
        
        grid_opts = {'padx': 5, 'pady': 5, 'sticky': 'w'}
        
        ttk.Label(info_frame, text="名前:").grid(row=0, column=0, **grid_opts)
        self.ent_name = ttk.Entry(info_frame, width=30)
        self.ent_name.grid(row=0, column=1, **grid_opts)
        
        ttk.Label(info_frame, text="部隊(Squad):").grid(row=0, column=2, **grid_opts)
        self.ent_squad = ttk.Entry(info_frame, width=30)
        self.ent_squad.grid(row=0, column=3, **grid_opts)
        
        ttk.Label(info_frame, text="武器種:").grid(row=1, column=0, **grid_opts)
        self.cb_weapon = ttk.Combobox(info_frame, values=[f"{k} : {v}" for k, v in WEAPON_TYPES.items()])
        self.cb_weapon.grid(row=1, column=1, **grid_opts)
        
        ttk.Label(info_frame, text="属性:").grid(row=1, column=2, **grid_opts)
        self.cb_element = ttk.Combobox(info_frame, values=[f"{k} : {v}" for k, v in ELEMENTS.items()])
        self.cb_element.grid(row=1, column=3, **grid_opts)
        
        ttk.Label(info_frame, text="クラス:").grid(row=2, column=0, **grid_opts)
        self.cb_class = ttk.Combobox(info_frame, values=[f"{k} : {v}" for k, v in CLASSES.items()])
        self.cb_class.grid(row=2, column=1, **grid_opts)

        # --- Stats ---
        stats_frame = ttk.LabelFrame(self.content, text="武器・挙動ステータス", padding=10)
        stats_frame.pack(fill="x", padx=10, pady=5)
        
        self.stats_entries = {}
        stat_labels = [
            ("max_ammo", "装弾数", "60"),
            ("reload_time", "リロード時間(秒)", "1.5"),
            ("damage_rate", "武器倍率(%)", "100"), 
            ("windup_frames", "Windup(F)", "12"),
            ("winddown_frames", "Winddown(F)", "10")
        ]
        
        for i, (key, label, default) in enumerate(stat_labels):
            ttk.Label(stats_frame, text=label).grid(row=0, column=i*2, padx=2)
            ent = ttk.Entry(stats_frame, width=10)
            ent.insert(0, default)
            ent.grid(row=0, column=i*2+1, padx=5)
            self.stats_entries[key] = ent

        # --- Skills (Tabs) ---
        skill_frame = ttk.LabelFrame(self.content, text="スキル設定 (複数追加可能)", padding=10)
        skill_frame.pack(fill="both", expand=True, padx=10, pady=5)
        
        toolbar = ttk.Frame(skill_frame)
        toolbar.pack(fill="x", pady=5)
        ttk.Button(toolbar, text="+ Skill 1 追加", command=lambda: self.add_skill_tab("Skill 1: ", "S1")).pack(side="left", padx=2)
        ttk.Button(toolbar, text="+ Skill 2 追加", command=lambda: self.add_skill_tab("Skill 2: ", "S2")).pack(side="left", padx=2)
        ttk.Button(toolbar, text="+ Burst 追加", command=lambda: self.add_skill_tab("Burst: ", "Burst")).pack(side="left", padx=2)
        ttk.Label(toolbar, text=" | ").pack(side="left")
        ttk.Button(toolbar, text="+ 汎用スキル追加", command=lambda: self.add_skill_tab("Skill: ", "Other")).pack(side="left", padx=2)
        
        self.skill_notebook = ttk.Notebook(skill_frame)
        self.skill_notebook.pack(fill="both", expand=True)
        
        self.add_skill_tab("Skill 1: ", "S1")
        self.add_skill_tab("Skill 2: ", "S2")
        self.add_skill_tab("Burst: ", "Burst")

        # --- Footer ---
        footer = ttk.Frame(self)
        footer.pack(fill="x", padx=10, pady=10)
        
        ttk.Button(footer, text="リセット / 新規作成", command=self.reset_form).pack(side="left")
        ttk.Button(footer, text="JSONファイルとして保存", command=self.save_json, style="Accent.TButton").pack(side="right")

    def add_skill_tab(self, default_name_prefix, type_label):
        count = 0
        for tab in self.skill_notebook.tabs():
            if type_label in self.skill_notebook.tab(tab, "text"):
                count += 1
        
        tab_title = type_label
        if count > 0:
            tab_title += f"({count+1})"
            
        tab = SkillTab(self.skill_notebook, default_name=default_name_prefix)
        self.skill_notebook.add(tab, text=tab_title)
        self.skill_notebook.select(tab)

    def reset_form(self):
        if messagebox.askyesno("確認", "フォームをリセットしますか？"):
            self.destroy()
            self.__init__()

    def save_json(self):
        try:
            data = {
                "name": self.ent_name.get(),
                "weapon_type": self.cb_weapon.get().split(" : ")[0],
                "element": self.cb_element.get().split(" : ")[0],
                "class": self.cb_class.get().split(" : ")[0],
                "squad": self.ent_squad.get(),
                "stats": {}
            }
            
            for key, ent in self.stats_entries.items():
                val_str = ent.get()
                val = float(val_str)
                if key == "damage_rate": val /= 100.0
                if key in ["max_ammo", "windup_frames", "winddown_frames"]: val = int(val)
                data["stats"][key] = val
            
            skills_list = []
            burst_skill_data = None
            
            for tab_id in self.skill_notebook.tabs():
                tab_widget = self.skill_notebook.nametowidget(tab_id)
                s_data = tab_widget.get_data()
                
                tab_text = self.skill_notebook.tab(tab_id, "text")
                is_burst = "Burst" in tab_text or s_data["name"].startswith("Burst")
                
                if is_burst:
                    burst_skill_data = s_data
                else:
                    skills_list.append(s_data)
            
            data["skills"] = skills_list
            if burst_skill_data:
                data["burst_skill"] = burst_skill_data
            
            filepath = filedialog.asksaveasfilename(
                defaultextension=".json",
                filetypes=[("JSON Files", "*.json")],
                initialfile=f"{data['name']}.json"
            )
            
            if filepath:
                with open(filepath, "w", encoding="utf-8") as f:
                    json.dump(data, f, indent=2, ensure_ascii=False)
                messagebox.showinfo("成功", f"保存しました:\n{filepath}")
                
        except Exception as e:
            messagebox.showerror("エラー", f"データの生成に失敗しました。\n入力値を確認してください。\n{e}")

if __name__ == "__main__":
    app = Application()
    app.mainloop()