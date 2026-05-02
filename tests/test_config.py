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
