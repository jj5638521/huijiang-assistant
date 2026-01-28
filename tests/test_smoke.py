from wage.settle_person import SettlementResult, settle_person


def test_settle_person_counts_rows():
    attendance_rows = [{"name": "A"}, {"name": "B"}]
    payment_rows = [{"name": "A"}]

    result = settle_person(attendance_rows, payment_rows)

    assert result == SettlementResult(attendance_rows=2, payment_rows=1)
