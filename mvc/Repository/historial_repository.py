import json
import os
import time


class HistorialRepository:
    def __init__(self, ruta, max_registros=26, conservar=6):
        self.archivo = os.path.abspath(str(ruta))
        self.max_registros = int(max_registros)
        self.conservar = int(conservar)
        self.lista = []
        self._load()

    def _load(self):
        self.lista = []
        if not os.path.exists(self.archivo):
            return None
        with open(self.archivo, 'r', encoding='utf-8') as file:
            for linea in file:
                texto = linea.strip()
                if not texto:
                    continue
                try:
                    self.lista.append(json.loads(texto))
                except Exception:
                    self.lista.append({
                        'id': 0,
                        'ts': 0,
                        'fecha': '--',
                        'tipo': 'error',
                        'nivel': 'warning',
                        'titulo': 'Linea de historial invalida',
                        'detalle': texto[:240],
                        'datos': {},
                    })
        self._compactar_si_ocupa()
        return True

    def _save(self):
        os.makedirs(os.path.dirname(self.archivo), exist_ok=True)
        with open(self.archivo, 'w', encoding='utf-8') as file:
            for item in self.lista:
                file.write(json.dumps(item, ensure_ascii=False, default=str) + '\n')
        return True

    def _compactar_si_ocupa(self):
        if len(self.lista) <= self.max_registros:
            return False
        self.lista = self.lista[-self.conservar:]
        self._save()
        return True

    def agregar(self, evento):
        self.lista.append(evento)
        if not self._compactar_si_ocupa():
            self._save()
        return True

    def listar(self, limite=300):
        self._load()
        try:
            limite = int(limite)
        except Exception:
            limite = 300
        return list(reversed(self.lista[-limite:]))

    def limpiar(self):
        self.lista = []
        self._save()
        return True

    def nuevo_evento(self, tipo, nivel, titulo, detalle='', datos=None):
        ahora = time.time()
        return {
            'id': int(ahora * 1000),
            'ts': ahora,
            'fecha': time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(ahora)),
            'tipo': str(tipo),
            'nivel': str(nivel),
            'titulo': str(titulo),
            'detalle': str(detalle),
            'datos': datos or {},
        }
