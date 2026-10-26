"""Alembic roundtrip test for 0040_escalation_recommendations_ack in disposable PostgreSQL."""
from uuid import uuid4
import pytest
from sqlalchemy import create_engine, inspect, text
from test_e2e_update_migration import cli


def test_recommendation_migration_roundtrip_and_guards(postgres_engine):
    name = 'rec_migration_' + uuid4().hex
    with postgres_engine.connect().execution_options(isolation_level='AUTOCOMMIT') as connection:
        connection.execute(text('CREATE DATABASE ' + name))
    engine = create_engine(postgres_engine.url.set(database=name))
    try:
        cli(engine.url, 'upgrade', '0039_device_templates')
        cli(engine.url, 'upgrade', '0040_escalation_recommend_ack')
        with engine.begin() as connection:
            tables = inspect(connection).get_table_names()
            assert 'position_escalation_destinations' in tables
            assert 'ticket_escalation_acks' in tables
            assert 'internal_ticket_escalation_acks' in tables
            pos_cols = {c['name'] for c in inspect(connection).get_columns('positions')}
            assert 'escalation_mode' in pos_cols
            assert 'general_escalation_time_minutes' in pos_cols
            ticket_cols = {c['name'] for c in inspect(connection).get_columns('tickets')}
            assert 'initial_position_id' in ticket_cols
            assert 'closed_seconds' in ticket_cols
            esc_cols = {c['name'] for c in inspect(connection).get_columns('ticket_escalations')}
            assert 'position_id' in esc_cols

        # Test downgrade to 0039
        cli(engine.url, 'downgrade', '0039_device_templates')
        with engine.begin() as connection:
            tables_after = inspect(connection).get_table_names()
            assert 'position_escalation_destinations' not in tables_after
            assert 'ticket_escalation_acks' not in tables_after

        # Re-upgrade to 0040
        cli(engine.url, 'upgrade', '0040_escalation_recommend_ack')

        # Insert data to verify downgrade guard
        with engine.begin() as connection:
            connection.execute(text("INSERT INTO departments(name) VALUES ('Dept')"))
            connection.execute(text("INSERT INTO positions(name, department_id) VALUES ('P1', 1), ('P2', 1)"))
            connection.execute(text("INSERT INTO position_escalation_destinations(position_id, target_position_id) VALUES (1, 2)"))

        with pytest.raises(AssertionError, match='Downgrade bloqueado'):
            cli(engine.url, 'downgrade', '0039_device_templates')
    finally:
        engine.dispose()
        with postgres_engine.connect().execution_options(isolation_level='AUTOCOMMIT') as connection:
            connection.execute(text('DROP DATABASE ' + name))
