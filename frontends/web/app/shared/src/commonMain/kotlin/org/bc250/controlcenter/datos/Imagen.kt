package org.bc250.controlcenter.datos

/** Una imagen ya preparada como logo de arranque: JPEG de 672 × 378 sobre negro. */
class ImagenLogo(val nombre: String, val ancho: Int, val alto: Int, val jpegBase64: String)

/** Si esta plataforma deja elegir una imagen. */
expect val puedeElegirImagen: Boolean

/** Abre el selector y entrega la imagen al tamaño pedido (30 a 100 %). */
expect fun elegirImagen(alElegir: (ImagenLogo) -> Unit)

/** Vuelve a preparar la última imagen elegida con otro tamaño. */
expect fun reescalarImagen(porcentaje: Int, alTerminar: (ImagenLogo) -> Unit)
