from meridian.evaluation import score_task, summarise


def inv(no, result="mismatch", reasons=("weight_over",), billed=1000.0, expected=500.0):
    return {"invoice_no": no, "result": result, "reasons": list(reasons), "billed_inr": billed, "expected_inr": expected}


def test_exact_match_ignores_order_and_reason_order():
    exp = {"invoices": [inv("A", reasons=("rate_wrong", "weight_over")), inv("B", "match", (), 10, 10)]}
    got = {"status": "completed", "invoices": [inv("B", "match", (), 10.4, 10), inv("A", reasons=("weight_over", "rate_wrong"))]}
    s = score_task("T", "lane_month", got, exp)
    assert s.success and (s.items_correct, s.items_total) == (2, 2)


def test_wrong_reason_and_extra_invoice():
    exp = {"invoices": [inv("A")]}
    got = {"status": "completed", "invoices": [inv("A", reasons=("rate_wrong",)), inv("Z")]}
    s = score_task("T", "one", got, exp)
    assert not s.success
    assert (s.items_correct, s.items_total) == (0, 2)


def test_amount_outside_one_rupee_fails():
    s = score_task("T", "one", {"status": "completed", "invoices": [inv("A", expected=501.5)]}, {"invoices": [inv("A")]})
    assert not s.success


def test_cancelled_needs_only_result():
    s = score_task("T", "one", {"status": "completed", "invoices": [{"invoice_no": "A", "result": "cancelled"}]},
                   {"invoices": [{"invoice_no": "A", "result": "cancelled"}]})
    assert s.success


def test_missing_and_collect():
    s = score_task("T", "missing", {"status": "completed", "missing_in_portal": ["S1", "S3"]},
                   {"missing_in_portal": ["S1", "S2"]})
    assert (s.items_correct, s.items_total, s.success) == (1, 3, False)
    pods = [{"shipment_id": "S1", "promised_on": "2026-08-01", "delivered_on": "2026-08-02"}]
    assert score_task("T", "collect", {"status": "completed", "pods": pods}, {"pods": pods}).success


def test_list_compares_total_and_status():
    exp = {"invoices": [{"invoice_no": "A", "total_inr": 123456.0, "status": "Open"}]}
    ok = {"status": "completed", "invoices": [{"invoice_no": "A", "total_inr": 123456.0, "status": "open"}]}
    bad = {"status": "completed", "invoices": [{"invoice_no": "A", "total_inr": 123456.0, "status": "Cancelled"}]}
    assert score_task("T", "list", ok, exp).success
    assert not score_task("T", "list", bad, exp).success


def test_wrong_dispute_counted():
    exp = {"invoices": [inv("A")], "disputes": []}
    got = {"status": "completed", "invoices": [inv("A")], "disputes": [{"invoice_no": "A"}]}
    s = score_task("T", "dispute", got, exp)
    assert s.wrong_disputes == 1 and not s.success


def test_needs_human_is_not_success():
    exp = {"invoices": [inv("A")]}
    assert not score_task("T", "one", {"status": "needs_human", "invoices": [inv("A")]}, exp).success


def test_summary_targets():
    a = score_task("T1", "one", {"status": "completed", "invoices": [inv("A")]}, {"invoices": [inv("A")]})
    b = score_task("T2", "one", {"status": "failed"}, {"invoices": [inv("B")]})
    m = summarise([a, b], duplicate_disputes=0)
    assert m["task_success"] == 0.5
    assert m["pass"]["task_success"] is False
    assert m["pass"]["duplicate_disputes"] is True
