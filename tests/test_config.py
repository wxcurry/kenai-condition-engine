from kenai_engine.config import Settings


def test_nws_locations_preserve_city_state_commas(monkeypatch) -> None:
    monkeypatch.setenv("NWS_LOCATIONS", "Kenai,AK;Soldotna,AK")

    settings = Settings.from_env()

    assert settings.nws_locations == ["Kenai,AK", "Soldotna,AK"]


def test_usgs_site_ids_remain_comma_separated(monkeypatch) -> None:
    monkeypatch.setenv("USGS_SITE_IDS", "15266300,15266110")

    settings = Settings.from_env()

    assert settings.usgs_site_ids == ["15266300", "15266110"]


def test_default_usgs_site_ids_include_validated_kenai_gages(monkeypatch) -> None:
    monkeypatch.delenv("USGS_SITE_IDS", raising=False)

    settings = Settings.from_env()

    assert settings.usgs_site_ids == ["15258000", "15266010", "15266110", "15266300"]


def test_empty_usgs_site_ids_are_rejected(monkeypatch) -> None:
    monkeypatch.setenv("USGS_SITE_IDS", " , ")

    try:
        Settings.from_env()
    except ValueError as error:
        assert str(error) == "USGS_SITE_IDS must include at least one site id."
    else:
        raise AssertionError("Expected empty USGS_SITE_IDS to be rejected.")


def test_non_positive_fetch_timeout_is_rejected(monkeypatch) -> None:
    monkeypatch.setenv("FETCH_TIMEOUT_SECONDS", "0")

    try:
        Settings.from_env()
    except ValueError as error:
        assert str(error) == "FETCH_TIMEOUT_SECONDS must be greater than 0."
    else:
        raise AssertionError("Expected non-positive FETCH_TIMEOUT_SECONDS to be rejected.")
