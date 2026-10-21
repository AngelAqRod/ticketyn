"""Real authenticated fixture for legacy operational regressions; no auth bypass."""
from contextlib import contextmanager
from functools import lru_cache
from sqlalchemy.orm import Session
from sqlalchemy import select
from ticketyn.models import Responsible
from ticketyn.models.security import SecurityRole
from ticketyn.security.service import seed_foundation
from ticketyn.security.passwords import hash_password

@lru_cache
def fixture_password():
    return hash_password('test-only-password')


def authenticate_test_client(app, client, bind):
    @contextmanager
    def factory():
        with Session(bind=bind, join_transaction_mode='create_savepoint') as session:
            yield session
    app.state.security_session_factory = factory
    with factory() as session:
        seed_foundation(session)
        role = session.scalar(select(SecurityRole).where(SecurityRole.code == 'SUPERADMIN'))
        account = session.scalar(select(Responsible).where(Responsible.username == 'security-test-superadmin'))
        if account is None:
            account = Responsible(id=2147000000, name='Security fixture administrator', username='security-test-superadmin', password_hash=fixture_password(), access_granted=True, security_role_id=role.id, password_change_required=False)
            session.add(account)
            session.flush()
        id, revision = account.id, account.access_revision
        session.commit()
    app.state.test_security_account_id = id
    token = app.state.security.create(id, revision)
    client.headers['Authorization'] = 'Bearer ' + token
    return id, token
