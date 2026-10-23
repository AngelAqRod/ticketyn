"""Validación de integridad del sistema de documentación técnica persistente.

Verifica que las referencias a archivos y directorios locales en:
  - docs/SYSTEM_MAP.md
  - docs/modules/*.md
existan físicamente respecto a la raíz del repositorio, evitando enlaces
rotos y documentación desfasada sin depender de base de datos ni servicios externos.
"""
from pathlib import Path
import re
import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
DOCS_DIR = REPO_ROOT / "docs"
SYSTEM_MAP = DOCS_DIR / "SYSTEM_MAP.md"
MODULES_DIR = DOCS_DIR / "modules"

EXPECTED_MODULE_DOCS = [
    "catalogos-configuracion.md",
    "clientes-circuitos.md",
    "control-cambios.md",
    "notificaciones-correo.md",
    "operaciones-fms.md",
    "reporteria-exportaciones.md",
    "seguridad-cuentas.md",
    "tickets-clientes.md",
    "tickets-internos.md",
]

# Extensiones de archivo reconocidas
FILE_EXTENSIONS = {
    ".py", ".tsx", ".ts", ".md", ".json", ".toml", ".css", ".html", ".svg", ".sh"
}

# Índices en memoria del repositorio para resolución rápida de nombres de archivo
CODEBASE_SEARCH_DIRS = ("src", "frontend/src", "tests", "docs", "alembic", "deploy")
REPO_FILES = set()
for search_dir in CODEBASE_SEARCH_DIRS:
    dir_path = REPO_ROOT / search_dir
    if dir_path.is_dir():
        for p in dir_path.rglob("*"):
            if p.is_file():
                REPO_FILES.add(p.name)

# Patrones a ignorar (parámetros CLI, rutas dinámicas, comodines, endpoints HTTP, etc.)
IGNORED_PATTERNS = [
    re.compile(r"^--"),                             # Opciones CLI (ej. --workers)
    re.compile(r"^\*"),                             # Comodines iniciales
    re.compile(r"\*"),                              # Patrones glob (ej. *exports.py)
    re.compile(r"^/api/"),                          # Rutas de endpoints HTTP
    re.compile(r"^/health"),                        # Endpoint de salud
    re.compile(r"^[A-Z_]+$"),                       # Variables de entorno o constantes
    re.compile(r"^(GET|POST|PUT|DELETE|PATCH)\s+"), # Declaraciones de métodos HTTP
    re.compile(r"^(http://|https://|mailto:)"),    # Enlaces externos
    re.compile(r"\{[^}]*\}"),                       # Parámetros dinámicos en rutas (ej. {id})
]

# Términos específicos del dominio que no son rutas en disco
IGNORED_EXACT_TOKENS = {
    "America/Guatemala",
    "responsibles",
    "ticket_number_configs",
    "internal_ticket_number_configs",
    "mail_notification_requests",
    "mail_jobs",
    "security_audit",
    "SecurityMemory",
    "MemorySecurity",
    "SafeAuthRoute",
    "PasswordHasher",
    "BoundedSemaphore",
    "ActivationNumberConfig",
    "ChangeNumberConfig",
    "InternalTicketNumberConfig",
    "TicketNumberConfig",
    "MaintenanceChange",
    "ChangeType",
    "ChangeCompletionType",
    "ChangeSupport",
    "ChangeTicket",
    "ChangeUpdate",
    "ChangeAudit",
    "Activation",
    "CapacityChange",
    "CircuitLifecycleOperation",
    "ActivationIntervention",
    "DeactivationReason",
    "InternalTicket",
    "InternalTicketUpdate",
    "InternalEscalation",
    "Provider",
    "InternalIncidentType",
    "Ticket",
    "TicketUpdate",
    "TicketEscalation",
    "Customer",
    "Circuit",
    "Sector",
    "Node",
    "Department",
    "Position",
    "Responsible",
    "IncidentType",
    "ServiceType",
    "CpeModel",
    "MailTransportConfig",
    "MailEventConfig",
    "MailNotificationRequest",
    "MailProcessorControl",
    "ChangeCalendar",
    "active",
    "access_granted",
    "operational_selectable",
    "revision",
    "is_customer_visible",
    "is_eligible_for_efficiency",
    "is_paused",
    "initial_bandwidth",
    "proposed_start",
    "proposed_end",
    "actual_start",
    "actual_end",
    "closed_at",
    "opened_at",
    "created_at",
    "activity_at",
    "recorded_at",
    "deactivation_reason_id",
    "change_type_id",
    "change_completion_type_id",
    "responsible_id",
    "department_id",
    "circuit_id",
    "customer_id",
    "sector_id",
    "node_id",
    "dummy_hash()",
    "lock_security(session)",
    "SELECT ... FOR UPDATE",
    "true",
    "false",
    "none",
    "null",
}


def is_path_candidate(token: str) -> bool:
    token = token.strip().rstrip(",;:.)").lstrip("(")
    if not token or " " in token:
        return False
    if token in IGNORED_EXACT_TOKENS:
        return False
    for pat in IGNORED_PATTERNS:
        if pat.search(token):
            return False
    # Excluir operadores matemáticos o expresiones de código
    if any(ch in token for ch in ["=", "<", ">", "$", "+", "|", "&", "\\"]):
        return False
    # Debe ser una ruta (contener '/') o terminar con una extensión conocida
    has_slash = "/" in token
    has_ext = any(token.endswith(ext) for ext in FILE_EXTENSIONS)
    return has_slash or has_ext


def extract_path_references(file_path: Path) -> list[str]:
    content = file_path.read_text(encoding="utf-8")
    references = []

    # 1. Referencias en código inline `...`
    for match in re.findall(r"`([^`\n]+)`", content):
        token = match.strip().rstrip(",;:.)").lstrip("(")
        if is_path_candidate(token):
            references.append(token)

    # 2. Enlaces Markdown [texto](ruta)
    for match in re.findall(r"\[[^\]]+\]\(([^)\n]+)\)", content):
        target = match.strip().split("#")[0].strip()
        if target.startswith("file://"):
            target = target.replace("file://", "")
        if target and is_path_candidate(target):
            references.append(target)

    return references


def check_reference_exists(ref: str, doc_file: Path) -> bool:
    """Verifica si una referencia existe respecto a REPO_ROOT, al doc o en el repositorio."""
    clean_ref = ref.rstrip("/")

    # 1. Comprobar si existe directamente relativo a la raíz del repositorio
    if (REPO_ROOT / clean_ref).exists():
        return True

    # 2. Comprobar si existe relativo al directorio del documento (enlaces relativos markdown)
    if (doc_file.parent / clean_ref).exists():
        return True

    # 3. Si es un nombre de archivo simple sin ruta (ej. 'tickets.py'), comprobar si existe en el codebase
    if any(clean_ref.endswith(ext) for ext in FILE_EXTENSIONS):
        return clean_ref in REPO_FILES

    return False


def test_expected_documents_exist():
    """Verifica que el mapa central y las 9 fichas técnicas modulares existan."""
    assert SYSTEM_MAP.is_file(), f"Falta el mapa técnico central: {SYSTEM_MAP}"
    assert MODULES_DIR.is_dir(), f"Falta el directorio de módulos: {MODULES_DIR}"

    for mod in EXPECTED_MODULE_DOCS:
        mod_path = MODULES_DIR / mod
        assert mod_path.is_file(), f"Falta la ficha técnica modular esperada: {mod_path}"


def test_system_map_references_integrity():
    """Valida que todas las referencias a archivos locales de SYSTEM_MAP.md existan."""
    refs = extract_path_references(SYSTEM_MAP)
    assert len(refs) > 0, "SYSTEM_MAP.md debe contener referencias a archivos"

    missing = []
    for ref in refs:
        if not check_reference_exists(ref, SYSTEM_MAP):
            missing.append(ref)

    assert not missing, (
        f"En {SYSTEM_MAP.relative_to(REPO_ROOT)} se encontraron {len(missing)} rutas inexistentes:\n"
        + "\n".join(f"  - {m}" for m in missing)
    )


@pytest.mark.parametrize("module_name", EXPECTED_MODULE_DOCS)
def test_module_sheet_references_integrity(module_name: str):
    """Valida que todas las referencias a archivos en cada ficha de docs/modules/ existan."""
    doc_path = MODULES_DIR / module_name
    refs = extract_path_references(doc_path)
    assert len(refs) > 0, f"La ficha {module_name} debe contener referencias a archivos"

    missing = []
    for ref in refs:
        if not check_reference_exists(ref, doc_path):
            missing.append(ref)

    assert not missing, (
        f"En {doc_path.relative_to(REPO_ROOT)} se encontraron {len(missing)} rutas inexistentes:\n"
        + "\n".join(f"  - {m}" for m in missing)
    )
