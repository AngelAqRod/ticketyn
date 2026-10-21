"""Project version for source checkouts and installed release packages."""
from importlib.metadata import distributions
from pathlib import Path
import re
import tomllib


# Resolve once: switching /opt/ticketyn/current must not relabel loaded code.
_MODULE_PATH = Path(__file__).resolve()


def _version(value: object) -> str:
    if (not isinstance(value, str) or len(value) > 64
            or re.fullmatch(r'\d+\.\d+\.\d+[a-zA-Z0-9.+-]*', value) is None):
        raise RuntimeError('La versión declarada de Ticketyn no es válida.')
    return value


def get_version() -> str:
    """Use project.version, or metadata proven to own this installed module.

    Setuptools generates installed METADATA from the same pyproject.toml.
    Never search the working directory or trust an unrelated distribution.
    """
    if _MODULE_PATH.parents[2].name == 'src':
        project_file = _MODULE_PATH.parents[3] / 'pyproject.toml'
        try:
            with project_file.open('rb') as stream:
                project = tomllib.load(stream).get('project', {})
        except (OSError, ValueError):
            raise RuntimeError('No se pudo leer pyproject.toml del código de Ticketyn.') from None
        if not isinstance(project, dict) or project.get('name') != 'ticketyn':
            raise RuntimeError('pyproject.toml no identifica el proyecto Ticketyn.')
        return _version(project.get('version'))

    versions = set()
    for distribution in distributions(name='ticketyn'):
        if any(Path(distribution.locate_file(file)).resolve() == _MODULE_PATH
               for file in distribution.files or ()):
            versions.add(_version(distribution.version))
    if len(versions) != 1:
        raise RuntimeError('No se pudo identificar inequívocamente la versión del paquete Ticketyn cargado.')
    return versions.pop()
