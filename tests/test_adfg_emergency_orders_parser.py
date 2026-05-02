import json

import httpx

from kenai_engine.config import Settings
from kenai_engine.sources.adfg_emergency_orders import (
    ADFG_EMERGENCY_ORDERS_URL,
    AdfgEmergencyOrdersAdapter,
    parse_emergency_orders,
)


def test_parse_emergency_orders_extracts_matching_links() -> None:
    html = """
    <html>
      <body>
        <a href="/orders/1">Emergency Order 2-KS-1</a>
        <a href="/news">News Release</a>
      </body>
    </html>
    """

    orders = parse_emergency_orders(html)

    assert orders == [
        {
            "title": "Emergency Order 2-KS-1",
            "url": "https://www.adfg.alaska.gov/orders/1",
        }
    ]


def test_parse_emergency_orders_extracts_cards_and_detects_closure_keywords() -> None:
    html = """
    <section class="card">
      <h3><a href="?adfg=some.order">Emergency Order 2-KS-4-26</a></h3>
      <p>Kenai River king salmon sport fishery is closed below Skilak Lake.</p>
      <span>Effective Saturday, May 2, 2026</span>
    </section>
    <section>
      <a href="/news">Advisory announcement</a>
    </section>
    """

    orders = parse_emergency_orders(
        html,
        base_url="https://www.adfg.alaska.gov/sf/EONR/index.cfm",
    )

    assert orders == [
        {
            "title": "Emergency Order 2-KS-4-26",
            "url": "https://www.adfg.alaska.gov/sf/EONR/index.cfm?adfg=some.order",
            "summary": (
                "Kenai River king salmon sport fishery is closed below Skilak Lake. "
                "Effective Saturday, May 2, 2026"
            ),
            "status": "closure",
            "effective_date": "2026-05-02",
        }
    ]


def test_parse_emergency_orders_extracts_table_rows_and_detects_restrictions() -> None:
    html = """
    <table>
      <tr>
        <th>Emergency Order</th>
        <th>Area</th>
        <th>Action</th>
      </tr>
      <tr>
        <td><a href="https://www.adfg.alaska.gov/static/orders/eo-2-rs.pdf">EO 2-RS-1-26</a></td>
        <td>Kenai River</td>
        <td>Restricts bait and harvest for sockeye salmon.</td>
      </tr>
    </table>
    """

    orders = parse_emergency_orders(html)

    assert orders == [
        {
            "title": "EO 2-RS-1-26",
            "url": "https://www.adfg.alaska.gov/static/orders/eo-2-rs.pdf",
            "summary": "Kenai River Restricts bait and harvest for sockeye salmon.",
            "status": "restriction",
        }
    ]


def test_parse_emergency_orders_filters_to_kenai_relevant_orders_by_default() -> None:
    html = """
    <main>
      <div class="views-row">
        <h3>
          <a href="/sf/EONR/index.cfm?ADFG=region.NR&Year=2026&NRID=4012">
            Emergency Order 2-KS-7-26
          </a>
        </h3>
        <p>
          Kenai River and Kasilof River king salmon sport fisheries are restricted to
          catch-and-release fishing.
        </p>
      </div>
      <div class="views-row">
        <h3>
          <a href="/sf/EONR/index.cfm?ADFG=region.NR&Year=2026&NRID=3999">
            Emergency Order 2-SW-1-26
          </a>
        </h3>
        <p>All flowing waters of Southeast Alaska are closed to sport fishing.</p>
      </div>
      <div class="views-row">
        <h3>
          <a href="/sf/EONR/index.cfm?ADFG=region.NR&Year=2026&NRID=4000">
            Emergency Order 2-STATE-1-26
          </a>
        </h3>
        <p>Statewide king salmon regulations are summarized for all anglers.</p>
      </div>
    </main>
    """

    orders = parse_emergency_orders(html)

    assert orders == [
        {
            "title": "Emergency Order 2-KS-7-26",
            "url": "https://www.adfg.alaska.gov/sf/EONR/index.cfm?ADFG=region.NR&Year=2026&NRID=4012",
            "summary": (
                "Kenai River and Kasilof River king salmon sport fisheries are restricted to "
                "catch-and-release fishing."
            ),
            "status": "restriction",
        }
    ]


def test_parse_emergency_orders_extracts_dates_from_actualish_eonr_card_text() -> None:
    html = """
    <article class="node node-news-release">
      <h2>
        <a href="/sf/EONR/index.cfm?ADFG=region.NR&Year=2026&NRID=4025">
          Emergency Order 2-RS-4-26
        </a>
      </h2>
      <div class="field-content">
        Russian River Sanctuary Area opens to sport fishing for sockeye salmon.
        Effective 12:01 a.m. Saturday, May 2, 2026 through 11:59 p.m. Tuesday, July 14, 2026.
      </div>
    </article>
    """

    orders = parse_emergency_orders(html)

    assert orders == [
        {
            "title": "Emergency Order 2-RS-4-26",
            "url": "https://www.adfg.alaska.gov/sf/EONR/index.cfm?ADFG=region.NR&Year=2026&NRID=4025",
            "summary": (
                "Russian River Sanctuary Area opens to sport fishing for sockeye salmon. "
                "Effective 12:01 a.m. Saturday, May 2, 2026 through 11:59 p.m. "
                "Tuesday, July 14, 2026."
            ),
            "status": "open",
            "effective_date": "2026-05-02",
            "expires_date": "2026-07-14",
        }
    ]


def test_parse_emergency_orders_allows_callers_to_disable_relevance_filter() -> None:
    html = """
    <div>
      <a href="/orders/statewide">Emergency Order 2-STATE-1-26</a>
      <p>Statewide king salmon restrictions apply in marine waters.</p>
    </div>
    """

    orders = parse_emergency_orders(html, is_relevant=lambda _order_text: True)

    assert orders == [
        {
            "title": "Emergency Order 2-STATE-1-26",
            "url": "https://www.adfg.alaska.gov/orders/statewide",
            "summary": "Statewide king salmon restrictions apply in marine waters.",
            "status": "restriction",
        }
    ]


def test_adfg_adapter_fetches_configured_url(tmp_path) -> None:
    settings = Settings(
        user_agent="test-agent",
        db_path=tmp_path / "db.sqlite3",
        output_dir=tmp_path / "reports",
        raw_dir=tmp_path / "raw",
        usgs_site_ids=["15266300"],
        nws_locations=["Kenai,AK"],
        fetch_timeout_seconds=1,
    )
    seen_requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen_requests.append(request)
        return httpx.Response(200, text="<html>orders</html>")

    client = httpx.Client(
        headers={"User-Agent": settings.user_agent},
        transport=httpx.MockTransport(handler),
    )

    snapshot = AdfgEmergencyOrdersAdapter(settings, client=client).fetch()

    assert snapshot.source == "adfg_emergency_orders"
    assert snapshot.payload == "<html>orders</html>"
    assert seen_requests
    assert str(seen_requests[0].url) == ADFG_EMERGENCY_ORDERS_URL
    assert seen_requests[0].headers["User-Agent"] == "test-agent"


def test_adfg_adapter_can_fetch_custom_url(tmp_path) -> None:
    settings = Settings(
        user_agent="test-agent",
        db_path=tmp_path / "db.sqlite3",
        output_dir=tmp_path / "reports",
        raw_dir=tmp_path / "raw",
        usgs_site_ids=["15266300"],
        nws_locations=["Kenai,AK"],
        fetch_timeout_seconds=1,
    )

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"url": str(request.url)})

    client = httpx.Client(transport=httpx.MockTransport(handler))

    snapshot = AdfgEmergencyOrdersAdapter(
        settings,
        client=client,
        url="https://www.adfg.alaska.gov/sf/EONR/",
    ).fetch()

    assert json.loads(snapshot.payload) == {"url": "https://www.adfg.alaska.gov/sf/EONR/"}
