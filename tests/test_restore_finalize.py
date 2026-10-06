"""Finalize uses isolated paths/fake services; never production databases."""
import json
import os
from pathlib import Path
import shlex
import signal
import subprocess

import pytest
from test_restore import (ROOT, SCRIPT, SECRET, environment, installation, setup, configure,
                          shell, safety_script, stat_mode)


@pytest.fixture
def completed(environment):
    i = environment; safety_script(i)
    result = shell(configure(i) + 'REPLACE=1\nrestore_validate\nrestore_begin\nrestore_run')
    assert result.returncode == 0, result.stderr
    i['work'].mkdir(mode=0o700)
    state = i['config']/'restore-state'
    progress = dict(line.split('=', 1) for line in (state/'progress.txt').read_text().splitlines())
    i['token'] = progress['operation']; i['previous'] = progress['previous_database']
    i['state'] = state
    db = json.loads(i['db'].read_text()); db['unrelated_database'] = '300'
    i['db'].write_text(json.dumps(db))
    i['calls'].write_text('')
    i['properties'] = i['root']/'db-properties.json'
    i['properties'].write_text('{}')
    i['fake'].write_text('''import json, pathlib, re, sys
path=pathlib.Path(sys.argv[1]); trace=pathlib.Path(sys.argv[2]); props=json.loads(pathlib.Path(sys.argv[3]).read_text()); args=sys.argv[4:]
sql=sys.stdin.read() if '--file=-' in args else args[args.index('-c')+1]
db=json.loads(path.read_text())
if sql.startswith('SELECT oid FROM '): print(db.get(re.search("datname='([^']+)'",sql)[1],''))
elif sql.startswith('SELECT oid||'):
    name=re.search("datname='([^']+)'",sql)[1]
    if name in db:
        extra=props.get(name, {})
        allow=extra.get('allow', 'true' if name=='ticketyn' else 'false')
        print(db[name]+':'+extra.get('owner','ticketyn')+':UTF8:'+allow)
elif "system_identifier" in sql: print(props.get('cluster','987654321'))
elif "current_setting('server_version_num')" in sql: print(''' + str(__import__('test_restore').MAJOR * 10000 + 6) + ''')
elif sql.startswith('SELECT count(*) FROM pg_stat_activity'): print(props.get('sessions',0))
elif sql.startswith('SELECT count(*) FROM pg_database WHERE oid='):
    print(sum(oid==re.search(r'oid=(\\d+)',sql)[1] for oid in db.values()))
elif sql.startswith('SELECT format('):
    name=re.search("datname='([^']+)'",sql)[1]; oid=re.search(r'AND oid=(\\d+)',sql)[1]
    with trace.open('a') as out: out.write(sql+'\\n')
    if db.get(name)==oid: db.pop(name)
    path.write_text(json.dumps(db))
else: raise SystemExit('Unexpected mock query')
''')
    yield i


def finalize_code(i):
    return configure(i) + f'''
restore_sql() {{
    if [[ "$*" == *'--file=-'* && ${{DROP_FAIL:-0}} == 1 ]]; then cat >/dev/null; return 7; fi
    command python3 "{i['fake']}" "{i['db']}" "{i['calls']}" "{i['properties']}" "$@"
}}
# Never open /run on the development host. Production uses the installer lock.
restore_lock() {{ :; }}
'''


def finalize(i, answer='FINALIZAR RESTAURACION\n', extra=''):
    if not i['work'].exists(): i['work'].mkdir(mode=0o700)
    return shell(finalize_code(i) + extra + '\nrestore_finalize', answer)


def test_finalize_argument_and_root_required():
    result = shell('restore_args --finalize\necho "FINALIZE=$FINALIZE ARCHIVE=$ARCHIVE REPLACE=$REPLACE"')
    assert result.returncode == 0 and 'FINALIZE=1 ARCHIVE= REPLACE=0' in result.stdout
    if os.geteuid() != 0:
        result = subprocess.run([str(SCRIPT), '--finalize'], text=True, capture_output=True)
        assert result.returncode != 0 and 'root' in result.stderr


@pytest.mark.parametrize('args', ['--finalize file', '--finalize --replace', '--replace --finalize'])
def test_finalize_strict_arguments(args):
    assert shell('restore_args '+args).returncode != 0


def test_finalize_without_state(environment):
    result = shell(configure(environment) + 'restore_finalize')
    assert result.returncode != 0
    assert json.loads(environment['db'].read_text()) == {'ticketyn': '100'}


@pytest.mark.parametrize('problem', ['phase', 'operation', 'oid', 'metadata', 'receipt', 'missing_receipt', 'extra', 'symlink', 'permissions'])
def test_modified_or_incomplete_state_rejected(completed, problem):
    i = completed
    if problem in ('phase', 'operation', 'oid'):
        p = i['state']/'progress.txt'; value = p.read_text()
        if problem == 'phase': value = value.replace('phase=completado', 'phase=arranque')
        elif problem == 'operation': value = value.replace(i['token'], 'f'*32)
        else: value = value.replace('original_oid=100', 'original_oid=300')
        p.write_text(value)
    elif problem == 'metadata':
        p = i['state']/'source-metadata.txt'; p.write_text(p.read_text().replace('ticketyn_version=0.1.0','ticketyn_version=0.2.0'))
    elif problem == 'receipt': (i['state']/'completion.json').write_text('{}')
    elif problem == 'missing_receipt': (i['state']/'completion.json').unlink()
    elif problem == 'extra': (i['state']/'unknown').write_text('no')
    elif problem == 'symlink':
        p=i['state']/'previous.env'; p.unlink(); p.symlink_to(i['env'])
    else: (i['state']/'progress.txt').chmod(0o644)
    before = i['db'].read_bytes()
    result = finalize(i)
    assert result.returncode != 0
    assert i['db'].read_bytes() == before and i['state'].exists()
    assert SECRET not in result.stdout + result.stderr
    assert not (i['state']/'finalize-intent.json').exists()


@pytest.mark.parametrize('problem', ['active_oid', 'previous_oid', 'previous_enabled', 'previous_owner', 'sessions', 'cluster', 'old_oid_renamed'])
def test_database_identity_mismatch_rejected(completed, problem):
    i=completed; db=json.loads(i['db'].read_text()); props={}
    if problem == 'active_oid': db['ticketyn']='999'
    elif problem == 'previous_oid': db[i['previous']]='300'
    elif problem == 'previous_enabled': props[i['previous']]={'allow':'true'}
    elif problem == 'previous_owner': props[i['previous']]={'owner':'foreign_owner'}
    elif problem == 'sessions': props['sessions']=1
    elif problem == 'cluster': props['cluster']='12345'
    else: db['renamed_old_database']=db.pop(i['previous'])
    i['db'].write_text(json.dumps(db)); i['properties'].write_text(json.dumps(props))
    result=finalize(i)
    assert result.returncode != 0
    assert json.loads(i['db'].read_text()) == db
    assert i['state'].exists() and not (i['state']/'finalize-intent.json').exists()


@pytest.mark.parametrize('problem', ['service', 'health', 'api', 'socket'])
def test_unhealthy_installation_rejected_before_deletion(completed, problem):
    i=completed
    extra=''
    if problem=='service': i['active'].write_text('0')
    elif problem=='socket': extra="ss() { echo 'LISTEN 0 2048 0.0.0.0:8000 0.0.0.0:*'; }"
    else: extra=f'HTTP_FAIL={problem}'
    before=i['db'].read_bytes()
    result=finalize(i, extra=extra)
    assert result.returncode != 0 and i['db'].read_bytes() == before
    assert not (i['state']/'finalize-intent.json').exists()
    assert SECRET not in result.stdout + result.stderr


@pytest.mark.parametrize('answer', ['\n','FINALIZAR\n','"FINALIZAR RESTAURACION"\n','yes\n',''])
def test_cancel_does_not_change_state_or_databases(completed, answer):
    i=completed; before=i['db'].read_bytes()
    state_before={p.name:p.read_bytes() for p in i['state'].iterdir()}
    result=finalize(i, answer)
    assert result.returncode != 0
    assert 'Escribe exactamente "FINALIZAR RESTAURACION"' in result.stdout
    assert i['db'].read_bytes()==before
    assert {p.name:p.read_bytes() for p in i['state'].iterdir()}==state_before


@pytest.mark.parametrize('legacy', [False,True])
def test_success_preserves_active_foreign_db_and_backups(completed, legacy):
    i=completed
    if legacy:
        (i['state']/'completion.json').unlink(); (i['state']/'state-format').unlink()
    backup=(i['backups']/'safety.tar').read_bytes(); config=i['env'].read_bytes()
    foreign_backup=i['backups']/'other.tar'; foreign_backup.write_bytes(b'keep')
    current=os.readlink(i['app']/'current')
    result=finalize(i,extra='HTTP_TRANSIENT=2')
    assert result.returncode==0, result.stderr
    assert json.loads(i['db'].read_text())=={'ticketyn':'200','unrelated_database':'300'}
    assert not i['state'].exists()
    assert (i['backups']/'safety.tar').read_bytes()==backup
    assert foreign_backup.read_bytes()==b'keep'
    assert i['env'].read_bytes()==config and os.readlink(i['app']/'current')==current
    history=i['config']/'restore-history'
    assert stat_mode(history)==0o700
    record=history/(i['token']+'.json')
    assert stat_mode(record)==0o600
    data=json.loads(record.read_text())
    assert data['deleted_previous_oid']=='100' and data['active_oid']=='200'
    assert data['operation']==i['token'] and data['safety_backup']==str(i['backups']/'safety.tar')
    assert SECRET not in record.read_text()+result.stdout+result.stderr
    assert set(p.name for p in history.iterdir())=={record.name}
    calls=i['calls'].read_text()
    assert 'DROP DATABASE' in calls and 'systemctl stop' not in calls and 'systemctl start' not in calls
    # The remaining role/db satisfies restore validation; no restore-state blocks it.
    assert not i['state'].exists()


def test_drop_failure_retains_state_and_safe_retry(completed):
    i=completed
    result=finalize(i,extra='DROP_FAIL=1')
    assert result.returncode!=0 and i['state'].exists()
    assert json.loads(i['db'].read_text())[i['previous']]=='100'
    assert (i['state']/'finalize-intent.json').exists()
    assert finalize(i).returncode==0
    assert not i['state'].exists()


def test_after_drop_before_close_retry_is_idempotent(completed):
    i=completed
    # Simulate abrupt end after DROP and before archive; no production signal/service.
    extra=f'''
python3() {{
    if [[ "$*" == *'finalize-archive '* ]]; then return 9
    else command python3 "$@"; fi
}}
'''
    result=finalize(i,extra=extra)
    assert result.returncode!=0 and i['state'].exists()
    assert i['previous'] not in json.loads(i['db'].read_text())
    first=i['calls'].read_text().count('DROP DATABASE')
    assert first==1
    assert finalize(i).returncode==0
    assert i['calls'].read_text().count('DROP DATABASE')==1
    assert not i['state'].exists()


def test_previous_absent_without_registered_intent_is_ambiguous(completed):
    i=completed; db=json.loads(i['db'].read_text()); db.pop(i['previous']); i['db'].write_text(json.dumps(db))
    result=finalize(i)
    assert result.returncode!=0 and i['state'].exists()
    assert not (i['state']/'finalize-intent.json').exists()


def test_db_reusing_old_name_never_deleted_on_retry(completed):
    i=completed
    assert finalize(i,extra='DROP_FAIL=1').returncode!=0
    db=json.loads(i['db'].read_text()); db[i['previous']]='999'; i['db'].write_text(json.dumps(db))
    result=finalize(i)
    assert result.returncode!=0 and json.loads(i['db'].read_text())[i['previous']]=='999'
    assert i['state'].exists()


@pytest.mark.parametrize('sig',[signal.SIGINT,signal.SIGTERM])
def test_signal_waiting_confirmation_is_innocuous(completed,sig):
    i=completed; before=i['db'].read_bytes(); progress=(i['state']/'progress.txt').read_bytes()
    code=finalize_code(i)+'''\nrestore_finalize_confirm() { echo READY; read -r wait; }\nrestore_finalize'''
    process=subprocess.Popen(['bash','-c','source "$1"\nsource "$2"\n'+code,'test',
                              str(ROOT/'backup.sh'),str(SCRIPT)],stdin=subprocess.PIPE,
                             stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
    assert process.stdout.readline().strip()=='READY'
    process.send_signal(sig); out,err=process.communicate(timeout=5)
    assert process.returncode!=0 and i['db'].read_bytes()==before
    assert (i['state']/'progress.txt').read_bytes()==progress
    assert not (i['state']/'finalize-intent.json').exists()
    assert SECRET not in out+err


def test_validation_does_not_write_recovery_state(completed):
    i=completed
    (i['state']/'diagnostic.log').write_text('keep existing private diagnostic')
    before={p.name:(p.read_bytes(),p.stat().st_mtime_ns,p.stat().st_ino) for p in i['state'].iterdir()}
    result=finalize(i,'\n')
    assert result.returncode!=0
    after={p.name:(p.read_bytes(),p.stat().st_mtime_ns,p.stat().st_ino) for p in i['state'].iterdir()}
    assert before==after


@pytest.mark.parametrize('problem',['missing','modified'])
def test_security_backup_must_still_be_present_and_valid(completed,problem):
    i=completed; path=i['backups']/'safety.tar'
    if problem=='missing': path.unlink()
    else: path.write_bytes(b'not a valid backup')
    before=i['db'].read_bytes()
    result=finalize(i)
    assert result.returncode!=0 and i['db'].read_bytes()==before
    assert i['state'].exists() and not (i['state']/'finalize-intent.json').exists()


def test_closed_state_allows_restore_validation_again(completed):
    i=completed
    assert finalize(i).returncode==0
    i['work'].mkdir(mode=0o700)
    # Restore's role validation is independent of finalize; model the unchanged valid role.
    extra=f'''
restore_sql() {{
    if [[ "$*" == *'SELECT count(*) FROM pg_roles'* ]]; then echo 1
    elif [[ "$*" == *'SELECT pg_get_userbyid'* ]]; then echo ticketyn:UTF8
    else command python3 "{i['fake']}" "{i['db']}" "{i['calls']}" "{i['properties']}" "$@"; fi
}}
REPLACE=1
restore_validate
'''
    result=shell(finalize_code(i)+extra)
    assert result.returncode==0,result.stderr
    assert not i['state'].exists()


def test_conflicting_history_detected_before_drop(completed):
    i=completed; history=i['config']/'restore-history'; history.mkdir(mode=0o700)
    target=history/(i['token']+'.json'); target.write_text('{}');target.chmod(0o600)
    before=i['db'].read_bytes()
    result=finalize(i)
    assert result.returncode!=0 and i['db'].read_bytes()==before
    assert target.read_text()=='{}' and i['state'].exists()


def test_sigkill_after_drop_can_complete_without_second_drop(completed):
    i=completed
    code=finalize_code(i)+'''
python3() {
    if [[ "$*" == *'finalize-archive '* ]]; then echo READY; read -r wait
    else command python3 "$@"; fi
}
restore_finalize
'''
    process=subprocess.Popen(['bash','-c','source "$1"\nsource "$2"\n'+code,'test',
                              str(ROOT/'backup.sh'),str(SCRIPT)],stdin=subprocess.PIPE,
                             stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
    process.stdin.write('FINALIZAR RESTAURACION\n'); process.stdin.flush()
    while True:
        line=process.stdout.readline()
        assert line, 'Finalize exited before the simulated crash point'
        if line.rstrip().endswith('READY'): break
    process.send_signal(signal.SIGKILL)
    out,err=process.communicate(timeout=5)
    assert process.returncode==-signal.SIGKILL
    assert i['state'].exists() and (i['state']/'finalize-intent.json').exists()
    assert i['previous'] not in json.loads(i['db'].read_text())
    assert i['calls'].read_text().count('DROP DATABASE')==1
    assert finalize(i).returncode==0
    assert i['calls'].read_text().count('DROP DATABASE')==1
    assert SECRET not in out+err
