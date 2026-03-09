# 配布用議案データの項目定義

この文書は、`data/gian/` に生成する配布用 JSON の各項目が何を意味するかをまとめたものである。
対象は以下の 2 種類。

- `data/gian/list/{session}.json`
  各回次に掲載されている議案一覧
- `data/gian/detail/{bill_id}.json`
  単一議案の個票

2026-03-09 時点では、`src/pipeline/gian/build_gian_distribution.py` がこの形式で生成する。

## 1. ファイル構成

### 1.1 一覧

- パス
  `data/gian/list/{session}.json`
- 例
  `data/gian/list/218.json`

### 1.2 個票

- パス
  `data/gian/detail/{bill_id}.json`
- 例
  `data/gian/detail/215-shu_law-2.json`

## 2. 共通の考え方

- `bill_id`
  議案を横断的に識別する ID。原則として `提出回次-カテゴリ-番号` の形を取る
- `category`
  議案一覧上の大分類。例: `衆法`, `参法`, `閣法`, `予算`, `承認`, `決算その他`
- `subcategory`
  `決算その他` のように下位分類がある場合の補足分類
- `submitted_session`
  その議案が提出された回次。議案が掲載されている回次とは一致しないことがある
- `status`
  その回次の議案一覧ページに掲載されていた審議状況

## 3. 一覧 JSON

一覧 JSON のトップレベルは以下。

- `session_number`
  この一覧が対象としている回次
- `built_at`
  配布用 JSON を生成した UTC 時刻
- `items`
  議案一覧の配列

### 3.1 `items[]`

- `bill_id`
  議案個票と対応づけるための ID
- `category`
  議案一覧上の大分類
- `subcategory`
  下位分類。なければ `null`
- `submitted_session`
  提出回次
- `bill_number`
  議案番号。番号がない場合は `null`
- `title`
  議案件名
- `status`
  当該回次の一覧ページでの審議状況
- `progress_url`
  衆議院サイト上の審議経過ページ URL。存在しない場合は `null`
- `text_url`
  衆議院サイト上の本文情報ページ URL。存在しない場合は `null`
- `has_progress`
  配布元の中間データに、この回次の進捗 JSON があるかどうか
- `has_honbun`
  配布元の中間データに、本文 HTML があるかどうか

## 4. 個票 JSON

個票 JSON のトップレベルは以下。

- `bill_id`
  議案 ID
- `category`
  議案一覧上の大分類
- `subcategory`
  下位分類。なければ `null`
- `submitted_session`
  提出回次
- `bill_number`
  議案番号
- `title`
  議案一覧由来の議案件名
- `listed_sessions`
  この議案が議案一覧に載っていた回次の配列
- `session_statuses`
  回次ごとの一覧上ステータス
- `basic_info`
  議案の基本情報
- `progress`
  回次ごとの審議経過情報。共通項目は除いた会期差分中心の配列
- `honbun_source_url`
  本文情報一覧ページの URL。本文未取得時は `null`
- `honbun_page_title`
  本文情報一覧ページの HTML タイトル。本文未取得時は `null`
- `honbun_documents`
  本文情報ページから辿れた文書の配列
- `built_at`
  配布用 JSON を生成した UTC 時刻

### 4.1 `session_statuses[]`

- `session_number`
  掲載回次
- `status`
  その回次の議案一覧に記載されていた審議状況

### 4.2 `basic_info`

進捗ページから抽出した基本情報をまとめたもの。

- `bill_type`
  進捗ページ上の議案種類
- `bill_title`
  進捗ページ上の議案件名
- `submitter`
  議案提出者。末尾の敬称 `君` は除去している
- `submitter_group`
  議案提出会派
- `member_law_extra`
  主に衆法で追加的に得られる情報。なければ `null`

#### `member_law_extra`

- `submitter_list`
  議案提出者一覧。各要素の末尾の敬称 `君` は除去している
- `supporters`
  議案提出の賛成者一覧。各要素の末尾の敬称 `君` は除去している

### 4.3 `progress[]`

各回次で取得できた進捗情報の配列。
一つの議案が複数回次にまたがって掲載される場合、複数件入る。

- `session_number`
  この進捗情報が対応する回次
- `source_url`
  審議経過ページ URL
- `page_title`
  審議経過ページの HTML タイトル
- `status`
  同じ回次の議案一覧上の審議状況
- `parsed`
  進捗ページを正規化した本体

#### `parsed`

`progress[].parsed` には会期ごとの差分だけを入れている。
議案種類、議案件名、提出者、提出者一覧のような共通情報は `basic_info` 側に寄せている。

- `house_of_reps`
  衆議院での審議状況
- `house_of_councillors`
  参議院での審議状況
- `promulgation`
  公布情報

#### `house_of_reps`, `house_of_councillors`

- `pre_review_received_at`
  予備審査議案受理年月日
- `pre_referral`
  予備付託年月日と委員会名など
- `bill_received_at`
  議案受理年月日
- `referral`
  付託年月日と付託委員会など
- `review_finished`
  審査終了年月日と審査結果など
- `plenary_finished`
  審議終了年月日と審議結果など
- `stance`
  審議時会派態度
- `supporting_groups`
  審議時賛成会派の配列
- `opposing_groups`
  審議時反対会派の配列

#### `pre_referral`, `referral`, `review_finished`, `plenary_finished`

- `occurred_at`
  日付を ISO 形式に正規化したもの。読めなかった場合は `null`
- `text`
  日付の右側にあった補足テキスト。委員会名や結果など

#### `promulgation`

- `promulgated_at`
  公布年月日
- `law_number`
  法律番号

### 4.4 `honbun_documents[]`

本文情報ページから辿れた各文書。
現時点では構造化パースを深く行わず、原本 HTML と単純整形したテキストを配布する。

- `label`
  本文情報ページ上のリンク表示名
- `title`
  `label` から推定した短いタイトル。例: `提出時法律案`, `要綱`, `修正案1`
- `document_type`
  文書種別
- `note`
  リンク表示名末尾の注記。例: `可決`
- `source_url`
  個別文書の URL
- `html`
  個別文書ページの raw HTML
- `text`
  `html` から単純抽出した本文テキスト

#### `document_type`

現時点の値は以下。

- `original_bill`
  提出時法律案
- `outline`
  要綱
- `amendment`
  修正案
- `other`
  上記に当てはまらないもの

## 5. 利用上の注意

- `listed_sessions` と `submitted_session` は意味が違う
  - `submitted_session` は議案の提出回次
  - `listed_sessions` はその議案が一覧に載っていた回次
- `progress` は掲載回次ごとの履歴であり、配列順は回次昇順
- `honbun_documents[].text` は単純なテキスト抽出であり、条文構造までは保持していない
- `basic_info` は主に進捗ページ由来であるため、進捗未取得の議案では情報が薄いことがある
- 提出者情報では人名末尾の `君` を削除している
- `bill_id` は配布用の安定識別子として運用するが、元サイトの公式 ID ではない
