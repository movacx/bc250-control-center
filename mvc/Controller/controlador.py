class Controlador:
    def __init__(self, servicio):
        self.servicio = servicio

    def rendimiento(self):
        return self.servicio.rendimiento()

    def procesos(self, ocultar_sistema=True):
        return self.servicio.procesos(ocultar_sistema)

    def cerrar(self, procesos):
        self.servicio.cerrar_procesos(procesos)

    def limpiar_cache(self):
        self.servicio.limpiar_cache()


    def registrar_evento(self, tipo, nivel, titulo, detalle='', datos=None):
        return self.servicio.registrar_evento(tipo, nivel, titulo, detalle, datos)

    def obtener_eventos(self, limite=300):
        return self.servicio.obtener_eventos(limite)

    def limpiar_historial(self):
        return self.servicio.limpiar_historial()



    def config_paths(self):
        return self.servicio.config_paths()

    def leer_config_local(self):
        return self.servicio.leer_config_local()

    def guardar_config_local(self, datos):
        return self.servicio.guardar_config_local(datos)

    def leer_perfiles_locales(self):
        return self.servicio.leer_perfiles_locales()

    def registrar_metrica_runtime(self, datos):
        return self.servicio.registrar_metrica_runtime(datos)

    def evaluar_presion_memoria(self):
        return self.servicio.evaluar_presion_memoria()

    def candidatos_cierre_memoria(self, limite=10):
        return self.servicio.candidatos_cierre_memoria(limite)

    def proteccion_memoria(self, aplicar=False):
        return self.servicio.proteccion_memoria(aplicar)

    def estado_bc250(self):
        return self.servicio.estado_bc250()

    def aplicar_rango_bc250(self, minimo, maximo):
        return self.servicio.aplicar_rango_bc250(minimo, maximo)

    def fijar_frecuencia_bc250(self, frecuencia):
        return self.servicio.fijar_frecuencia_bc250(frecuencia)

    def estado_herramientas_bc250(self):
        return self.servicio.estado_herramientas_bc250()

    def instalar_dependencias_bc250(self):
        return self.servicio.instalar_dependencias_bc250()

    def instalar_governor(self):
        return self.servicio.instalar_governor()

    def controlar_governor(self, accion):
        return self.servicio.controlar_governor(accion)

    def status_governor(self):
        return self.servicio.status_governor()

    def abrir_laboratorio_voltaje_gpu(self):
        return self.servicio.abrir_laboratorio_voltaje_gpu()

    def aplicar_laboratorio_voltaje_gpu(self, nivel):
        return self.servicio.aplicar_laboratorio_voltaje_gpu(nivel)

    def aplicar_laboratorio_voltaje_gpu_personalizado(self, valores):
        return self.servicio.aplicar_laboratorio_voltaje_gpu_personalizado(valores)

    def instalar_cpu_oc(self):
        return self.servicio.instalar_cpu_oc()

    def instalar_umr(self):
        return self.servicio.instalar_umr()

    def ejecutar_cpu_oc_temporal(self, frecuencia, vid, temp=90):
        return self.servicio.ejecutar_cpu_oc_temporal(frecuencia, vid, temp)

    def comando_cpu_oc_temporal_embebido(self, frecuencia, vid, temp=90):
        return self.servicio.comando_cpu_oc_temporal_embebido(frecuencia, vid, temp)

    def comando_cpu_oc_persistente_embebido(self):
        return self.servicio.comando_cpu_oc_persistente_embebido()

    def estado_cpu_oc_persistente(self):
        return self.servicio.estado_cpu_oc_persistente()

    def comando_cpu_oc_desactivar_persistente_embebido(self):
        return self.servicio.comando_cpu_oc_desactivar_persistente_embebido()

    def obtener_mapa_cu(self):
        return self.servicio.obtener_mapa_cu()

    def obtener_dashboard_cu(self):
        return self.servicio.obtener_dashboard_cu()

    def ejecutar_cu_manager(self, accion):
        return self.servicio.ejecutar_cu_manager(accion)

    def estado_fans_bc250(self):
        return self.servicio.estado_fans_bc250()

    def cargar_nct6683_solo_lectura(self):
        return self.servicio.cargar_nct6683_solo_lectura()

    def preparar_nct6687_control_pwm(self):
        return self.servicio.preparar_nct6687_control_pwm()

    def desactivar_nct6687_control_pwm(self):
        return self.servicio.desactivar_nct6687_control_pwm()

    def aplicar_pwm_fan(self, pwm, valor):
        return self.servicio.aplicar_pwm_fan(pwm, valor)
