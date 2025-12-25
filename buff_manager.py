class BuffManager:
    def __init__(self):
        self.buffs = {}
        self.active_stacks = {}

    def add_buff(self, buff_type, value, duration_frames, current_frame, source=None, stack_name=None, max_stack=1, tag=None, shot_duration=0, remove_on_reload=False, stack_amount=1):
        buff_data = {
            'val': value, 'end_frame': current_frame + duration_frames, 
            'source': source, 'tag': tag, 'shot_life': shot_duration, 'remove_on_reload': remove_on_reload
            ,'start_frame': current_frame  # ▼ 追加: 開始フレームを記録 (LIFO用)
        }
        if stack_name:
            if stack_name in self.active_stacks:
                stack_data = self.active_stacks[stack_name]
                stack_data['count'] = min(stack_data['max_stack'], stack_data['count'] + stack_amount)
                stack_data['start_frame'] = current_frame
                stack_data['end_frame'] = current_frame + duration_frames
                stack_data['unit_value'] = value 
                stack_data['tag'] = tag
                stack_data['shot_life'] = shot_duration
                stack_data['remove_on_reload'] = remove_on_reload
                return stack_data['count']
            else:
                self.active_stacks[stack_name] = {
                    'count': min(max_stack, stack_amount), 'max_stack': max_stack, 'buff_type': buff_type,
                    'unit_value': value, 'end_frame': current_frame + duration_frames,
                    'tag': tag, 'shot_life': shot_duration, 'remove_on_reload': remove_on_reload,
                    'start_frame': current_frame  # ▼ 追加
                }
                return stack_amount
        else:
            if buff_type not in self.buffs: self.buffs[buff_type] = []
            existing_buff = None
            if source is not None:
                for b in self.buffs[buff_type]:
                    if b.get('source') == source: existing_buff = b; break
            if existing_buff: 
                existing_buff.update(buff_data)
                existing_buff['start_frame'] = current_frame # ▼ 更新時もタイムスタンプ更新
            
            else: self.buffs[buff_type].append(buff_data)
            return 1

    def set_stack_count(self, stack_name, count, max_stack=100):
        if stack_name in self.active_stacks:
            self.active_stacks[stack_name]['count'] = min(self.active_stacks[stack_name]['max_stack'], count)
        else:
            self.active_stacks[stack_name] = {
                'count': min(max_stack, count), 'max_stack': max_stack, 'buff_type': 'counter',
                'unit_value': 0, 'end_frame': 99999999, 'tag': None, 'shot_life': 0, 'remove_on_reload': False
            }

    def modify_active_stack_counts(self, delta, frame, ignore_tags=None):
        if ignore_tags is None:
            ignore_tags = []
            
        modified_count = 0
        
        if isinstance(self.buffs, dict):
            all_buff_lists = self.buffs.values()
        else:
            all_buff_lists = [self.buffs]
            
        for buff_list in all_buff_lists:
            for b in buff_list:
                
                current_tag = b.get('tag')
                
                is_ignored = False
                if current_tag:
                    if isinstance(current_tag, list):
                        # タグリストの中に ignore_tags に含まれるものが1つでもあれば除外
                        if any(t in ignore_tags for t in current_tag):
                            is_ignored = True
                    else:
                        # 文字列の場合
                        if current_tag in ignore_tags:
                            is_ignored = True
                
                if is_ignored:
                    continue
                # ▲▲▲ 修正ここまで ▲▲▲

                if 'stack_count' in b:
                    old_count = b['stack_count']
                    max_stack = b.get('max_stack', 1)
                    
                    # 新しいスタック数を計算（最大値を超えないように）
                    new_count = max(1, min(max_stack, old_count + delta))
                    
                    # ▼▼▼ 修正: スタック増加操作 (delta > 0) なら無条件で時間リセット ▼▼▼
                    if delta > 0:
                        # スタック数が変わるか、既に最大値の場合でもリセットを実行
                        
                        # 時間リセット
                        if 'duration_frames' in b:
                             b['duration'] = b['duration_frames']
                             b['start_frame'] = frame
                        
                        # スタック数を更新（値が変わっていれば）
                        if new_count != old_count:
                            b['stack_count'] = new_count
                        
                        # 「効果が適用された（リセット含む）」としてカウント
                        modified_count += 1
                        
                    # ▼▼▼ スタック減少操作の場合 ▼▼▼
                    elif new_count < old_count:
                         b['stack_count'] = new_count
                         modified_count += 1
                    
        return modified_count


    def remove_buffs_by_tag(self, tag, current_frame):
        if not tag: return
        # ▼▼▼ 内部関数: 削除対象判定 (リスト対応) ▼▼▼
        def should_remove(b_tag):
            if isinstance(b_tag, list):
                return tag in b_tag
            return b_tag == tag
        # ▲▲▲
        for buff_type in self.buffs:
            self.buffs[buff_type] = [b for b in self.buffs[buff_type] if b.get('tag') != tag]
        keys_to_remove = [k for k, v in self.active_stacks.items() if v.get('tag') == tag]
        for k in keys_to_remove: del self.active_stacks[k]

    # ▼▼▼ 追加: LIFO方式でのデバフ解除 ▼▼▼
    def remove_debuffs_lifo(self, tag, count, current_frame):
        """
        指定されたタグ(tag)を持つバフ・スタックを、付与されたのが新しい順に count 個解除する。
        スタック型の場合はスタック数を減らす。
        """
        if count <= 0: return 0
        
        # 1. 解除候補（バフリストのエントリ または スタック）をすべて収集
        candidates = []

        # ▼▼▼ 判定関数の定義 ▼▼▼
        def is_match(b_tag):
            if isinstance(b_tag, list): return tag in b_tag
            return b_tag == tag
        # ▲▲▲
        
        # (A) 通常バフリストから候補収集
        for b_type, b_list in self.buffs.items():
            for b in b_list:
                if is_match(b.get('tag')):
                    # 参照を保持して後で削除/変更できるようにする
                    candidates.append({
                        'type': 'list', 'buff_type': b_type, 'data': b, 
                        'start_frame': b.get('start_frame', 0)
                    })
                    
        # (B) スタックから候補収集
        for s_name, s_data in self.active_stacks.items():
            if is_match(s_data.get('tag')):
                # スタックの場合は現在のスタック数分だけ候補に入れる（1つずつ減らすため）
                # ただし効率のため、スタックエントリ自体を1つの候補とし、処理時に count 分減らす
                candidates.append({
                    'type': 'stack', 'stack_name': s_name, 'data': s_data, 
                    'start_frame': s_data.get('start_frame', 0)
                })

        # 2. 開始フレームの降順（新しい順）にソート
        candidates.sort(key=lambda x: x['start_frame'], reverse=True)
        
        removed_count = 0
        
        # 3. 候補を上から順に処理
        for cand in candidates:
            if removed_count >= count: break
            
            if cand['type'] == 'list':
                # リスト型バフ: 1つ削除
                b_list = self.buffs[cand['buff_type']]
                if cand['data'] in b_list:
                    b_list.remove(cand['data'])
                    removed_count += 1
                    
            elif cand['type'] == 'stack':
                # スタック型バフ: 必要な分だけスタックを減らす
                s_data = cand['data']
                current_stack = s_data['count']
                
                needed = count - removed_count
                to_remove = min(current_stack, needed)
                
                s_data['count'] -= to_remove
                removed_count += to_remove
                
                # スタック0になったら削除
                if s_data['count'] <= 0:
                    del self.active_stacks[cand['stack_name']]
                    
        return removed_count
    # ▲▲▲ 追加ここまで ▲▲▲

    # ▼▼▼ 追加: 免疫 (Immunity) 関連 ▼▼▼
    def has_active_immunity(self, current_frame):
        """免疫バフ (tag: 'immunity') が有効かチェック"""
        # バフリスト走査
        for b_list in self.buffs.values():
            for b in b_list:
                if b.get('tag') == 'immunity' and (b['end_frame'] >= current_frame or b['shot_life'] > 0):
                    return True
        # スタック走査
        for s_data in self.active_stacks.values():
            if s_data.get('tag') == 'immunity' and (s_data['end_frame'] >= current_frame or s_data['shot_life'] > 0):
                if s_data['count'] > 0: return True
        return False

    def consume_immunity_stack(self, current_frame):
        """免疫バフのスタックを1つ消費する (スタックがないタイプなら消費せずTrueを返す)"""

        # ▼▼▼ 内部関数: タグ一致判定 (リスト対応) ▼▼▼
        def is_match(b_tag):
            if isinstance(b_tag, list):
                return 'immunity' in b_tag
            return b_tag == 'immunity'
        # ▲▲▲
        # 1. スタック型の免疫を優先して探し、減らす
        # 辞書の変更エラーを防ぐため list() でラップするか、見つけたら即 return する
        for s_name, s_data in self.active_stacks.items():
            # 修正: is_match を使用して判定
            if is_match(s_data.get('tag')) and (s_data['end_frame'] >= current_frame or s_data['shot_life'] > 0):
                if s_data['count'] > 0:
                    s_data['count'] -= 1
                    # スタックが0になったら削除
                    if s_data['count'] <= 0:
                        del self.active_stacks[s_name]
                    return True # 消費成功
        
        # 2. スタック型でない免疫があれば、消費なしで機能する (回数制限なし免疫)
        # (has_active_immunity は既にリスト対応済みと想定)
        if self.has_active_immunity(current_frame):
            return True
            
        return False
    # ▲▲▲ 追加ここまで ▲▲▲

    def remove_reload_buffs(self):
        for buff_type in self.buffs:
            self.buffs[buff_type] = [b for b in self.buffs[buff_type] if not b.get('remove_on_reload', False)]
        keys_to_remove = [k for k, v in self.active_stacks.items() if v.get('remove_on_reload', False)]
        for k in keys_to_remove: del self.active_stacks[k]

    def has_active_tag(self, tag, current_frame):
        if not tag: return False

        # ▼▼▼ 内部関数: タグ一致判定 (リスト対応) ▼▼▼
        def is_match(b_tag):
            if isinstance(b_tag, list):
                return tag in b_tag
            return b_tag == tag
        # ▲▲▲

        for buff_list in self.buffs.values():
            for b in buff_list:
                if b.get('tag') == tag and (b['end_frame'] >= current_frame or b['shot_life'] > 0): return True
        for stack in self.active_stacks.values():
            if stack.get('tag') == tag and (stack['end_frame'] >= current_frame or stack['shot_life'] > 0): return True
        return False

    def get_total_value(self, buff_type, current_frame):
        total = 0.0
        if buff_type in self.buffs:
            valid_buffs = [b for b in self.buffs[buff_type] if b['end_frame'] >= current_frame or b['shot_life'] > 0]
            self.buffs[buff_type] = valid_buffs
            total += sum(b['val'] for b in valid_buffs)
        expired_stacks = []
        for name, stack in self.active_stacks.items():
            if stack['end_frame'] < current_frame and stack['shot_life'] <= 0:
                expired_stacks.append(name)
                continue
            if stack['buff_type'] == buff_type:
                total += stack['unit_value'] * stack['count']
        for name in expired_stacks: del self.active_stacks[name]
        return total
    
    def get_active_buffs(self, buff_type, current_frame):
        vals = []
        if buff_type in self.buffs:
            valid_buffs = [b for b in self.buffs[buff_type] if b['end_frame'] >= current_frame or b['shot_life'] > 0]
            self.buffs[buff_type] = valid_buffs
            vals.extend([b['val'] for b in valid_buffs])
        for name, stack in list(self.active_stacks.items()):
            if stack['end_frame'] >= current_frame or stack['shot_life'] > 0:
                if stack['buff_type'] == buff_type:
                    for _ in range(stack['count']): vals.append(stack['unit_value'])
            else: del self.active_stacks[name]
        return vals
    
    def get_stack_count(self, stack_name, current_frame):
        if stack_name in self.active_stacks:
            stack = self.active_stacks[stack_name]
            if stack['end_frame'] >= current_frame or stack['shot_life'] > 0: return stack['count']
            else: del self.active_stacks[stack_name]
        return 0

    def decrement_shot_buffs(self):
        for buff_type in self.buffs:
            for b in self.buffs[buff_type]:
                if b['shot_life'] > 0: b['shot_life'] -= 1
        for name, stack in self.active_stacks.items():
            if stack['shot_life'] > 0: stack['shot_life'] -= 1
    
    def get_active_buffs_debug(self, current_frame):
        parts = []
        for b_type, b_list in self.buffs.items():
            active_list = [b for b in b_list if b['end_frame'] >= current_frame or b['shot_life'] > 0]
            if active_list:
                total = sum(b['val'] for b in active_list)
                parts.append(f"{b_type}:{total:.2f}")
        for name, stack in self.active_stacks.items():
            if stack['end_frame'] >= current_frame or stack['shot_life'] > 0:
                val = stack['unit_value'] * stack['count']
                parts.append(f"[{name} x{stack['count']} (Val:{val:.2f})]")
        return " | ".join(parts) if parts else "None"
    
    def remove_stack(self, stack_name):
        """指定された名前のスタックを削除する"""
        if stack_name in self.active_stacks:
            del self.active_stacks[stack_name]

    # ▼▼▼ 追加: 指定タグを持つスタックのカウントを減らす ▼▼▼
    def decrease_stack_count_by_tag(self, tag, amount=1):
        """
        指定されたタグ(tag)を持つ全てのアクティブなスタックについて、
        スタック数を amount だけ減らす。0以下になってもエントリは残すが効果は消える(count=0)。
        """
        for stack_name, data in self.active_stacks.items():
            # ▼▼▼ 修正: リスト対応 ▼▼▼
            b_tag = data.get('tag')
            is_target = False
            if isinstance(b_tag, list):
                if tag in b_tag: is_target = True
            elif b_tag == tag:
                is_target = True
            
            if is_target:
            # ▲▲▲
                current = data['count']
                new_count = max(0, current - amount)
                data['count'] = new_count
                return True
        return False
    # ▲▲▲ 追加ここまで ▲▲▲