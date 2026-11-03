import pytest

from glareshield.model import Settings


@pytest.fixture(autouse=True)
def immediate_release(request):
    """Most tests check instant rule hand-over; the hold has its own tests."""
    if request.node.get_closest_marker('release_hold'):
        yield
        return
    field = Settings.model_fields['release_hold_s']
    default = field.default
    field.default = 0
    Settings.model_rebuild(force=True)
    try:
        yield
    finally:
        field.default = default
        Settings.model_rebuild(force=True)
