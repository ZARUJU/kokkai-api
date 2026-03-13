# 議案データ

この文書は、議案データについて「どこから取得するか」「途中でどのように整形するか」「最終的にどの JSON を配布するか」をまとめたものである。

2026-03-13 時点では、`src/pipeline/gian/` 配下のパイプラインと `src/pipeline/gian/build_gian_distribution.py` がこの構成で生成する。

## 1. 対象データ

- 一覧データ
  `data/gian/list/{session}.json`
- 個票データ
  `data/gian/detail/{bill_id}.json`

## 2. 取得元

### 2.1 議案一覧ページ

- URL
  `https://www.shugiin.go.jp/internet/itdb_gian.nsf/html/gian/kaiji{session}.htm`
- 例
  `https://www.shugiin.go.jp/internet/itdb_gian.nsf/html/gian/kaiji221.htm`
- 主な取得項目
  - カテゴリ
  - 下位分類
  - 提出回次
  - 議案番号
  - 議案件名
  - 審議状況
  - `progress_url`
  - `text_url`

### 2.2 審議経過ページ

- URL 形式
  `https://www.shugiin.go.jp/internet/itdb_gian.nsf/html/gian/keika/{id}.htm`
- 例
  `https://www.shugiin.go.jp/internet/itdb_gian.nsf/html/gian/keika/1DE153E.htm`
- 主な取得項目
  - 議案種類
  - 議案件名
  - 議案提出者
  - 議案提出会派
  - 衆参それぞれの受理・付託・審査終了・審議終了
  - 公布年月日・法律番号
  - 衆法では追加で `議案提出者一覧` と `議案提出の賛成者`

### 2.3 本文情報一覧ページ

- URL 形式
  `https://www.shugiin.go.jp/internet/itdb_gian.nsf/html/gian/honbun/{id}.htm`
- 例
  `https://www.shugiin.go.jp/internet/itdb_gian.nsf/html/gian/honbun/g22105001.htm`
- 主な取得項目
  - 本文情報一覧ページ自体のタイトル
  - `提出時法律案`
  - `要綱`
  - `修正案`
  - 文書リンクに付く注記

## 3. 生成フロー

### 3.1 一覧取得

- パイプライン
  `src/pipeline/gian/get_gian_list.py`
- 入力
  議案一覧ページ
- 出力
  `tmp/gian/list/{session}.html`

### 3.2 一覧パース

- パイプライン
  `src/pipeline/gian/parse_gian_list.py`
- 入力
  `tmp/gian/list/{session}.html`
- 出力
  `tmp/gian/list/{session}.json`

### 3.3 審議経過取得

- パイプライン
  `src/pipeline/gian/get_gian_progress.py`
- 入力
  `tmp/gian/list/{session}.json`
- 出力
  `tmp/gian/detail/{bill_id}/progress/{session}.html`

### 3.4 審議経過パース

- パイプライン
  `src/pipeline/gian/parse_gian_progress.py`
- 入力
  `tmp/gian/detail/{bill_id}/progress/{session}.html`
- 出力
  `tmp/gian/detail/{bill_id}/progress/{session}.json`

### 3.5 本文情報取得

- パイプライン
  `src/pipeline/gian/get_gian_text.py`
- 入力
  `tmp/gian/list/{session}.json`
- 出力
  `tmp/gian/detail/{bill_id}/honbun/index.html`
  `tmp/gian/detail/{bill_id}/honbun/documents/*.html`

### 3.6 本文情報パース

- パイプライン
  `src/pipeline/gian/parse_gian_text.py`
- 入力
  `tmp/gian/detail/{bill_id}/honbun/index.html`
- 出力
  `tmp/gian/detail/{bill_id}/honbun/index.json`

### 3.7 配布データ生成

- パイプライン
  `src/pipeline/gian/build_gian_distribution.py`
- 入力
  `tmp/gian/list/{session}.json`
  `tmp/gian/detail/{bill_id}/progress/{session}.json`
  `tmp/gian/detail/{bill_id}/honbun/index.html`
  `tmp/gian/detail/{bill_id}/honbun/documents/*.html`
- 出力
  `data/gian/list/{session}.json`
  `data/gian/detail/{bill_id}.json`

## 4. 中間データと配布データの役割

- `tmp/gian/list/{session}.html`
  原本 HTML
- `tmp/gian/list/{session}.json`
  一覧ページの整形済み中間 JSON
- `tmp/gian/detail/{bill_id}/progress/{session}.json`
  会期ごとの審議経過 JSON
- `tmp/gian/detail/{bill_id}/honbun/index.json`
  本文一覧ページの整形済み JSON
- `data/gian/list/{session}.json`
  配布用の一覧 JSON
- `data/gian/detail/{bill_id}.json`
  配布用の議案個票

`tmp/` は取得元の構造をある程度残した中間生成物、`data/` は横断利用しやすい配布形式として扱う。

## 5. 配布データの共通概念

- `bill_id`
  議案を横断的に識別する ID。原則として `提出回次-カテゴリ-番号` の形を取る
- `category`
  議案一覧上の大分類。例: `衆法`, `参法`, `閣法`, `予算`, `承認`, `決算その他`
- `subcategory`
  `決算その他` のように下位分類がある場合の補足分類
- `submitted_session`
  その議案が提出された回次。掲載回次とは一致しないことがある
- `status`
  その回次の議案一覧ページに掲載されていた審議状況

## 6. 一覧 JSON

### 6.1 ファイル構成

- パス
  `data/gian/list/{session}.json`
- 例
  `data/gian/list/218.json`

### 6.2 トップレベル

- `session_number`
  この一覧が対象としている回次
- `built_at`
  配布用 JSON を生成した UTC 時刻
- `items`
  議案一覧の配列

### 6.3 `items[]`

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
  中間データに、この回次の進捗 JSON があるかどうか
- `has_honbun`
  中間データに、本文 HTML があるかどうか

## 7. 個票 JSON

### 7.1 ファイル構成

- パス
  `data/gian/detail/{bill_id}.json`
- 例
  `data/gian/detail/215-shu_law-2.json`

### 7.2 トップレベル

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
  回次ごとの審議経過情報
- `honbun_source_url`
  本文情報一覧ページの URL。本文未取得時は `null`
- `honbun_page_title`
  本文情報一覧ページの HTML タイトル。本文未取得時は `null`
- `honbun_documents`
  本文情報ページから辿れた文書の配列
- `meeting_references`
  会議録から照合できた関連会議の配列
- `built_at`
  配布用 JSON を生成した UTC 時刻

### 7.3 `session_statuses[]`

- `session_number`
  掲載回次
- `status`
  その回次の議案一覧に記載されていた審議状況

### 7.4 `basic_info`

進捗ページから抽出した共通情報をまとめたもの。

- `bill_type`
  進捗ページ上の議案種類
- `bill_title`
  進捗ページ上の議案件名
- `submitter`
  議案提出者の代表者名。末尾の敬称 `君` と `外X名` 表記は除去している
- `submitter_count`
  `submitter` を含む提出者総数。`外X名` がある場合だけ入る
- `submitter_has_more`
  `submitter` 以外にも提出者がいることを表すフラグ
- `submitter_group`
  議案提出会派
- `member_law_extra`
  主に衆法で追加的に得られる情報。なければ `null`

#### `member_law_extra`

- `submitter_list`
  議案提出者一覧。各要素の末尾の敬称 `君` は除去している
- `supporters`
  議案提出の賛成者一覧。各要素の末尾の敬称 `君` は除去している

### 7.5 `progress[]`

各回次で取得できた進捗情報の配列。

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

`progress[].parsed` には会期ごとの差分だけを入れている。共通情報は `basic_info` 側に寄せている。

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
  日付の右側にあった補足テキスト

#### `promulgation`

- `promulgated_at`
  公布年月日
- `law_number`
  法律番号

### 7.6 `honbun_documents[]`

本文情報ページから辿れた各文書。

- `label`
  本文情報ページ上のリンク表示名
- `title`
  `label` から推定した短いタイトル
- `document_type`
  文書種別
- `note`
  リンク表示名末尾の注記
- `source_url`
  原本ページ URL
- `html`
  原本文書 HTML
- `text`
  HTML から単純整形したプレーンテキスト

### 7.7 `meeting_references[]`

- `issue_id`
  関連会議の ID
- `session`
  会議の回次
- `date`
  会議日
- `name_of_house`
  院名
- `name_of_meeting`
  会議名

## 8. 実装上の注意

- `項目` 名に `/` や `／` が含まれ、1 行に複数の意味が混在する
- 値が改行区切りで入ることがある
- `bill_number` が空のケースがある
- `text_url` があっても、実際に辿れる文書種別は議案ごとに異なる
- 議案一覧上の回次と、本文ページや進捗ページ内部の回次表現は一致しないことがある
