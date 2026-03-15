# 人物インデックス

この文書は、人物インデックスについて「どの配布データを入力にするか」「どのように人物単位へ集約するか」「最終的にどの JSON を配布するか」をまとめたものである。

2026-03-13 時点では、`src/pipeline/people/build_people_index.py` がこの形式で生成する。

## 1. 対象データ

- 配布データ
  `data/people/index.json`
  `data/people/detail/*.json`

## 2. 入力元

人物インデックスは外部サイトから直接取得せず、他の配布用 JSON を再利用して生成する。

- `data/gian/detail/*.json`
  議案の提出者代表、提出者一覧、賛成者
- `data/seigan/{house}/detail/*.json`
  請願紹介議員
- `data/shitsumon/shugiin/detail/*.json`
  衆議院質問主意書の提出者、答弁者
- `data/shitsumon/sangiin/detail/*.json`
  参議院質問主意書の提出者、答弁者
- `data/kaigiroku/detail/*.json`
  会議録個票に入った出席者や発言者との関係
- `tmp/kaigiroku/meeting/*.json`
  会議録 API 原本から拾う発言者名などの補助情報

## 3. 生成フロー

### 3.1 入力 JSON の走査

- パイプライン
  `src/pipeline/people/build_people_index.py`
- 処理
  各配布データを読み込み、人物名が含まれるフィールドを列挙する

### 3.2 人物名の正規化

- 代表処理
  - 空白正規化
  - 末尾敬称 `君` の除去
- 出力
  `person_key`

現時点では厳密な名寄せではなく、日本語表記ベースの緩い正規化キーとして扱う。

### 3.3 関係データの集約

人物ごとに、元データ側の役割を保ったまま関係配列へ格納する。

- 議案
  `submitter_representative`, `submitter`, `supporter`
- 請願
  `presenter`
- 質問主意書
  `submitter`, `answerer`
- 会議録
  出席会議、発言会議

### 3.4 保存

- 出力
  `data/people/index.json`
  `data/people/detail/*.json`

## 4. 配布 JSON

### 4.1 ファイル構成

- パス
  `data/people/index.json`
  `data/people/detail/*.json`

### 4.2 トップレベル

- `built_at`
  人物インデックスを生成した UTC 時刻
- `items`
  人物ごとの配列

### 4.3 `items[]`

- `person_key`
  人物名の正規化キー
- `canonical_name`
  代表表示名。現時点では `person_key` と同じ
- `name_variants`
  配布元 JSON に現れた人物名表記の一覧
- `detail_id`
  正規化済み `person_key` から生成した人物個票ファイル用 ID
- `relation_counts`
  関連件数の要約

## 5. 人物個票 JSON

- パス
  `data/people/detail/{detail_id}.json`

- `built_at`
  人物インデックスを生成した UTC 時刻
- `person_key`
  人物名の正規化キー
- `canonical_name`
  代表表示名。現時点では `person_key` と同じ
- `name_variants`
  配布元 JSON に現れた人物名表記の一覧
- `relation_counts`
  関連件数の要約
- `gian_relations`
  議案との関係配列
- `seigan_relations`
  請願との関係配列
- `shitsumon_relations`
  質問主意書との関係配列
- `meeting_relations`
  出席会議との関係配列
- `speaking_meeting_relations`
  発言会議との関係配列

## 6. 関係配列

### 6.1 `gian_relations[]`

- `bill_id`
  議案 ID
- `title`
  議案件名
- `role`
  人物の役割。現時点では `submitter_representative` `submitter` `supporter`
- `submitted_session`
  議案提出回次

### 6.2 `seigan_relations[]`

- `petition_id`
  請願 ID
- `title`
  請願件名
- `role`
  人物の役割。現時点では `presenter`
- `house`
  `shugiin` または `sangiin`
- `session_number`
  回次

### 6.3 `shitsumon_relations[]`

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

### 6.4 `meeting_relations[]`

- `issue_id`
  会議 ID
- `session`
  回次
- `date`
  会議日
- `name_of_house`
  院名
- `name_of_meeting`
  会議名
- `role`
  出席上の役割

### 6.5 `speaking_meeting_relations[]`

- `issue_id`
  会議 ID
- `session`
  回次
- `date`
  会議日
- `name_of_house`
  院名
- `name_of_meeting`
  会議名
- `speech_count`
  当該人物の発言回数

## 7. 利用上の注意

- 人物の同一性判定はまだ厳密な名寄せを行っていない
- `person_key` は外部公開用の永続 ID ではなく、配布用の正規化キーである
- 議案の `submitter_representative` は、`外X名` がある場合でも代表者 1 名だけを指す
