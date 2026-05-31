from __future__ import annotations

import unittest

import pandas as pd

from src.schema.schema_profiler import SchemaProfiler


class SchemaProfilerTest(unittest.TestCase):
    def test_profiles_columns_without_manual_row_inspection(self) -> None:
        dataframe = pd.DataFrame(
            {
                "生源地": ["广东", "广东"],
                "学费": ["5000", "20000"],
                "公私性质": ["公办", "民办"],
                "城市水平标签": ["一线城市", "三线城市"],
            }
        )
        profile = SchemaProfiler().profile(
            dataframe=dataframe,
            headers=list(dataframe.columns),
            workbook_name="demo.xlsx",
            sheet_name="Sheet1",
            header_row=3,
        )
        by_column = {item["source_column"]: item for item in profile["columns"]}
        self.assertEqual(profile["column_count"], 4)
        self.assertEqual(by_column["生源地"]["suggested_field_id"], "source_province")
        self.assertEqual(by_column["学费"]["suggested_field_id"], "tuition_yuan_per_year")
        self.assertEqual(by_column["公私性质"]["suggested_field_id"], "school_ownership")
        self.assertEqual(by_column["城市水平标签"]["suggested_field_id"], "city_level_tag")
        self.assertEqual(by_column["学费"]["type_guess"], "number_from_string")


if __name__ == "__main__":
    unittest.main()
