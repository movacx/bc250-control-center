"""Grabador y filtros con muestras conocidas; se ejecutan también con unittest."""
from types import SimpleNamespace
import unittest

from scripts.qa.web.servicio_ejemplo import ServicioEjemplo, ConfiguracionEjemplo, InventarioSensoresEjemplo
from frontends.tui.runtime import Context
from frontends.desktop.core.performance_model import PerformanceRecorder, KIND_FILTERS
from frontends.desktop.core.performance_views import views_for
from frontends.web.actions import Invalid
from frontends.web.modulos import rendimiento


class PruebasRendimiento(unittest.TestCase):
    def setUp(self):
        ctx = Context(service=ServicioEjemplo(), settings=ConfiguracionEjemplo())
        grabador = PerformanceRecorder(inventory=InventarioSensoresEjemplo())
        for _ in range(3):
            grabador.record(ctx.service.metricas_tiempo_real())
        ctx.state("performance")["recorder"] = grabador
        self.web = SimpleNamespace(ctx=ctx, live=SimpleNamespace(ctx=ctx, recorder=grabador))

    def test_recursos_y_cada_vista(self):
        for tab in ("cpu", "gpu", "vram", "memory", "disk", "network"):
            for vista in [tab] + [vista.key for vista in views_for(tab)]:
                with self.subTest(tab=tab, vista=vista):
                    datos = rendimiento.consultar(self.web, {"tab": tab, "view": vista})
                    self.assertEqual(datos["tab"], tab)
                    self.assertEqual(datos["view"], vista)
                    if datos.get("chart"):
                        self.assertGreater(datos["chart"]["max"], datos["chart"]["min"])
                        self.assertTrue(datos["chart"]["ages"])
        self.assertEqual(self.web.live.recorder.depth, 1801)

    def test_filtros_y_seleccion_multiple(self):
        datos = rendimiento.consultar(self.web, {"hide": "0", "ticked": "cpu/usage,gpu/usage"})
        self.assertEqual({traza["key"] for traza in datos["traces"]}, {"cpu/usage", "gpu/usage"})
        tipos = [i for i, (_label, kinds) in enumerate(KIND_FILTERS) if "temperature" in kinds or "clock" in kinds]
        filtrados = rendimiento.consultar(self.web, {"kinds": ",".join(map(str, tipos))})
        for fila in filtrados["rows"]:
            if "key" in fila:
                self.assertIn(self.web.live.recorder.log.entries[fila["key"]].reading.kind,
                              {kind for i in tipos for kind in KIND_FILTERS[i][1]})
        datos = rendimiento.consultar(self.web, {"q": "MCLK", "hide": "0", "ticked": "gpu/mclk,cpu/usage"})
        self.assertEqual([fila["key"] for fila in datos["rows"] if "key" in fila], ["gpu/mclk"])
        self.assertEqual([traza["key"] for traza in datos["traces"]], ["gpu/mclk"])
        self.assertEqual(set(datos["ticked"]), {"gpu/mclk", "cpu/usage"})

    def test_ocultar_cero_y_reiniciar_conserva_historial(self):
        datos = rendimiento.consultar(self.web, {})
        self.assertNotIn("gpu/unused", {fila.get("key") for fila in datos["rows"]})
        datos = rendimiento.consultar(self.web, {"hide": "0"})
        self.assertIn("gpu/unused", {fila.get("key") for fila in datos["rows"]})
        log = self.web.live.recorder.log
        antes = list(log.entries["cpu/usage"].trace)
        rendimiento.reiniciar(self.web.ctx, {})
        self.assertIsNone(log.entries["cpu/usage"].minimum)
        self.assertEqual(list(log.entries["cpu/usage"].trace), antes)

    def test_ventana_escala_y_retencion(self):
        antes = self.web.live.recorder.window
        datos = rendimiento.consultar(self.web, {"tab": "cpu", "scale": "fixed", "window": "60"})
        self.assertEqual(datos["chart"]["max"], 100)
        self.assertEqual(datos["window"], 60)
        self.assertEqual(self.web.live.recorder.window, antes)
        self.assertEqual(self.web.live.recorder.histories["cpu"].times.maxlen, 1801)

    def test_parametros_fuera_de_listas(self):
        for parametros in ({"tab": "bad"}, {"tab": "cpu", "view": "gpu.voltage"}, {"scale": "bad"},
                           {"window": "1"}, {"window": "abc"}, {"kind": "-1"}, {"kinds": "-1,2"},
                           {"kinds": "xyz"}, {"hide": "yes"}, {"q": "a" * 161}, {"ticked": "x" * 16385}):
            with self.subTest(parametros=parametros), self.assertRaises(Invalid):
                rendimiento.consultar(self.web, parametros)

    def test_preferencias_y_validacion(self):
        parametros = {"layout": "graphs", "hide": False, "window": 600, "kinds": [1, 2], "ticked": ["cpu/usage"]}
        rendimiento.guardar_preferencias(self.web.ctx, parametros)
        self.assertEqual(rendimiento.leer_preferencias(self.web.ctx, self.web.live)["preferences"], parametros)
        for clave, valor in (("window", True), ("window", 100), ("kinds", [True]), ("layout", "unsafe"),
                             ("hide", 1), ("ticked", ["x" * 257])):
            with self.subTest(clave=clave, valor=valor), self.assertRaises(Invalid):
                rendimiento.guardar_preferencias(self.web.ctx, {**parametros, clave: valor})

    def test_ventana_recorta_trazas_sin_borrar_estadisticas(self):
        import time
        entrada = self.web.live.recorder.log.entries["cpu/usage"]
        entrada.trace.clear()
        entrada.trace.extend([(time.monotonic() - 90, 90.0), (time.monotonic(), 16.0)])
        datos = rendimiento.consultar(self.web, {"window": "60", "ticked": "cpu/usage"})
        grafica = datos["traces"][0]["chart"]
        self.assertEqual(grafica["series"][0]["values"], [16.0])
        self.assertLessEqual(max(grafica["ages"]), 60)
        self.assertEqual(len(entrada.trace), 2)
