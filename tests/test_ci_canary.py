"""TEMPORARY — spec 009 T6: deliberately failing test to prove CI turns
red on a broken test. Reverted before merging."""


def test_ci_turns_red_on_a_failing_test() -> None:
    assert 1 + 1 == 3
