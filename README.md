# kokkai-api

散逸している国会データを収集し、機械処理しやすい JSON に整形して保存するリポジトリです。
配布対象のデータは `data/`、一時生成物や検証用データは `tmp/` に置きます。

## 目的

- 国会関連データの取得処理をパイプラインとして明示する
- 元データの所在と整形後データの保存先を追いやすくする
- 人間にも読みやすい JSON を残し、後続の API 配布に使える形にする

## ディレクトリ構成

- `src/pipeline`
  データ取得・整形・保存を行う ETL パイプラインを置く
- `src/models.py`
  各パイプラインの出力 JSON に対応する Pydantic モデルを定義する
- `src/utils.py`
  文字列正規化や日付変換など、パイプライン共通の補助関数を置く
- `docs`
  取得元サイトの構造整理、配布データ仕様、今後の実装方針に関するドキュメントを置く
- `data`
  配布対象の整形済みデータを置く
- `tmp`
  一時出力、検証用ファイル、配布前の中間生成物を置く

配布用として確定した JSON は `data/` に置き、raw HTML や途中生成物は `tmp/` に残す。

## ドキュメント

データ種別ごとの取得元・中間生成物・配布 JSON の仕様は `docs/` にまとめています。

- `docs/gian_data.md`
  議案データの取得元、生成フロー、配布形式
- `docs/kaigiroku_data.md`
  会議録データの取得元、生成フロー、配布形式
- `docs/seigan_data.md`
  請願データの取得元、生成フロー、配布形式
- `docs/shitsumon_data.md`
  質問主意書データの取得元、生成フロー、配布形式
- `docs/people_data.md`
  人物インデックスの入力元、集約方法、配布形式

## セットアップ

Python 3.11 以上を前提としています。

```bash
uv sync
```

取得系パイプラインは、スクレイピング先への負荷を抑えるためリクエスト間に既定で 1 秒の待機を入れます。待機秒数を変える場合は `KOKKAI_FETCH_INTERVAL_SECONDS` を指定してください。

## 一括実行 CLI

回次をまとめて処理する入口として `cli.py` と `scripts/update-kokkai-data` を用意しています。

- 引数なし
  会期一覧を更新した上で、最新2回分の会議録・議案・請願・質問主意書を強制更新しながら取得・整形・`data/` 生成まで実行
- 引数あり
  指定回次だけ処理。既定では取得済み raw データを再利用し、`--force` 指定時のみ再取得。`data/kaiki.json` がなくても実行可能
- `--all`
  会期一覧をもとに、取得可能な全回次をまとめて処理
- `--latest-count`
  引数省略時に処理する最新回次数を指定
- `--parse-only`
  取得済みの raw HTML / 中間 JSON だけを使って、パースと `data/` 再生成だけを行う
- `--cleanup-tmp`
  配布用データ生成に成功した回次について、対応する `tmp/` 中間生成物を削除する

`--force` なしで回次を指定した場合や `--all` を使った場合は、各データ種別の配布用一覧 JSON が既にあれば、その回次の取得・再パース・再配布をスキップします。判定に使う主なファイルは以下です。

- 議案
  `data/gian/list/{session}.json`
- 会議録
  `data/kaigiroku/list/{session}.json`
- 請願
  `data/seigan/{house}/list/{session}.json`
- 質問主意書
  `data/shitsumon/{house}/list/{session}.json`

`--parse-only` はこの配布済み判定を使わず、`tmp/` にある raw / 中間データを前提に再パースと `data/` 再生成を行います。`--cleanup-tmp` を付けると、配布用 JSON 生成後にその回次の `tmp/` を掃除できます。

実行例:

```bash
./scripts/update-kokkai-data
./scripts/update-kokkai-data 220 221
./scripts/update-kokkai-data --all
./scripts/update-kokkai-data --latest-count 1 --cleanup-tmp
./scripts/update-kokkai-data 220 221 --force --cleanup-tmp
./scripts/update-kokkai-data 217 --parse-only
```

## パイプライン

### `get_kaiki.py`

衆議院サイトの「国会会期一覧」から会期情報を取得し、整形済み JSON として保存します。

- 入力
  衆議院サイトの会期一覧ページ `https://www.shugiin.go.jp/internet/itdb_annai.nsf/html/statics/shiryo/kaiki.htm`
- 引数
  `--skip-existing`: `data/kaiki.json` が既にある場合は取得をスキップ
- 出力
  `data/kaiki.json`

実行例:

```bash
uv run python src/pipeline/kaiki/get_kaiki.py --skip-existing
```

### `get_meeting_records.py`

国会会議録検索システム API の `meeting` エンドポイントを使い、指定回次の会議録 JSON を取得して保存します。

- 入力
  `https://kokkai.ndl.go.jp/api/meeting`
- 引数
  `session`: 取得対象の国会回次
  `--skip-existing`: `tmp/kaigiroku/meeting/{回次}.json` が既にある場合は取得をスキップ
- 出力
  `tmp/kaigiroku/meeting/{回次}.json`

実行例:

```bash
uv run python src/pipeline/kaigiroku/get_meeting_records.py 221 --skip-existing
```

### `parse_meeting_records.py`

保存済みの会議録 API JSON をパースし、会議冒頭と終盤の発言から開会・散会時刻、出席者、委員異動、付託案件、本日の案件を抽出して保存します。衆議院・参議院で異なる冒頭書式は同一 JSON 形式に正規化します。

- 入力
  `tmp/kaigiroku/meeting/{回次}.json`
- 引数
  `session`: 取得対象の国会回次
- 出力
  `tmp/kaigiroku/parsed/{回次}.json`

実行例:

```bash
uv run python src/pipeline/kaigiroku/parse_meeting_records.py 221
```

### `build_kaigiroku_distribution.py`

保存済みの会議録パース結果から、配布用の一覧 JSON と個票 JSON を `data/kaigiroku/` に生成します。`tmp` に残す `intro_text` や `closing_text` のような解析補助情報、付託案件は配布しません。本日の案件は照合可否にかかわらず配布し、議案・請願と照合できたものには ID を付与します。人物インデックス再生成に必要な発言者集計は `data/kaigiroku/detail/{issue_id}.json` に含めます。

- 入力
  `tmp/kaigiroku/parsed/{回次}.json`
  `data/gian/list/{回次}.json`
- 引数
  `sessions...`: 対象の国会回次。省略時は `tmp/kaigiroku/parsed/*.json` を全件処理
- 出力
  `data/kaigiroku/list/{回次}.json`
  `data/kaigiroku/detail/{issue_id}.json`

実行例:

```bash
uv run python src/pipeline/kaigiroku/build_kaigiroku_distribution.py 221
```

### `get_gian_list.py`

衆議院サイトの「議案の一覧」から、指定した国会回次の raw HTML を取得して保存します。

- 入力
  `https://www.shugiin.go.jp/internet/itdb_gian.nsf/html/gian/kaiji{回次}.htm`
- 引数
  `session`: 取得対象の国会回次
  `--skip-existing`: `tmp/gian/list/{回次}.html` が既にある場合は取得をスキップ
- 出力
  `tmp/gian/list/{回次}.html`

実行例:

```bash
uv run python src/pipeline/gian/get_gian_list.py 221 --skip-existing
```

### `parse_gian_list.py`

保存済みの議案一覧 HTML をパースし、カテゴリ情報つきの JSON として保存します。

- 入力
  `tmp/gian/list/{回次}.html`
- 引数
  `session`: 取得対象の国会回次
- 出力
  `tmp/gian/list/{回次}.json`

実行例:

```bash
uv run python src/pipeline/gian/parse_gian_list.py 221
```

### `get_gian_progress.py`

議案一覧 JSON を入力に、各議案の審議経過ページを取得して raw HTML を保存します。

- 入力
  `tmp/gian/list/{回次}.json`
- 引数
  `session`: 取得対象の国会回次
  `--skip-existing`: `tmp/gian/detail/{bill_id}/progress/{回次}.html` が既にある場合は取得をスキップ
- 出力
  `tmp/gian/detail/{bill_id}/progress/{回次}.html`

実行例:

```bash
uv run python src/pipeline/gian/get_gian_progress.py 221 --skip-existing
```

### `parse_gian_progress.py`

保存済みの進捗 HTML をパースし、型付きの整形済み JSON として保存します。

- 入力
  `tmp/gian/list/{回次}.json`
  `tmp/gian/detail/{bill_id}/progress/{回次}.html`
- 引数
  `session`: 取得対象の国会回次
- 出力
  `tmp/gian/detail/{bill_id}/progress/{回次}.json`

実行例:

```bash
uv run python src/pipeline/gian/parse_gian_progress.py 221
```

### `get_gian_text.py`

議案一覧 JSON を入力に、各議案の本文一覧ページと関連文書HTMLを raw で保存します。

- 入力
  `tmp/gian/list/{回次}.json`
- 引数
  `session`: 取得対象の国会回次
  `--skip-existing`: `tmp/gian/detail/{bill_id}/honbun/` 配下の既存HTML取得をスキップ
- 出力
  `tmp/gian/detail/{bill_id}/honbun/index.html`
  `tmp/gian/detail/{bill_id}/honbun/documents/*.html`

実行例:

```bash
uv run python src/pipeline/gian/get_gian_text.py 221 --skip-existing
```

### `parse_gian_text.py`

保存済みの本文一覧 HTML をパースし、型付きの整形済み JSON として保存します。

- 入力
  `tmp/gian/list/{回次}.json`
  `tmp/gian/detail/{bill_id}/honbun/index.html`
- 引数
  `session`: 取得対象の国会回次
- 出力
  `tmp/gian/detail/{bill_id}/honbun/index.json`

実行例:

```bash
uv run python src/pipeline/gian/parse_gian_text.py 221
```

### `build_gian_distribution.py`

保存済みの議案一覧・進捗・本文データから、配布用の議案一覧 JSON と議案個票 JSON を `data/` に生成します。
議案個票では、`山田太郎君外一名` のような提出者表記を代表者名と提出者人数に分けて保持します。

- 入力
  `tmp/gian/list/{回次}.json`
  `tmp/gian/detail/{bill_id}/progress/{回次}.json`
  `tmp/gian/detail/{bill_id}/honbun/index.html`
  `tmp/gian/detail/{bill_id}/honbun/documents/*.html`
- 引数
  `sessions...`: 対象の国会回次。省略時は `tmp/gian/list/*.json` を全件処理
- 出力
  `data/gian/list/{回次}.json`
  `data/gian/detail/{bill_id}.json`

実行例:

```bash
uv run python src/pipeline/gian/build_gian_distribution.py 218 220 221
```

### `get_shugiin_seigan_list.py`

衆議院サイトの「請願一覧」から、指定した国会回次の raw HTML を取得して保存します。

- 入力
  `https://www.shugiin.go.jp/internet/itdb_seigan.nsf/html/seigan/{回次}_l.htm`
- 引数
  `session`: 取得対象の国会回次
  `--skip-existing`: `tmp/seigan/shugiin/list/{回次}.html` が既にある場合は取得をスキップ
- 出力
  `tmp/seigan/shugiin/list/{回次}.html`

実行例:

```bash
uv run python src/pipeline/seigan/get_shugiin_seigan_list.py 217 --skip-existing
```

### `parse_shugiin_seigan_list.py`

保存済みの衆議院請願一覧 HTML をパースし、共通形式の一覧 JSON として保存します。

- 入力
  `tmp/seigan/shugiin/list/{回次}.html`
- 引数
  `session`: 取得対象の国会回次
- 出力
  `tmp/seigan/shugiin/list/{回次}.json`

実行例:

```bash
uv run python src/pipeline/seigan/parse_shugiin_seigan_list.py 217
```

### `get_shugiin_seigan_detail.py`

衆議院請願一覧 JSON を入力に、各請願個票の raw HTML を保存します。

- 入力
  `tmp/seigan/shugiin/list/{回次}.json`
- 引数
  `session`: 取得対象の国会回次
  `--skip-existing`: `tmp/seigan/shugiin/detail/{petition_id}/detail.html` が既にある場合は取得をスキップ
- 出力
  `tmp/seigan/shugiin/detail/{petition_id}/detail.html`

実行例:

```bash
uv run python src/pipeline/seigan/get_shugiin_seigan_detail.py 217 --skip-existing
```

### `parse_shugiin_seigan_detail.py`

保存済みの衆議院請願個別 HTML をパースし、共通形式の個票 JSON として保存します。

- 入力
  `tmp/seigan/shugiin/list/{回次}.json`
  `tmp/seigan/shugiin/detail/{petition_id}/detail.html`
- 引数
  `session`: 取得対象の国会回次
- 出力
  `tmp/seigan/shugiin/detail/{petition_id}/index.json`

実行例:

```bash
uv run python src/pipeline/seigan/parse_shugiin_seigan_detail.py 217
```

### `get_sangiin_seigan_list.py`

参議院サイトの「請願一覧」から、指定した国会回次の raw HTML を取得して保存します。

- 入力
  `https://www.sangiin.go.jp/japanese/joho1/kousei/seigan/{回次}/seigan.htm`
- 引数
  `session`: 取得対象の国会回次
  `--skip-existing`: `tmp/seigan/sangiin/list/{回次}.html` が既にある場合は取得をスキップ
- 出力
  `tmp/seigan/sangiin/list/{回次}.html`

実行例:

```bash
uv run python src/pipeline/seigan/get_sangiin_seigan_list.py 217 --skip-existing
```

### `parse_sangiin_seigan_list.py`

保存済みの参議院請願一覧 HTML をパースし、共通形式の一覧 JSON として保存します。

- 入力
  `tmp/seigan/sangiin/list/{回次}.html`
- 引数
  `session`: 取得対象の国会回次
- 出力
  `tmp/seigan/sangiin/list/{回次}.json`

実行例:

```bash
uv run python src/pipeline/seigan/parse_sangiin_seigan_list.py 217
```

### `get_sangiin_seigan_detail.py`

参議院請願一覧 JSON を入力に、各請願の要旨ページと同趣旨一覧ページの raw HTML を保存します。

- 入力
  `tmp/seigan/sangiin/list/{回次}.json`
- 引数
  `session`: 取得対象の国会回次
  `--skip-existing`: `tmp/seigan/sangiin/detail/{petition_id}/*.html` が既にある場合は取得をスキップ
- 出力
  `tmp/seigan/sangiin/detail/{petition_id}/detail.html`
  `tmp/seigan/sangiin/detail/{petition_id}/similar.html`

実行例:

```bash
uv run python src/pipeline/seigan/get_sangiin_seigan_detail.py 217 --skip-existing
```

### `parse_sangiin_seigan_detail.py`

保存済みの参議院請願個別 HTML をパースし、衆議院側と同じ共通形式の個票 JSON として保存します。

- 入力
  `tmp/seigan/sangiin/list/{回次}.json`
  `tmp/seigan/sangiin/detail/{petition_id}/detail.html`
  `tmp/seigan/sangiin/detail/{petition_id}/similar.html`
- 引数
  `session`: 取得対象の国会回次
- 出力
  `tmp/seigan/sangiin/detail/{petition_id}/index.json`

実行例:

```bash
uv run python src/pipeline/seigan/parse_sangiin_seigan_detail.py 217
```

### `build_seigan_distribution.py`

保存済みの衆参請願一覧・個票 JSON を、配布用データとして `data/` に保存します。

- 入力
  `tmp/seigan/{house}/list/{回次}.json`
  `tmp/seigan/{house}/detail/{petition_id}/index.json`
- 引数
  `sessions...`: 対象の国会回次。省略時は保存済み一覧 JSON を全件処理
  `--house`: `shugiin` `sangiin` `all`。既定値は `all`
- 出力
  `data/seigan/{house}/list/{回次}.json`
  `data/seigan/{house}/detail/{petition_id}.json`

実行例:

```bash
uv run python src/pipeline/seigan/build_seigan_distribution.py --house all 217
```

### `get_shugiin_shitsumon_list.py`

衆議院サイトの「質問主意書一覧」から、指定した国会回次の raw HTML を取得して保存します。
回次によって `itdb_shitsumon` と `itdb_shitsumona` のどちらかが使われるため、候補 URL を順に試します。

- 入力
  `https://www.shugiin.go.jp/internet/itdb_shitsumon.nsf/html/shitsumon/kaiji{回次3桁}_l.htm`
  `https://www.shugiin.go.jp/internet/itdb_shitsumona.nsf/html/shitsumon/kaiji{回次3桁}_l.htm`
- 引数
  `session`: 取得対象の国会回次
  `--skip-existing`: `tmp/shitsumon/shugiin/list/{回次}.html` が既にある場合は取得をスキップ
- 出力
  `tmp/shitsumon/shugiin/list/{回次}.html`

実行例:

```bash
uv run python src/pipeline/shitsumon/get_shugiin_shitsumon_list.py 221 --skip-existing
```

### `parse_shugiin_shitsumon_list.py`

保存済みの衆議院質問主意書一覧 HTML をパースし、型付き JSON として保存します。

- 入力
  `tmp/shitsumon/shugiin/list/{回次}.html`
- 引数
  `session`: 取得対象の国会回次
- 出力
  `tmp/shitsumon/shugiin/list/{回次}.json`

実行例:

```bash
uv run python src/pipeline/shitsumon/parse_shugiin_shitsumon_list.py 221
```

### `get_shugiin_shitsumon_detail.py`

質問主意書一覧 JSON を入力に、各質問主意書の経過ページ・質問本文ページ・答弁本文ページの raw HTML を保存します。

- 入力
  `tmp/shitsumon/shugiin/list/{回次}.json`
- 引数
  `session`: 取得対象の国会回次
  `--skip-existing`: `tmp/shitsumon/shugiin/detail/{question_id}/*.html` が既にある場合は取得をスキップ
- 出力
  `tmp/shitsumon/shugiin/detail/{question_id}/progress.html`
  `tmp/shitsumon/shugiin/detail/{question_id}/question.html`
  `tmp/shitsumon/shugiin/detail/{question_id}/answer.html`

実行例:

```bash
uv run python src/pipeline/shitsumon/get_shugiin_shitsumon_detail.py 221 --skip-existing
```

### `parse_shugiin_shitsumon_detail.py`

保存済みの衆議院質問主意書個別 HTML をパースし、個票 JSON として保存します。

- 入力
  `tmp/shitsumon/shugiin/list/{回次}.json`
  `tmp/shitsumon/shugiin/detail/{question_id}/progress.html`
  `tmp/shitsumon/shugiin/detail/{question_id}/question.html`
  `tmp/shitsumon/shugiin/detail/{question_id}/answer.html`
- 引数
  `session`: 取得対象の国会回次
- 出力
  `tmp/shitsumon/shugiin/detail/{question_id}/index.json`

実行例:

```bash
uv run python src/pipeline/shitsumon/parse_shugiin_shitsumon_detail.py 221
```

### `get_sangiin_shitsumon_list.py`

参議院サイトの「質問主意書・答弁書一覧」から、指定した国会回次の raw HTML を取得して保存します。

- 入力
  `https://www.sangiin.go.jp/japanese/joho1/kousei/syuisyo/{回次}/syuisyo.htm`
- 引数
  `session`: 取得対象の国会回次
  `--skip-existing`: `tmp/shitsumon/sangiin/list/{回次}.html` が既にある場合は取得をスキップ
- 出力
  `tmp/shitsumon/sangiin/list/{回次}.html`

実行例:

```bash
uv run python src/pipeline/shitsumon/get_sangiin_shitsumon_list.py 218 --skip-existing
```

### `parse_sangiin_shitsumon_list.py`

保存済みの参議院質問主意書一覧 HTML をパースし、一覧 JSON として保存します。

- 入力
  `tmp/shitsumon/sangiin/list/{回次}.html`
- 引数
  `session`: 取得対象の国会回次
- 出力
  `tmp/shitsumon/sangiin/list/{回次}.json`

実行例:

```bash
uv run python src/pipeline/shitsumon/parse_sangiin_shitsumon_list.py 218
```

### `get_sangiin_shitsumon_detail.py`

参議院質問主意書一覧 JSON を入力に、各質問主意書の詳細ページ・質問本文ページ・答弁本文ページの raw HTML を保存します。

- 入力
  `tmp/shitsumon/sangiin/list/{回次}.json`
- 引数
  `session`: 取得対象の国会回次
  `--skip-existing`: `tmp/shitsumon/sangiin/detail/{question_id}/*.html` が既にある場合は取得をスキップ
- 出力
  `tmp/shitsumon/sangiin/detail/{question_id}/detail.html`
  `tmp/shitsumon/sangiin/detail/{question_id}/question.html`
  `tmp/shitsumon/sangiin/detail/{question_id}/answer.html`

実行例:

```bash
uv run python src/pipeline/shitsumon/get_sangiin_shitsumon_detail.py 218 --skip-existing
```

### `parse_sangiin_shitsumon_detail.py`

保存済みの参議院質問主意書個別 HTML をパースし、衆議院側と同じ最終形の個票 JSON として保存します。

- 入力
  `tmp/shitsumon/sangiin/list/{回次}.json`
  `tmp/shitsumon/sangiin/detail/{question_id}/detail.html`
  `tmp/shitsumon/sangiin/detail/{question_id}/question.html`
  `tmp/shitsumon/sangiin/detail/{question_id}/answer.html`
- 引数
  `session`: 取得対象の国会回次
- 出力
  `tmp/shitsumon/sangiin/detail/{question_id}/index.json`

実行例:

```bash
uv run python src/pipeline/shitsumon/parse_sangiin_shitsumon_detail.py 218
```

### `build_shitsumon_distribution.py`

保存済みの衆参質問主意書一覧・個票 JSON を、配布用データとして `data/` に保存します。

- 入力
  `tmp/shitsumon/{house}/list/{回次}.json`
  `tmp/shitsumon/{house}/detail/{question_id}/index.json`
- 引数
  `sessions...`: 対象の国会回次。省略時は保存済み一覧 JSON を全件処理
  `--house`: `shugiin` `sangiin` `all`。既定値は `all`
- 出力
  `data/shitsumon/{house}/list/{回次}.json`
  `data/shitsumon/{house}/detail/{question_id}.json`

実行例:

```bash
uv run python src/pipeline/shitsumon/build_shitsumon_distribution.py --house all 218 221
```

### `build_people_index.py`

配布用の議案個票、請願個票、質問主意書個票から、人物ごとのリレーションをまとめた人物インデックスを生成します。

- 入力
  `data/gian/detail/*.json`
  `data/seigan/{house}/detail/*.json`
  `data/shitsumon/shugiin/detail/*.json`
  `data/shitsumon/sangiin/detail/*.json`
  `data/kaigiroku/detail/*.json`
- 引数
  なし
- 出力
  `data/people/index.json`
  `data/people/detail/*.json`

実行例:

```bash
uv run python src/pipeline/people/build_people_index.py
```

## API

会期一覧、議案、請願、質問主意書、人物インデックスの配布用 JSON を FastAPI で配信できます。
公開用の正式エンドポイントは `/v1` 配下です。

起動例:

```bash
uv run api.py
```

主なエンドポイント:

- `GET /health`
- `GET /meta`
- `GET /v1/kaiki`
- `GET /v1/gian/list`
- `GET /v1/gian/list/{session}`
- `GET /v1/gian/detail`
- `GET /v1/gian/detail/{bill_id}`
- `GET /v1/seigan/{house}/list`
- `GET /v1/seigan/{house}/list/{session}`
- `GET /v1/seigan/{house}/detail`
- `GET /v1/seigan/{house}/detail/{petition_id}`
- `GET /v1/shitsumon/{house}/list`
- `GET /v1/shitsumon/{house}/list/{session}`
- `GET /v1/shitsumon/{house}/detail`
- `GET /v1/shitsumon/{house}/detail/{question_id}`
- `GET /v1/people`
- `GET /v1/people/search?q=高市`
- `GET /v1/people/{person_key}`

## Flask UI

既存 API を利用して、人物検索と議案・請願・質問主意書の閲覧ができる簡易 UI を `ui.py` で起動できます。
Flask 側は JSON を直接読まず、`API_BASE_URL` で指定した API に HTTP で接続します。

起動例:

```bash
uv run api.py
uv run flask --app ui run --port 5001
```

環境変数:

- `API_BASE_URL`
  Flask UI が参照する API のベース URL。既定値は `http://127.0.0.1:9000`
- `FLASK_HOST`
  `python ui.py` で直接起動するときのホスト。既定値は `127.0.0.1`
- `FLASK_PORT`
  `python ui.py` で直接起動するときのポート。既定値は `5001`

## 出力方針

- JSON は UTF-8、インデント付きで保存する
- 日付は可能な限り ISO 形式へ正規化する
- 元ページにあるカテゴリや注記は、意味を落とさない範囲でフィールドとして保持する
