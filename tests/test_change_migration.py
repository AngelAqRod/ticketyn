# Historical migration coverage is intentionally pinned; current HEAD is tested
# in test_deployment.py and test_mail_jobs.py.
from uuid import uuid4
from sqlalchemy import create_engine,text,inspect
from test_e2e_update_migration import cli

def test_change_upgrade_preserves_existing_data(postgres_engine):
 name='change_upgrade_'+uuid4().hex
 with postgres_engine.connect().execution_options(isolation_level='AUTOCOMMIT') as admin:admin.execute(text('CREATE DATABASE '+name))
 engine=create_engine(postgres_engine.url.set(database=name))
 try:
  cli(engine.url,'upgrade','0021_internal_tickets')
  with engine.begin() as db:
   for table in ('sectors','departments','internal_incident_types'):db.execute(text(f"INSERT INTO {table}(id,name) VALUES (1,'Histórico')"))
   db.execute(text("INSERT INTO internal_tickets(ticket_number,reference,title,description,sector_id,department_id,incident_type_id,start_at,status) VALUES (1,'INT-0000001','Conservar','Descripción',1,1,1,'2026-01-01T12:00:00Z','OPEN')"))
   before=db.scalar(text('SELECT to_jsonb(t) FROM internal_tickets t'))
  cli(engine.url,'upgrade','0024_default_change_types_upper');cli(engine.url,'upgrade','0024_default_change_types_upper')
  with engine.connect() as db:
   assert db.scalar(text('SELECT to_jsonb(t) FROM internal_tickets t'))==before
   assert db.scalar(text('SELECT count(*) FROM maintenance_changes'))==0
   assert db.scalar(text('SELECT count(*) FROM change_completion_types'))==5
   assert db.scalar(text('SELECT count(*) FROM change_completion_types WHERE applies_efficiency'))==1
   assert db.scalar(text('SELECT version_num FROM alembic_version'))=='0024_default_change_types_upper'
   assert 'change_audit' in inspect(db).get_table_names()
 finally:
  engine.dispose()
  with postgres_engine.connect().execution_options(isolation_level='AUTOCOMMIT') as admin:admin.execute(text('DROP DATABASE '+name))


def test_change_types_upgrade_keeps_unclassified_history_and_seeds_once(postgres_engine):
 import runpy
 from pathlib import Path
 name='change_types_upgrade_'+uuid4().hex
 with postgres_engine.connect().execution_options(isolation_level='AUTOCOMMIT') as admin:admin.execute(text('CREATE DATABASE '+name))
 engine=create_engine(postgres_engine.url.set(database=name))
 try:
  cli(engine.url,'upgrade','0022_change_control')
  with engine.begin() as db:
   db.execute(text("INSERT INTO sectors(id,name) VALUES (1,'Sector histórico')"))
   db.execute(text("INSERT INTO departments(id,name) VALUES (1,'NOC')"))
   db.execute(text("INSERT INTO responsibles(id,name,department_id) VALUES (1,'Encargado',1)"))
   db.execute(text("INSERT INTO maintenance_changes(ticket_number,reference,title,description,sector_id,manager_id,manager_name,department_id,department_name,status,proposed_start,proposed_end) VALUES (1,'CAM-0000001','Histórico','Conservar',1,1,'Encargado',1,'NOC','SCHEDULED','2026-10-15T23:00:50-06:00','2026-10-16T03:00:00-06:00')"))
   before=db.scalar(text('SELECT to_jsonb(t) FROM maintenance_changes t'))
  cli(engine.url,'upgrade','0024_default_change_types_upper');cli(engine.url,'upgrade','0024_default_change_types_upper')
  migration=runpy.run_path(str(Path(__file__).resolve().parents[1]/'alembic/versions/0023_change_types.py'))
  with engine.begin() as db:
   migration['seed_types'](db);migration['seed_types'](db)
   after=db.scalar(text('SELECT to_jsonb(t) FROM maintenance_changes t'))
   assert after.pop('change_type_id') is None and after==before
   assert db.scalar(text('SELECT count(*) FROM change_types'))==8
   assert set(db.execute(text('SELECT name,description FROM change_types')).all())=={(name.upper(),description) for name,description in migration['INITIAL_TYPES']}
   assert db.scalar(text('SELECT version_num FROM alembic_version'))=='0024_default_change_types_upper'
   db.execute(text('UPDATE maintenance_changes SET change_type_id=(SELECT id FROM change_types LIMIT 1)'))
  from sqlalchemy.exc import IntegrityError
  import pytest
  with pytest.raises(IntegrityError):
   with engine.begin() as db:db.execute(text('DELETE FROM change_types WHERE id=(SELECT change_type_id FROM maintenance_changes LIMIT 1)'))
  from alembic.autogenerate import compare_metadata
  from alembic.migration import MigrationContext
  from ticketyn.db.base import Base
  with engine.connect() as db:
   assert compare_metadata(MigrationContext.configure(db,opts={'include_object':lambda obj,name,kind,reflected,compare_to: kind!='table' or name in {'change_types','maintenance_changes'}}),Base.metadata)==[]
 finally:
  engine.dispose()
  with postgres_engine.connect().execution_options(isolation_level='AUTOCOMMIT') as admin:admin.execute(text('DROP DATABASE '+name))
