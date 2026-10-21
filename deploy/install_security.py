"""Read-only capability checks for the installer; no application imports or DB access."""
import ast
from pathlib import Path
import sys


class CapabilityError(ValueError):
    pass


def syntax(path):
    return ast.parse(path.read_text(encoding='utf-8'), filename=str(path))


def revisions(root):
    result = {}
    for path in (root / 'alembic/versions').glob('*.py'):
        values = {}
        for node in syntax(path).body:
            if isinstance(node, ast.Assign):
                for name in node.targets:
                    if isinstance(name, ast.Name) and name.id in {'revision', 'down_revision'}:
                        values[name.id] = ast.literal_eval(node.value)
        if 'revision' in values:
            revision = values['revision']
            if not isinstance(revision, str) or revision in result:
                raise CapabilityError('Revisiones Alembic inválidas o duplicadas.')
            result[revision] = values.get('down_revision')
    return result


def capability(root):
    """Use the downloaded package, never the local checkout's version or DB.

    Cross-check migration metadata and the authentication wiring. A partial
    security distribution must never fall back to an unauthenticated install.
    """
    root = Path(root)
    main = syntax(root / 'src/ticketyn/main.py')
    graph = revisions(root)
    imports_security = any(isinstance(node, ast.ImportFrom) and
                           (node.module or '').startswith('ticketyn.security')
                           for node in ast.walk(main))
    calls_security = any(isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
                         and node.func.id == 'install_security' for node in ast.walk(main))
    has_foundation = '0030_security_foundation' in graph
    security_files = any((root / name).exists() for name in (
        'src/ticketyn/security', 'src/ticketyn/api/auth.py', 'bootstrap-superadmin.sh'))
    if not (imports_security or calls_security or has_foundation or security_files):
        return 'legacy'

    if not (imports_security and calls_security and has_foundation):
        raise CapabilityError('Paquete de autenticación incompleto: código y migraciones no coinciden.')
    if (graph.get('0030_security_foundation') != '0029_mail_requests'
            or graph.get('0031_role_permissions') != '0030_security_foundation'
            or graph.get('0032_responsible_selectable') != '0031_role_permissions'):
        raise CapabilityError('Faltan las migraciones compatibles con el bootstrap de seguridad.')

    auth = syntax(root / 'src/ticketyn/api/auth.py')
    prefix = any(isinstance(node, ast.keyword) and node.arg == 'prefix'
                 and isinstance(node.value, ast.Constant) and node.value.value == '/api/auth'
                 for node in ast.walk(auth))
    login = any(isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                and node.func.attr == 'post' and node.args and isinstance(node.args[0], ast.Constant)
                and node.args[0].value == '/login' for node in ast.walk(auth))
    aliases = {alias.asname or alias.name for node in ast.walk(main)
               if isinstance(node, ast.ImportFrom) and node.module == 'ticketyn.api.auth'
               for alias in node.names if alias.name == 'router'}
    wired = any(isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                and node.func.attr == 'include_router' and node.args
                and isinstance(node.args[0], ast.Name) and node.args[0].id in aliases
                for node in ast.walk(main))
    if not (prefix and login and wired):
        raise CapabilityError('No se puede verificar el contrato de autenticación de la release.')

    script = root / 'bootstrap-superadmin.sh'
    module = root / 'src/ticketyn/security/bootstrap.py'
    if not script.is_file() or script.is_symlink() or not script.stat().st_mode & 0o111:
        raise CapabilityError('La release con autenticación necesita bootstrap-superadmin.sh ejecutable.')
    bootstrap = syntax(module)
    functions = {node.name for node in bootstrap.body if isinstance(node, ast.FunctionDef)}
    arguments = {node.args[0].value for node in ast.walk(bootstrap)
                 if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                 and node.func.attr == 'add_argument' and node.args
                 and isinstance(node.args[0], ast.Constant)}
    if not ({'main', 'check_status_cli', 'interactive_bootstrap'} <= functions
            and {'--check', '--config'} <= arguments):
        raise CapabilityError('El módulo bootstrap no ofrece los contratos requeridos por el instalador.')
    return 'required'


def main():
    try:
        if len(sys.argv) != 2:
            raise CapabilityError('Se requiere el directorio de la release para verificar autenticación.')
        print(capability(Path(sys.argv[1])))
    except CapabilityError as error:
        print(f'Error: {error}', file=sys.stderr)
        return 1
    except (ValueError, OSError, SyntaxError, TypeError):
        # No raw exception text: distribution contents need not be trusted as diagnostics.
        print('Error: capacidades de seguridad incompletas o incompatibles; revisa código, migraciones y bootstrap de la release.', file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
