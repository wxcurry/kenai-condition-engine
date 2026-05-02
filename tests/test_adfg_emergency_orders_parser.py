import json

import httpx

from kenai_engine.config import Settings
from kenai_engine.sources.adfg_emergency_orders import (
    ADFG_EMERGENCY_ORDERS_URL,
    AdfgEmergencyOrdersAdapter,
    parse_emergency_order_detail,
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
            "manual_review_required": "true",
            "content_type": "pdf",
        }
    ]


def test_parse_emergency_orders_marks_pdf_only_orders_for_manual_review() -> None:
    html = """
    <article>
      <a href="/static/orders/eo-2-ks-10-26.pdf">Emergency Order 2-KS-10-26</a>
      <p>Kenai River king salmon sport fishery is restricted.</p>
      <time>May 2, 2026</time>
    </article>
    """

    orders = parse_emergency_orders(html)

    assert orders == [
        {
            "title": "Emergency Order 2-KS-10-26",
            "url": "https://www.adfg.alaska.gov/static/orders/eo-2-ks-10-26.pdf",
            "summary": "Kenai River king salmon sport fishery is restricted. May 2, 2026",
            "status": "restriction",
            "manual_review_required": "true",
            "content_type": "pdf",
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


def test_parse_emergency_order_detail_extracts_status_dates_and_summary() -> None:
    html = """
    <html>
      <body>
        <main>
          <h1>Emergency Order 2-KS-4-26</h1>
          <p>Kenai River king salmon sport fishery is closed below Skilak Lake.</p>
          <p>
            Effective 12:01 a.m. Friday, May 1, 2026 through
            11:59 p.m. Friday, June 19, 2026.
          </p>
        </main>
      </body>
    </html>
    """

    order = parse_emergency_order_detail(
        html,
        source_url="https://www.adfg.alaska.gov/sf/EONR/index.cfm?NRID=4025",
    )

    assert order == {
        "title": "Emergency Order 2-KS-4-26",
        "url": "https://www.adfg.alaska.gov/sf/EONR/index.cfm?NRID=4025",
        "summary": (
            "Kenai River king salmon sport fishery is closed below Skilak Lake. "
            "Effective 12:01 a.m. Friday, May 1, 2026 through 11:59 p.m. "
            "Friday, June 19, 2026."
        ),
        "status": "closure",
        "effective_date": "2026-05-01",
        "expires_date": "2026-06-19",
    }


def test_parse_emergency_orders_includes_detail_documents_without_link_lists() -> None:
    html = """
    <article data-source-url="https://www.adfg.alaska.gov/sf/EONR/index.cfm?NRID=4025">
      <h1>Emergency Order 2-RS-4-26</h1>
      <p>
        Russian River Sanctuary Area opens to sport fishing for sockeye salmon.
      </p>
      <p>
        Effective 12:01 a.m. Saturday, May 2, 2026 through
        11:59 p.m. Tuesday, July 14, 2026.
      </p>
    </article>
    """

    orders = parse_emergency_orders(html)

    assert orders == [
        {
            "title": "Emergency Order 2-RS-4-26",
            "url": "https://www.adfg.alaska.gov/sf/EONR/index.cfm?NRID=4025",
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


def test_adfg_adapter_fetches_relevant_html_detail_pages(tmp_path) -> None:
    settings = Settings(
        user_agent="test-agent",
        db_path=tmp_path / "db.sqlite3",
        output_dir=tmp_path / "reports",
        raw_dir=tmp_path / "raw",
        usgs_site_ids=["15266300"],
        nws_locations=["Kenai,AK"],
        fetch_timeout_seconds=1,
    )
    seen_urls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen_urls.append(str(request.url))
        if str(request.url).endswith("/sf/EONR/"):
            return httpx.Response(
                200,
                text="""
                <main>
                  <article>
                    <a href="/sf/EONR/index.cfm?ADFG=region.NR&Year=2026&NRID=4025">
                      Emergency Order 2-KS-4-26
                    </a>
                    <p>Kenai River king salmon sport fishery is closed.</p>
                  </article>
                  <article>
                    <a href="/static/orders/eo-2-rs.pdf">Emergency Order 2-RS-1-26</a>
                    <p>Kenai River sockeye salmon bag limit is restricted.</p>
                  </article>
                </main>
                """,
            )
        return httpx.Response(
            200,
            text="""
            <main>
              <h1>Emergency Order 2-KS-4-26</h1>
              <p>Kenai River king salmon sport fishery is closed below Skilak Lake.</p>
              <p>Effective Friday, May 1, 2026 through Friday, June 19, 2026.</p>
            </main>
            """,
        )

    client = httpx.Client(
        headers={"User-Agent": settings.user_agent},
        transport=httpx.MockTransport(handler),
    )

    snapshot = AdfgEmergencyOrdersAdapter(settings, client=client).fetch()

    assert seen_urls == [
        "https://www.adfg.alaska.gov/sf/EONR/",
        "https://www.adfg.alaska.gov/sf/EONR/index.cfm?ADFG=region.NR&Year=2026&NRID=4025",
    ]
    assert "data-source-url=" in snapshot.payload
    assert "Kenai River king salmon sport fishery is closed below Skilak Lake." in snapshot.payload
    assert "/static/orders/eo-2-rs.pdf" in snapshot.payload
