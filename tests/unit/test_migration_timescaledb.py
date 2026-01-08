"""Tests for TimescaleDB migration (migration 32)."""
from unittest.mock import MagicMock, patch
from pathlib import Path
import importlib.util

# Load the migration module dynamically
migration_path = Path(__file__).parent.parent.parent / "alembic" / "versions" / "32_convert_to_timescaledb.py"
spec = importlib.util.spec_from_file_location("migration_32", migration_path)
migration_module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(migration_module)


class TestTimescaleDBMigration:
    """Tests for TimescaleDB migration behavior."""

    def test_is_timescaledb_available_sqlite(self):
        """Test that TimescaleDB is detected as unavailable for SQLite."""
        # Create a mock bind with SQLite dialect
        mock_bind = MagicMock()
        mock_bind.dialect.name = "sqlite"
        
        with patch("alembic.op.get_bind", return_value=mock_bind):
            result = migration_module._is_timescaledb_available()
            assert result is False

    def test_is_timescaledb_available_postgresql_without_extension(self):
        """Test that TimescaleDB is detected as unavailable for PostgreSQL without extension."""
        # Create a mock bind with PostgreSQL dialect
        mock_bind = MagicMock()
        mock_bind.dialect.name = "postgresql"
        
        # Mock the execute result to return 0 (no extension)
        mock_result = MagicMock()
        mock_result.scalar.return_value = 0
        mock_bind.execute.return_value = mock_result
        
        with patch("alembic.op.get_bind", return_value=mock_bind):
            result = migration_module._is_timescaledb_available()
            assert result is False

    def test_is_timescaledb_available_postgresql_with_extension(self):
        """Test that TimescaleDB is detected as available for PostgreSQL with extension."""
        # Create a mock bind with PostgreSQL dialect
        mock_bind = MagicMock()
        mock_bind.dialect.name = "postgresql"
        
        # Mock the execute result to return 1 (extension installed)
        mock_result = MagicMock()
        mock_result.scalar.return_value = 1
        mock_bind.execute.return_value = mock_result
        
        with patch("alembic.op.get_bind", return_value=mock_bind):
            result = migration_module._is_timescaledb_available()
            assert result is True

    def test_is_timescaledb_available_postgresql_with_exception(self):
        """Test that TimescaleDB check handles exceptions gracefully."""
        from sqlalchemy.exc import OperationalError
        
        # Create a mock bind with PostgreSQL dialect
        mock_bind = MagicMock()
        mock_bind.dialect.name = "postgresql"
        
        # Mock execute to raise a SQLAlchemy exception
        mock_bind.execute.side_effect = OperationalError("Database error", None, None)
        
        with patch("alembic.op.get_bind", return_value=mock_bind):
            result = migration_module._is_timescaledb_available()
            assert result is False

    def test_upgrade_skips_for_sqlite(self):
        """Test that upgrade is a no-op for SQLite."""
        mock_bind = MagicMock()
        mock_bind.dialect.name = "sqlite"
        
        with patch("alembic.op.get_bind", return_value=mock_bind):
            # Should not raise any exceptions
            migration_module.upgrade()
            
            # Verify no SQL was executed
            mock_bind.execute.assert_not_called()

    def test_downgrade_skips_for_sqlite(self):
        """Test that downgrade is a no-op for SQLite."""
        mock_bind = MagicMock()
        mock_bind.dialect.name = "sqlite"
        
        with patch("alembic.op.get_bind", return_value=mock_bind):
            # Should not raise any exceptions
            migration_module.downgrade()
            
            # Verify no SQL was executed
            mock_bind.execute.assert_not_called()

    def test_upgrade_executes_for_postgresql_with_timescaledb(self):
        """Test that upgrade executes TimescaleDB commands for PostgreSQL with extension."""
        mock_bind = MagicMock()
        mock_bind.dialect.name = "postgresql"
        
        # Mock the extension check to return 1 (extension installed)
        mock_result = MagicMock()
        mock_result.scalar.return_value = 1
        
        # Track execute calls
        execute_calls = []
        
        def mock_execute(sql):
            execute_calls.append(sql)
            return mock_result
        
        mock_bind.execute = mock_execute
        
        with patch("alembic.op.get_bind", return_value=mock_bind):
            migration_module.upgrade()
            
            # Verify TimescaleDB commands were executed
            assert len(execute_calls) > 1
            # Check that key commands are present
            sql_texts = [str(call) for call in execute_calls]
            assert any("create_hypertable" in sql for sql in sql_texts)
            assert any("add_retention_policy" in sql for sql in sql_texts)
            assert any("health_checks_hourly" in sql for sql in sql_texts)

    def test_downgrade_executes_for_postgresql_with_timescaledb(self):
        """Test that downgrade executes cleanup commands for PostgreSQL with extension."""
        mock_bind = MagicMock()
        mock_bind.dialect.name = "postgresql"
        
        # Mock the extension check to return 1 (extension installed)
        mock_result = MagicMock()
        mock_result.scalar.return_value = 1
        
        # Track execute calls
        execute_calls = []
        
        def mock_execute(sql):
            execute_calls.append(sql)
            return mock_result
        
        mock_bind.execute = mock_execute
        
        with patch("alembic.op.get_bind", return_value=mock_bind):
            # Execute downgrade; any unexpected exceptions should fail the test
            migration_module.downgrade()
            
            # Verify some cleanup commands were attempted
            assert len(execute_calls) > 0

    def test_upgrade_skips_for_postgresql_without_timescaledb(self):
        """Test that upgrade is a no-op for PostgreSQL without TimescaleDB."""
        mock_bind = MagicMock()
        mock_bind.dialect.name = "postgresql"
        
        # Mock the execute result to return 0 (no extension)
        mock_result = MagicMock()
        mock_result.scalar.return_value = 0
        mock_bind.execute.return_value = mock_result
        
        # Track if execute was called after the extension check
        execute_count = 0
        original_execute = mock_bind.execute
        
        def counting_execute(sql):
            nonlocal execute_count
            execute_count += 1
            return original_execute(sql)
        
        mock_bind.execute = counting_execute
        
        with patch("alembic.op.get_bind", return_value=mock_bind):
            # Should not raise any exceptions
            migration_module.upgrade()
            
            # Verify only the extension check was executed (1 call)
            assert execute_count == 1

    def test_downgrade_skips_for_postgresql_without_timescaledb(self):
        """Test that downgrade is a no-op for PostgreSQL without TimescaleDB."""
        mock_bind = MagicMock()
        mock_bind.dialect.name = "postgresql"
        
        # Mock the execute result to return 0 (no extension)
        mock_result = MagicMock()
        mock_result.scalar.return_value = 0
        mock_bind.execute.return_value = mock_result
        
        # Track if execute was called after the extension check
        execute_count = 0
        original_execute = mock_bind.execute
        
        def counting_execute(sql):
            nonlocal execute_count
            execute_count += 1
            return original_execute(sql)
        
        mock_bind.execute = counting_execute
        
        with patch("alembic.op.get_bind", return_value=mock_bind):
            # Should not raise any exceptions
            migration_module.downgrade()
            
            # Verify only the extension check was executed (1 call)
            assert execute_count == 1
