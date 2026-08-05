def test_pulse_board_exports_deterministic_summary(tmp_path):
    from app.pulse_board import add_pulse, complete_pulse, list_pulses, summarize

    store = tmp_path / "pulses.json"
    first = add_pulse(store, "Ship a review packet")
    add_pulse(store, "Wait for human review")
    complete_pulse(store, first["id"])
    before = list_pulses(store)
    assert summarize(store) == {"total": 2, "completed": 1, "pending": 1}
    assert list_pulses(store) == before
