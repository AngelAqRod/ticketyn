"""Sectores explícitos para escenarios de creación de circuitos nuevos."""
from uuid import uuid4


def create_test_sector(client):
    response = client.post('/api/sectors', json={'name': 'Sector ' + uuid4().hex})
    assert response.status_code == 201, response.text
    return response.json()['id']


def create_test_node(client):
    response = client.post('/api/nodes', json={'name': 'Nodo ' + uuid4().hex})
    assert response.status_code == 201, response.text
    return response.json()['id']
