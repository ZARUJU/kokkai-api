# 人物インデックスの項目定義

この文書は、`data/people/index.json` に生成する人物インデックス JSON の各項目が何を意味するかをまとめたものである。

2026-03-13 時点では、`src/pipeline/people/build_people_index.py` がこの形式で生成する。

## 1. ファイル構成

- パス
  `data/people/index.json`

## 2. トップレベル

- `built_at`
  人物インデックスを生成した UTC 時刻
- `items`
  人物ごとの配列

## 3. `items[]`

- `person_key`
  人物名の正規化キー。現時点では空白正規化と末尾敬称 `君` の除去を行った日本語名
- `canonical_name`
  代表表示名。現時点では `person_key` と同じ
- `name_variants`
  配布元 JSON に現れた人物名表記の一覧
- `gian_relations`
  議案との関係配列
- `shitsumon_relations`
  質問主意書との関係配列

## 4. `gian_relations[]`

- `bill_id`
  議案 ID
- `title`
  議案件名
- `role`
  人物の役割。現時点では `submitter_representative` `submitter` `supporter`
- `submitted_session`
  議案提出回次

## 5. `shitsumon_relations[]`

- `question_id`
  質問主意書 ID
- `title`
  質問主意書件名
- `role`
  人物の役割。現時点では `submitter` `answerer`
- `house`
  `shugiin` または `sangiin`
- `session_number`
  質問主意書 ID から復元した回次

## 6. 利用上の注意

- 人物の同一性判定はまだ厳密な名寄せを行っていない
- `person_key` は将来の外部公開用永続 ID ではなく、日本語表記ベースの配布用キーである
- 議案の `submitter_representative` は、`外X名` がある場合でも代表者1名だけを指す
