"""保存済みの議案本文 HTML をパースして JSON に保存する。

引数:
    - session: 取得対象の国会回次

入力:
    - tmp/gian/list/{session}.json
    - tmp/gian/detail/{bill_id}/honbun/index.html
    - tmp/gian/detail/{bill_id}/honbun/documents/*.html

出力:
    - tmp/gian/detail/{bill_id}/honbun/index.json
"""

from __future__ import annotations

import argparse
import json
import logging
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urljoin

from bs4 import BeautifulSoup

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.models import GianListDataset, GianTextDataset, GianTextDocumentParsed, GianTextParsed
from src.utils import build_gian_bill_id, build_text_document_filename, normalize_text

INPUT_LIST_DIR = Path("tmp/gian/list")
DETAIL_ROOT = Path("tmp/gian/detail")
logger = logging.getLogger(__name__)


def parse_args() -> argparse.Namespace:
    """コマンドライン引数から対象の国会回次を受け取る。"""

    parser = argparse.ArgumentParser(description="指定した回次の議案本文 HTML をパースする")
    parser.add_argument("session", type=int, help="取得対象の国会回次")
    return parser.parse_args()


def load_gian_list(session: int, input_dir: Path = INPUT_LIST_DIR) -> GianListDataset:
    """議案一覧 JSON を読み込んでモデルに変換する。"""

    input_path = input_dir / f"{session}.json"
    return GianListDataset.model_validate_json(input_path.read_text(encoding="utf-8"))


def classify_document(label: str) -> tuple[str, str | None, str | None]:
    """リンク表示名から文書種別・短いタイトル・注記を推定する。"""

    text = normalize_text(label)
    note_match = re.search(r"\((.+?)\)$", text)
    note = note_match.group(1) if note_match else None
    base = re.sub(r"\(.+?\)$", "", text).strip()
    if "提出時法律案" in base:
        return "original_bill", "提出時法律案", note
    if "要綱" in base:
        return "outline", "要綱", note
    if base.startswith("修正案"):
        short = base.split("：", 1)[0]
        return "amendment", short, note
    return "other", base or None, note


def parse_text_page_metadata(text: str) -> tuple[str | None, str | None, str | None, str | None]:
    """本文一覧ページのテキストから基本情報を抽出する。"""

    submit_session = None
    bill_type = None
    bill_number_label = None
    bill_title = None

    session_match = re.search(r"提出回次[:：]\s*(第?\d+回)", text)
    if session_match:
        submit_session = session_match.group(1)

    type_match = re.search(r"議案種類[:：]\s*([^\s]+)", text)
    if type_match:
        bill_type = type_match.group(1)

    title_match = re.search(r"議案名[:：]\s*(.+?)\s*照会できる情報の一覧", text)
    if title_match:
        bill_title = normalize_text(title_match.group(1))

    number_match = re.search(r"議案種類[:：]\s*[^\s]+\s+(\d+号)", text)
    if number_match:
        bill_number_label = number_match.group(1)

    return submit_session, bill_type, bill_number_label, bill_title


def parse_documents(soup: BeautifulSoup, bill_id: str, base_url: str) -> list[GianTextDocumentParsed]:
    """本文一覧ページから関連文書リンクを抽出してモデル化する。"""

    documents: list[GianTextDocumentParsed] = []
    for link in soup.find_all("a", href=True):
        href = link["href"]
        if not href.startswith("./"):
            continue
        label = normalize_text(link.get_text(" ", strip=True))
        url = urljoin(base_url, href)
        document_type, title, note = classify_document(label)
        local_path = f"tmp/gian/detail/{bill_id}/honbun/documents/{build_text_document_filename(url)}"
        documents.append(
            GianTextDocumentParsed(
                label=label,
                title=title,
                document_type=document_type,
                note=note,
                url=url,
                local_path=local_path,
            )
        )
    return documents


def build_text_dataset(session: int, item, html: str) -> GianTextDataset:
    """議案一覧の1件と本文一覧 HTML から保存用データを構築する。"""

    if item.text_url is None:
        raise ValueError("text_url がない議案は本文取得できません。")

    soup = BeautifulSoup(html, "html.parser")
    page_title = normalize_text(soup.title.get_text(" ", strip=True)) if soup.title else None
    page_text = soup.get_text(" ", strip=True)
    submit_session_label, bill_type, bill_number_label, bill_title = parse_text_page_metadata(page_text)
    bill_id = build_gian_bill_id(
        category=item.category,
        submitted_session=item.submitted_session,
        bill_number=item.bill_number,
        title=item.title,
        subcategory=item.subcategory,
    )

    return GianTextDataset(
        bill_id=bill_id,
        category=item.category,
        subcategory=item.subcategory,
        submitted_session=item.submitted_session,
        bill_number=item.bill_number,
        title=item.title,
        status=item.status,
        source_url=str(item.text_url),
        fetched_at=datetime.now(timezone.utc),
        parsed=GianTextParsed(
            page_title=page_title,
            submit_session_label=submit_session_label,
            bill_type=bill_type,
            bill_number_label=bill_number_label,
            bill_title=bill_title,
            documents=parse_documents(soup=soup, bill_id=bill_id, base_url=str(item.text_url)),
        ),
    )


def save_text_dataset(dataset: GianTextDataset, detail_root: Path = DETAIL_ROOT) -> Path:
    """パース済み本文情報を JSON に保存する。"""

    output_path = detail_root / dataset.bill_id / "honbun" / "index.json"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(dataset.model_dump(mode="json"), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return output_path


def process_session(session: int, detail_root: Path = DETAIL_ROOT) -> list[Path]:
    """指定回次の保存済み本文 HTML を一括パースして保存する。"""

    gian_list = load_gian_list(session)
    logger.info("本文JSONパース開始: session=%s items=%s", session, len(gian_list.items))
    saved_paths: list[Path] = []
    for item in gian_list.items:
        if item.text_url is None:
            logger.info("スキップ: text_urlなし title=%s", item.title)
            continue

        bill_id = build_gian_bill_id(
            category=item.category,
            submitted_session=item.submitted_session,
            bill_number=item.bill_number,
            title=item.title,
            subcategory=item.subcategory,
        )
        html_path = detail_root / bill_id / "honbun" / "index.html"
        logger.info("読込: bill_id=%s path=%s", bill_id, html_path)
        html = html_path.read_text(encoding="utf-8")
        dataset = build_text_dataset(session=session, item=item, html=html)
        output_path = save_text_dataset(dataset, detail_root=detail_root)
        logger.info("保存: bill_id=%s path=%s", bill_id, output_path)
        saved_paths.append(output_path)

    logger.info("本文JSONパース完了: session=%s saved=%s", session, len(saved_paths))
    return saved_paths


def main() -> None:
    """指定回次の保存済み本文 HTML をパースして JSON に保存する。"""

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    args = parse_args()
    process_session(args.session)


if __name__ == "__main__":
    main()
