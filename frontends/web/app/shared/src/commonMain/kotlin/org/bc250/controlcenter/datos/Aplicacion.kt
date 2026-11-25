package org.bc250.controlcenter.datos

import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateListOf
import androidx.compose.runtime.mutableStateMapOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.setValue
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Job
import kotlinx.coroutines.delay
import kotlinx.coroutines.isActive
import kotlinx.coroutines.launch
import kotlinx.coroutines.withTimeoutOrNull
import kotlinx.serialization.json.JsonElement
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.buildJsonObject
import org.bc250.controlcenter.componentes.TextoAbierto
import org.bc250.controlcenter.tema.Medidas
import org.bc250.controlcenter.tema.Paleta
import org.bc250.controlcenter.tema.PaletaInicial
import org.bc250.controlcenter.tema.Paletas

/** En qué punto está la conexión con el equipo. */
enum class EstadoSesion { CARGANDO, PIDE_DIRECCION, PIDE_CONFIANZA, SIN_CONEXION, PIDE_CLAVE, DENTRO }

/** Una pregunta antes de una operación. */
class Confirmacion(val titulo: String, val mensaje: String, val peligro: Boolean, val aceptar: () -> Unit)

/** Un aviso breve en una esquina. */
class Aviso(val texto: String, val error: Boolean)

/** La operación que corre en la consola. */
data class Trabajo(
    val id: Int = 0,
    val titulo: String = "",
    val texto: String = "",
    val terminado: Boolean = true,
    val correcto: Boolean = false,
    val cancelado: Boolean = false,
    val esperaClave: Boolean = false,
    val esperaRespuesta: Boolean = false,
) {
    /** Terminó mal sin que la persona lo detuviera. */
    val fallo: Boolean get() = id > 0 && terminado && !correcto && !cancelado
}

private const val PESTANAS_CONSOLA = 5

/** Al principio una operación se mira seguido, para que las cortas se noten al instante. */
private const val VUELTAS_RAPIDAS = 25
private const val PULSO_RAPIDO = 120L
private const val PULSO_LENTO = 350L
private const val ESPERA_FINAL = 2500L
private const val ANTES_DE_ADELANTAR = 900L
private const val MARCA_DE_PAREJA = "pair="
private const val MARCA_DE_AJUSTES = "settings/"
private const val PUERTO_NORMAL = 8250

private fun primeraPagina(): String {
    val marca = paginaDeLaDireccion()
    if (marca.isEmpty() || marca == "settings" || marca.contains("=") || marca.startsWith(MARCA_DE_AJUSTES)) {
        return "dashboard"
    }
    return marca
}

/**
 * El estado de toda la aplicación: la sesión, las lecturas y la operación en curso.
 * Las páginas solo leen de aquí y llaman a sus funciones.
 */
class Aplicacion(private val tareas: CoroutineScope) {
    val conexion = Conexion()

    var sesion by mutableStateOf(EstadoSesion.CARGANDO)
        private set
    var puedeControlar by mutableStateOf(false)
        private set
    var mensajeIngreso by mutableStateOf("")
        private set
    var pagina by mutableStateOf(primeraPagina())
        private set
    /** La parte de la página que pidió quien la abrió; la página la lee y la borra. */
    var partePedida by mutableStateOf("")
    var barraPlegada by mutableStateOf(false)
    var metricas by mutableStateOf(ObjetoVacio)
        private set
    var paleta by mutableStateOf(PaletaInicial)
        private set
    var confirmacion by mutableStateOf<Confirmacion?>(null)
    var aviso by mutableStateOf<Aviso?>(null)
        private set
    var trabajo by mutableStateOf(Trabajo())

    /** Las operaciones de esta visita, una por pestaña de la consola. */
    val trabajos = mutableStateListOf<Trabajo>()
    var trabajoElegido by mutableStateOf(0)
    var consolaVisible by mutableStateOf(false)

    /** En un teléfono la consola es una ventana inferior y no se abre sola. */
    var enTelefono by mutableStateOf(false)

    /** La ventana de Configuración y la sección que muestra; vacía si está cerrada. */
    var seccionAjustes by mutableStateOf("")
        private set
    var textoAbierto by mutableStateOf<TextoAbierto?>(null)
    var actualizacionAbierta by mutableStateOf(false)
    var idioma by mutableStateOf("en")
        private set
    var recorridoAbierto by mutableStateOf(false)

    /** Cambia cada vez que se cargan textos en otro idioma. */
    var revisionDeTextos by mutableStateOf(0)
        private set
    var preferencias by mutableStateOf(ObjetoVacio)
        private set
    var paletas by mutableStateOf(Paletas())
        private set
    var sistemaOscuro = true

    /** Lo último que se leyó de cada página. */
    private val lecturas = mutableStateMapOf<String, JsonObject>()
    private var temas = ObjetoVacio
    private var idiomaPedido = ""
    private var temaUsado: List<Any> = emptyList()

    /** El orden en que se pidió cada lectura: la que llega tarde no pisa a otra más nueva. */
    private val pedidos = mutableMapOf<String, Int>()
    private val publicados = mutableMapOf<String, Int>()

    /** La ficha de un solo uso del código QR, hasta que se pueda entrar con ella. */
    private var claveDePareja = ""
    private var lector: Job? = null
    private var seguimiento: Job? = null

    // -- inicio y sesión ---------------------------------------------------------------------

    fun iniciar() {
        val marca = paginaDeLaDireccion()
        if (marca.startsWith(MARCA_DE_PAREJA)) {
            // El código QR trae una ficha de un solo uso: se borra de la dirección y se entra con ella.
            anotarPagina(pagina)
            ingresar(marca.removePrefix(MARCA_DE_PAREJA).substringBefore("&"))
        } else if (pideDireccion && conexion.direccion.isEmpty()) {
            sesion = EstadoSesion.PIDE_DIRECCION
        } else {
            tareas.launch { revisarSesion() }
        }
    }

    /**
     * Todo lo necesario para dibujar llega en una sola respuesta. Un equipo con una versión anterior
     * no la conoce, y entonces se piden las partes una por una.
     */
    suspend fun revisarSesion() {
        val respuesta = conexion.pedir("/api/start")
        if (respuesta.codigo == 0) {
            sesion = if (CertificadoDelEquipo.pendiente.isEmpty()) EstadoSesion.SIN_CONEXION else EstadoSesion.PIDE_CONFIANZA
            return
        }
        val datos = respuesta.datos
        if (!respuesta.correcta || datos.objeto("session").isEmpty()) {
            revisarPorPartes()
            return
        }
        conexion.sello = datos.objeto("session").texto("csrf")
        puedeControlar = datos.objeto("session").logico("control")
        usarTextos(datos.objeto("texts"))
        temas = datos.objeto("theme").objeto("palettes")
        if (datos.objeto("session").logico("authenticated")) {
            lecturas["preferences"] = datos.objeto("preferences")
            idiomaPedido = datos.objeto("preferences").objeto("valores").texto("language")
            aplicarPreferencias()
            abrirDentro()
        } else {
            val tema = datos.objeto("theme")
            usarTema(tema.texto("style", "formal"), tema.texto("theme", "dark"), tema.texto("accent", "green"))
            sesion = EstadoSesion.PIDE_CLAVE
        }
    }

    private suspend fun revisarPorPartes() {
        val respuesta = conexion.pedir("/api/session")
        if (respuesta.codigo == 0) {
            sesion = if (CertificadoDelEquipo.pendiente.isEmpty()) EstadoSesion.SIN_CONEXION else EstadoSesion.PIDE_CONFIANZA
            return
        }
        conexion.sello = respuesta.datos.texto("csrf")
        puedeControlar = respuesta.datos.logico("control")
        cargarTextos("")
        if (respuesta.datos.logico("authenticated")) {
            entrar()
        } else {
            cargarTemas()
            sesion = EstadoSesion.PIDE_CLAVE
        }
    }

    /** Conecta con la dirección que se escribió o con el enlace completo del código QR. */
    fun conectar(escrita: String) {
        val enlace = escrita.trim()
        val completa = if (enlace.contains("://")) enlace else "https://$enlace"
        var direccion = completa.substringBefore("#").trimEnd('/')
        if (!direccion.substringAfter("://").contains(":")) {
            direccion += ":$PUERTO_NORMAL"
        }
        val ficha = completa.substringAfter("#$MARCA_DE_PAREJA", "")
        claveDePareja = ficha.substringBefore("&")
        if (direccion != conexion.direccion) {
            CertificadoDelEquipo.olvidar()
            lecturas.clear()
            pedidos.clear()
            publicados.clear()
        }
        CertificadoDelEquipo.confiarEn(ficha.substringAfter("&ca=", ""))
        conexion.direccion = direccion
        guardarDato(GUARDADO_DIRECCION, direccion)
        seguirConectando()
    }

    /** La persona comparó la huella y es la del equipo. */
    fun confiar() {
        CertificadoDelEquipo.confirmar()
        seguirConectando()
    }

    fun cambiarDireccion() {
        sesion = EstadoSesion.PIDE_DIRECCION
    }

    private fun seguirConectando() {
        sesion = EstadoSesion.CARGANDO
        tareas.launch {
            revisarSesion()
            if (sesion == EstadoSesion.PIDE_CLAVE && claveDePareja.isNotEmpty()) {
                ingresar(claveDePareja)
                claveDePareja = ""
            }
        }
    }

    fun ingresar(clave: String) {
        tareas.launch {
            val datos = buildJsonObject { put("key", JsonPrimitive(clave)) }
            val respuesta = conexion.enviar("/api/login", datos)
            if (respuesta.correcta) {
                mensajeIngreso = ""
                revisarSesion()
            } else {
                mensajeIngreso = respuesta.error.ifEmpty { t("Not connected") }
                revisarSesion()
            }
        }
    }

    fun salir() {
        tareas.launch {
            conexion.enviar("/api/logout")
            lector?.cancel()
            sesion = EstadoSesion.PIDE_CLAVE
        }
    }

    private suspend fun entrar() {
        cargarTemas()
        leerPreferencias()
        abrirDentro()
    }

    private fun abrirDentro() {
        abrirPaginaInicial()
        sesion = EstadoSesion.DENTRO
        lector?.cancel()
        lector = tareas.launch {
            launch { adelantarPaginas() }
            leerSinParar()
        }
    }

    /** Las páginas que más se abren quedan leídas de antemano, una a una y sin estorbar a la que se ve. */
    private suspend fun adelantarPaginas() {
        delay(ANTES_DE_ADELANTAR)
        for (nombre in listOf("cu", "cpu", "gpu", "fans")) {
            if (nombre != pagina && lecturas[nombre] == null) {
                leerPagina(nombre)
            }
        }
    }

    /** Abre una página y, si se pide, una parte de ella («Escalado», «Soporte»…). */
    fun irA(nueva: String, parte: String = "") {
        if (nueva == "settings") {
            abrirAjustes(parte.ifEmpty { "general" })
            return
        }
        pagina = nueva
        partePedida = parte
        anotarPagina(nueva)
    }

    fun abrirAjustes(seccion: String) {
        seccionAjustes = seccion
    }

    fun cerrarAjustes() {
        seccionAjustes = ""
    }

    fun abrirActualizacion() {
        actualizacionAbierta = true
    }

    fun empezarRecorrido() {
        cerrarAjustes()
        recorridoAbierto = true
    }

    // -- textos y tema -----------------------------------------------------------------------

    suspend fun cargarTextos(idioma: String) {
        val parametros = if (idioma.isEmpty()) emptyMap() else mapOf("lang" to idioma)
        val respuesta = conexion.pedir("/api/i18n", parametros)
        if (!respuesta.correcta) {
            return
        }
        usarTextos(respuesta.datos)
    }

    private fun usarTextos(datos: JsonObject) {
        conexion.idioma = datos.texto("language", "en")
        idioma = conexion.idioma
        val cadenas = datos.objeto("strings")
        val traducciones = cadenas.keys.associateWith { clave -> cadenas.texto(clave, clave) }
        Textos.cambiar(traducciones)
        revisionDeTextos += 1
    }

    private suspend fun cargarTemas() {
        val respuesta = conexion.pedir("/api/theme")
        if (!respuesta.correcta) {
            return
        }
        temas = respuesta.datos.objeto("palettes")
        usarTema(respuesta.datos.texto("style", "formal"), respuesta.datos.texto("theme", "dark"), respuesta.datos.texto("accent", "green"))
    }

    fun usarTema(estilo: String, tema: String, acento: String) {
        val delSistema = if (sistemaOscuro) "dark" else "light"
        val elegido = if (tema == "system") delSistema else tema
        val marca = listOf(estilo, elegido, acento, preferencias.texto("console_theme"), temas)
        if (marca == temaUsado) {
            return
        }
        paletas = Paletas(temas, estilo, elegido)
        val nueva = paletas.paleta(estilo, elegido, acento)
        if (nueva != null) {
            paleta = nueva.conTerminal(coloresDeTerminal())
            temaUsado = marca
        }
    }

    /** Los colores de consola del tema de terminal elegido, o ninguno si sigue a la aplicación. */
    private fun coloresDeTerminal(): Map<String, String> {
        val tema = lectura("preferences").objeto("terminales").objeto(preferencias.texto("console_theme"))
        if (tema.isEmpty()) {
            return emptyMap()
        }
        return mapOf(
            "console_bg" to tema.texto("fondo"),
            "console_text" to tema.texto("texto"),
            "console_border" to tema.texto("borde"),
        )
    }

    // -- preferencias ------------------------------------------------------------------------

    suspend fun leerPreferencias() {
        leerPagina("preferences")
        aplicarPreferencias()
        val idioma = preferencias.texto("language")
        if (preferencias.isNotEmpty() && idioma != idiomaPedido) {
            idiomaPedido = idioma
            cargarTextos(if (idioma == "auto") "" else idioma)
        }
    }

    private fun aplicarPreferencias() {
        preferencias = lectura("preferences").objeto("valores")
        if (preferencias.isEmpty()) {
            return
        }
        Medidas.compacta = preferencias.texto("density") == "compact"
        usarTema(preferencias.texto("style"), preferencias.texto("theme"), preferencias.texto("accent"))
    }

    private fun abrirPaginaInicial() {
        barraPlegada = preferencias.logico("sidebar_collapsed")
        val pedida = paginaDeLaDireccion()
        if (pedida.startsWith(MARCA_DE_AJUSTES)) {
            abrirAjustes(pedida.removePrefix(MARCA_DE_AJUSTES))
        } else if (pedida.isEmpty() || pedida.contains("=")) {
            irA(preferencias.texto("start_page", "dashboard"))
        }
    }

    /** Guarda una preferencia y la aplica al momento. */
    fun guardarPreferencia(clave: String, valor: JsonElement, despues: () -> Unit) {
        val parametros = mapOf("key" to JsonPrimitive(clave), "value" to valor)
        guardarYLuego("settings.preference", parametros, despues)
    }

    /** Guarda algo sin consola, vuelve a leer las preferencias y avisa a quien lo pidió. */
    fun guardarYLuego(accion: String, parametros: Map<String, JsonElement>, despues: () -> Unit) {
        tareas.launch {
            val datos = buildJsonObject {
                put("action", JsonPrimitive(accion))
                put("params", JsonObject(parametros))
            }
            val respuesta = conexion.enviar("/api/setting", datos)
            if (!respuesta.correcta) {
                avisar(respuesta.error.ifEmpty { t("Not connected") }, error = true)
            }
            leerPreferencias()
            despues()
        }
    }

    /** Guarda en el equipo los datos grandes de una acción y, si se aceptan, la ejecuta. */
    fun guardarYEjecutar(ajuste: String, datos: JsonObject, accion: String, titulo: String, mensaje: String) {
        tareas.launch {
            val pedido = buildJsonObject {
                put("action", JsonPrimitive(ajuste))
                put("params", datos)
            }
            val respuesta = conexion.enviar("/api/setting", pedido)
            if (!respuesta.correcta) {
                avisar(respuesta.error.ifEmpty { t("Not connected") }, error = true)
            } else if (mensaje.isEmpty()) {
                ejecutar(accion, titulo)
            } else {
                preguntarYEjecutar(accion, titulo, mensaje)
            }
        }
    }

    /** Guarda algo y dice si se pudo. */
    /** Un botón que contesta en el momento, sin consola: el mando de la TV. */
    suspend fun pulsarAhora(accion: String, parametros: JsonObject): JsonObject {
        val pedido = buildJsonObject {
            put("action", JsonPrimitive(accion))
            put("params", parametros)
        }
        val respuesta = conexion.enviar("/api/setting", pedido)
        if (!respuesta.correcta) {
            return JsonObject(mapOf("text" to JsonPrimitive(respuesta.error.ifEmpty { t("Not connected") })))
        }
        return respuesta.datos.objeto("data")
    }

    suspend fun guardarAhora(accion: String, parametros: JsonObject): Boolean {
        val pedido = buildJsonObject {
            put("action", JsonPrimitive(accion))
            put("params", parametros)
        }
        val respuesta = conexion.enviar("/api/setting", pedido)
        if (!respuesta.correcta) {
            avisar(respuesta.error.ifEmpty { t("Not connected") }, error = true)
        }
        return respuesta.correcta
    }

    /** Una pregunta de sí o no que no ejecuta ninguna operación del equipo. */
    fun preguntar(titulo: String, mensaje: String, peligro: Boolean, aceptar: () -> Unit) {
        confirmacion = Confirmacion(titulo, mensaje, peligro, aceptar)
    }

    // -- lecturas ----------------------------------------------------------------------------

    fun lectura(nombre: String): JsonObject {
        return lecturas[nombre] ?: ObjetoVacio
    }

    private suspend fun leerSinParar() {
        while (tareas.isActive) {
            PrimerPlano.esperar()
            val respuesta = conexion.pedir("/api/live")
            if (respuesta.codigo == 401) {
                sesion = EstadoSesion.PIDE_CLAVE
                return
            }
            if (respuesta.correcta) {
                metricas = respuesta.datos.objeto("metrics")
            }
            delay(1000)
        }
    }

    suspend fun leerPagina(nombre: String) {
        val turno = (pedidos[nombre] ?: 0) + 1
        pedidos[nombre] = turno
        val respuesta = conexion.pedir("/api/page", mapOf("name" to nombre))
        if (!respuesta.correcta || turno < (publicados[nombre] ?: 0)) {
            return
        }
        publicados[nombre] = turno
        val nueva = respuesta.datos.objeto("data")
        if (lecturas[nombre] != nueva) {
            lecturas[nombre] = nueva
        }
    }

    /** Espera para volver a leer; con la aplicación escondida espera hasta que se vea otra vez. */
    suspend fun pausar(milisegundos: Long) {
        delay(milisegundos)
        PrimerPlano.esperar()
    }

    /** Una lectura con parámetros; devuelve vacío si falla. */
    suspend fun consultar(nombre: String, parametros: Map<String, String> = emptyMap()): JsonObject {
        val respuesta = conexion.pedir("/api/query", parametros + mapOf("name" to nombre))
        return respuesta.datos.objeto("data")
    }

    // -- operaciones -------------------------------------------------------------------------

    /** Pregunta primero y, si la respuesta es sí, ejecuta la operación. */
    fun preguntarYEjecutar(
        accion: String,
        titulo: String,
        mensaje: String = titulo,
        parametros: Map<String, JsonElement> = emptyMap(),
        peligro: Boolean = false,
    ) {
        confirmacion = Confirmacion(titulo, mensaje, peligro) {
            ejecutar(accion, titulo, parametros, confirmada = true)
        }
    }

    fun ejecutar(
        accion: String,
        titulo: String,
        parametros: Map<String, JsonElement> = emptyMap(),
        confirmada: Boolean = false,
    ) {
        tareas.launch {
            val datos = buildJsonObject {
                put("action", JsonPrimitive(accion))
                put("title", JsonPrimitive(titulo))
                put("params", JsonObject(parametros))
                put("confirm", JsonPrimitive(confirmada))
            }
            val respuesta = conexion.enviar("/api/action", datos)
            if (respuesta.correcta) {
                // La operación se ve desde el toque, sin esperar a la primera lectura.
                trabajo = Trabajo(id = respuesta.datos.entero("job"), titulo = titulo, terminado = false)
                anotarTrabajo(trabajo)
                consolaVisible = !enTelefono
                seguirTrabajo()
            } else {
                avisar(respuesta.error.ifEmpty { t("Not connected") }, error = true)
            }
        }
    }

    /** Guarda una preferencia: no usa la consola ni pregunta. */
    fun guardar(accion: String, parametros: Map<String, JsonElement>, pagina: String) {
        tareas.launch {
            val datos = buildJsonObject {
                put("action", JsonPrimitive(accion))
                put("params", JsonObject(parametros))
            }
            val respuesta = conexion.enviar("/api/setting", datos)
            if (!respuesta.correcta) {
                avisar(respuesta.error.ifEmpty { t("Not connected") }, error = true)
            }
            leerPagina(pagina)
        }
    }

    /** Abre una dirección de internet fuera de la aplicación. */
    fun abrirEnlace(direccion: String) {
        if (direccion.startsWith("https://")) {
            abrirDireccion(direccion)
        }
    }

    private fun seguirTrabajo() {
        seguimiento?.cancel()
        seguimiento = tareas.launch {
            var vueltas = 0
            do {
                delay(if (vueltas < VUELTAS_RAPIDAS) PULSO_RAPIDO else PULSO_LENTO)
                vueltas += 1
                leerTrabajo()
            } while (!trabajo.terminado)
            if (trabajo.correcto && preferencias.logico("console_auto_hide")) {
                consolaVisible = false
            }
            // Las demás páginas se leen al abrirse; hasta entonces se ve lo último que se supo.
            leerPreferencias()
        }
    }

    private suspend fun leerTrabajo() {
        val respuesta = conexion.pedir("/api/job")
        if (!respuesta.correcta) {
            return
        }
        val datos = respuesta.datos
        if (datos.entero("id") != trabajo.id && trabajo.id > 0 && !trabajo.terminado) {
            // El equipo ya no la conoce: se reinició o empezó otra. Que no quede corriendo para siempre.
            trabajo = trabajo.copy(terminado = true, cancelado = true, esperaClave = false, esperaRespuesta = false)
            anotarTrabajo(trabajo)
            if (datos.entero("id") == 0) {
                return
            }
        }
        val nuevo = Trabajo(
            id = datos.entero("id"),
            titulo = datos.texto("label"),
            texto = datos.texto("text"),
            terminado = datos.logico("done", defecto = true),
            correcto = datos.logico("ok"),
            cancelado = datos.logico("cancelled"),
            esperaClave = datos.logico("waiting"),
            esperaRespuesta = datos.logico("interactive"),
        )
        if (nuevo.terminado && !trabajo.terminado) {
            // El final y lo que cambió se ven a la vez: nunca el final con los datos de antes.
            withTimeoutOrNull(ESPERA_FINAL) { leerPagina(pagina) }
        }
        trabajo = nuevo
        anotarTrabajo(nuevo)
    }

    /** Anota cómo va la operación en su pestaña; las más viejas que salieron bien dejan sitio. */
    private fun anotarTrabajo(nuevo: Trabajo) {
        if (nuevo.id <= 0) {
            return
        }
        val lugar = trabajos.indexOfFirst { abierto -> abierto.id == nuevo.id }
        if (lugar >= 0) {
            trabajos[lugar] = nuevo
            return
        }
        while (trabajos.size >= PESTANAS_CONSOLA) {
            trabajos.remove(trabajos.firstOrNull { abierto -> abierto.correcto } ?: trabajos.first())
        }
        trabajos.add(nuevo)
        trabajoElegido = nuevo.id
    }

    fun trabajoEnPantalla(): Trabajo {
        return trabajos.firstOrNull { abierto -> abierto.id == trabajoElegido } ?: trabajos.lastOrNull() ?: trabajo
    }

    fun cerrarTrabajo(id: Int) {
        trabajos.removeAll { abierto -> abierto.id == id && abierto.terminado }
        if (trabajos.isEmpty()) {
            consolaVisible = false
        }
    }

    /** Lo que se escribe en la consola; si no llegó, avisa para poder intentarlo otra vez. */
    fun responderTrabajo(texto: String, siFalla: () -> Unit = {}) {
        tareas.launch {
            val respuesta = conexion.enviar("/api/job/input", buildJsonObject { put("text", JsonPrimitive(texto)) })
            if (!respuesta.correcta || !respuesta.datos.logico("ok", defecto = true)) {
                siFalla()
                avisar(respuesta.error.ifEmpty { t("Not connected") }, error = true)
            }
        }
    }

    fun interrumpirTrabajo() {
        tareas.launch { conexion.enviar("/api/job/interrupt") }
    }

    /** Cierra lo que esté encima, de lo más reciente a lo más viejo. */
    fun volverAtras() {
        when {
            confirmacion != null -> confirmacion = null
            textoAbierto != null -> textoAbierto = null
            seccionAjustes.isNotEmpty() -> cerrarAjustes()
            recorridoAbierto -> recorridoAbierto = false
            consolaVisible -> consolaVisible = false
        }
    }

    // -- avisos ------------------------------------------------------------------------------

    fun avisar(texto: String, error: Boolean = false) {
        val nuevo = Aviso(texto, error)
        aviso = nuevo
        tareas.launch {
            delay(5000)
            if (aviso === nuevo) {
                aviso = null
            }
        }
    }
}
