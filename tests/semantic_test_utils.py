from __future__ import annotations

from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Iterator

import pandas as pd

from scripts.generate_domain_pack import load_source_dataset
from src.adapters.excel_adapter import ExcelDataSet


NEW_ADMISSIONS_ROWS = [
    {
        "年份": 2025,
        "院校名称": "中山大学",
        "院校代码": "10558",
        "科类": "物理类",
        "批次": "本科批",
        "专业": "预防医学",
        "专业代码": "095",
        "所属专业组": "（219）",
        "专业备注": "（深圳校区）",
        "选科要求": "首选物理，再选化学",
        "录取人数": 5,
        "最低分数": 630,
        "最低位次": 9850,
        "学校所在": "广东",
        "学校性质": "公办",
        "是否985": "是",
        "是否211": "是",
    },
    {
        "年份": 2025,
        "院校名称": "深圳大学",
        "院校代码": "10590",
        "科类": "物理类",
        "批次": "本科批",
        "专业": "计算机科学与技术",
        "专业代码": "080901",
        "所属专业组": "（230）",
        "专业备注": "（粤海校区）",
        "选科要求": "首选物理，再选化学",
        "录取人数": 24,
        "最低分数": 628,
        "最低位次": 10257,
        "学校所在": "广东",
        "学校性质": "公办",
        "是否985": "否",
        "是否211": "否",
    },
    {
        "年份": 2025,
        "院校名称": "暨南大学",
        "院校代码": "10559",
        "科类": "物理类",
        "批次": "本科批",
        "专业": "软件工程",
        "专业代码": "080902",
        "所属专业组": "（222）",
        "专业备注": "（番禺校区）",
        "选科要求": "首选物理，再选化学",
        "录取人数": 42,
        "最低分数": 616,
        "最低位次": 16212,
        "学校所在": "广东",
        "学校性质": "公办",
        "是否985": "否",
        "是否211": "是",
    },
    {
        "年份": 2025,
        "院校名称": "电子科技大学",
        "院校代码": "19614",
        "科类": "物理类",
        "批次": "本科批",
        "专业": "电子信息类",
        "专业代码": "008",
        "所属专业组": "（204）",
        "专业备注": "（中外合作办学）",
        "选科要求": "首选物理，再选化学",
        "录取人数": 10,
        "最低分数": 630,
        "最低位次": 9850,
        "学校所在": "四川",
        "学校性质": "公办",
        "是否985": "是",
        "是否211": "是",
    },
]


def write_new_admissions_excel(path: Path) -> Path:
    dataframe = pd.DataFrame(NEW_ADMISSIONS_ROWS)
    dataframe.to_excel(path, index=False)
    return path


def new_admissions_dataset() -> Iterator[ExcelDataSet]:
    with NamedTemporaryFile(delete=False, suffix=".xlsx") as tmpfile:
        source_path = Path(tmpfile.name)
    write_new_admissions_excel(source_path)
    yield load_source_dataset(source_path)
