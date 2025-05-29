import time

from src.qa_shu_utils import get_qa_shu_list_data
from src.utils import write_to_json

session = 217
data = get_qa_shu_list_data(session)
write_to_json(data.model_dump(), f"data/qa_shu/list/{session}.json")
