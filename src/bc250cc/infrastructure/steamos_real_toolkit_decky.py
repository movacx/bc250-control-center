"""Attested fan ownership checks for the optional upstream Decky plugin.

The separate plugin can coexist with native Quick Access. Guard its fan writes
and configuration mutations without replacing either plugin or its protocol.
"""
from __future__ import annotations

import ast
import hashlib

from .steamos_real_toolkit import CONFLICT_CHECK_COMMAND

_DIGESTS = {
    'main.py': '55cf6782752732178c42b31f519dc0d8d30f547280a504124ee114bb4b661e9b',
    'fan_manager.py': '64401d79de7bea0948c3898b2e2c7f8fc4ec4df0df12d47e1014ed8383dc9cd6',
}
_CHECK = (*CONFLICT_CHECK_COMMAND, 'fans')


def adapt_decky_payload(name: str, source: bytes) -> bytes:
    if name not in _DIGESTS or hashlib.sha256(source).hexdigest() != _DIGESTS[name]:
        raise ValueError('Real Toolkit Decky payload differs from reviewed source: ' + name)
    text = source.decode('utf-8')
    tree = ast.parse(text)
    lines = text.splitlines(keepends=True)
    if name == 'main.py':
        plugin = next(node for node in tree.body if isinstance(node, ast.ClassDef) and node.name == 'Plugin')
        names = {'set_fan_mode', 'save_profile', 'select_profile', 'delete_profile'}
        methods = [node for node in plugin.body if isinstance(node, ast.AsyncFunctionDef) and node.name in names]
        if {method.name for method in methods} != names:
            raise ValueError('Real Toolkit Decky fan methods changed')
        for method in reversed(methods):
            lines.insert(method.body[0].lineno - 1, '        await self._run(*' + repr(_CHECK) + ')\n')
    else:
        write = next(node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == 'write_fan')
        lines.insert(write.body[0].lineno - 1,
                     '    import subprocess\n'
                     '    result = subprocess.run(' + repr(_CHECK) + ', capture_output=True, text=True, check=False)\n'
                     '    if result.returncode:\n'
                     '        raise RuntimeError(result.stderr.strip() or "Native fan ownership check failed")\n')
    adapted = ''.join(lines)
    compile(adapted, name, 'exec')
    return adapted.encode('utf-8')
