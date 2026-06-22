from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path
from tempfile import TemporaryDirectory
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
        "专业代码": "001",
        "所属专业组": "201",
        "专业备注": "",
        "选科要求": "物理+化学",
        "录取人数": 12,
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
        "专业代码": "002",
        "所属专业组": "202",
        "专业备注": "",
        "选科要求": "物理+化学",
        "录取人数": 20,
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
        "专业代码": "003",
        "所属专业组": "203",
        "专业备注": "",
        "选科要求": "物理+化学",
        "录取人数": 16,
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
        "院校代码": "10614",
        "科类": "物理类",
        "批次": "本科批",
        "专业": "电子信息类",
        "专业代码": "004",
        "所属专业组": "204",
        "专业备注": "中外合作办学",
        "选科要求": "物理+化学",
        "录取人数": 8,
        "最低分数": 625,
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


@contextmanager
def new_admissions_dataset() -> Iterator[ExcelDataSet]:
    with TemporaryDirectory() as tmpdir:
        source_path = write_new_admissions_excel(Path(tmpdir) / "new_admissions.xlsx")
        yield load_source_dataset(source_path)
