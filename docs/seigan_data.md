# 請願データ

この文書は、請願データについて「どこから取得するか」「途中でどのように整形するか」「最終的にどの JSON を配布するか」をまとめたものである。

2026-03-13 時点では、`src/pipeline/seigan/` 配下のパイプラインと `src/pipeline/seigan/build_seigan_distribution.py` がこの構成で生成する。

## 1. 対象データ

- 一覧データ
  `data/seigan/{house}/list/{session}.json`
- 個票データ
  `data/seigan/{house}/detail/{petition_id}.json`

`house` は `shugiin` または `sangiin`。

## 2. 取得元

### 2.1 衆議院 請願一覧ページ

- URL 形式
  `https://www.shugiin.go.jp/internet/itdb_seigan.nsf/html/seigan/{session}_l.htm`
- 主な取得項目
  - 新件番号
  - 件名
  - 付託委員会名
  - 請願個票 URL

### 2.2 参議院 請願一覧ページ

- URL 形式
  `https://www.sangiin.go.jp/japanese/joho1/kousei/seigan/{session}/seigan.htm`
- 主な取得項目
  - 新件番号
  - 件名
  - 委員会名
  - 請願要旨 URL
  - 同趣旨一覧 URL

### 2.3 衆議院 請願個票ページ

- 入力元
  一覧 JSON に含まれる `detail_url`
- 主な取得項目
  - 件名
  - 請願要旨
  - 受理件数
  - 請願者通数
  - 付託委員会
  - 結果
  - 紹介議員一覧

### 2.4 参議院 請願個票ページ

- 入力元
  一覧 JSON に含まれる `detail_url` と `similar_petitions_url`
- 主な取得項目
  - 請願要旨ページからの要旨
  - 同趣旨一覧ページからの件数
  - 署名者数
  - 紹介議員・受理情報
  - 結果

## 3. 生成フロー

### 3.1 一覧取得

- パイプライン
  `src/pipeline/seigan/get_shugiin_seigan_list.py`
  `src/pipeline/seigan/get_sangiin_seigan_list.py`
- 出力
  `tmp/seigan/shugiin/list/{session}.html`
  `tmp/seigan/sangiin/list/{session}.html`

### 3.2 一覧パース

- パイプライン
  `src/pipeline/seigan/parse_shugiin_seigan_list.py`
  `src/pipeline/seigan/parse_sangiin_seigan_list.py`
- 出力
  `tmp/seigan/{house}/list/{session}.json`

### 3.3 個票取得

- パイプライン
  `src/pipeline/seigan/get_shugiin_seigan_detail.py`
  `src/pipeline/seigan/get_sangiin_seigan_detail.py`
- 入力
  `tmp/seigan/{house}/list/{session}.json`
- 出力
  `tmp/seigan/shugiin/detail/{petition_id}/detail.html`
  `tmp/seigan/sangiin/detail/{petition_id}/detail.html`
  `tmp/seigan/sangiin/detail/{petition_id}/similar.html`

### 3.4 個票パース

- パイプライン
  `src/pipeline/seigan/parse_shugiin_seigan_detail.py`
  `src/pipeline/seigan/parse_sangiin_seigan_detail.py`
- 出力
  `tmp/seigan/{house}/detail/{petition_id}/index.json`

### 3.5 配布データ生成

- パイプライン
  `src/pipeline/seigan/build_seigan_distribution.py`
- 入力
  `tmp/seigan/{house}/list/{session}.json`
  `tmp/seigan/{house}/detail/{petition_id}/index.json`
- 出力
  `data/seigan/{house}/list/{session}.json`
  `data/seigan/{house}/detail/{petition_id}.json`

## 4. 中間データと配布データの役割

- `tmp/seigan/{house}/list/{session}.html`
  一覧の原本 HTML
- `tmp/seigan/{house}/list/{session}.json`
  一覧ページの整形済み中間 JSON
- `tmp/seigan/{house}/detail/{petition_id}/detail.html`
  個票原本 HTML
- `tmp/seigan/sangiin/detail/{petition_id}/similar.html`
  参議院の同趣旨一覧原本 HTML
- `tmp/seigan/{house}/detail/{petition_id}/index.json`
  個票の整形済み中間 JSON
- `data/seigan/{house}/list/{session}.json`
  配布用一覧 JSON
- `data/seigan/{house}/detail/{petition_id}.json`
  配布用個票 JSON

## 5. 配布用一覧 JSON

### 5.1 ファイル構成

- パス
  `data/seigan/{house}/list/{session}.json`

### 5.2 トップレベル

- `house`
  院別。`shugiin` または `sangiin`
- `session_number`
  回次
- `built_at`
  配布用 JSON を生成した UTC 時刻
- `items`
  請願一覧の配列

### 5.3 `items[]`

- `house`
  院別
- `petition_number`
  請願番号
- `title`
  件名
- `committee_name`
  委員会名
- `committee_code`
  一覧ページ内のアンカー由来コード
- `detail_url`
  個票 URL
- `similar_petitions_url`
  同趣旨一覧 URL。主に参議院で使用
- `is_referred`
  付託済みかどうか

## 6. 配布用個票 JSON

### 6.1 ファイル構成

- パス
  `data/seigan/{house}/detail/{petition_id}.json`

### 6.2 トップレベル

- `petition_id`
  請願 ID
- `house`
  院別
- `session_number`
  回次
- `petition_number`
  請願番号
- `title`
  件名
- `committee_name`
  委員会名
- `committee_code`
  一覧ページ由来の委員会コード
- `detail_source_url`
  個票ページ URL
- `similar_petitions_source_url`
  同趣旨一覧ページ URL
- `summary_text`
  請願要旨
- `accepted_count`
  受理件数
- `signer_count`
  署名者または請願者通数
- `outcome`
  結果
- `presenters`
  紹介議員配列
- `built_at`
  配布用 JSON を生成した UTC 時刻

### 6.3 `presenters[]`

- `receipt_number`
  受理番号
- `presenter_name`
  紹介議員名
- `party_name`
  会派名
- `received_at`
  受理日
- `referred_at`
  付託日
- `result`
  個別受理単位の結果

## 7. 実装上の注意

- 衆議院と参議院で一覧 HTML の構造が大きく異なるため、取得・パースは別実装にしている
- 参議院の `accepted_count`、`signer_count`、`presenters` は同趣旨一覧ページ依存で、`detail.html` だけでは揃わない
- `signer_count` は院ごとに元ページの表現が異なるが、配布時には同じ数値項目へ寄せている
- `petition_id` は院別接頭辞と回次・番号から組み立てた配布用 ID である
