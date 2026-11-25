"""Regresiones de integración, con servicios simulados y sin acceso al equipo."""
from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from frontends.desktop.i18n import current_language, set_language
from frontends.tui.i18n import tr
from frontends.tui.runtime import Context
from frontends.web.actions import Invalid, all_actions
from frontends.web.modulos import gpu, panel, rendimiento, unidades
from scripts.qa.web.servicio_ejemplo import ConfiguracionEjemplo, ServicioEjemplo


@pytest.fixture
def contexto():
    servicio = ServicioEjemplo()
    estado = servicio.estado_bc250()
    estado.update(range_control_ok=True, dbus_ok=True)
    servicio.datos_gpu = estado
    return SimpleNamespace(service=servicio, settings=ConfiguracionEjemplo())


@pytest.fixture
def idioma_espanol():
    anterior = current_language()
    set_language("es")
    yield
    set_language(anterior)


def test_rango_usa_la_politica_del_escritorio(contexto):
    revision = gpu.revisar_rango(SimpleNamespace(ctx=contexto), {"min": "1000", "max": "1850"})
    assert revision["risk"]
    assert tr("Do not change frequency while a game, FurMark, or another 3D workload is active.") in revision["message"]
    assert tr("This updates only the active Cyan range through D-Bus. Persistent TOML limits are left unchanged; "
              "advanced safe-points are loaded only when explicitly enabled.") in revision["message"]
    assert contexto.service.llamadas == []


@pytest.mark.parametrize("cambio", [
    {"range_control_ok": False},
    {"tools": {"incompatible_gpu_governors": ["otro"]}},
    {"safe_points_error": "configuración inválida"},
    {"safe_points_duplicate_frequencies": [1500]},
    {"safe_points_missing_voltage": [{"frequency": 1500}]},
    {"safe_points_voltage_errors": [{"frequency": 1500}]},
    {"allowed_max": 1500},
    {"safe_points": []},
])
def test_rango_se_revalida_al_ejecutar(contexto, cambio):
    _, ejecutar = all_actions()["gpu.profile"](contexto, {"min": 1000, "max": 1850}, None)
    contexto.service.datos_gpu.update(cambio)
    with pytest.raises(Invalid):
        ejecutar()
    with pytest.raises(Invalid):
        gpu.revisar_rango(SimpleNamespace(ctx=contexto), {"min": "1000", "max": "1850"})
    assert contexto.service.llamadas == []


def test_rango_interpolado_valido_llega_al_servicio(contexto):
    nivel, ejecutar = all_actions()["gpu.profile"](contexto, {"min": 700, "max": 1600}, None)
    assert nivel == 1
    ejecutar()
    assert contexto.service.llamadas == [("aplicar_perfil_gpu", (700, 1600), {})]


def test_bajada_brusca_muestra_el_aviso_del_escritorio(contexto):
    contexto.service.datos_gpu.update(current_max=2000, gpu_busy=80, sclk_actual=1900)
    revision = gpu.revisar_rango(SimpleNamespace(ctx=contexto), {"min": "500", "max": "1500"})
    assert "80" in revision["message"] and "2000" in revision["message"]


def test_oberon_rechaza_perfiles_arbitrarios(contexto):
    contexto.service.datos_gpu["governor_backend"] = "oberon-governor"
    _, ejecutar = all_actions()["gpu.profile"](contexto, {"min": 1000, "max": 1700}, None)
    with pytest.raises(Invalid):
        ejecutar()
    assert contexto.service.llamadas == []


@pytest.mark.parametrize("accion,parametros,cambio", [
    ("gpu.voltage", {"level": 1}, {"governor_backend": "oberon-governor"}),
    ("gpu.voltage", {"level": 1}, {"service_active": "inactive"}),
    ("gpu.voltage_custom", {"values": {"500": 705}}, {"service_active": "inactive"}),
    ("gpu.compat", {"set_method": "smu", "usage_method": "busy-flag", "metrics": True,
                    "frequencies": False, "temp_read": "drm"}, {"governor_backend": "oberon-governor"}),
    ("gpu.high_points", {"enable": True}, {"high_frequency_points": {"available": False}}),
    ("gpu.high_points", {"enable": True}, {"tools": {"incompatible_gpu_governors": ["otro"]}}),
    ("gpu.save_boot", {}, {"current_min": 0, "current_max": 0}),
    ("gpu.save_boot", {}, {"governor_backend": "oberon-governor"}),
    ("gpu.service", {"action": "reiniciar"}, {"service_active": "inactive"}),
    ("gpu.service", {"action": "activar"}, {"service_active": "active", "service_enabled": "enabled"}),
    ("gpu.service", {"action": "desactivar"}, {"service_active": "inactive", "service_enabled": "disabled"}),
])
def test_acciones_gpu_comprueban_disponibilidad_actual(contexto, accion, parametros, cambio):
    _, ejecutar = all_actions()[accion](contexto, parametros, None)
    contexto.service.datos_gpu.update(cambio)
    with pytest.raises(Invalid):
        ejecutar()
    assert contexto.service.llamadas == []


def test_disponibilidad_gpu_distingue_servicio_y_rango(contexto):
    contexto.service.datos_gpu.update(range_control_ok=False, service_active="inactive", service_enabled="enabled")
    disponible = gpu.leer(contexto, None)["availability"]
    assert not disponible["range"] and not disponible["restart"]
    assert disponible["start"] and disponible["stop"]


def test_errores_de_lectura_no_exponen_excepciones(contexto, idioma_espanol):
    contexto.service.estado_bc250 = Mock(side_effect=RuntimeError("secreto /ruta/interna"))
    assert gpu.leer(contexto, None) == {"error": tr("Read error")}
    contexto.service.obtener_estado_cu_cache = Mock(side_effect=RuntimeError("secreto /ruta/interna"))
    assert unidades.leer(contexto, None) == {"error": tr("Could not read the CU map.")}


def test_cu_traduce_confirmaciones_y_guia(contexto, idioma_espanol):
    resultado = unidades.leer(contexto, None)
    assert "error" not in resultado
    assert resultado["confirmations"]["apply"]["title"] == tr("Apply WGP routing table")
    assert resultado["guide"]["title"] == tr("CU stability validation")
    assert resultado["guide"]["message"] == tr(unidades.GUIA_VALIDACION)
    assert resultado["telemetry"][0]["label"] == tr("Service")


@pytest.mark.parametrize("nombre", ["cu.raw", "cu.sync", "cu.prepare", "gpu.save_boot"])
def test_acciones_sin_parametros_rechazan_campos_del_navegador(contexto, nombre):
    with pytest.raises(Invalid):
        all_actions()[nombre](contexto, {"command": "arbitrario"}, None)
    assert contexto.service.llamadas == []


def test_cu_preparacion_respeta_el_kernel_al_ejecutar(contexto):
    estado = contexto.service.obtener_estado_cu_cache()
    contexto.service.obtener_estado_cu_cache = Mock(return_value=estado)
    _, ejecutar = unidades.preparar(contexto, {}, None)
    estado["kernel_managed"] = True
    with pytest.raises(Invalid):
        ejecutar()
    assert contexto.service.llamadas == []


def test_panel_traduce_textos_sin_cambiar_identificadores(idioma_espanol):
    original = {"quick_access": {"label": "Preview", "message": "Not detected"},
                "components": [{"key": "governor", "title": "Governor", "available": True}]}
    copia = deepcopy(original)
    resultado = panel.traducir_presentacion(original)
    assert resultado["quick_access"]["label"] == tr("Preview")
    assert resultado["components"][0]["title"] == tr("Governor")
    assert resultado["components"][0]["key"] == "governor"
    assert original == copia


@pytest.mark.parametrize("parametros", [{"q": []}, {"kinds": None}, {"tab": {}}, {"window": True}])
def test_rendimiento_rechaza_tipos_invalidos_antes_de_leer(parametros):
    with pytest.raises(Invalid):
        rendimiento.consultar(SimpleNamespace(), parametros)


def test_rendimiento_no_expone_error_crudo(idioma_espanol):
    contexto = SimpleNamespace(settings=ConfiguracionEjemplo(), metrics_error="secreto /ruta/interna")
    resultado = rendimiento.leer_preferencias(contexto, SimpleNamespace(recorder=SimpleNamespace(sampled_at="12:00")))
    assert resultado["error"] == tr("Read error")


def test_laboratorio_inactivo_no_ofrece_aplicar(contexto):
    contexto.service.datos_gpu["service_active"] = "inactive"
    resultado = gpu.laboratorio(SimpleNamespace(ctx=contexto), {"level": "1"})
    assert resultado["rows"] and not resultado["available"]
    assert resultado["error"] == tr("The Cyan governor must be active before changing its voltage curve.")


def test_confirmacion_personalizada_usa_claves_existentes(idioma_espanol):
    confirmacion = gpu.confirmacion_voltaje(-1)["confirmation"]
    assert confirmacion["title"] == tr("Custom voltage laboratory")
    assert tr("Only mV voltages in existing TOML safe-points are modified.") in confirmacion["message"]


def test_panel_oculta_el_error_interno_y_traduce_decky(idioma_espanol):
    contexto = Context(service=ServicioEjemplo(), settings=ConfiguracionEjemplo())
    contexto.metrics = contexto.service.metricas_tiempo_real()
    contexto.metrics_error = "secreto /ruta/interna"
    resultado = panel.leer(contexto, SimpleNamespace(gddr6={}))
    assert resultado["error"] == tr("Read error")
    assert resultado["quick_access"]["label"] == tr("Install / repair BC250 Quick Access")
    assert contexto.service.llamadas == []


def test_ningun_rango_supera_el_tope_de_la_pagina():
    for altos, tope in (({}, 2000), ({"enabled": True}, 2400), ({"enabled": True, "ceiling_mhz": 2150}, 2150)):
        assert gpu.techo_de({"high_frequency_points": altos}) == tope
    estado = {"governor_backend": "cyan-skillfish-governor-smu", "dbus_ok": True, "allowed_max": 2400}
    with pytest.raises(Invalid):
        gpu.validar_rango(estado, 1000, 2100)
