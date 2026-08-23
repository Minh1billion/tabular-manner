import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import polars as pl
import pytest

from tabular_manner.engine.infrastructure.writer.database import DatabaseWriterAdapter

class TestInit:
    @pytest.mark.parametrize("mode", ["append", "replace", "fail"])
    def test_accepts_valid_modes(self, mode):
        adapter = DatabaseWriterAdapter(dsn="postgresql://localhost/db", table="customers", if_table_exists=mode)

        assert adapter.if_table_exists == mode

    def test_rejects_invalid_mode(self):
        with pytest.raises(ValueError, match="Unsupported if_table_exists 'overwrite'"):
            DatabaseWriterAdapter(dsn="postgresql://localhost/db", table="customers", if_table_exists="overwrite")

    def test_defaults_to_append(self):
        adapter = DatabaseWriterAdapter(dsn="postgresql://localhost/db", table="customers")

        assert adapter.if_table_exists == "append"

class TestExecute:
    def test_collects_and_writes_to_database(self):
        adapter = DatabaseWriterAdapter(dsn="postgresql://localhost/db", table="customers", if_table_exists="replace")
        lf = pl.LazyFrame({"a": [1, 2]})

        write_mock = MagicMock()
        with patch.object(pl.DataFrame, "write_database", write_mock):
            adapter.execute(lf)

        write_mock.assert_called_once_with(
            table_name="customers",
            connection="postgresql://localhost/db",
            if_table_exists="replace",
        )
