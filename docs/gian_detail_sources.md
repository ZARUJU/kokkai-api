# 議案詳細情報の取得元とデータ構造整理

この文書は、次に実装する「議案詳細情報の取得パイプライン」の前提を整理するためのメモである。
対象は、議案一覧から辿れる以下の 2 種類の詳細ページ。

- `progress_url`
  議案審議経過情報ページ
- `text_url`
  議案本文情報一覧ページ

2026-03-09 時点で、既存の `tmp/gian/list/{session}.json` と実サイトの代表ページを確認した内容をまとめている。

## 1. 既存パイプラインとの関係

現在の実装では、以下まで取得できている。

- `src/pipeline/get_kaiki.py`
  会期一覧を `data/kaiki.json` に保存
- `src/pipeline/get_gian_list.py`
  各会期の議案一覧を `tmp/gian/list/{session}.json` に保存

次の詳細取得は、基本的に `tmp/gian/list/{session}.json` を入力にして進めるのが自然である。

最低限使う入力フィールドは以下。

- `category`
- `subcategory`
- `submitted_session`
- `bill_number`
- `title`
- `progress_url`
- `text_url`

## 2. 取得元 URL の構造

### 2.1 議案一覧ページ

- 形式
  `https://www.shugiin.go.jp/internet/itdb_gian.nsf/html/gian/kaiji{session}.htm`
- 例
  `https://www.shugiin.go.jp/internet/itdb_gian.nsf/html/gian/kaiji221.htm`

ここから各議案の `progress_url` と `text_url` が得られる。

### 2.2 進捗ページ `progress_url`

- 形式
  `https://www.shugiin.go.jp/internet/itdb_gian.nsf/html/gian/keika/{id}.htm`
- 例
  `https://www.shugiin.go.jp/internet/itdb_gian.nsf/html/gian/keika/1DE153E.htm`

### 2.3 本文一覧ページ `text_url`

- 形式
  `https://www.shugiin.go.jp/internet/itdb_gian.nsf/html/gian/honbun/{id}.htm`
- 例
  `https://www.shugiin.go.jp/internet/itdb_gian.nsf/html/gian/honbun/g22105001.htm`

本文一覧ページの内部リンクとして、さらに以下の相対リンクが現れる。

- `./houan/...`
  提出時法律案
- `./youkou/...`
  要綱
- `./syuuseian/...`
  修正案

## 3. `progress_url` の観測結果

### 3.1 共通構造

カテゴリが違っても、進捗ページの主テーブルはかなり共通している。
代表例:

- 衆法
  `https://www.shugiin.go.jp/internet/itdb_gian.nsf/html/gian/keika/1DE153E.htm`
- 予算
  `https://www.shugiin.go.jp/internet/itdb_gian.nsf/html/gian/keika/1DE14C2.htm`
- 決算
  `https://www.shugiin.go.jp/internet/itdb_gian.nsf/html/gian/keika/1DE1146.htm`

主テーブルはおおむね以下の 2 列。

- `項目`
- `内容`

行ラベルとして頻出するもの:

- `議案種類`
- `議案提出回次`
- `議案番号`
- `議案件名`
- `議案提出者`
- `議案提出会派`
- `衆議院予備審査議案受理年月日`
- `衆議院予備付託年月日／衆議院予備付託委員会`
- `衆議院議案受理年月日`
- `衆議院付託年月日／衆議院付託委員会`
- `衆議院審査終了年月日／衆議院審査結果`
- `衆議院審議終了年月日／衆議院審議結果`
- `衆議院審議時会派態度`
- `衆議院審議時賛成会派`
- `衆議院審議時反対会派`
- `参議院予備審査議案受理年月日`
- `参議院予備付託年月日／参議院予備付託委員会`
- `参議院議案受理年月日`
- `参議院付託年月日／参議院付託委員会`
- `参議院審査終了年月日／参議院審査結果`
- `参議院審議終了年月日／参議院審議結果`
- `公布年月日／法律番号`

### 3.2 カテゴリ差分

完全に別 HTML というより、「主テーブルは似ているが補助テーブルや一部項目が違う」と見るのがよい。

### 衆法

衆法では、主テーブルに加えて 2 個目のテーブルが付くことがある。
観測できた追加情報:

- `議案提出者一覧`
- `議案提出の賛成者`

例:

- `https://www.shugiin.go.jp/internet/itdb_gian.nsf/html/gian/keika/1DE153E.htm`

### 閣法・予算・承認・決算その他

確認した範囲では、主テーブル 1 個だけのことが多い。
ただし、主テーブルの中身はカテゴリにより少しずつ異なる。

例:

- 閣法
  `https://www.shugiin.go.jp/internet/itdb_gian.nsf/html/gian/keika/1DE14CE.htm`
- 予算
  `https://www.shugiin.go.jp/internet/itdb_gian.nsf/html/gian/keika/1DE14C2.htm`
- 承認
  `https://www.shugiin.go.jp/internet/itdb_gian.nsf/html/gian/keika/1DE15BE.htm`
- 決算
  `https://www.shugiin.go.jp/internet/itdb_gian.nsf/html/gian/keika/1DE1146.htm`

### 3.3 パース上の注意

- `項目` 名に `/` や `／` が含まれ、1 行に複数の意味が混在する
  - 例: `衆議院付託年月日／衆議院付託委員会`
  - 値側も `日付／委員会名` のような形になる
- 空欄でも項目自体は存在する
- `議案番号` が空のケースがある
  - 決算その他で観測
- 改行込みで値が入ることがある
  - 例: 日付と委員会名が改行区切り
- `衆議院審議時賛成会派` など、長いセミコロン区切りテキストが入ることがある

### 3.4 `progress_url` の推奨データモデル方針

初期実装では、無理に完全正規化しないほうがよい。

`progress.html` を原本として保存する前提なら、`progress.json` は整形済みデータに寄せてよい。
その場合は、`entries` や `extra_sections` の raw 断片を JSON に重複保存せず、
型付きの `parsed` と最低限のメタ情報だけを保存するのが扱いやすい。

## 4. `text_url` の観測結果

### 4.1 共通構造

本文一覧ページは、進捗ページと違ってテーブル中心ではない。
見出しとリンク一覧を読むページになっている。

代表例:

- `https://www.shugiin.go.jp/internet/itdb_gian.nsf/html/gian/honbun/g22105001.htm`
- `https://www.shugiin.go.jp/internet/itdb_gian.nsf/html/gian/honbun/g22109001.htm`
- `https://www.shugiin.go.jp/internet/itdb_gian.nsf/html/gian/honbun/g22006001.htm`

主な見出し:

- `議案本文情報一覧`
- `選択された議案の情報`
- `照会できる情報の一覧`

ページ内には、議案の基本情報テキストと、参照可能な本文リンク一覧が並ぶ。

### 4.2 取得できる本文リンクの種類

確認できたリンク種別:

- `提出時法律案`
- `[要綱]`
- `修正案1：第219回提出`
- `修正案1：第219回提出(可決)`
- `修正案2：第219回提出`
- `修正案3：第219回提出(可決)`

つまり、本文一覧ページからは「本文そのもの」ではなく、
「取得可能な本文系ページのメニュー」が取れると考えるのが正しい。

### 4.3 本文一覧ページの重要な性質

- すべての議案に `text_url` があるわけではない
  - `tmp/gian/list/221.json` でも `null` が多い
- `text_url` があっても、リンク先の種類は議案ごとに違う
  - `提出時法律案` だけ
  - `提出時法律案` と `[要綱]`
  - `提出時法律案` と複数の修正案
- 修正案リンクには可決・否決の注記が入ることがある

### 4.4 回次・カテゴリのずれ

議案一覧上の `session_number` と、本文ページのタイトルや本文リンク ID は一致しないことがある。
これは継続審査や再掲のためと考えられる。

例:

- `tmp/gian/list/220.json` から辿れる本文 URL の一つ
  `https://www.shugiin.go.jp/internet/itdb_gian.nsf/html/gian/honbun/g22006001.htm`
- タイトル
  `参法 第220回国会 1 政府等特定資産の運用の効率化を図るための措置に関する法律案`

このため、本文詳細の保存キーは「一覧ページ上の会期」だけでなく、本文ページ自身が持つ情報も保持したほうが安全。

### 4.5 `text_url` の推奨データモデル方針

推奨:

- 本文一覧ページの基本情報
  - `page_title`
  - `session_label`
  - `bill_type`
  - `bill_number_label`
  - `title`
- 参照可能リンク一覧
  - `documents: list[{label, url, document_type, note}]`

`document_type` の初期分類案:

- `original_bill`
  提出時法律案
- `outline`
  要綱
- `amendment`
  修正案
- `other`
  将来の未知リンク用

`note` には `(可決)` `(否決)` などを入れる。

## 5. 実装方針の提案

### 5.1 パイプラインの単位

詳細取得は、進捗と本文で責務がかなり違うため、別パイプラインに分ける前提で考えるのがよい。

推奨:

- `src/pipeline/get_gian_progress.py`
  一覧 JSON を入力に `progress_url` を巡回し、`progress/{session}.html` を保存する
- `src/pipeline/parse_gian_progress.py`
  保存済み `progress/{session}.html` を読み、`progress/{session}.json` を生成する
- `src/pipeline/get_gian_text.py`
  一覧 JSON を入力に `text_url` を巡回し、`honbun/index.html` と関連文書 HTML を保存する
- `src/pipeline/parse_gian_text.py`
  保存済み `honbun/index.html` を読み、`honbun/index.json` を生成する

理由:

- `progress_url` は取得とパースを分けたほうが再実行しやすい
- `text_url` は本文リンクのメニューを取り、さらに子リンク先の HTML まで辿る処理
- 再実行や検証を分けやすい
- 進捗だけ正規化強化、本文だけ追加取得、のような拡張がしやすい

### 5.2 入力

候補:

- `session`
  既存の `tmp/gian/list/{session}.json` を入力にする
- 必要なら将来 `--force` や `--limit` を追加

### 5.3 議案 ID の生成規則

議案詳細の保存先は、一覧ページ URL ではなく、一覧データ上の議案単位で安定した ID を使って切るのがよい。

#### カテゴリコード

- `衆法 -> shu_law`
- `参法 -> san_law`
- `閣法 -> cab_law`
- `予算 -> budget`
- `承認 -> approval`
- `決算その他 -> settlement`

#### 基本ルール

番号がある議案は、ハッシュを使わず、以下の形式で十分。

- `{submitted_session}-{category_code}-{bill_number}`

例:

- `221-shu_law-1`
- `221-cab_law-1`
- `220-san_law-1`
- `221-budget-1`

#### 番号がない議案

`決算その他` のように `bill_number` が空のケースだけ、例外的にハッシュを使う。

- `{submitted_session}-{category_code}-{subcategory_slug}-{title_hash8}`

例:

- `216-settlement-kessan-a1b2c3d4`

この設計にすると、通常ケースは人間に分かりやすく、例外ケースだけ安全に一意化できる。

### 5.4 保存先

現在の前提としては、以下の保存方針がよい。

- 進捗
  `tmp/gian/detail/{bill_id}/progress/{session}.html`
  `tmp/gian/detail/{bill_id}/progress/{session}.json`
- 本文
  `tmp/gian/detail/{bill_id}/honbun/index.html`
  `tmp/gian/detail/{bill_id}/honbun/documents/*.html`
  `tmp/gian/detail/{bill_id}/honbun/index.json`

考え方:

- `progress/{session}.html` は取得時点の原本として保持する
- `progress/{session}.json` は `progress/{session}.html` のパース結果として扱う
- `progress` は会期ごとの差分を持ちうるため、`session` をディレクトリに含める
- `honbun` は議案共通の本文情報をまとめるディレクトリとして扱う
- `honbun/index.html` は本文一覧ページの原本として保持する
- `honbun/documents/*.html` は提出時法律案、要綱、修正案などの原本として保持する
- `honbun/index.json` は本文一覧ページをパースした整形済みデータとして扱う
- 保存単位を議案 ID ベースにすると、あとから一覧データとの結合がしやすい

### 5.5 初期段階で保存したい最小単位

#### 進捗

- 一覧側の識別情報
  - `bill_id`
  - `category`
  - `subcategory`
  - `submitted_session`
  - `bill_number`
  - `title`
- 取得元
  - `progress_url`
- 保存済み raw HTML
  - `progress/{session}.html`
- 型付きの `parsed`

#### 本文一覧

- 一覧側の識別情報
  - `bill_id`
  - `category`
  - `subcategory`
  - `submitted_session`
  - `bill_number`
  - `title`
- 取得元
  - `text_url`
- 本文一覧ページに書かれている基本情報
- 文書リンク一覧
- 各文書リンク先のローカル保存先

本文については、以下のような配列構造が扱いやすい。

- `documents: list[{label, title, url, document_type, note, local_path}]`

例:

- `label`
  元ページ上のリンク表示名
- `title`
  表示用途の短いタイトル
- `url`
  絶対 URL
- `document_type`
  `original_bill` / `outline` / `amendment` / `other`
- `note`
  `(可決)` `(否決)` など
- `html`
  リンク先ページの raw HTML 文字列

## 6. 実装時の注意点

- `progress_url` と `text_url` は `null` の場合がある
- 相対リンクは必ず絶対 URL に変換する
- HTML 構造がカテゴリで少し違っても、まずは情報を落とさない構造で保存する
- いきなり完全正規化せず、「原文ラベル + 原文値」の保全を優先する
- 日付の正規化は、進捗の `内容` を段階的に分解してから進めるほうが安全
- 本文リンク先は HTML をそのまま保持し、後から必要に応じて別段階でパースするほうが安全

## 7. 次の実装で目指す到達点

まずは以下を満たせば十分。

- `tmp/gian/list/{session}.json` を入力に詳細ページを巡回できる
- 議案ごとの `bill_id` を安定して生成できる
- `progress_url` の raw HTML を保存できる
- `progress.html` から主テーブルと追加テーブルを JSON 化できる
- `text_url` の raw HTML を保存できる
- `text.html` から文書リンク一覧を JSON 化できる
- 文書リンク先 HTML を raw のまま保存できる

その上で次段階として、

- 主テーブルの一部項目の正規化
- 修正案リンクの可決・否決判定
- 個別本文 HTML の構造化

へ進むのがよい。
