def test_pulse_board_creates_and_lists(tmp_path):
    from app.pulse_board import add_pulse, list_pulses

    store = tmp_path / "pulses.json"
    created = add_pulse(store, "Implement bounded heartbeat")
    assert created["title"] == "Implement bounded heartbeat"
    assert created["completed"] is False
    assert created["id"]
    assert created["created_at"]
    assert list_pulses(store) == [created]
