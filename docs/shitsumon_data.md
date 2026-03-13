# 質問主意書データ

この文書は、質問主意書データについて「どこから取得するか」「途中でどのように整形するか」「最終的にどの JSON を配布するか」をまとめたものである。

2026-03-13 時点では、`src/pipeline/shitsumon/` 配下のパイプラインと `src/pipeline/shitsumon/build_shitsumon_distribution.py` がこの構成で生成する。

## 1. 対象データ

- 一覧データ
  `data/shitsumon/{house}/list/{session}.json`
- 個票データ
  `data/shitsumon/{house}/detail/{question_id}.json`

`house` は `shugiin` または `sangiin`。

## 2. 取得元

### 2.1 衆議院 質問主意書一覧ページ

- URL 形式
  `https://www.shugiin.go.jp/internet/itdb_shitsumon.nsf/html/shitsumon/kaiji{session:03d}_l.htm`
  `https://www.shugiin.go.jp/internet/itdb_shitsumona.nsf/html/shitsumon/kaiji{session:03d}_l.htm`
- 主な取得項目
  - 質問番号
  - 質問件名
  - 提出者氏名
  - 経過状況
  - 経過情報 URL
  - 質問本文 URL/PDF URL
  - 答弁本文 URL/PDF URL

### 2.2 参議院 質問主意書一覧ページ

- URL 形式
  `https://www.sangiin.go.jp/japanese/joho1/kousei/syuisyo/{session}/syuisyo.htm`
- 主な取得項目
  - 質問番号
  - 質問件名
  - 提出者氏名
  - 詳細ページ URL
  - 質問本文 URL/PDF URL
  - 答弁本文 URL/PDF URL

### 2.3 衆議院 個票ページ

- 入力元
  一覧 JSON に含まれる `progress_url` `question_html_url` `answer_html_url`
- 主な取得項目
  - 経過情報
  - 質問本文の日付と本文
  - 答弁本文の日付、答弁者名、本文

### 2.4 参議院 個票ページ

- 入力元
  一覧 JSON に含まれる `detail_url` `question_html_url` `answer_html_url`
- 主な取得項目
  - 詳細ページ由来の経過情報
  - 質問本文の日付と本文
  - 答弁本文の日付、答弁者名、本文

## 3. 生成フロー

### 3.1 一覧取得

- パイプライン
  `src/pipeline/shitsumon/get_shugiin_shitsumon_list.py`
  `src/pipeline/shitsumon/get_sangiin_shitsumon_list.py`
- 出力
  `tmp/shitsumon/shugiin/list/{session}.html`
  `tmp/shitsumon/sangiin/list/{session}.html`

### 3.2 一覧パース

- パイプライン
  `src/pipeline/shitsumon/parse_shugiin_shitsumon_list.py`
  `src/pipeline/shitsumon/parse_sangiin_shitsumon_list.py`
- 出力
  `tmp/shitsumon/{house}/list/{session}.json`

### 3.3 個票取得

- パイプライン
  `src/pipeline/shitsumon/get_shugiin_shitsumon_detail.py`
  `src/pipeline/shitsumon/get_sangiin_shitsumon_detail.py`
- 入力
  `tmp/shitsumon/{house}/list/{session}.json`
- 出力
  `tmp/shitsumon/shugiin/detail/{question_id}/progress.html`
  `tmp/shitsumon/shugiin/detail/{question_id}/question.html`
  `tmp/shitsumon/shugiin/detail/{question_id}/answer.html`
  `tmp/shitsumon/sangiin/detail/{question_id}/detail.html`
  `tmp/shitsumon/sangiin/detail/{question_id}/question.html`
  `tmp/shitsumon/sangiin/detail/{question_id}/answer.html`

### 3.4 個票パース

- パイプライン
  `src/pipeline/shitsumon/parse_shugiin_shitsumon_detail.py`
  `src/pipeline/shitsumon/parse_sangiin_shitsumon_detail.py`
- 出力
  `tmp/shitsumon/{house}/detail/{question_id}/index.json`

### 3.5 配布データ生成

- パイプライン
  `src/pipeline/shitsumon/build_shitsumon_distribution.py`
- 入力
  `tmp/shitsumon/{house}/list/{session}.json`
  `tmp/shitsumon/{house}/detail/{question_id}/index.json`
- 出力
  `data/shitsumon/{house}/list/{session}.json`
  `data/shitsumon/{house}/detail/{question_id}.json`

## 4. 中間データと配布データの役割

- `tmp/shitsumon/{house}/list/{session}.html`
  一覧の原本 HTML
- `tmp/shitsumon/{house}/list/{session}.json`
  一覧ページの整形済み中間 JSON
- `tmp/shitsumon/{house}/detail/{question_id}/*.html`
  個票関連ページの原本 HTML
- `tmp/shitsumon/{house}/detail/{question_id}/index.json`
  個票の整形済み中間 JSON
- `data/shitsumon/{house}/list/{session}.json`
  配布用一覧 JSON
- `data/shitsumon/{house}/detail/{question_id}.json`
  配布用個票 JSON

現時点では `build_shitsumon_distribution.py` は検証済み `tmp` JSON を `data` へ移す役割が中心で、`data` と `tmp` の構造差分は大きくない。

## 5. 配布用一覧 JSON

### 5.1 ファイル構成

- パス
  `data/shitsumon/{house}/list/{session}.json`

### 5.2 衆議院トップレベル

- `source_url`
  元一覧 URL
- `source_series`
  `itdb_shitsumon` または `itdb_shitsumona`
- `session_number`
  回次
- `fetched_at`
  中間 JSON 生成時刻
- `items`
  一覧配列

### 5.3 参議院トップレベル

- `source_url`
  元一覧 URL
- `session_number`
  回次
- `session_label`
  一覧ページ上の回次ラベル
- `fetched_at`
  中間 JSON 生成時刻
- `items`
  一覧配列

### 5.4 `items[]`

- `question_number`
  質問番号
- `title`
  件名
- `submitter_name`
  提出者氏名
- `status`
  衆議院一覧上の経過状況。参議院では通常なし
- `detail_url`
  参議院詳細ページ URL
- `progress_url`
  衆議院経過ページ URL
- `question_html_url`
  質問本文 HTML URL
- `question_pdf_url`
  質問本文 PDF URL
- `answer_html_url`
  答弁本文 HTML URL
- `answer_pdf_url`
  答弁本文 PDF URL

## 6. 配布用個票 JSON

### 6.1 ファイル構成

- パス
  `data/shitsumon/{house}/detail/{question_id}.json`

### 6.2 トップレベル

- `question_id`
  質問主意書 ID
- `source_url`
  一覧または詳細の元 URL
- `fetched_at`
  個票 JSON 生成時刻
- `title`
  件名
- `submitter_name`
  提出者氏名
- `progress`
  経過情報
- `question_document`
  質問本文情報
- `answer_document`
  答弁本文情報

### 6.3 `progress`

- `session_type`
  常会・臨時会などの別
- `group_name`
  会派名。主に衆議院
- `submitted_at`
  提出日
- `cabinet_sent_at`
  内閣転送日
- `answer_delay_notice_received_at`
  答弁延期通知受領日
- `answer_due_at`
  答弁期限日
- `answer_received_at`
  答弁書受領日
- `withdrawn_at`
  撤回日
- `withdrawal_notice_at`
  撤回通知日
- `status`
  経過状況

### 6.4 `question_document`, `answer_document`

- `document_date`
  文書日付
- `answerer_name`
  答弁者名。`answer_document` で使用
- `body_text`
  本文テキスト

## 7. 実装上の注意

- 衆議院は一覧に経過ページ URL があり、参議院は詳細ページから経過を読む構成
- 衆議院一覧は回次によって `itdb_shitsumon` と `itdb_shitsumona` の 2 系列を使い分ける
- 参議院一覧は 3 行 1 件に近い構造なので、一覧パースは複数行をまとめて 1 件へ変換している
- 本文配布は HTML そのものではなく、日付や答弁者名を抜き出した上でプレーンテキスト中心にしている
