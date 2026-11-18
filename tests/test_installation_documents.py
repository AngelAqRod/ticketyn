from ticketyn.incoming.config import IncomingSettings


def test_private_upload_preview_and_validation(api_client,ticket_payload,monkeypatch,tmp_path):
    monkeypatch.setenv('INSTALLATION_STORAGE_DIR',str(tmp_path/'originals'))
    payload={'order_type':'NORMAL','customer_id':ticket_payload['customer_id'],'circuit_id':ticket_payload['circuit_id'],'requested_at':'2026-10-28T12:00:00-06:00'}
    order=api_client.post('/api/installation-orders',json=payload).json()
    endpoint=f"/api/installation-orders/{order['id']}/documents"
    assert api_client.post(endpoint+'?filename=bad.pdf',content=b'not pdf').status_code==422
    content=b'%PDF-1.7\noriginal'
    response=api_client.post(endpoint+'?filename=original.pdf',content=content)
    assert response.status_code==201,response.text
    document=response.json()
    downloaded=api_client.get(f"/api/installation-documents/{document['id']}/content")
    assert downloaded.status_code==200 and downloaded.content==content
    assert downloaded.headers['x-content-type-options']=='nosniff'
    assert downloaded.headers['content-disposition'].startswith('inline')
    assert api_client.get('/var/installation-originals/'+document['checksum']).status_code!=200
    api_client.headers.pop('Authorization')
    assert api_client.get(f"/api/installation-documents/{document['id']}/content").status_code==401


def test_manual_mode_without_imap(api_client,monkeypatch):
    monkeypatch.delenv('INSTALLATION_IMAP_HOST',raising=False)
    response=api_client.get('/api/incoming-mail/status')
    assert response.status_code==200
    assert response.json()['enabled'] is False
    assert api_client.post('/api/incoming-mail/poll').json()['received']==0


def test_order_permission_does_not_expose_unprocessed_mail(api_client,db_session,monkeypatch,tmp_path):
    from datetime import datetime,timezone
    from sqlalchemy import select
    from ticketyn.models import Responsible
    from ticketyn.models.security import SecurityRole,SecurityRolePermission
    from ticketyn.models.installation_orders import InstallationRequest
    from ticketyn.incoming.storage import save_document,storage_lock
    from security_helpers import fixture_password
    monkeypatch.setenv('INSTALLATION_STORAGE_DIR',str(tmp_path/'private'))
    request=InstallationRequest(mailbox='orders@example.test',folder='INBOX',uidvalidity=1,uid=55,checksum='b'*64,sender='private@example.test',subject='Private',body='Private body',received_at=datetime.now(timezone.utc))
    db_session.add(request); db_session.flush()
    with storage_lock():
        document=save_document(db_session,content=b'%PDF-1.7\nprivate',name='private.pdf',request_id=request.id)
        db_session.flush(); document_id=document.id; request_id=request.id; db_session.commit()
    role=SecurityRole(name='Order reader only'); db_session.add(role); db_session.flush()
    db_session.add(SecurityRolePermission(role_id=role.id,permission_code='installation_orders.view'))
    person=Responsible(name='Order reader',username='order-reader',password_hash=fixture_password(),access_granted=True,security_role_id=role.id,password_change_required=False)
    db_session.add(person);db_session.commit()
    token=api_client.post('/api/auth/login',json={'username':'order-reader','password':'test-only-password'}).json()['token']
    api_client.headers['Authorization']='Bearer '+token
    assert api_client.get(f'/api/installation-documents/{document_id}').status_code==403
    assert api_client.get(f'/api/installation-documents/{document_id}/content').status_code==403
    assert api_client.get(f'/api/installation-requests/{request_id}').status_code==403
    assert api_client.get('/api/installation-orders').status_code==200
