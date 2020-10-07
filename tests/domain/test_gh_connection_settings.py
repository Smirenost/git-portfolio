"""Test cases for the Github connection settings model."""
import git_portfolio.domain.gh_connection_settings as cs


def test_gh_connection_settings_model_init() -> None:
    """Verify model initialization."""
    connection_settings = cs.GhConnectionSettings("mytoken", "myhost.com")

    assert connection_settings.access_token == "mytoken"
    assert connection_settings.hostname == "myhost.com"
