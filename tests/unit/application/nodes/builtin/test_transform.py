import polars as pl

import pytest

from tabular_manner.engine.application.nodes.builtin.transform import (
    Abs,
    AddRowIndex,
    Bin,
    Cast,
    Clip,
    CumulativeSum,
    DatePart,
    Derive,
    Drop,
    DropDuplicates,
    DropNulls,
    Explode,
    ExtractRegex,
    FillBackward,
    FillForward,
    FillMean,
    FillNull,
    Filter,
    GroupBy,
    Head,
    Limit,
    Log,
    MapValues,
    MinMaxNormalize,
    ParseDate,
    Power,
    Rank,
    Rename,
    Round,
    Select,
    Shift,
    Sort,
    Sqrt,
    StrCase,
    StrReplace,
    StrStrip,
    Tail,
    Unpivot,
    ZScoreNormalize,
)
from tabular_manner.engine.domain.models.plan import Plan

def _plan(data: dict) -> Plan:
    return Plan(handle=pl.LazyFrame(data))

class TestSelect:
    def test_keeps_only_requested_columns(self):
        node = Select(name="sel", columns=["a"])
        plan = _plan({"a": [1, 2], "b": [3, 4]})

        result, port = node.forward(plan)

        assert result.handle.collect_schema().names() == ["a"]
        assert port == "out"

    def test_commits_step_with_node_name(self):
        node = Select(name="sel", columns=["a"])
        plan = _plan({"a": [1], "b": [2]})

        result, _ = node.forward(plan)

        assert result.history == ("sel",)

class TestFillMean:
    def test_fills_nulls_with_column_mean(self):
        node = FillMean(name="fill", columns=["a"])
        plan = _plan({"a": [1.0, None, 3.0]})

        result, port = node.forward(plan)
        collected = result.handle.collect()

        assert collected["a"].to_list() == [1.0, 2.0, 3.0]
        assert port == "out"

    def test_only_fills_specified_columns(self):
        node = FillMean(name="fill", columns=["a"])
        plan = _plan({"a": [1.0, None], "b": [None, 5.0]})

        result, _ = node.forward(plan)
        collected = result.handle.collect()

        assert collected["b"].to_list() == [None, 5.0]

    def test_commits_step_with_node_name(self):
        node = FillMean(name="fill", columns=["a"])
        plan = _plan({"a": [1.0]})

        result, _ = node.forward(plan)

        assert result.history == ("fill",)

class TestFillNull:
    def test_fills_nulls_with_given_value(self):
        node = FillNull(name="fill_null", columns=["a"], value=0)
        plan = _plan({"a": [1, None, 3]})

        result, port = node.forward(plan)
        collected = result.handle.collect()

        assert collected["a"].to_list() == [1, 0, 3]
        assert port == "out"

    def test_only_fills_specified_columns(self):
        node = FillNull(name="fill_null", columns=["a"], value="x")
        plan = _plan({"a": [None], "b": [None]})

        result, _ = node.forward(plan)
        collected = result.handle.collect()

        assert collected["b"].to_list() == [None]

class TestDropNulls:
    def test_drops_rows_with_null_in_subset(self):
        node = DropNulls(name="dropna", columns=["a"])
        plan = _plan({"a": [1, None, 3], "b": [4, 5, 6]})

        result, _ = node.forward(plan)
        collected = result.handle.collect()

        assert collected["a"].to_list() == [1, 3]

    def test_defaults_to_all_columns(self):
        node = DropNulls(name="dropna")
        plan = _plan({"a": [1, 2], "b": [None, 5]})

        result, _ = node.forward(plan)
        collected = result.handle.collect()

        assert collected.height == 1

class TestDropDuplicates:
    def test_removes_duplicate_rows(self):
        node = DropDuplicates(name="dedupe")
        plan = _plan({"a": [1, 1, 2]})

        result, _ = node.forward(plan)
        collected = result.handle.collect()

        assert sorted(collected["a"].to_list()) == [1, 2]

    def test_rejects_invalid_keep(self):
        with pytest.raises(ValueError):
            DropDuplicates(name="dedupe", keep="bogus")

class TestRename:
    def test_renames_columns(self):
        node = Rename(name="rn", mapping={"a": "renamed"})
        plan = _plan({"a": [1], "b": [2]})

        result, _ = node.forward(plan)

        assert result.handle.collect_schema().names() == ["renamed", "b"]

    def test_rejects_empty_mapping(self):
        with pytest.raises(ValueError):
            Rename(name="rn", mapping={})

class TestSort:
    def test_sorts_ascending_by_default(self):
        node = Sort(name="sort", by=["a"])
        plan = _plan({"a": [3, 1, 2]})

        result, _ = node.forward(plan)
        collected = result.handle.collect()

        assert collected["a"].to_list() == [1, 2, 3]

    def test_sorts_descending(self):
        node = Sort(name="sort", by=["a"], descending=True)
        plan = _plan({"a": [3, 1, 2]})

        result, _ = node.forward(plan)
        collected = result.handle.collect()

        assert collected["a"].to_list() == [3, 2, 1]

class TestCast:
    def test_casts_column_to_requested_dtype(self):
        node = Cast(name="cast", types={"a": "Float64"})
        plan = _plan({"a": [1, 2, 3]})

        result, _ = node.forward(plan)

        assert result.handle.collect_schema()["a"] == pl.Float64

    def test_rejects_unknown_dtype(self):
        with pytest.raises(ValueError):
            Cast(name="cast", types={"a": "NotADtype"})

    def test_rejects_non_dtype_polars_attribute(self):
        with pytest.raises(ValueError):
            Cast(name="cast", types={"a": "DataFrame"})

class TestDrop:
    def test_removes_specified_columns(self):
        node = Drop(name="drop", columns=["b"])
        plan = _plan({"a": [1], "b": [2]})

        result, port = node.forward(plan)

        assert result.handle.collect_schema().names() == ["a"]
        assert port == "out"

class TestLimit:
    def test_keeps_only_first_n_rows(self):
        node = Limit(name="limit", n=2)
        plan = _plan({"a": [1, 2, 3, 4]})

        result, _ = node.forward(plan)
        collected = result.handle.collect()

        assert collected["a"].to_list() == [1, 2]

    def test_rejects_negative_n(self):
        with pytest.raises(ValueError):
            Limit(name="limit", n=-1)

class TestHead:
    def test_keeps_only_first_n_rows(self):
        node = Head(name="head", n=2)
        plan = _plan({"a": [1, 2, 3, 4]})

        result, _ = node.forward(plan)
        collected = result.handle.collect()

        assert collected["a"].to_list() == [1, 2]

    def test_rejects_negative_n(self):
        with pytest.raises(ValueError):
            Head(name="head", n=-1)

class TestTail:
    def test_keeps_only_last_n_rows(self):
        node = Tail(name="tail", n=2)
        plan = _plan({"a": [1, 2, 3, 4]})

        result, _ = node.forward(plan)
        collected = result.handle.collect()

        assert collected["a"].to_list() == [3, 4]

    def test_rejects_negative_n(self):
        with pytest.raises(ValueError):
            Tail(name="tail", n=-1)

class TestExplode:
    def test_explodes_list_column_into_rows(self):
        node = Explode(name="explode", columns=["a"])
        plan = _plan({"a": [[1, 2], [3]], "b": ["x", "y"]})

        result, port = node.forward(plan)
        collected = result.handle.collect()

        assert collected["a"].to_list() == [1, 2, 3]
        assert collected["b"].to_list() == ["x", "x", "y"]
        assert port == "out"

class TestGroupBy:
    def test_aggregates_by_group(self):
        node = GroupBy(name="grp", by=["b"], aggregations={"a": "sum"})
        plan = _plan({"a": [1, 2, 3], "b": ["x", "y", "x"]})

        result, _ = node.forward(plan)
        collected = result.handle.collect().sort("b")

        assert collected["b"].to_list() == ["x", "y"]
        assert collected["a"].to_list() == [4, 2]

    def test_rejects_empty_aggregations(self):
        with pytest.raises(ValueError):
            GroupBy(name="grp", by=["b"], aggregations={})

    def test_rejects_unknown_aggregation(self):
        with pytest.raises(ValueError):
            GroupBy(name="grp", by=["b"], aggregations={"a": "bogus"})

class TestLog:
    def test_applies_natural_log_by_default(self):
        node = Log(name="log", columns=["a"])
        plan = _plan({"a": [1.0]})

        result, _ = node.forward(plan)
        collected = result.handle.collect()

        assert collected["a"].to_list() == [0.0]

    def test_applies_log_with_given_base(self):
        node = Log(name="log", columns=["a"], base=2.0)
        plan = _plan({"a": [8.0]})

        result, _ = node.forward(plan)
        collected = result.handle.collect()

        assert collected["a"].to_list() == [3.0]

    def test_rejects_non_positive_base(self):
        with pytest.raises(ValueError):
            Log(name="log", columns=["a"], base=0.0)

class TestZScoreNormalize:
    def test_centers_and_scales_column(self):
        node = ZScoreNormalize(name="z", columns=["a"])
        plan = _plan({"a": [1.0, 2.0, 3.0, 4.0]})

        result, port = node.forward(plan)
        collected = result.handle.collect()

        assert collected["a"].mean() == pytest.approx(0.0, abs=1e-9)
        assert port == "out"

class TestMinMaxNormalize:
    def test_scales_column_to_zero_one_range(self):
        node = MinMaxNormalize(name="mm", columns=["a"])
        plan = _plan({"a": [1.0, 2.0, 3.0, 4.0]})

        result, port = node.forward(plan)
        collected = result.handle.collect()

        assert collected["a"].to_list() == [0.0, pytest.approx(1 / 3), pytest.approx(2 / 3), 1.0]
        assert port == "out"

class TestFilter:
    def test_keeps_rows_matching_expression(self):
        node = Filter(name="filter", expression="df.a >= 2")
        plan = _plan({"a": [1, 2, 3]})

        result, port = node.forward(plan)
        collected = result.handle.collect()

        assert collected["a"].to_list() == [2, 3]
        assert port == "out"

    def test_rejects_empty_expression(self):
        with pytest.raises(ValueError):
            Filter(name="filter", expression="   ")

    def test_rejects_disallowed_expression(self):
        with pytest.raises(ValueError):
            Filter(name="filter", expression="__import__('os')")

    def test_rejects_expression_not_evaluating_to_expr(self):
        node = Filter(name="filter", expression="1 + 1")
        plan = _plan({"a": [1, 2, 3]})

        with pytest.raises(TypeError):
            node.forward(plan)

class TestDerive:
    def test_adds_computed_column(self):
        node = Derive(name="derive", column="doubled", expression="df.a * 2")
        plan = _plan({"a": [1, 2, 3]})

        result, port = node.forward(plan)
        collected = result.handle.collect()

        assert collected["doubled"].to_list() == [2, 4, 6]
        assert port == "out"

    def test_rejects_empty_column(self):
        with pytest.raises(ValueError):
            Derive(name="derive", column="  ", expression="df.a")

    def test_rejects_disallowed_expression(self):
        with pytest.raises(ValueError):
            Derive(name="derive", column="x", expression="df.a.map_elements(pl.read_csv)")

class TestAbs:
    def test_takes_absolute_value(self):
        node = Abs(name="abs", columns=["a"])
        plan = _plan({"a": [-1, 2, -3]})

        result, _ = node.forward(plan)
        collected = result.handle.collect()

        assert collected["a"].to_list() == [1, 2, 3]

class TestRound:
    def test_rounds_to_given_decimals(self):
        node = Round(name="round", columns=["a"], decimals=1)
        plan = _plan({"a": [1.234, 2.567]})

        result, _ = node.forward(plan)
        collected = result.handle.collect()

        assert collected["a"].to_list() == [1.2, 2.6]

    def test_defaults_to_zero_decimals(self):
        node = Round(name="round", columns=["a"])
        plan = _plan({"a": [1.6]})

        result, _ = node.forward(plan)
        collected = result.handle.collect()

        assert collected["a"].to_list() == [2.0]

class TestClip:
    def test_clips_values_to_bounds(self):
        node = Clip(name="clip", columns=["a"], lower=-2.0, upper=2.0)
        plan = _plan({"a": [-5.0, 0.0, 5.0]})

        result, _ = node.forward(plan)
        collected = result.handle.collect()

        assert collected["a"].to_list() == [-2.0, 0.0, 2.0]

    def test_rejects_when_no_bound_given(self):
        with pytest.raises(ValueError):
            Clip(name="clip", columns=["a"])

class TestSqrt:
    def test_applies_square_root(self):
        node = Sqrt(name="sqrt", columns=["a"])
        plan = _plan({"a": [4.0, 9.0]})

        result, _ = node.forward(plan)
        collected = result.handle.collect()

        assert collected["a"].to_list() == [2.0, 3.0]

class TestPower:
    def test_raises_to_given_exponent(self):
        node = Power(name="power", columns=["a"], exponent=2.0)
        plan = _plan({"a": [2.0, 3.0]})

        result, _ = node.forward(plan)
        collected = result.handle.collect()

        assert collected["a"].to_list() == [4.0, 9.0]

class TestFillForward:
    def test_fills_nulls_from_previous_value(self):
        node = FillForward(name="ffill", columns=["a"])
        plan = _plan({"a": [1, None, None, 4]})

        result, _ = node.forward(plan)
        collected = result.handle.collect()

        assert collected["a"].to_list() == [1, 1, 1, 4]

class TestFillBackward:
    def test_fills_nulls_from_next_value(self):
        node = FillBackward(name="bfill", columns=["a"])
        plan = _plan({"a": [1, None, None, 4]})

        result, _ = node.forward(plan)
        collected = result.handle.collect()

        assert collected["a"].to_list() == [1, 4, 4, 4]

class TestStrCase:
    def test_uppercases_text(self):
        node = StrCase(name="case", columns=["a"], case="upper")
        plan = _plan({"a": ["hi there"]})

        result, _ = node.forward(plan)
        collected = result.handle.collect()

        assert collected["a"].to_list() == ["HI THERE"]

    def test_rejects_unknown_case(self):
        with pytest.raises(ValueError):
            StrCase(name="case", columns=["a"], case="bogus")

class TestStrStrip:
    def test_strips_surrounding_whitespace(self):
        node = StrStrip(name="strip", columns=["a"])
        plan = _plan({"a": ["  hi  "]})

        result, _ = node.forward(plan)
        collected = result.handle.collect()

        assert collected["a"].to_list() == ["hi"]

class TestStrReplace:
    def test_replaces_all_matches(self):
        node = StrReplace(name="replace", columns=["a"], pattern="o", value="0")
        plan = _plan({"a": ["foo bar"]})

        result, _ = node.forward(plan)
        collected = result.handle.collect()

        assert collected["a"].to_list() == ["f00 bar"]

class TestRank:
    def test_ranks_values_ascending(self):
        node = Rank(name="rank", columns=["a"], method="ordinal")
        plan = _plan({"a": [30, 10, 20]})

        result, _ = node.forward(plan)
        collected = result.handle.collect()

        assert collected["a"].to_list() == [3.0, 1.0, 2.0]

    def test_rejects_unknown_method(self):
        with pytest.raises(ValueError):
            Rank(name="rank", columns=["a"], method="bogus")

class TestCumulativeSum:
    def test_accumulates_values(self):
        node = CumulativeSum(name="cumsum", columns=["a"])
        plan = _plan({"a": [1, 2, 3]})

        result, _ = node.forward(plan)
        collected = result.handle.collect()

        assert collected["a"].to_list() == [1, 3, 6]

class TestShift:
    def test_shifts_values_down_by_n(self):
        node = Shift(name="shift", columns=["a"], n=1)
        plan = _plan({"a": [1, 2, 3]})

        result, _ = node.forward(plan)
        collected = result.handle.collect()

        assert collected["a"].to_list() == [None, 1, 2]

class TestAddRowIndex:
    def test_adds_incrementing_index_column(self):
        node = AddRowIndex(name="idx")
        plan = _plan({"a": [10, 20, 30]})

        result, _ = node.forward(plan)
        collected = result.handle.collect()

        assert collected["index"].to_list() == [0, 1, 2]

    def test_respects_custom_name_and_offset(self):
        node = AddRowIndex(name="idx", index_name="row_id", offset=5)
        plan = _plan({"a": [10, 20]})

        result, _ = node.forward(plan)
        collected = result.handle.collect()

        assert collected["row_id"].to_list() == [5, 6]

class TestBin:
    def test_buckets_values_with_labels(self):
        node = Bin(name="bin", column="a", breaks=[10.0, 20.0], labels=["low", "mid", "high"])
        plan = _plan({"a": [1, 15, 25]})

        result, _ = node.forward(plan)
        collected = result.handle.collect()

        assert collected["a_bin"].to_list() == ["low", "mid", "high"]

    def test_rejects_mismatched_label_count(self):
        with pytest.raises(ValueError):
            Bin(name="bin", column="a", breaks=[10.0], labels=["low"])

class TestExtractRegex:
    def test_extracts_capture_group(self):
        node = ExtractRegex(name="extract", column="s", pattern=r"id-(\d+)")
        plan = _plan({"s": ["id-123", "no-match"]})

        result, _ = node.forward(plan)
        collected = result.handle.collect()

        assert collected["s_extracted"].to_list() == ["123", None]

class TestParseDate:
    def test_parses_string_into_date(self):
        node = ParseDate(name="parse", columns=["d"], format="%Y-%m-%d")
        plan = _plan({"d": ["2024-01-15"]})

        result, _ = node.forward(plan)
        collected = result.handle.collect()

        assert collected["d"].dtype == pl.Date

class TestDatePart:
    def test_extracts_year_from_date(self):
        node = DatePart(name="part", column="d", part="year")
        plan = Plan(handle=pl.LazyFrame({"d": ["2024-01-15"]}).with_columns(pl.col("d").str.to_date()))

        result, _ = node.forward(plan)
        collected = result.handle.collect()

        assert collected["d_year"].to_list() == [2024]

    def test_rejects_unknown_part(self):
        with pytest.raises(ValueError):
            DatePart(name="part", column="d", part="bogus")

class TestUnpivot:
    def test_melts_value_columns_into_rows(self):
        node = Unpivot(name="unpivot", index=["id"])
        plan = _plan({"id": [1, 2], "x": [10, 20], "y": [100, 200]})

        result, _ = node.forward(plan)
        collected = result.handle.collect().sort(["variable", "id"])

        assert collected["variable"].to_list() == ["x", "x", "y", "y"]
        assert collected["value"].to_list() == [10, 20, 100, 200]

class TestMapValues:
    def test_replaces_mapped_values(self):
        node = MapValues(name="map", column="a", mapping={"x": "X", "y": "Y"})
        plan = _plan({"a": ["x", "y", "z"]})

        result, _ = node.forward(plan)
        collected = result.handle.collect()

        assert collected["a"].to_list() == ["X", "Y", "z"]

    def test_uses_default_for_unmapped_values(self):
        node = MapValues(name="map", column="a", mapping={"x": "X"}, default="OTHER")
        plan = _plan({"a": ["x", "z"]})

        result, _ = node.forward(plan)
        collected = result.handle.collect()

        assert collected["a"].to_list() == ["X", "OTHER"]

    def test_rejects_empty_mapping(self):
        with pytest.raises(ValueError):
            MapValues(name="map", column="a", mapping={})