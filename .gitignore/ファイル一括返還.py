import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import json
import os

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

KWARGS_KEYS = [
    "buff_type", "value", "duration", "shot_duration",
    "multiplier", "loop_count", "trigger_all_stages",
    "scale_by_caster_stats", "stat_type",
    "max_stack", "stack_name", "remove_on_reload",
    "target_condition"
]

BUFF_TYPES = [
    "atk_buff_rate", "atk_buff_fixed", "atk_dmg_buff",
    "crit_rate_buff", "crit_dmg_buff",
    "reload_speed_rate", "max_ammo_rate",
    "charge_speed_rate", "charge_dmg_buff",
    "def_buff_rate", "hit_rate_buff",
    "pierce_dmg_buff", "core_dmg_buff", "part_dmg_buff",
    "elemental_buff",
    "dummy_heal", "dummy_effect"
]

TARGET_CONDITION_TYPES = {
    "highest_atk": "highest_atk (攻撃力が高い順)",
    "weapon_type": "weapon_type (武器種指定)",
    "element": "element (属性指定)",
    "class": "class (クラス指定)",
    "used_burst": "used_burst (バースト使用済み)"
}

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

class TargetConditionDialog(tk.Toplevel):
    def __init__(self, parent, current_data=None):
        super().__init__(parent)
        self.title("ターゲット条件設定")
        self.geometry("400x300")
        self.result = None
        
        if current_data is None:
            current_data = {}
            
        ttk.Label(self, text="条件タイプ:").pack(pady=(10, 2))
        self.cb_type = ttk.Combobox(self, values=[f"{k} : {v}" for k, v in TARGET_CONDITION_TYPES.items()], width=35)
        self.cb_type.pack(pady=5)
        
        # Set initial type
        init_type = current_data.get("type", "highest_atk")
        for k in TARGET_CONDITION_TYPES:
            if k == init_type:
                self.cb_type.set(f"{k} : {TARGET_CONDITION_TYPES[k]}")
                break
        
        self.cb_type.bind("<<ComboboxSelected>>", self.update_fields)
        
        self.param_frame = ttk.Frame(self)
        self.param_frame.pack(fill="both", expand=True, padx=10, pady=10)
        
        self.widgets = {}
        
        ttk.Button(self, text="確定", command=self.on_ok).pack(pady=10)
        
        self.update_fields()
        
        # Set initial values
        if init_type == "highest_atk" and "count" in current_data:
            self.widgets["count"].delete(0, tk.END)
            self.widgets["count"].insert(0, str(current_data["count"]))
        elif "value" in current_data and "value" in self.widgets:
            # For combos, find matching text
            val = current_data["value"]
            w = self.widgets["value"]
            if isinstance(w, ttk.Combobox):
                # Try to set matching key
                for v in w['values']:
                    if v.startswith(val):
                        w.set(v)
                        break
                else:
                    w.set(val)
            else:
                w.delete(0, tk.END)
                w.insert(0, str(val))

    def update_fields(self, event=None):
        # Clear frame
        for w in self.param_frame.winfo_children():
            w.destroy()
        self.widgets = {}
        
        c_type = self.cb_type.get().split(" : ")[0]
        
        if c_type == "highest_atk":
            ttk.Label(self.param_frame, text="対象人数 (count):").pack(anchor="w")
            ent = ttk.Entry(self.param_frame)
            ent.insert(0, "1")
            ent.pack(fill="x")
            self.widgets["count"] = ent
            
        elif c_type == "weapon_type":
            ttk.Label(self.param_frame, text="武器種 (value):").pack(anchor="w")
            cb = ttk.Combobox(self.param_frame, values=[k for k in WEAPON_TYPES.keys()])
            cb.pack(fill="x")
            self.widgets["value"] = cb
            
        elif c_type == "element":
            ttk.Label(self.param_frame, text="属性 (value):").pack(anchor="w")
            cb = ttk.Combobox(self.param_frame, values=[k for k in ELEMENTS.keys()])
            cb.pack(fill="x")
            self.widgets["value"] = cb
            
        elif c_type == "class":
            ttk.Label(self.param_frame, text="クラス (value):").pack(anchor="w")
            cb = ttk.Combobox(self.param_frame, values=[k for k in CLASSES.keys()])
            cb.pack(fill="x")
            self.widgets["value"] = cb
            
        elif c_type == "used_burst":
            ttk.Label(self.param_frame, text="追加パラメータはありません").pack(pady=20)

    def on_ok(self):
        c_type = self.cb_type.get().split(" : ")[0]
        data = {"type": c_type}
        
        if "count" in self.widgets:
            try:
                data["count"] = int(self.widgets["count"].get())
            except:
                data["count"] = 1
        
        if "value" in self.widgets:
            val = self.widgets["value"].get()
            if not val:
                messagebox.showwarning("警告", "値を入力してください")
                return
            data["value"] = val
            
        self.result = data
        self.destroy()

class KwargsRow(ttk.Frame):
    def __init__(self, parent, key="", val="", delete_callback=None):
        super().__init__(parent)
        self.delete_callback = delete_callback
        self.complex_data = None # For dictionaries like target_condition
        
        self.cb_key = ttk.Combobox(self, values=KWARGS_KEYS, width=23)
        self.cb_key.set(key)
        self.cb_key.pack(side="left")
        self.cb_key.bind("<<ComboboxSelected>>", self.on_key_changed)
        self.cb_key.bind("<KeyRelease>", self.on_key_changed)

        self.val_frame = ttk.Frame(self)
        self.val_frame.pack(side="left", padx=2)
        
        self.val_widget = None
        
        # Initial Setup
        if key == "target_condition" and isinstance(val, dict):
            self.complex_data = val
            self.create_val_widget(val)
        else:
            self.create_val_widget(val)

        btn_del = ttk.Button(self, text="x", width=3, command=self.delete)
        btn_del.pack(side="left", padx=2)

    def create_val_widget(self, initial_val=""):
        if self.val_widget:
            self.val_widget.destroy()
        
        key = self.cb_key.get()
        
        if key == "target_condition":
            self.val_widget = ttk.Button(self.val_frame, text="設定...", command=self.open_condition_dialog, width=22)
            # Show summary label if data exists
            if self.complex_data:
                summary = f"{self.complex_data.get('type', '?')}"
            else:
                summary = ""
                # Default init if empty
                if isinstance(initial_val, dict): self.complex_data = initial_val
            
        elif key == "buff_type":
            self.val_widget = ttk.Combobox(self.val_frame, values=BUFF_TYPES, width=23)
            self.val_widget.set(str(initial_val))
        elif key in ["trigger_all_stages", "scale_by_caster_stats", "remove_on_reload"]:
            self.val_widget = ttk.Combobox(self.val_frame, values=["true", "false"], width=23)
            current = str(initial_val).lower()
            self.val_widget.set("true" if current == "true" else "false" if current == "false" else "")
        else:
            self.val_widget = ttk.Entry(self.val_frame, width=25)
            if not isinstance(initial_val, dict):
                self.val_widget.insert(0, str(initial_val))
            
        self.val_widget.pack(fill="x")

    def open_condition_dialog(self):
        dlg = TargetConditionDialog(self, self.complex_data)
        self.wait_window(dlg)
        if dlg.result:
            self.complex_data = dlg.result
            # Update button text to show set
            self.val_widget.configure(text=f"設定済: {dlg.result.get('type')}")

    def on_key_changed(self, event=None):
        current_key = self.cb_key.get()
        
        # Check current widget type matches key requirement
        is_button = isinstance(self.val_widget, ttk.Button)
        is_combobox = isinstance(self.val_widget, ttk.Combobox)
        
        if current_key == "target_condition":
            if not is_button:
                self.create_val_widget()
        elif current_key == "buff_type":
            if not is_combobox or getattr(self.val_widget, 'values', None) != tuple(BUFF_TYPES):
                self.create_val_widget()
        elif current_key in ["trigger_all_stages", "scale_by_caster_stats", "remove_on_reload"]:
             if not is_combobox or getattr(self.val_widget, 'values', None) != ("true", "false"):
                 self.create_val_widget()
        else:
            if is_button or is_combobox:
                self.create_val_widget()

    def delete(self):
        if self.delete_callback:
            self.delete_callback(self)

    def get_data(self):
        k = self.cb_key.get().strip()
        if not k: return None, None
        
        if k == "target_condition":
            return k, self.complex_data
            
        v_str = self.val_widget.get().strip()
        if v_str.lower() == "true": v = True
        elif v_str.lower() == "false": v = False
        else:
            try:
                if "." in v_str: v = float(v_str)
                else: v = int(v_str)
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

    def set_data(self, data):
        for row in list(self.rows):
            self.delete_row(row)
        if not data: return
        for k, v in data.items():
            self.add_row(k, v)

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

    def set_data(self, data):
        eff = data.get("effect_type", "buff")
        for k in EFFECT_TYPES:
            if k == eff:
                self.cb_effect.set(f"{k} : {EFFECT_TYPES[k]}")
                break
        else:
            self.cb_effect.set(eff)
            
        tgt = data.get("target", "")
        if tgt:
            for k in TARGETS:
                if k == tgt:
                    self.cb_target.set(f"{k} : {TARGETS[k]}")
                    break
            else:
                self.cb_target.set(tgt)
                
        kwargs = data.get("kwargs", {}).copy()
        if "profile" in kwargs:
            prof = kwargs["profile"]
            if isinstance(prof, dict) and prof.get("is_skill_damage"):
                self.var_skill_dmg.set(True)
            del kwargs["profile"]
            
        self.kwargs_editor.set_data(kwargs)

class SkillTab(ttk.Frame):
    def __init__(self, parent, notebook, default_name=""):
        super().__init__(parent)
        self.notebook = notebook 
        
        btn_del_skill = ttk.Button(self, text="このスキルタブを削除", command=self.delete_self)
        btn_del_skill.pack(anchor="e", padx=5, pady=2)

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

        f_kwargs = ttk.LabelFrame(self, text="スキルパラメータ (kwargs)", padding=5)
        f_kwargs.pack(fill="x", pady=5)
        self.main_kwargs = KwargsEditor(f_kwargs)
        self.main_kwargs.pack(fill="x")
        
        btn_frame = ttk.Frame(f_kwargs)
        btn_frame.pack(anchor="e")
        
        # --- Helper Buttons ---
        ttk.Button(btn_frame, text="条件(Target Condition)追加",
                   command=lambda: self.main_kwargs.add_row("target_condition", {})).pack(side="right", padx=2)
        ttk.Button(btn_frame, text="一括発動(All Stages)追加", 
                   command=lambda: self.main_kwargs.add_row("trigger_all_stages", "true")).pack(side="right", padx=2)
        ttk.Button(btn_frame, text="攻撃力固定値バフ(Caster Base)", 
                   command=lambda: [self.main_kwargs.add_row("buff_type", "atk_buff_fixed"), 
                                    self.main_kwargs.add_row("scale_by_caster_stats", "true"),
                                    self.main_kwargs.add_row("stat_type", "base")]).pack(side="right", padx=2)
        ttk.Button(btn_frame, text="ダミー効果(効果なし)", 
                   command=lambda: [self.main_kwargs.add_row("buff_type", "dummy_effect"), 
                                    self.main_kwargs.add_row("value", "0")]).pack(side="right", padx=2)

        self.f_stages = ttk.LabelFrame(self, text="Stages (効果詳細リスト)", padding=5)
        self.f_stages.pack(fill="both", expand=True, pady=5)
        
        btn_add_stage = ttk.Button(self.f_stages, text="+ ステージ効果を追加", command=self.add_stage)
        btn_add_stage.pack(anchor="nw", pady=2)
        
        self.stages_container = ttk.Frame(self.f_stages)
        self.stages_container.pack(fill="both", expand=True)

    def delete_self(self):
        if messagebox.askyesno("確認", "このスキルタブを削除しますか？"):
            self.notebook.forget(self)
            self.destroy()

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
        
        trigger_val_final = trig_val
        if isinstance(trig_val, float) and trig_val.is_integer():
            trigger_val_final = int(trig_val)
        
        skill_data = {
            "name": self.ent_name.get(),
            "trigger_type": trig_raw,
            "trigger_value": trigger_val_final,
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

    def set_data(self, data):
        self.ent_name.delete(0, tk.END)
        self.ent_name.insert(0, data.get("name", ""))
        
        trig = data.get("trigger_type", "")
        for k in TRIGGER_TYPES:
            if k == trig:
                self.cb_trigger.set(f"{k} : {TRIGGER_TYPES[k]}")
                break
        else:
            self.cb_trigger.set(trig)
            
        self.ent_trig_val.delete(0, tk.END)
        self.ent_trig_val.insert(0, str(data.get("trigger_value", 0)))
        
        self.ent_cd.delete(0, tk.END)
        self.ent_cd.insert(0, str(data.get("cooldown", 0)))
        
        eff = data.get("effect_type", "")
        for k in EFFECT_TYPES:
            if k == eff:
                self.cb_effect.set(f"{k} : {EFFECT_TYPES[k]}")
                break
        else:
            self.cb_effect.set(eff)
            
        tgt = data.get("target", "")
        for k in TARGETS:
            if k == tgt:
                self.cb_target.set(f"{k} : {TARGETS[k]}")
                break
        else:
            self.cb_target.set(tgt)
            
        self.main_kwargs.set_data(data.get("kwargs", {}))
        
        for child in self.stages_container.winfo_children():
            child.destroy()
            
        stages = data.get("stages", [])
        for i, s_data in enumerate(stages):
            stage = StageEditor(self.stages_container, i)
            stage.pack(fill="x", pady=2)
            stage.set_data(s_data)

class Application(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("NIKKE Simulator JSON Maker v6")
        self.geometry("950x900")
        
        main_scroll = ScrollableFrame(self)
        main_scroll.pack(fill="both", expand=True)
        self.content = main_scroll.scrollable_frame
        
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
        self.cb_weapon.bind("<<ComboboxSelected>>", self.on_weapon_changed)
        
        ttk.Label(info_frame, text="属性:").grid(row=1, column=2, **grid_opts)
        self.cb_element = ttk.Combobox(info_frame, values=[f"{k} : {v}" for k, v in ELEMENTS.items()])
        self.cb_element.grid(row=1, column=3, **grid_opts)
        
        ttk.Label(info_frame, text="クラス:").grid(row=2, column=0, **grid_opts)
        self.cb_class = ttk.Combobox(info_frame, values=[f"{k} : {v}" for k, v in CLASSES.items()])
        self.cb_class.grid(row=2, column=1, **grid_opts)

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

        footer = ttk.Frame(self)
        footer.pack(fill="x", padx=10, pady=10)
        
        ttk.Button(footer, text="リセット / 新規作成", command=self.reset_form).pack(side="left")
        
        btn_right = ttk.Frame(footer)
        btn_right.pack(side="right")
        ttk.Button(btn_right, text="JSONファイルを読み込み", command=self.load_json).pack(side="left", padx=5)
        ttk.Button(btn_right, text="JSONファイルとして保存", command=self.save_json, style="Accent.TButton").pack(side="left", padx=5)

    def on_weapon_changed(self, event=None):
        w_raw = self.cb_weapon.get().split(" : ")[0].lower()
        if not w_raw: return
        
        json_path = f"weapons/{w_raw}_standard.json"
        if not os.path.exists(json_path):
            print(f"Warning: Template {json_path} not found.")
            return
            
        try:
            with open(json_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            if "max_ammo" in data:
                self.stats_entries["max_ammo"].delete(0, tk.END)
                self.stats_entries["max_ammo"].insert(0, str(data["max_ammo"]))
            
            if "reload_frames" in data:
                sec = data["reload_frames"] / 60.0
                self.stats_entries["reload_time"].delete(0, tk.END)
                self.stats_entries["reload_time"].insert(0, str(sec))
            
            if "multiplier" in data:
                pct = data["multiplier"] * 100.0
                self.stats_entries["damage_rate"].delete(0, tk.END)
                self.stats_entries["damage_rate"].insert(0, str(pct))
                
            if "windup_frames" in data:
                self.stats_entries["windup_frames"].delete(0, tk.END)
                self.stats_entries["windup_frames"].insert(0, str(data["windup_frames"]))
                
            if "winddown_frames" in data:
                self.stats_entries["winddown_frames"].delete(0, tk.END)
                self.stats_entries["winddown_frames"].insert(0, str(data["winddown_frames"]))
                
            print(f"Loaded template for {w_raw.upper()}")
            
        except Exception as e:
            print(f"Error loading template: {e}")

    def add_skill_tab(self, default_name_prefix, type_label):
        count = 0
        for tab in self.skill_notebook.tabs():
            if type_label in self.skill_notebook.tab(tab, "text"):
                count += 1
        
        tab_title = type_label
        if count > 0:
            tab_title += f"({count+1})"
            
        tab = SkillTab(self.skill_notebook, self.skill_notebook, default_name=default_name_prefix)
        self.skill_notebook.add(tab, text=tab_title)
        self.skill_notebook.select(tab)
        return tab

    def reset_form(self):
        if messagebox.askyesno("確認", "フォームをリセットしますか？"):
            self.destroy()
            self.__init__()

    def load_json(self):
        filepath = filedialog.askopenfilename(
            filetypes=[("JSON Files", "*.json")],
            title="JSONファイルを選択"
        )
        if not filepath: return
        
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            self.ent_name.delete(0, tk.END)
            self.ent_squad.delete(0, tk.END)
            
            self.ent_name.insert(0, data.get("name", ""))
            self.ent_squad.insert(0, data.get("squad", ""))
            
            w_type = data.get("weapon_type", "AR")
            self.cb_weapon.set(f"{w_type} : {WEAPON_TYPES.get(w_type, w_type)}")
            
            el = data.get("element", "Iron")
            self.cb_element.set(f"{el} : {ELEMENTS.get(el, el)}")
            
            cls = data.get("class", "Attacker")
            self.cb_class.set(f"{cls} : {CLASSES.get(cls, cls)}")
            
            stats = data.get("stats", {})
            if "max_ammo" in stats:
                self.stats_entries["max_ammo"].delete(0, tk.END)
                self.stats_entries["max_ammo"].insert(0, str(stats["max_ammo"]))
            if "reload_time" in stats:
                self.stats_entries["reload_time"].delete(0, tk.END)
                self.stats_entries["reload_time"].insert(0, str(stats["reload_time"]))
            if "damage_rate" in stats:
                self.stats_entries["damage_rate"].delete(0, tk.END)
                self.stats_entries["damage_rate"].insert(0, str(stats["damage_rate"] * 100.0))
            if "windup_frames" in stats:
                self.stats_entries["windup_frames"].delete(0, tk.END)
                self.stats_entries["windup_frames"].insert(0, str(stats["windup_frames"]))
            if "winddown_frames" in stats:
                self.stats_entries["winddown_frames"].delete(0, tk.END)
                self.stats_entries["winddown_frames"].insert(0, str(stats["winddown_frames"]))
                
            for tab_id in self.skill_notebook.tabs():
                self.skill_notebook.forget(tab_id)
            
            skills = data.get("skills", [])
            for i, sk_data in enumerate(skills):
                label = f"Skill {i+1}"
                tab = self.add_skill_tab("", label)
                tab.set_data(sk_data)
                
            burst_skill = data.get("burst_skill")
            if burst_skill:
                tab = self.add_skill_tab("", "Burst")
                tab.set_data(burst_skill)
                
            messagebox.showinfo("完了", "ファイルを読み込みました。")
            
        except Exception as e:
            messagebox.showerror("エラー", f"読み込みに失敗しました:\n{e}")

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
                try:
                    tab_widget = self.skill_notebook.nametowidget(tab_id)
                    s_data = tab_widget.get_data()
                    
                    tab_text = self.skill_notebook.tab(tab_id, "text")
                    is_burst = "Burst" in tab_text or s_data["name"].startswith("Burst")
                    
                    if is_burst:
                        burst_skill_data = s_data
                    else:
                        skills_list.append(s_data)
                except tk.TclError:
                    continue
            
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