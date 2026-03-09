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

現時点では、議案の統合済み JSON はまだ公開仕様確定前のため `tmp/ready/` に置く。
最終的に外部公開する形式まで固まったものだけ `data/` に昇格させる。

## セットアップ

Python 3.11 以上を前提としています。

```bash
uv sync
```

## パイプライン

### `get_kaiki.py`

衆議院サイトの「国会会期一覧」から会期情報を取得し、整形済み JSON として保存します。

- 入力
  衆議院サイトの会期一覧ページ `https://www.shugiin.go.jp/internet/itdb_annai.nsf/html/statics/shiryo/kaiki.htm`
- 引数
  なし
- 出力
  `data/kaiki.json`

実行例:

```bash
uv run python src/pipeline/kaiki/get_kaiki.py
```

### `get_gian_list.py`

衆議院サイトの「議案の一覧」から、指定した国会回次の raw HTML を取得して保存します。

- 入力
  `https://www.shugiin.go.jp/internet/itdb_gian.nsf/html/gian/kaiji{回次}.htm`
- 引数
  `session`: 取得対象の国会回次
- 出力
  `tmp/gian/list/{回次}.html`

実行例:

```bash
uv run python src/pipeline/gian/get_gian_list.py 221
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
- 出力
  `tmp/gian/detail/{bill_id}/progress/{回次}.html`

実行例:

```bash
uv run python src/pipeline/gian/get_gian_progress.py 221
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
- 出力
  `tmp/gian/detail/{bill_id}/honbun/index.html`
  `tmp/gian/detail/{bill_id}/honbun/documents/*.html`

実行例:

```bash
uv run python src/pipeline/gian/get_gian_text.py 221
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

保存済みの議案一覧・進捗・本文データから、配布一歩手前の議案一覧 JSON と議案個票 JSON を `tmp/ready/` に生成します。

- 入力
  `tmp/gian/list/{回次}.json`
  `tmp/gian/detail/{bill_id}/progress/{回次}.json`
  `tmp/gian/detail/{bill_id}/honbun/index.html`
  `tmp/gian/detail/{bill_id}/honbun/documents/*.html`
- 引数
  `sessions...`: 対象の国会回次。省略時は `tmp/gian/list/*.json` を全件処理
- 出力
  `tmp/ready/gian/list/{回次}.json`
  `tmp/ready/gian/detail/{bill_id}.json`

実行例:

```bash
uv run python src/pipeline/gian/build_gian_distribution.py 218 220 221
```

### `get_shugiin_shitsumon_list.py`

衆議院サイトの「質問主意書一覧」から、指定した国会回次の raw HTML を取得して保存します。
回次によって `itdb_shitsumon` と `itdb_shitsumona` のどちらかが使われるため、候補 URL を順に試します。

- 入力
  `https://www.shugiin.go.jp/internet/itdb_shitsumon.nsf/html/shitsumon/kaiji{回次3桁}_l.htm`
  `https://www.shugiin.go.jp/internet/itdb_shitsumona.nsf/html/shitsumon/kaiji{回次3桁}_l.htm`
- 引数
  `session`: 取得対象の国会回次
- 出力
  `tmp/shitsumon/shugiin/list/{回次}.html`

実行例:

```bash
uv run python src/pipeline/shitsumon/get_shugiin_shitsumon_list.py 221
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
- 出力
  `tmp/shitsumon/shugiin/detail/{question_id}/progress.html`
  `tmp/shitsumon/shugiin/detail/{question_id}/question.html`
  `tmp/shitsumon/shugiin/detail/{question_id}/answer.html`

実行例:

```bash
uv run python src/pipeline/shitsumon/get_shugiin_shitsumon_detail.py 221
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
- 出力
  `tmp/shitsumon/sangiin/list/{回次}.html`

実行例:

```bash
uv run python src/pipeline/shitsumon/get_sangiin_shitsumon_list.py 218
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
- 出力
  `tmp/shitsumon/sangiin/detail/{question_id}/detail.html`
  `tmp/shitsumon/sangiin/detail/{question_id}/question.html`
  `tmp/shitsumon/sangiin/detail/{question_id}/answer.html`

実行例:

```bash
uv run python src/pipeline/shitsumon/get_sangiin_shitsumon_detail.py 218
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

保存済みの衆参質問主意書一覧・個票 JSON を、そのまま配布一歩手前データとして `tmp/ready/` に保存します。

- 入力
  `tmp/shitsumon/{house}/list/{回次}.json`
  `tmp/shitsumon/{house}/detail/{question_id}/index.json`
- 引数
  `sessions...`: 対象の国会回次。省略時は保存済み一覧 JSON を全件処理
  `--house`: `shugiin` `sangiin` `all`。既定値は `all`
- 出力
  `tmp/ready/shitsumon/{house}/list/{回次}.json`
  `tmp/ready/shitsumon/{house}/detail/{question_id}.json`

実行例:

```bash
uv run python src/pipeline/shitsumon/build_shitsumon_distribution.py --house all 218 221
```

## API

会期一覧と、議案の配布一歩手前 JSON を FastAPI で配信できます。

起動例:

```bash
uv run api.py
```

主なエンドポイント:

- `GET /health`
- `GET /kaiki`
- `GET /gian/list`
- `GET /gian/list/{session}`
- `GET /gian/detail`
- `GET /gian/detail/{bill_id}`

## 出力方針

- JSON は UTF-8、インデント付きで保存する
- 日付は可能な限り ISO 形式へ正規化する
- 元ページにあるカテゴリや注記は、意味を落とさない範囲でフィールドとして保持する
