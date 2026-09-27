import sys


def test_package_imports() -> None:
    import hokm

    assert hokm.__name__ == "hokm"


def test_python_is_3_12_or_newer() -> None:
    assert sys.version_info >= (3, 12)
