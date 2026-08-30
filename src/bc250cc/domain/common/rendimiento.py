class Rendimiento:
    def __init__(self, datos):
        self.datos = datos

    def get(self, clave, defecto=None):
        return self.datos.get(clave, defecto)

    def to_dict(self):
        return self.datos
