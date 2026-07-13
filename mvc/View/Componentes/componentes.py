from PyQt6.QtCore import Qt, QSize
from PyQt6.QtGui import QColor, QIcon, QPainter, QPen, QPixmap, QBrush
from PyQt6.QtWidgets import QFrame, QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget

def formato_bytes(valor):
    valor = float(valor or 0)
    for unidad in ['B', 'KB', 'MB', 'GB', 'TB']:
        if valor < 1024 or unidad == 'TB':
            if unidad in ['B', 'KB', 'MB']:
                return f'{valor:.0f} {unidad}'
            return f'{valor:.1f} {unidad}'
        valor /= 1024


def formato_temp(valor):
    if valor is None:
        return '--'
    return f'{valor:.1f} C'


def icono_app(nombre, comando):
    texto = f'{nombre} {comando}'.lower()
    mapa = [
        ('firefox', 'firefox'), ('chromium', 'chromium'), ('chrome', 'google-chrome'),
        ('legcord', 'discord'), ('discord', 'discord'), ('steam', 'steam'),
        ('java', 'minecraft'), ('minecraft', 'minecraft'), ('konsole', 'utilities-terminal'),
        ('code', 'visual-studio-code'), ('pycharm', 'pycharm'), ('dolphin', 'system-file-manager'),
        ('spectacle', 'spectacle'), ('kate', 'kate'), ('kwrite', 'kwrite'), ('vlc', 'vlc'),
        ('wine', 'wine'), ('proton', 'steam'), ('lutris', 'lutris'), ('heroic', 'heroic')
    ]
    for llave, icono in mapa:
        if llave in texto:
            ico = QIcon.fromTheme(icono)
            if not ico.isNull():
                return ico
    ico = QIcon.fromTheme(nombre.lower())
    if not ico.isNull():
        return ico
    return QIcon.fromTheme('application-x-executable')




def crear_nav_icono(tipo):
    colores = {
        'Procesos': ('#38bdf8', '#0ea5e9'),
        'Rendimiento': ('#a78bfa', '#7c3aed'),
        'Memoria': ('#34d399', '#16a34a'),
        'BC250': ('#fb923c', '#ea580c'),
        'Historial': ('#60a5fa', '#2563eb'),
    }
    claro, oscuro = colores.get(tipo, ('#93c5fd', '#2563eb'))
    pix = QPixmap(96, 96)
    pix.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pix)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(QBrush(QColor(claro)))
    painter.drawRoundedRect(10, 10, 76, 76, 20, 20)
    painter.setBrush(QBrush(QColor(oscuro)))
    if tipo == 'Procesos':
        painter.drawRoundedRect(26, 24, 18, 18, 5, 5)
        painter.drawRoundedRect(52, 24, 18, 18, 5, 5)
        painter.drawRoundedRect(26, 52, 18, 18, 5, 5)
        painter.drawRoundedRect(52, 52, 18, 18, 5, 5)
    elif tipo == 'Rendimiento':
        painter.setPen(QPen(QColor(oscuro), 8, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
        painter.drawLine(22, 60, 36, 44)
        painter.drawLine(36, 44, 49, 54)
        painter.drawLine(49, 54, 66, 28)
        painter.drawLine(66, 28, 76, 36)
    elif tipo == 'Memoria':
        painter.drawRoundedRect(22, 28, 52, 38, 8, 8)
        painter.setBrush(QBrush(QColor(claro)))
        for x in [28, 40, 52, 64]:
            painter.drawRoundedRect(x, 36, 6, 22, 3, 3)
    elif tipo == 'BC250':
        painter.drawEllipse(24, 24, 48, 48)
        painter.setBrush(QBrush(QColor(claro)))
        painter.drawEllipse(38, 38, 20, 20)
        painter.setBrush(QBrush(QColor(oscuro)))
        for x, y in [(46, 12), (46, 76), (12, 46), (76, 46)]:
            painter.drawRoundedRect(x, y, 10, 8, 3, 3)
    elif tipo == 'Historial':
        for y in [28, 44, 60]:
            painter.drawRoundedRect(26, y, 44, 6, 3, 3)
        painter.setBrush(QBrush(QColor(claro)))
        for y in [27, 43, 59]:
            painter.drawEllipse(18, y, 8, 8)
    painter.end()
    return QIcon(pix)

class MiniSpark(QWidget):
    def __init__(self, color='#2563eb'):
        super().__init__()
        self.valores = []
        self.maximo = 45
        self.color = QColor(color)
        self.setFixedHeight(30)

    def agregar(self, valor):
        try:
            valor = max(0, min(100, float(valor)))
        except Exception:
            valor = 0
        self.valores.append(valor)
        if len(self.valores) > self.maximo:
            self.valores.pop(0)
        self.update()

    def paintEvent(self, event):
        if len(self.valores) < 2:
            return
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = self.rect().adjusted(3, 4, -3, -4)
        painter.setPen(QPen(QColor('#d8e2ef'), 1))
        painter.drawLine(rect.left(), rect.center().y(), rect.right(), rect.center().y())
        paso = rect.width() / max(1, self.maximo - 1)
        inicio = self.maximo - len(self.valores)
        puntos = []
        for i, valor in enumerate(self.valores):
            x = rect.left() + (inicio + i) * paso
            y = rect.bottom() - (valor / 100) * rect.height()
            puntos.append((x, y))
        painter.setPen(QPen(self.color, 2, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
        for a, b in zip(puntos, puntos[1:]):
            painter.drawLine(int(a[0]), int(a[1]), int(b[0]), int(b[1]))


class MetricStrip(QFrame):
    def __init__(self, titulo, color='#2563eb'):
        super().__init__()
        self.setObjectName('MetricStrip')
        self.recurso = None
        self.callback = None
        self.titulo = QLabel(titulo)
        self.titulo.setObjectName('MetricTitle')
        self.valor = QLabel('--')
        self.valor.setObjectName('MetricValue')
        self.detalle = QLabel('')
        self.detalle.setObjectName('Muted')
        self.detalle.setFixedHeight(18)
        self.spark = MiniSpark(color)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 9, 12, 8)
        layout.setSpacing(1)
        top = QHBoxLayout()
        top.setSpacing(8)
        top.addWidget(self.titulo)
        top.addStretch(1)
        top.addWidget(self.valor)
        layout.addLayout(top)
        layout.addWidget(self.detalle)
        layout.addWidget(self.spark)

    def set_callback(self, recurso, callback):
        self.recurso = recurso
        self.callback = callback

    def mousePressEvent(self, event):
        if self.callback is not None and self.recurso is not None:
            self.callback(self.recurso)
        super().mousePressEvent(event)

    def set_activo(self, activo):
        self.setProperty('active', bool(activo))
        self.style().unpolish(self)
        self.style().polish(self)

    def actualizar(self, valor, detalle='', grafico=None):
        self.valor.setText(str(valor))
        self.detalle.setText(str(detalle))
        if grafico is not None:
            self.spark.agregar(grafico)


class NavButton(QPushButton):
    def __init__(self, texto, icono=None):
        super().__init__(texto)
        self.setObjectName('NavButton')
        self.setCheckable(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        if icono is not None:
            self.setIcon(icono)
            self.setIconSize(QSize(24, 24))



class GraficoGrande(QWidget):
    def __init__(self, color='#8b5cf6', relleno='#eadcff'):
        super().__init__()
        self.valores = []
        self.maximo = 90
        self.color = QColor(color)
        self.relleno = QColor(relleno)
        self.setMinimumHeight(280)

    def configurar(self, color, relleno):
        self.color = QColor(color)
        self.relleno = QColor(relleno)
        self.update()

    def agregar(self, valor):
        try:
            valor = max(0, min(100, float(valor)))
        except Exception:
            valor = 0
        self.valores.append(valor)
        if len(self.valores) > self.maximo:
            self.valores.pop(0)
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = self.rect().adjusted(8, 8, -8, -8)
        painter.setPen(QPen(QColor('#d7d7d7'), 1))
        for i in range(1, 8):
            x = rect.left() + rect.width() * i / 8
            painter.drawLine(int(x), rect.top(), int(x), rect.bottom())
        for i in range(1, 5):
            y = rect.top() + rect.height() * i / 5
            painter.drawLine(rect.left(), int(y), rect.right(), int(y))
        if len(self.valores) < 2:
            return
        paso = rect.width() / max(1, self.maximo - 1)
        inicio = self.maximo - len(self.valores)
        puntos = []
        for i, valor in enumerate(self.valores):
            x = rect.left() + (inicio + i) * paso
            y = rect.bottom() - (valor / 100) * rect.height()
            puntos.append((x, y))
        from PyQt6.QtGui import QPainterPath
        path = QPainterPath()
        path.moveTo(puntos[0][0], puntos[0][1])
        for x, y in puntos[1:]:
            path.lineTo(x, y)
        fill = QPainterPath(path)
        fill.lineTo(puntos[-1][0], rect.bottom())
        fill.lineTo(puntos[0][0], rect.bottom())
        fill.closeSubpath()
        painter.fillPath(fill, self.relleno)
        painter.setPen(QPen(self.color, 2))
        painter.drawPath(path)


class ResourceCard(QFrame):
    def __init__(self, titulo, color='#2563eb'):
        super().__init__()
        self.setObjectName('ResourceCard')
        self.titulo = QLabel(titulo)
        self.titulo.setObjectName('ResourceTitle')
        self.valor = QLabel('--')
        self.valor.setObjectName('ResourceValue')
        self.detalle = QLabel('')
        self.detalle.setObjectName('Muted')
        self.recurso = ''
        self.callback = None
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.spark = MiniSpark(color)
        self.spark.setFixedSize(96, 56)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(12)
        layout.addWidget(self.spark)
        textos = QVBoxLayout()
        textos.setSpacing(2)
        textos.addWidget(self.titulo)
        textos.addWidget(self.valor)
        textos.addWidget(self.detalle)
        layout.addLayout(textos, 1)

    def set_callback(self, recurso, callback):
        self.recurso = recurso
        self.callback = callback

    def mousePressEvent(self, event):
        if self.callback is not None and self.recurso is not None:
            self.callback(self.recurso)
        super().mousePressEvent(event)

    def set_activo(self, activo):
        self.setProperty('active', bool(activo))
        self.style().unpolish(self)
        self.style().polish(self)

    def actualizar(self, valor, detalle='', grafico=None):
        self.valor.setText(str(valor))
        self.detalle.setText(str(detalle))
        if grafico is not None:
            self.spark.agregar(grafico)
