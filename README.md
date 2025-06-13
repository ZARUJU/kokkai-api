# 取得プログラムの実行について

## 会期一覧の更新

```
uv run session_list.py
```

## 会議録

```bash
# 最新取得済みから実行日までを取得
uv run minutes.py

# 指定期間のものを取得
uv run minutes.py --from 2025-06-06 --until 2025-06-13
```

## 議案データ

## 質問主意書

### 衆議院

```bash
# 最新セッションのみ取得
uv run qa_shu.py

# 最新＋過去すべてのセッションを取得
uv run qa_shu.py --all
```

### 参議院

```bash
# 最新セッションのみ取得
uv run qa_san.py

# 最新＋過去すべてのセッションを取得
uv run qa_san.py --all
```

## 衆議院TV

```bash
# 本日分だけ取得
uv run shugiintv.py

# 任意の日だけ取得
uv run shugiintv.py -s 20250610

# 範囲指定でまとめて取得
uv run shugiintv.py -s 20250601 -e 20250605
```

## 参議院TV

## 紐付け

### 会議録と衆議院の映像

```bash
uv run relations_shutv_minutes.py
```

