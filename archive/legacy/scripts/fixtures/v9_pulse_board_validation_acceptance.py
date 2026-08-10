import pytest


def test_pulse_board_validates_completion_and_persists(tmp_path):
    from app.pulse_board import add_pulse, complete_pulse, list_pulses

    store = tmp_path / "pulses.json"
    with pytest.raises(ValueError):
        add_pulse(store, "   ")
    first = add_pulse(store, "Write evidence")
    second = add_pulse(store, "Review evidence")
    completed = complete_pulse(store, first["id"])
    assert completed["completed"] is True
    assert list_pulses(store)[1] == second
    with pytest.raises(KeyError):
        complete_pulse(store, "missing")
    assert list_pulses(store)[0]["completed"] is True
