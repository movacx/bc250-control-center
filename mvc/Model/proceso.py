class Proceso:
    def __init__(self, pid, nombre, memoria, comando, protegido=False, razon=''):
        self.pid = pid
        self.nombre = nombre
        self.memoria = memoria
        self.comando = comando
        self.protegido = protegido
        self.razon = razon

    def memoria_mb(self):
        return self.memoria / 1024 / 1024

    def __str__(self):
        return f'{self.pid},{self.nombre},{self.memoria_mb():.0f} MB'
