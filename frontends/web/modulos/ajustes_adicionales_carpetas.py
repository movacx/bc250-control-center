"""Selector de juegos: sólo directorios del inventario y raíces de juegos.

No acepta una ruta del navegador, no sigue enlaces y no enumera documentos
personales. La lista se reconstruye al ejecutar, antes de entregar la ruta al
servicio, que comprueba los archivos del juego y conserva sus copias.
"""
from pathlib import Path


def carpetas_disponibles(datos):
    tools = datos.get("tools") or {}
    carpetas = set()
    for herramienta in ("fsr4", "helixsr"):
        estado = tools.get(herramienta) or {}
        for grupo in ("games", "bridge_games", "scaler_games"):
            for juego in estado.get(grupo) or ():
                ruta = juego.get("folder") or juego.get("install")
                if ruta:
                    candidato = Path(ruta)
                    if candidato.is_absolute() and not candidato.is_symlink() and candidato.is_dir():
                        carpetas.add(str(candidato.resolve()))
    # Las bibliotecas ya identificadas por el servicio y ~/Games permiten
    # añadir juegos ajenos a Steam sin un campo de rutas libres.
    raices = [Path.home() / "Games"]
    for ruta in tools.get("game_roots") or ():
        raices.append(Path(ruta))
    pendientes = [(raiz, 0) for raiz in raices]
    while pendientes and len(carpetas) < 1024:
        ruta, profundidad = pendientes.pop()
        if ruta.is_symlink() or not ruta.is_dir():
            continue
        if profundidad:
            carpetas.add(str(ruta.resolve()))
        if profundidad >= 4:
            continue
        try:
            hijos = sorted(ruta.iterdir())[:256]
        except OSError:
            continue
        for hijo in hijos:
            if not hijo.name.startswith(".") and not hijo.is_symlink() and hijo.is_dir():
                pendientes.append((hijo, profundidad + 1))
    return tuple(sorted(carpetas))
