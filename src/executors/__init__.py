"""规则执行器。"""

from src.executors.duckdb_executor import DuckDBExecutor
from src.executors.pandas_executor import PandasExecutor

__all__ = ["DuckDBExecutor", "PandasExecutor"]
