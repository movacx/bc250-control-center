"""Pruebas sin red ni Qt; también las descubre pytest cuando esté disponible."""
import sys
import unittest
from unittest.mock import patch

from scripts.qa.web.servicio_ejemplo import ServicioEjemplo, ConfiguracionEjemplo
from frontends.tui.runtime import Context
from frontends.web.data import Live
from frontends.web.actions import Invalid, all_actions
from frontends.web.modulos import panel


class PruebasPanel(unittest.TestCase):
    def setUp(self):
        self.ctx = Context(service=ServicioEjemplo(), settings=ConfiguracionEjemplo())
        self.ctx.metrics = self.ctx.service.metricas_tiempo_real()

    def test_lecturas_completas_sin_qt(self):
        datos = Live(self.ctx).reading("dashboard")
        self.assertEqual([card["key"] for card in datos["cards"]], ["cpu", "gpu", "fans"])
        self.assertEqual(len(datos["cores"]), 8)
        self.assertEqual(len(datos["components"]), 7)
        self.assertEqual(len(datos["rails"]), 8)
        self.assertTrue(datos["repositories"])
        self.assertEqual(len(datos["links"]), 4)
        self.assertEqual(datos["quick_access"]["label"], "Install / repair BC250 Quick Access")
        self.assertEqual(self.ctx.service.llamadas, [])
        self.assertFalse(any(nombre.startswith("PyQt6") for nombre in sys.modules))

    def test_rechaza_componentes_sin_ejecutar(self):
        for seleccion in ([], ["runtime", "evil"], ["runtime", "runtime"], ["umr"],
                          ["runtime", "cu_manager"], "runtime", [True], ["runtime", {}]):
            with self.subTest(seleccion=seleccion), self.assertRaises(Invalid):
                panel.preparar(self.ctx, {"components": seleccion, "governor": "auto"}, None)
        self.assertFalse(self.ctx.service.llamadas)

    def test_preparar_componentes_exactos_y_confirmacion(self):
        for seleccion in (["runtime"], ["runtime", "umr", "cu_manager"], list(panel.CLAVES)):
            with self.subTest(seleccion=seleccion):
                nivel, trabajo = panel.preparar(self.ctx, {"components": seleccion, "governor": "auto"}, None)
                self.assertEqual(nivel, 1)
                trabajo()
                self.assertEqual(self.ctx.service.llamadas[-1], ("instalar_dependencias_bc250", (), {
                    "components": seleccion, "governor_preference": "auto", "include_pwm": "fan_pwm" in seleccion}))

    def test_revalida_capacidad_antes_del_trabajo(self):
        _, trabajo = panel.preparar(self.ctx, {"components": ["runtime"], "governor": "auto"}, None)
        self.ctx.service.estado_herramientas_bc250 = lambda: {"prepare_components": {"runtime": {"available": False}}}
        with self.assertRaises(Invalid):
            trabajo()
        self.assertFalse(self.ctx.service.llamadas)

    def test_decky_reparacion_o_instalacion(self):
        for compatible, esperado in ((True, False), (False, True)):
            self.ctx.service.estado_herramientas_bc250 = lambda: {"quick_access": {"supported": True,
                "decky_detected": True, "decky_frontend_compatible": compatible, "decky_plugin_root_safe": True}}
            nivel, trabajo = panel.decky(self.ctx, {}, None)
            self.assertEqual(nivel, 2)
            trabajo()
            self.assertEqual(self.ctx.service.llamadas[-1], ("preparar_quick_access_steamos", (), {"install_decky": esperado}))

    def test_decky_bloquea_ruta_no_segura(self):
        self.ctx.service.estado_herramientas_bc250 = lambda: {"quick_access": {"supported": True, "decky_plugin_root_safe": False}}
        _, trabajo = panel.decky(self.ctx, {}, None)
        with self.assertRaises(Invalid):
            trabajo()
        self.assertFalse(self.ctx.service.llamadas)

    def test_preparar_memoria_pasa_por_consola(self):
        consola = []
        nivel, trabajo = all_actions()["gddr6.prepare"](self.ctx, {}, consola.append)
        self.assertEqual(nivel, 1)
        self.assertFalse(consola)
        trabajo()
        self.assertEqual(consola, ["comando_preparar_gddr6_memory_temp: ejemplo"])

    def test_acciones_sin_parametros_rechazan_texto(self):
        for accion in (panel.preparar_memoria, panel.reparar_vrm, panel.reparar_telemetria, panel.decky):
            with self.subTest(accion=accion.__name__), self.assertRaises(Invalid):
                accion(self.ctx, {"command": "untrusted"}, None)
        self.assertFalse(self.ctx.service.llamadas)

    def test_actualizacion_sin_red(self):
        from bc250cc.domain.updates import UpdateStatus
        with patch("bc250cc.infrastructure.release_check.check_for_update", return_value=UpdateStatus("1.0", "2.0", reachable=True)):
            self.assertTrue(panel.actualizacion(None, {})["available"])

    def test_conflicto_requiere_consentimiento_explicito(self):
        self.ctx.service.estado_herramientas_bc250 = lambda: {"incompatible_gpu_governors": [{"identifier": "oberon-governor"}]}
        parametros = {"components": ["runtime", "governor"], "governor": "auto"}
        _, trabajo = panel.preparar(self.ctx, parametros, None)
        with self.assertRaises(Invalid):
            trabajo()
        self.assertFalse(self.ctx.service.llamadas)
        nivel, trabajo = panel.preparar(self.ctx, {**parametros, "disable_conflicts": True}, None)
        self.assertEqual(nivel, 2)
        trabajo()
        self.assertTrue(self.ctx.service.llamadas[-1][2]["desactivar_conflictos"])
        self.assertTrue(self.ctx.service.llamadas[-1][2]["confirmar_conflictos"])

    def test_reparaciones_despachan_servicios_sin_texto_libre(self):
        for construir, nombre in ((panel.reparar_vrm, "reiniciar_sensor_vrm"),
                                  (panel.reparar_telemetria, "reparar_telemetria_8core")):
            nivel, trabajo = construir(self.ctx, {}, None)
            self.assertEqual(nivel, 1)
            trabajo()
            self.assertEqual(self.ctx.service.llamadas[-1], (nombre, (), {}))

    def test_monitor_memoria_solo_con_guardas_y_sesion_acotada(self):
        self.ctx.service.estado_gddr6_memory_temp = lambda: {"hardware_detected": True, "repository_ready": True,
            "reader_ready": True, "helper_ready": True, "firmware_supported": True, "payload_present": True}
        consola = []
        nivel, trabajo = all_actions()["gddr6.monitor"](self.ctx, {}, consola.append)
        self.assertEqual(nivel, 2)
        trabajo()
        self.assertEqual(self.ctx.service.llamadas[-1], ("comando_monitorizar_vram", (600,), {}))
        self.assertEqual(len(consola), 1)
        self.ctx.service.estado_gddr6_memory_temp = lambda: {"external": {"state": "active"}}
        with self.assertRaises(Invalid):
            trabajo()
        self.assertEqual(len(consola), 1)

    def test_guardas_memoria_copiadas_sin_cambios_del_escritorio(self):
        import ast
        from pathlib import Path
        original = ast.parse(Path("frontends/desktop/core/gddr6_monitor.py").read_text())
        modelo = ast.parse(Path("frontends/web/modulos/panel_modelo_memoria.py").read_text())
        for nombre in ("Gddr6Reading", "Gddr6Chip", "firmware_blocker"):
            primero = next(item for item in original.body if getattr(item, "name", None) == nombre)
            segundo = next(item for item in modelo.body if getattr(item, "name", None) == nombre)
            self.assertEqual(ast.dump(primero), ast.dump(segundo))
