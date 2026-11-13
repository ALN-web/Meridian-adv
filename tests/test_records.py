from meridian.records import delivered_in, load_shipments


def test_missing_tasks_use_delivery_month(tmp_path):
    csv = tmp_path / "s.csv"
    csv.write_text(
        "shipment_id,booked_on,lane,actual_weight_kg,delivered_on,meridian_ref\n"
        "SHP-1,2026-09-26,PUN-BLR,100.0,2026-10-01,MF-1\n"
        "SHP-2,2026-09-10,PUN-BLR,200.0,2026-09-12,MF-2\n",
        encoding="utf-8",
    )
    s = load_shipments(csv)
    assert [x.shipment_id for x in delivered_in(s, "PUN-BLR", "2026-10")] == ["SHP-1"]
    assert [x.shipment_id for x in delivered_in(s, "PUN-BLR", "2026-09")] == ["SHP-2"]
