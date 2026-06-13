# Union Raid CSV Exporter

`https://oooooo.rip/` の `Global / JP / KR / NA / SEA` ページから、Union Raid の Step ごとのデータを CSV に出力するスクリプトです。

## 出力内容

各サーバーごとに、`output/<server>/step_XX_<boss>.csv` を作成します。

CSV には次の情報を入れています。

- `UTC`
- `Raid Lv`
- `Team Lv`
- `Team 1 Name` から `Team 5 Name`
- `Team 1 LB` から `Team 5 LB`
- `Team (Name+LB)` のカンマ区切り文字列
- `Damage`
- `Union Name` / `Union Rank` / `Player Name` などの識別用情報

文字コードは Excel で開きやすい `UTF-8 with BOM` です。

## 使い方

```powershell
& 'C:\Users\memor\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' .\export_union_raid_steps.py
```

別の出力先にしたい場合:

```powershell
& 'C:\Users\memor\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' .\export_union_raid_steps.py --output-dir .\exports
```

特定サーバーだけ出したい場合:

```powershell
& 'C:\Users\memor\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' .\export_union_raid_steps.py --servers jp kr
```

## 補足

- スクリプトは `lxml` を使って HTML を解析します。
- 対象サイトの HTML 構造が変わると、抽出ロジックの修正が必要になる場合があります。
