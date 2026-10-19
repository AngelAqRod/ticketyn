# Historical migration coverage is intentionally pinned; current HEAD is tested
# in test_deployment.py and test_mail_jobs.py.
"""Only original seeded names change; manual capitalization and history survive."""
from pathlib import Path
import runpy
from uuid import uuid4
import pytest
from sqlalchemy import create_engine, text
from test_e2e_update_migration import cli


@pytest.mark.parametrize('customized',[False,True])
def test_uppercase_defaults_upgrade_is_targeted_and_idempotent(postgres_engine,customized):
    name='uppercase_types_'+uuid4().hex
    with postgres_engine.connect().execution_options(isolation_level='AUTOCOMMIT') as admin:
        admin.execute(text('CREATE DATABASE '+name))
    engine=create_engine(postgres_engine.url.set(database=name))
    migration=runpy.run_path(str(Path(__file__).resolve().parents[1]/'alembic/versions/0024_default_change_types_upper.py'))
    try:
        cli(engine.url,'upgrade','0023_change_types')
        with engine.begin() as db:
            db.execute(text("UPDATE change_types SET description='Descripción personalizada',active=false WHERE id=2"))
            if customized:
                db.execute(text("UPDATE change_types SET name='Preventivo Especial' WHERE id=1"))
                # Same name as the original seed, but this is a new manual row.
                db.execute(text("INSERT INTO change_types(name,description) VALUES ('Mantenimiento preventivo','Manual'),('Clasificación Mixta de Usuario','Personalizada')"))
                # Preserve capitalization explicitly customized on a seeded row.
                db.execute(text("UPDATE change_types SET name='migración de SERVICIOS' WHERE id=6"))
            db.execute(text("INSERT INTO sectors(id,name) VALUES (1,'Sector')"))
            db.execute(text("INSERT INTO departments(id,name) VALUES (1,'NOC')"))
            db.execute(text("INSERT INTO responsibles(id,name,department_id) VALUES (1,'Encargado',1)"))
            db.execute(text("INSERT INTO maintenance_changes(ticket_number,reference,title,description,sector_id,manager_id,manager_name,department_id,department_name,status,proposed_start,proposed_end,change_type_id) VALUES (1,'CAM-0000001','Conservar','Descripción',1,1,'Encargado',1,'NOC','SCHEDULED','2026-10-15T23:00:50-06:00','2026-10-16T03:00:00-06:00',2)"))
            before=db.execute(text('SELECT to_jsonb(t) FROM change_types t ORDER BY id')).scalars().all()
            change_before=db.scalar(text('SELECT to_jsonb(t) FROM maintenance_changes t'))
        cli(engine.url,'upgrade','0024_default_change_types_upper');cli(engine.url,'upgrade','0024_default_change_types_upper')
        with engine.begin() as db:
            migration['uppercase_default_types'](db);migration['uppercase_default_types'](db)
            after=db.execute(text('SELECT to_jsonb(t) FROM change_types t ORDER BY id')).scalars().all()
            expected=[]
            for row in before:
                updated=row.copy()
                if 1<=row['id']<=8 and row['name']==migration['DEFAULT_NAMES'][row['id']-1]:
                    updated['name']=row['name'].upper()
                expected.append(updated)
            assert after==expected
            assert db.scalar(text('SELECT to_jsonb(t) FROM maintenance_changes t'))==change_before
            assert db.scalar(text('SELECT version_num FROM alembic_version'))=='0024_default_change_types_upper'
            if not customized:
                assert [row['name'] for row in after]==[
                    'MANTENIMIENTO PREVENTIVO','MANTENIMIENTO CORRECTIVO','ACTUALIZACIÓN DE SOFTWARE',
                    'CAMBIO DE CONFIGURACIÓN','AMPLIACIÓN DE CAPACIDAD','MIGRACIÓN DE SERVICIOS','PRUEBAS TÉCNICAS','OTROS']
            else:
                assert after[0]['name']=='Preventivo Especial'
                assert after[5]['name']=='migración de SERVICIOS'
                assert after[8]['name']=='Mantenimiento preventivo'
                assert after[9]['name']=='Clasificación Mixta de Usuario'
    finally:
        engine.dispose()
        with postgres_engine.connect().execution_options(isolation_level='AUTOCOMMIT') as admin:
            admin.execute(text('DROP DATABASE '+name))
