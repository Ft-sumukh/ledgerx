"""
Unit tests for application configuration.
"""

from __future__ import annotations

import pytest
from packages.configuration.settings import Environment, Settings


class TestSettings:
    def test_default_environment_is_development(self) -> None:
        s = Settings()
        assert s.environment == Environment.DEVELOPMENT

    def test_default_database_is_sqlite(self) -> None:
        s = Settings()
        assert s.is_sqlite

    def test_is_production_false_by_default(self) -> None:
        s = Settings()
        assert not s.is_production

    def test_environment_override(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("ORBIT_ENVIRONMENT", "production")
        s = Settings()
        assert s.environment == Environment.PRODUCTION
        assert s.is_production

    def test_database_url_override(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("ORBIT_DATABASE_URL", "postgresql+asyncpg://user:pass@localhost/db")
        s = Settings()
        assert "postgresql" in s.database_url
        assert not s.is_sqlite

    def test_is_test_environment(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("ORBIT_ENVIRONMENT", "test")
        s = Settings()
        assert s.is_test
