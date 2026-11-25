@file:OptIn(kotlin.js.ExperimentalWasmJsInterop::class)

package org.bc250.controlcenter.datos

actual val puedeElegirImagen: Boolean = true

/**
 * El navegador dibuja la imagen centrada sobre negro en 672 × 378 y la guarda como JPEG,
 * bajando la calidad hasta que quepa en 60 KB. Entrega: nombre, ancho, alto y datos, separados por «|».
 */
private fun elegirEnElNavegador(alElegir: (String) -> Unit): Unit = js(
    """{
        const entrada = document.createElement('input');
        entrada.type = 'file';
        entrada.accept = 'image/*';
        entrada.onchange = () => {
            const archivo = entrada.files[0];
            if (!archivo) return;
            const direccion = URL.createObjectURL(archivo);
            const imagen = new Image();
            imagen.onload = () => {
                window.bc250Logo = { imagen: imagen, nombre: archivo.name };
                window.bc250DibujarLogo = (porcentaje) => {
                    const elegida = window.bc250Logo.imagen;
                    const lienzo = document.createElement('canvas');
                    lienzo.width = 672;
                    lienzo.height = 378;
                    const pincel = lienzo.getContext('2d');
                    pincel.fillStyle = '#000000';
                    pincel.fillRect(0, 0, 672, 378);
                    const escala = Math.min(672 * porcentaje / 100 / elegida.width, 378 * porcentaje / 100 / elegida.height);
                    const ancho = elegida.width * escala;
                    const alto = elegida.height * escala;
                    pincel.drawImage(elegida, (672 - ancho) / 2, (378 - alto) / 2, ancho, alto);
                    let calidad = 0.85;
                    let datos = lienzo.toDataURL('image/jpeg', calidad).split(',')[1];
                    while (datos.length > 81000 && calidad > 0.2) {
                        calidad -= 0.1;
                        datos = lienzo.toDataURL('image/jpeg', calidad).split(',')[1];
                    }
                    const nombre = window.bc250Logo.nombre.split('|').join(' ');
                    return [nombre, elegida.width, elegida.height, datos].join('|');
                };
                alElegir(window.bc250DibujarLogo(100));
            };
            imagen.src = direccion;
        };
        entrada.click();
    }""",
)

private fun dibujarDeNuevo(porcentaje: Int): String =
    js("(window.bc250DibujarLogo ? window.bc250DibujarLogo(porcentaje) : '')")

private fun leerImagen(texto: String): ImagenLogo? {
    val partes = texto.split("|")
    if (partes.size != 4) {
        return null
    }
    return ImagenLogo(partes[0], partes[1].toIntOrNull() ?: 0, partes[2].toIntOrNull() ?: 0, partes[3])
}

actual fun elegirImagen(alElegir: (ImagenLogo) -> Unit) {
    elegirEnElNavegador { texto ->
        val imagen = leerImagen(texto)
        if (imagen != null) {
            alElegir(imagen)
        }
    }
}

actual fun reescalarImagen(porcentaje: Int, alTerminar: (ImagenLogo) -> Unit) {
    val imagen = leerImagen(dibujarDeNuevo(porcentaje))
    if (imagen != null) {
        alTerminar(imagen)
    }
}
