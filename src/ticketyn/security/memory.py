"""Bounded process-local sessions and progressive throttling. No raw tokens retained."""
from dataclasses import dataclass
from collections import OrderedDict
import hashlib
import secrets
import threading
import time
from dataclasses import replace

class SessionLimit(Exception):
    pass

@dataclass
class LoginSession:
    id: str
    responsible_id: int
    revision: int
    last_activity: float
    ip: str
    agent: str
    idle_seconds: int = 1800

class MemorySecurity:
    MAX_SESSIONS = 10000
    MAX_COUNTERS = 20000
    MAX_FLOWS = 256
    def __init__(self, clock=time.monotonic):
        self.clock = clock
        self.lock = threading.RLock()
        self.sessions = {}
        self.counters = OrderedDict()
        self.flows = {}

    @staticmethod
    def digest(value):
        return hashlib.sha256(value.encode()).hexdigest()

    def cleanup(self, idle=None):
        with self.lock:
            now = self.clock()
            for key, item in list(self.sessions.items()):
                if now - item.last_activity >= (item.idle_seconds if idle is None else idle):
                    del self.sessions[key]
            for key, (start, _, _) in list(self.counters.items()):
                if now - start >= 900:
                    del self.counters[key]
            for key, (_, expires) in list(self.flows.items()):
                if expires <= now:
                    del self.flows[key]

    def create(self, responsible_id, revision, ip='', agent='', idle=1800):
        with self.lock:
            self.cleanup(idle)
            for key, item in list(self.sessions.items()):
                if item.responsible_id == responsible_id and item.revision != revision:
                    del self.sessions[key]
            if len(self.sessions) >= self.MAX_SESSIONS:
                raise SessionLimit('Capacidad temporal de sesiones alcanzada')
            if sum(s.responsible_id == responsible_id for s in self.sessions.values()) >= 5:
                raise SessionLimit('Ya existen cinco sesiones activas para esta cuenta')
            token = secrets.token_urlsafe(32)
            self.sessions[self.digest(token)] = LoginSession(secrets.token_hex(16), responsible_id, revision, self.clock(), ip[:64], agent[:256], idle)
            return token

    def get(self, token, idle=1800):
        if not isinstance(token, str) or len(token) > 128:
            return None
        with self.lock:
            self.cleanup(idle)
            return self.sessions.get(self.digest(token))

    def revoke(self, token):
        with self.lock:
            self.sessions.pop(self.digest(token), None)

    def revoke_account(self, responsible_id, keep=None, revision=None):
        with self.lock:
            for key, item in list(self.sessions.items()):
                if item.responsible_id == responsible_id:
                    if key == keep:
                        item.revision = revision
                    else:
                        del self.sessions[key]

    def touch(self, item):
        with self.lock:
            # Do not resurrect an expired or concurrently revoked session.
            if any(current is item for current in self.sessions.values()):
                item.last_activity = self.clock()

    def snapshot(self):
        """Detached metadata only. Never expose token digests to callers."""
        with self.lock:
            self.cleanup()
            return [replace(item) for item in self.sessions.values()]

    def revoke_ids(self, ids):
        with self.lock:
            for key, item in list(self.sessions.items()):
                if item.id in ids:
                    del self.sessions[key]

    def wait(self, username, ip):
        username = username.lower()
        with self.lock:
            self.cleanup()
            now = self.clock()
            # Account keys stop IP rotation. Pair keys protect unknown usernames.
            # IP-wide spray threshold is deliberately higher for shared NOC NATs.
            keys = [('account', self.digest(username)), ('pair', self.digest(username + '\0' + ip)), ('ip', ip)]
            return max((max(0, self.counters.get(key, (0, 0, 0))[2] - now) for key in keys), default=0)

    def failed(self, username, ip):
        username = username.lower()
        with self.lock:
            self.cleanup()
            now = self.clock()
            first = False
            for kind, value, threshold in [('account', self.digest(username), 5), ('pair', self.digest(username + '\0' + ip), 5), ('ip', ip, 100)]:
                key = (kind, value)
                start, count, _ = self.counters.pop(key, (now, 0, 0))
                count += 1
                delay = min(60, 2 ** min(6, max(0, count - threshold))) if count >= threshold else 0
                self.counters[key] = (start, count, now + delay)
                if kind == 'pair': first = count == 1
            while len(self.counters) > self.MAX_COUNTERS:
                self.counters.popitem(last=False)
            return first

    def succeeded(self, username, ip):
        username = username.lower()
        with self.lock:
            for key in [('account', self.digest(username)), ('pair', self.digest(username + '\0' + ip))]:
                self.counters.pop(key, None)

    def bind_flow(self, binding, item):
        with self.lock:
            self.cleanup()
            if len(self.flows) >= self.MAX_FLOWS:
                raise SessionLimit('Demasiados flujos OAuth2 pendientes')
            self.flows[self.digest(binding)] = (item.id, self.clock() + 600)

    def flow_session(self, binding):
        with self.lock:
            self.cleanup()
            flow = self.flows.pop(self.digest(binding), None)
            return next((s for s in self.sessions.values() if flow and s.id == flow[0]), None)
