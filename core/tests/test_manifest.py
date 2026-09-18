from lmp_real.common import grid_product, stable_id


def test_grid_product_is_deterministic():
    grid = {"b": [2, 3], "a": [1]}
    assert list(grid_product(grid)) == [{"a": 1, "b": 2}, {"a": 1, "b": 3}]


def test_stable_id_ignores_mapping_order():
    assert stable_id("x", {"a": 1, "b": 2}) == stable_id("x", {"b": 2, "a": 1})
