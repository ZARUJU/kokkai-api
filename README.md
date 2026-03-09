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
  取得元サイトの構造整理や、今後の実装方針に関するドキュメントを置く
- `data`
  配布対象の整形済みデータを置く
- `tmp`
  一時出力、検証用ファイル、配布前の中間生成物を置く

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
uv run python src/pipeline/get_kaiki.py
```

### `get_gian_list.py`

衆議院サイトの「議案の一覧」から、指定した国会回次の議案一覧を取得し、カテゴリ情報つきの JSON として保存します。

- 入力
  `https://www.shugiin.go.jp/internet/itdb_gian.nsf/html/gian/kaiji{回次}.htm`
- 引数
  `session`: 取得対象の国会回次
- 出力
  `tmp/gian/list/{回次}.json`

実行例:

```bash
uv run python src/pipeline/get_gian_list.py 221
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
uv run python src/pipeline/get_gian_progress.py 221
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
uv run python src/pipeline/parse_gian_progress.py 221
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
uv run python src/pipeline/get_gian_text.py 221
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
uv run python src/pipeline/parse_gian_text.py 221
```

## 出力方針

- JSON は UTF-8、インデント付きで保存する
- 日付は可能な限り ISO 形式へ正規化する
- 元ページにあるカテゴリや注記は、意味を落とさない範囲でフィールドとして保持する
