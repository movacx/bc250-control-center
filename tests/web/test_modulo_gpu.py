"""El servicio de ejemplo cubre perfiles, laboratorio y los límites de las acciones GPU."""
import json
import subprocess
import sys
import unittest
from types import SimpleNamespace

from bc250cc.domain.gpu.oberon import OBERON_DESKTOP_PROFILES
from frontends.web.actions import Invalid, all_actions
from frontends.web.modulos import gpu
from scripts.qa.web.servicio_ejemplo import ConfiguracionEjemplo, ServicioEjemplo


class PruebasGpu(unittest.TestCase):

    def setUp(self):
        self.ctx = SimpleNamespace(service=ServicioEjemplo(), settings=ConfiguracionEjemplo())

    def test_modulos_importan_sin_qt(self):
        resultado = subprocess.run([sys.executable, '-c', "import frontends.web.modulos; import sys; assert not any(k.startswith('PyQt6') for k in sys.modules)"], capture_output=True, text=True)
        assert resultado.returncode == 0, resultado.stderr

    def test_lectura_perfiles_y_edicion_persistente(self):
        ctx = self.ctx
        datos = gpu.leer(ctx, None)
        assert not datos.get('error')
        assert len(datos['profiles']) == 3 and len(datos['rail']) > 10
        cambiado = {'key': 'gaming', 'name': 'Mi perfil', 'min': 1000, 'max': 1700}
        gpu.guardar_perfil(ctx, cambiado)
        assert gpu.leer(ctx, None)['profiles'][1] == {**cambiado, 'voltage': '800 – 950 mV'}
        assert not ctx.service.llamadas

    def test_editor_rechaza_perfiles_invalidos(self):
        ctx = self.ctx
        for cambio in [{'key': 'x'}, {'name': ''}, {'min': True}, {'max': 3001}, {'min': 2001, 'max': 2000}]:
            with self.subTest(cambio=cambio):
                perfil = {'key': 'gaming', 'name': 'Gaming', 'min': 1000, 'max': 1850, **cambio}
                with self.assertRaises(Invalid):
                    gpu.guardar_perfil(ctx, perfil)
                assert not ctx.service.llamadas

    def test_exporta_los_tres_perfiles_guardados(self):
        ctx = self.ctx
        gpu.guardar_perfil(ctx, {'key': 'balanced', 'name': 'Local', 'min': 700, 'max': 1500})
        nivel, trabajo = gpu.exportar(ctx, {}, None)
        assert nivel == 1
        trabajo()
        llamada = ctx.service.llamadas[0]
        assert llamada[0] == 'exportar_perfiles_gpu_decky'
        assert len(llamada[1][0]) == 3 and llamada[1][0][0]['name'] == 'Local'

    def test_laboratorio_previsualiza_todos_los_niveles(self):
        ctx = self.ctx
        for nivel in range(7):
            with self.subTest(nivel=nivel):
                tabla = gpu.laboratorio(SimpleNamespace(ctx=ctx), {'level': str(nivel)})
                assert tabla['rows'] and tabla['available']
                assert tabla['peak'] >= 1000
                assert not ctx.service.llamadas

    def test_laboratorio_personalizado_y_curva_descendente(self):
        ctx = self.ctx
        web = SimpleNamespace(ctx=ctx)
        datos = gpu.laboratorio(web, {'level': '-1', 'values': json.dumps({'500': 805})})
        assert not datos['available'] and datos['error']
        datos = gpu.laboratorio(web, {'level': '-1', 'values': json.dumps({'500': 705})})
        assert datos['available'] and datos['changed'] == 1
        with self.assertRaises(Invalid):
            gpu.laboratorio(web, {'level': '-1', 'values': '{"777":800}'})

    def test_oberon_perfiles_fijos_laboratorio_solo_lectura(self):
        ctx = self.ctx
        original = ctx.service.estado_bc250()
        ctx.service.estado_bc250 = lambda: {**original, 'governor_backend': 'oberon-governor'}
        assert gpu.leer(ctx, None)['profiles'][2]['min'] == OBERON_DESKTOP_PROFILES[2][0]
        assert not gpu.laboratorio(SimpleNamespace(ctx=ctx), {'level': '3'})['available']

    def test_conflictos_del_servicio_se_presentan_y_se_resuelven(self):
        ctx = self.ctx
        ctx.service.estado_bc250 = lambda: {'tools': {'incompatible_gpu_governors': ['oberon-governor']}}
        datos = gpu.leer(ctx, None)
        assert 'oberon-governor' in datos['service_plans']['activar']['message']
        nivel, trabajo = gpu.servicio(ctx, {'action': 'activar'}, None)
        assert nivel > 0
        trabajo()
        assert ctx.service.llamadas[-1] == ('controlar_governor', ('activar', True, True), {})

    def test_acciones_solo_llaman_al_servicio(self):
        ctx = self.ctx
        for accion, parametros, metodo in [('gpu.profile', {'min': 1000, 'max': 1850}, 'aplicar_perfil_gpu'), ('gpu.compat', {'set_method': 'kernel', 'usage_method': 'kernel', 'metrics': False, 'frequencies': False, 'temp_read': 'sysfs'}, 'configurar_compatibilidad_gpu_cyan'), ('gpu.high_points', {'enable': True}, 'alternar_puntos_gpu_altos'), ('gpu.voltage', {'level': 3}, 'aplicar_laboratorio_voltaje_gpu'), ('gpu.voltage_custom', {'values': {'500': 705}}, 'aplicar_laboratorio_voltaje_gpu_personalizado'), ('gpu.save_boot', {}, 'guardar_rango_gpu_arranque')]:
            with self.subTest(accion=accion, parametros=parametros, metodo=metodo):
                ctx.service.llamadas.clear()
                nivel, trabajo = all_actions()[accion](ctx, parametros, lambda _: self.fail('No hay comandos del navegador'))
                assert nivel in (1, 2)
                assert not ctx.service.llamadas
                trabajo()
                assert ctx.service.llamadas[-1][0] == metodo

    def test_revision_de_rango_y_limites(self):
        web = SimpleNamespace(ctx=self.ctx)
        revision = gpu.revisar_rango(web, {"min": "1000", "max": "1850"})
        assert revision["max"] == 1850 and revision["message"]
        for valores in ({"min": "500", "max": "2400"}, {"min": "2000", "max": "1000"}, {"min": "x", "max": "1000"}):
            with self.subTest(valores=valores), self.assertRaises(Invalid):
                gpu.revisar_rango(web, valores)
        assert not self.ctx.service.llamadas

    def test_configuracion_solo_abre_una_ruta_cerrada(self):
        from io import StringIO
        from unittest.mock import MagicMock, patch
        archivo = MagicMock()
        archivo.is_symlink.return_value = False
        archivo.open.return_value.__enter__.side_effect = lambda: StringIO("[gpu]\nset-method='smu'\n")
        with patch.object(gpu, "Path", return_value=archivo) as ruta:
            datos = gpu.configuracion(SimpleNamespace(ctx=self.ctx), {"path": "/otro/archivo"})
            ruta.assert_called_once_with("/etc/cyan-skillfish-governor-smu/config.toml")
            assert "set-method" in datos["text"]
        archivo.is_symlink.return_value = True
        with patch.object(gpu, "Path", return_value=archivo):
            assert gpu.configuracion(SimpleNamespace(ctx=self.ctx), {})["error"]

    def test_apertura_del_laboratorio_selecciona_la_curva_real(self):
        from bc250cc.domain.gpu.voltage_profiles import voltage_profile
        original = self.ctx.service.estado_bc250()
        assert gpu.leer(self.ctx, None)["opening_level"] == -1
        for nivel, esperado in ((0, 1), (1, 1), (3, 3), (6, -1)):
            with self.subTest(nivel=nivel):
                self.ctx.service.datos_gpu = {**original, "safe_points_with_voltage": [
                    {"frequency": f, "voltage": v} for f, v in voltage_profile(nivel).items()]}
                assert gpu.leer(self.ctx, None)["opening_level"] == esperado

    def test_estado_vacio_y_error_se_presentan(self):
        self.ctx.service.datos_gpu = {}
        assert gpu.leer(self.ctx, None)["empty"]
        def falla():
            raise RuntimeError("Ejemplo de lectura fallida")
        self.ctx.service.estado_bc250 = falla
        assert gpu.leer(self.ctx, None)["error"] == "Ejemplo de lectura fallida"
