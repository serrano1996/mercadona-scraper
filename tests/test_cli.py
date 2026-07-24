import json
from unittest.mock import MagicMock

import pytest
import requests

from mercadona_scraper import cli
from mercadona_scraper.exceptions import MercadonaScraperError
from mercadona_scraper.models import ProductResult, ScraperResult, SearchMeta


def _fake_result() -> ScraperResult:
    return ScraperResult(
        search=SearchMeta(
            postal_code="28001",
            term="leche",
            warehouse="mad1",
            strategy_used="api",
            scraped_at="2026-07-24T10:00:00Z",
            total_results=1,
        ),
        products=[
            ProductResult(
                id="1",
                name="Leche entera",
                price=1.05,
                price_format="1.05 €/L",
                image_url="https://example.com/1.jpg",
                category="Lácteos",
            )
        ],
    )


def _mock_scraper_cls(run_return=None, run_side_effect=None) -> MagicMock:
    mock_cls = MagicMock()
    if run_side_effect is not None:
        mock_cls.return_value.run.side_effect = run_side_effect
    else:
        mock_cls.return_value.run.return_value = run_return or _fake_result()
    return mock_cls


# --------------------------------------------------------------------- #
# Happy path
# --------------------------------------------------------------------- #


def test_main_prints_json_to_stdout_when_no_output_given(monkeypatch, capsys):
    monkeypatch.setattr(
        "sys.argv", ["cli.py", "--postal-code", "28001", "--product", "leche"]
    )
    monkeypatch.setattr("mercadona_scraper.cli.MercadonaScraper", _mock_scraper_cls())

    cli.main()

    captured = capsys.readouterr()
    printed = json.loads(captured.out)
    assert printed == _fake_result().to_dict()


def test_main_writes_output_file_and_prints_confirmation_to_stderr(monkeypatch, capsys, tmp_path):
    output_file = tmp_path / "resultados.json"
    monkeypatch.setattr(
        "sys.argv",
        [
            "cli.py",
            "--postal-code",
            "28001",
            "--product",
            "leche",
            "--output",
            str(output_file),
        ],
    )
    monkeypatch.setattr("mercadona_scraper.cli.MercadonaScraper", _mock_scraper_cls())

    cli.main()

    captured = capsys.readouterr()
    assert "Resultados guardados" in captured.err
    assert str(output_file) in captured.err
    written = json.loads(output_file.read_text(encoding="utf-8"))
    assert written == _fake_result().to_dict()
    assert captured.out == ""


# --------------------------------------------------------------------- #
# Invalid postal code
# --------------------------------------------------------------------- #


@pytest.mark.parametrize("bad_pc", ["1234", "123456", "abcde", "280a1"])
def test_main_exits_on_invalid_postal_code(monkeypatch, capsys, bad_pc):
    monkeypatch.setattr(
        "sys.argv", ["cli.py", "--postal-code", bad_pc, "--product", "leche"]
    )
    monkeypatch.setattr("mercadona_scraper.cli.MercadonaScraper", _mock_scraper_cls())

    with pytest.raises(SystemExit) as exc_info:
        cli.main()

    assert exc_info.value.code == 2
    captured = capsys.readouterr()
    assert "5 dígitos" in captured.err


# --------------------------------------------------------------------- #
# scraper.run() errors
# --------------------------------------------------------------------- #


def test_main_exits_with_error_message_on_mercadona_scraper_error(monkeypatch):
    monkeypatch.setattr(
        "sys.argv", ["cli.py", "--postal-code", "28001", "--product", "leche"]
    )
    monkeypatch.setattr(
        "mercadona_scraper.cli.MercadonaScraper",
        _mock_scraper_cls(run_side_effect=MercadonaScraperError("almacén no encontrado")),
    )

    with pytest.raises(SystemExit) as exc_info:
        cli.main()

    assert str(exc_info.value) == "ERROR: almacén no encontrado"


def test_main_exits_with_error_message_on_request_exception(monkeypatch):
    monkeypatch.setattr(
        "sys.argv", ["cli.py", "--postal-code", "28001", "--product", "leche"]
    )
    monkeypatch.setattr(
        "mercadona_scraper.cli.MercadonaScraper",
        _mock_scraper_cls(run_side_effect=requests.RequestException("network down")),
    )

    with pytest.raises(SystemExit) as exc_info:
        cli.main()

    assert str(exc_info.value) == "ERROR: network down"


# --------------------------------------------------------------------- #
# OSError writing --output file
# --------------------------------------------------------------------- #


def test_main_exits_with_error_message_on_output_write_failure(monkeypatch):
    monkeypatch.setattr(
        "sys.argv",
        [
            "cli.py",
            "--postal-code",
            "28001",
            "--product",
            "leche",
            "--output",
            "/nonexistent-dir/out.json",
        ],
    )
    monkeypatch.setattr("mercadona_scraper.cli.MercadonaScraper", _mock_scraper_cls())

    def raise_oserror(*args, **kwargs):
        raise OSError("permission denied")

    monkeypatch.setattr("builtins.open", raise_oserror)

    with pytest.raises(SystemExit) as exc_info:
        cli.main()

    assert "ERROR: No se pudo escribir" in str(exc_info.value)


# --------------------------------------------------------------------- #
# --headless / --no-headless
# --------------------------------------------------------------------- #


def test_headless_defaults_to_true_when_flag_omitted(monkeypatch):
    monkeypatch.setattr(
        "sys.argv", ["cli.py", "--postal-code", "28001", "--product", "leche"]
    )
    mock_cls = _mock_scraper_cls()
    monkeypatch.setattr("mercadona_scraper.cli.MercadonaScraper", mock_cls)

    cli.main()

    assert mock_cls.call_args.kwargs["headless"] is True


def test_headless_flag_sets_true_explicitly(monkeypatch):
    monkeypatch.setattr(
        "sys.argv",
        ["cli.py", "--postal-code", "28001", "--product", "leche", "--headless"],
    )
    mock_cls = _mock_scraper_cls()
    monkeypatch.setattr("mercadona_scraper.cli.MercadonaScraper", mock_cls)

    cli.main()

    assert mock_cls.call_args.kwargs["headless"] is True


def test_no_headless_flag_sets_false(monkeypatch):
    monkeypatch.setattr(
        "sys.argv",
        ["cli.py", "--postal-code", "28001", "--product", "leche", "--no-headless"],
    )
    mock_cls = _mock_scraper_cls()
    monkeypatch.setattr("mercadona_scraper.cli.MercadonaScraper", mock_cls)

    cli.main()

    assert mock_cls.call_args.kwargs["headless"] is False


# --------------------------------------------------------------------- #
# --strategy is forwarded correctly
# --------------------------------------------------------------------- #


def test_strategy_argument_is_forwarded_to_scraper(monkeypatch):
    monkeypatch.setattr(
        "sys.argv",
        [
            "cli.py",
            "--postal-code",
            "28001",
            "--product",
            "leche",
            "--strategy",
            "playwright",
        ],
    )
    mock_cls = _mock_scraper_cls()
    monkeypatch.setattr("mercadona_scraper.cli.MercadonaScraper", mock_cls)

    cli.main()

    assert mock_cls.call_args.kwargs["strategy"] == "playwright"


def test_invalid_strategy_choice_exits(monkeypatch, capsys):
    monkeypatch.setattr(
        "sys.argv",
        [
            "cli.py",
            "--postal-code",
            "28001",
            "--product",
            "leche",
            "--strategy",
            "not-a-strategy",
        ],
    )
    monkeypatch.setattr("mercadona_scraper.cli.MercadonaScraper", _mock_scraper_cls())

    with pytest.raises(SystemExit) as exc_info:
        cli.main()

    assert exc_info.value.code == 2
