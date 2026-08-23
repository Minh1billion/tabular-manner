import polars as pl
import pytest

from tabular_manner.engine.application.io.reader_factory import ReaderFactory
from tabular_manner.engine.application.io.writer_factory import WriterFactory
from tabular_manner.engine.application.ports.reader_adapter import ReaderAdapter
from tabular_manner.engine.application.ports.writer_adapter import WriterAdapter

class _FakeReader(ReaderAdapter):
    def __init__(self, value: int):
        self.value = value

    def execute(self) -> pl.LazyFrame:
        return pl.LazyFrame({"value": [self.value]})

class _FakeWriter(WriterAdapter):
    calls: list = []

    def __init__(self, target: str):
        self.target = target

    def execute(self, lf: pl.LazyFrame) -> None:
        _FakeWriter.calls.append((self.target, lf.collect().to_dict(as_series=False)))

class TestReaderFactory:
    def test_defaults_include_file_and_database(self):
        factory = ReaderFactory()

        assert "file" in factory._adapters
        assert "database" in factory._adapters

    def test_create_unknown_kind_raises(self):
        factory = ReaderFactory()

        with pytest.raises(KeyError, match="Unknown reader kind 'ghost'"):
            factory.create("ghost")

    def test_register_adds_new_kind(self):
        factory = ReaderFactory()

        factory.register("fake", _FakeReader)
        adapter = factory.create("fake", value=42)

        assert isinstance(adapter, _FakeReader)

    def test_read_creates_and_executes_adapter(self):
        factory = ReaderFactory().register("fake", _FakeReader)

        result = factory.read("fake", value=7)

        assert result.collect().to_dict(as_series=False) == {"value": [7]}

    def test_constructor_accepts_extra_adapters(self):
        factory = ReaderFactory(adapters={"fake": _FakeReader})

        assert isinstance(factory.create("fake", value=1), _FakeReader)

class TestWriterFactory:
    def test_defaults_include_file_and_database(self):
        factory = WriterFactory()

        assert "file" in factory._adapters
        assert "database" in factory._adapters

    def test_create_unknown_kind_raises(self):
        factory = WriterFactory()

        with pytest.raises(KeyError, match="Unknown writer kind 'ghost'"):
            factory.create("ghost")

    def test_register_adds_new_kind(self):
        factory = WriterFactory()

        factory.register("fake", _FakeWriter)
        adapter = factory.create("fake", target="out")

        assert isinstance(adapter, _FakeWriter)

    def test_write_creates_and_executes_adapter(self):
        _FakeWriter.calls.clear()
        factory = WriterFactory().register("fake", _FakeWriter)

        factory.write("fake", pl.LazyFrame({"a": [1]}), target="out")

        assert _FakeWriter.calls == [("out", {"a": [1]})]

    def test_constructor_accepts_extra_adapters(self):
        factory = WriterFactory(adapters={"fake": _FakeWriter})

        assert isinstance(factory.create("fake", target="out"), _FakeWriter)
