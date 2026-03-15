# 会議録データ

この文書は、会議録データについて「どこから取得するか」「途中でどのように整形するか」「最終的にどの JSON を配布するか」をまとめたものである。

2026-03-13 時点では、`src/pipeline/kaigiroku/` 配下のパイプラインと `src/pipeline/kaigiroku/build_kaigiroku_distribution.py` がこの構成で生成する。

## 1. 対象データ

- 一覧データ
  `data/kaigiroku/list/{session}.json`
- 個票データ
  `data/kaigiroku/detail/{issue_id}.json`

## 2. 取得元

### 2.1 国会会議録検索システム API

- エンドポイント
  `https://kokkai.ndl.go.jp/api/meeting`
- 主な取得項目
  - `issueID`
  - `session`
  - `nameOfHouse`
  - `nameOfMeeting`
  - `issue`
  - `date`
  - `meetingURL`
  - `pdfURL`
  - `speechRecord`

会議録データは HTML 取得ではなく API JSON を原本として扱う。

## 3. 生成フロー

### 3.1 API 取得

- パイプライン
  `src/pipeline/kaigiroku/get_meeting_records.py`
- 入力
  `https://kokkai.ndl.go.jp/api/meeting`
- 出力
  `tmp/kaigiroku/meeting/{session}.json`

### 3.2 メタデータ抽出

- パイプライン
  `src/pipeline/kaigiroku/parse_meeting_records.py`
- 入力
  `tmp/kaigiroku/meeting/{session}.json`
- 出力
  `tmp/kaigiroku/parsed/{session}.json`

### 3.3 配布データ生成

- パイプライン
  `src/pipeline/kaigiroku/build_kaigiroku_distribution.py`
- 入力
  `tmp/kaigiroku/parsed/{session}.json`
  `data/gian/list/{session}.json`
  `data/seigan/{house}/list/{session}.json`
- 出力
  `data/kaigiroku/list/{session}.json`
  `data/kaigiroku/detail/{issue_id}.json`

`cli.py` から `--force` なしで実行する場合は、`data/kaigiroku/list/{session}.json` が既にあれば、その回次の会議録取得・パース・配布生成をスキップする。

## 4. 中間データと配布データの役割

- `tmp/kaigiroku/meeting/{session}.json`
  API の回次別原本 JSON
- `tmp/kaigiroku/parsed/{session}.json`
  開会・散会、出席者、案件などを抽出した中間 JSON
- `data/kaigiroku/list/{session}.json`
  配布用の会議録一覧
- `data/kaigiroku/detail/{issue_id}.json`
  配布用の会議録個票

`tmp/kaigiroku/parsed/` には `intro_text`、`closing_text`、`membership_changes`、`referred_items` のような解析補助情報が残るが、配布 JSON では主に一覧・個票利用に必要な項目へ絞る。

## 5. 配布用一覧 JSON

### 5.1 ファイル構成

- パス
  `data/kaigiroku/list/{session}.json`

### 5.2 トップレベル

- `session_number`
  対象回次
- `built_at`
  配布用 JSON を生成した UTC 時刻
- `items`
  会議ごとの配列

### 5.3 `items[]`

- `issue_id`
  会議録 ID
- `session`
  回次
- `name_of_house`
  院名
- `name_of_meeting`
  会議名
- `issue`
  号数などを含む会議表記
- `date`
  会議日
- `meeting_url`
  会議録検索システムの会議ページ URL
- `pdf_url`
  会議録 PDF URL
- `opening_time`
  開会時刻
- `closing_time`
  散会時刻
- `speech_count`
  発言件数
- `matched_item_count`
  本日の案件のうち議案または請願と照合できた件数

## 6. 配布用個票 JSON

### 6.1 ファイル構成

- パス
  `data/kaigiroku/detail/{issue_id}.json`

### 6.2 トップレベル

- `issue_id`
  会議録 ID
- `session`
  回次
- `name_of_house`
  院名
- `name_of_meeting`
  会議名
- `issue`
  号数などを含む会議表記
- `date`
  会議日
- `meeting_url`
  会議ページ URL
- `pdf_url`
  PDF URL
- `opening_line`
  開会行の原文
- `opening_time`
  開会時刻
- `closing_line`
  散会行の原文
- `closing_time`
  散会時刻
- `speech_count`
  発言件数
- `attendance`
  出席者配列
- `agenda_items`
  本日の会議に付した案件の配列
- `built_at`
  配布用 JSON を生成した UTC 時刻

### 6.3 `attendance[]`

- `section`
  出席者セクション名
- `role`
  役割
- `title`
  肩書
- `name`
  氏名

### 6.4 `agenda_items[]`

- `text`
  本日の案件テキスト
- `item_type`
  `bill` または `petition`。照合できない場合は `null`
- `bill_id`
  議案と照合できた場合の ID
- `bill_title`
  対応する議案件名
- `petition_id`
  請願と照合できた場合の ID
- `petition_title`
  対応する請願件名

## 7. 実装上の注意

- 会議録 API 自体は発言本文を大量に含むが、現時点の配布 JSON はメタデータ中心で本文全文は配布しない
- 開会・散会時刻、出席者、案件は発言冒頭・終盤の定型文から抽出している
- `agenda_items` は本日の案件を照合可否にかかわらず保持し、照合できた場合だけ `item_type` や各種 ID を付与する
- 案件照合は会議録本文の完全一致ではなく、正規化した件名テキストに基づく
- 議案・請願データが未生成の回次では `matched_item_count` や `agenda_items[].bill_id` などが少なくなる
