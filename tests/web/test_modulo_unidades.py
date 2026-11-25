"""CU: rejilla, balance, persistencia y bloqueos comprobados antes de escribir."""
from types import SimpleNamespace
from copy import deepcopy
import json
import unittest
from frontends.web.actions import Invalid, all_actions
from frontends.web.modulos import unidades
from scripts.qa.web.servicio_ejemplo import ConfiguracionEjemplo, ServicioEjemplo, CU

class PruebasUnidades(unittest.TestCase):

    def setUp(self):
        service = ServicioEjemplo()
        estado = deepcopy(CU)
        estado.update(masks=[7] * 4, driver_masks=[7] * 4, boot_sync_key='saved', service='active', persistence_supported=True)
        service.obtener_estado_cu_cache = lambda: deepcopy(estado)
        self.ctx = SimpleNamespace(service=service, settings=ConfiguracionEjemplo(), estado=estado)

    def test_lectura_y_telemetria_no_escriben(self):
        ctx = self.ctx
        datos = unidades.leer(ctx, None)
        assert not datos.get('error')
        assert len(datos['telemetry']) == 8
        assert datos['presentation']['active_cus'] == 24
        assert datos['selection']['rows'][0]['cells'][0]['token'] == 'D+'
        assert datos['selection']['rows'][0]['cells'][4]['token'] == '--'
        assert not ctx.service.llamadas

    def test_seleccion_y_balance_en_servidor(self):
        ctx = self.ctx
        resultado = unidades.consultar(SimpleNamespace(ctx=ctx), {'masks': json.dumps([31, 31, 15, 31])})
        assert resultado['target'] == 38
        assert not resultado['balanced']
        assert resultado['balanced_masks'] == [15, 31, 15, 31]
        assert resultado['pending'] == 7
        assert resultado['availability']['apply_live']
        assert resultado['rows'][0]['target'] == '0x1f'
        assert not ctx.service.llamadas

    def test_mascaras_invalidas_no_ejecutan(self):
        ctx = self.ctx
        for valor in [[], [1, 2, 3], [31, 31, 31, 32], [True, 1, 2, 3], ['7', 7, 7, 7], 'texto']:
            with self.subTest(valor=valor):
                with self.assertRaises(Invalid):
                    unidades.aplicar(ctx, {'masks': valor}, None)
                assert not ctx.service.llamadas

    def test_bloqueo_kernel_incluye_confirmaciones_anteriores(self):
        ctx = self.ctx
        _, trabajo = unidades.aplicar(ctx, {'masks': [31] * 4}, None)
        ctx.estado['kernel_managed'] = True
        with self.assertRaises(Invalid):
            trabajo()
        assert not ctx.service.llamadas
        datos = unidades.leer(ctx, None)
        assert datos['notice'] and (not datos['selection']['availability']['save_boot'])
        _, quitar = unidades.accion(ctx, {'name': 'remove_service'}, None)
        quitar()
        assert ctx.service.llamadas[-1][0] == 'ejecutar_accion_cu_grafica'

    def test_sin_backend_o_sin_lectura_autorizada_no_se_escribe(self):
        ctx = self.ctx
        for estado in [{'privileged_backend_ready': False}, {'available': False}, {'masks': []}]:
            with self.subTest(estado=estado):
                ctx.estado.update(estado)
                _, trabajo = unidades.aplicar(ctx, {'masks': [31] * 4}, None)
                with self.assertRaises(Invalid):
                    trabajo()
                assert not ctx.service.llamadas

    def test_acciones_con_confirmacion_y_servicio_existente(self):
        ctx = self.ctx
        for accion, parametros, metodo in [('cu.apply', {'masks': [31] * 4}, 'aplicar_tabla_cu'), ('cu.save', {'masks': [31] * 4}, 'guardar_tabla_cu'), ('cu.action', {'name': 'install_service'}, 'ejecutar_accion_cu_grafica'), ('cu.action', {'name': 'remove_service'}, 'ejecutar_accion_cu_grafica'), ('cu.action', {'name': 'factory'}, 'ejecutar_accion_cu_grafica'), ('cu.action', {'name': 'factory_repair'}, 'ejecutar_accion_cu_grafica'), ('cu.action', {'name': 'apply_saved'}, 'ejecutar_accion_cu_grafica'), ('cu.prepare', {}, 'instalar_dependencias_bc250')]:
            with self.subTest(accion=accion, parametros=parametros, metodo=metodo):
                ctx.service.llamadas.clear()
                nivel, trabajo = all_actions()[accion](ctx, parametros, None)
                assert nivel in (1, 2) and (not ctx.service.llamadas)
                trabajo()
                assert ctx.service.llamadas[-1][0] == metodo

    def test_sin_persistencia_se_conserva_control_en_vivo(self):
        ctx = self.ctx
        ctx.estado['persistence_supported'] = False
        plan = unidades.seleccion(ctx.estado, [31] * 4)['availability']
        assert plan['apply_live'] and (not plan['save_boot']) and (not plan['install_service'])

    def test_crudo_es_el_estado_autorizado(self):
        ctx = self.ctx
        nivel, trabajo = unidades.estado_crudo(ctx, {}, None)
        assert nivel == 0 and trabajo() == CU['raw']

    def test_telemetria_pmbus_y_fahrenheit(self):
        self.ctx.service.datos_metricas = {
            "vrm_source": "pmbus", "vrm_gpu_power_w": 72.5, "vrm_temp_gpu": 60.0,
            "gpu_temp": 50.0, "fan_rpm": 1200, "gpu_busy": 0,
        }
        self.ctx.settings.save_local_config({"temperature_unit": "fahrenheit"})
        datos = unidades.leer(self.ctx, None)
        valores = {item["label"]: item["value"] for item in datos["telemetry"]}
        assert valores["GPU power"] == "72.5 W"
        assert valores["VRM temperature"] == "140 °F"
        assert valores["Fan speed"] == "1200 RPM"

    def test_lectura_fallida_se_presenta(self):
        def falla():
            raise RuntimeError("Ejemplo de lectura fallida")
        self.ctx.service.obtener_estado_cu_cache = falla
        assert unidades.leer(self.ctx, None)["error"] == "Ejemplo de lectura fallida"
