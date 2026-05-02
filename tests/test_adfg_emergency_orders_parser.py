from kenai_engine.sources.adfg_emergency_orders import parse_emergency_orders


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

    assert orders == [{"title": "Emergency Order 2-KS-1", "url": "/orders/1"}]
