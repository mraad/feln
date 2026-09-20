import importlib.util
import pathlib


def test_literals_compare_numbers_numerically() -> None:
    spec = importlib.util.spec_from_file_location(
        "humanize", pathlib.Path(__file__).parents[1] / "scripts" / "humanize.py"
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    src = "quantity is less than 4.0 and name is 'ROMA' within 1.5 kilometers"
    assert mod.literals(src) <= mod.literals("under 4 for 'ROMA', 1.50 km away")
    assert not mod.literals(src) <= mod.literals("under 5 for 'ROMA', 1.5 km away")
    assert not mod.literals(src) <= mod.literals("under 4 for 'Roma', 1.5 km away")
    assert mod.literals(src) <= mod.literals("isn't over 4 for 'ROMA', within 1.5.")
    assert mod.literals("status is not 'N'") <= mod.literals("status isn't 'N'.")
