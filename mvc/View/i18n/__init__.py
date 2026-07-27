from __future__ import annotations

import locale
import logging
import re
from functools import lru_cache
from typing import Iterable

from .backend_catalog import BASE_TRANSLATIONS

from .catalog import EXTRA_TRANSLATIONS
from .interface_catalog import INTERFACE_TRANSLATIONS


logger = logging.getLogger(__name__)


LANGUAGE_OPTIONS = (
    ("auto", "Automatic"),
    ("en", "English"),
    ("es", "Español"),
    ("pt", "Português"),
    ("ru", "Русский"),
    ("uk", "Українська"),
    ("de", "Deutsch"),
)
SUPPORTED_LANGUAGES = {code for code, _name in LANGUAGE_OPTIONS if code != "auto"}
_CURRENT_LANGUAGE = "en"


def normalize_language(value: object) -> str:
    raw = str(value or "auto").strip().lower()
    aliases = {
        "automatic": "auto", "automático": "auto", "automatico": "auto", "system": "auto",
        "english": "en", "español": "es", "spanish": "es", "português": "pt", "portuguese": "pt",
        "русский": "ru", "russian": "ru", "українська": "uk", "ukrainian": "uk",
        "deutsch": "de", "german": "de",
    }
    raw = aliases.get(raw, raw.split("_", 1)[0].split("-", 1)[0])
    return raw if raw in SUPPORTED_LANGUAGES or raw == "auto" else "auto"


def system_language() -> str:
    candidates: list[str] = []
    try:
        code, _encoding = locale.getlocale()
        if code:
            candidates.append(code)
    except (TypeError, ValueError):
        logger.debug("locale.getlocale() did not return a usable language", exc_info=True)
    try:
        code = locale.getdefaultlocale()[0]  # type: ignore[attr-defined]
        if code:
            candidates.append(code)
    except (AttributeError, TypeError, ValueError):
        logger.debug("locale.getdefaultlocale() did not return a usable language", exc_info=True)
    for candidate in candidates:
        normalized = normalize_language(candidate)
        if normalized in SUPPORTED_LANGUAGES:
            return normalized
    return "en"


def resolve_language(value: object) -> str:
    normalized = normalize_language(value)
    return system_language() if normalized == "auto" else normalized


def set_language(value: object) -> str:
    global _CURRENT_LANGUAGE
    _CURRENT_LANGUAGE = resolve_language(value)
    return _CURRENT_LANGUAGE


def current_language() -> str:
    return _CURRENT_LANGUAGE


def _entry(en: str, es: str, pt: str, ru: str, uk: str, de: str) -> tuple[str, dict[str, str]]:
    return en, {"en": en, "es": es, "pt": pt, "ru": ru, "uk": uk, "de": de}


# Exact translations cover Settings, About, repositories, history, daemon controls,
# navigation, shared dialogs and the most visible labels across every interface module.
_EXACT = dict([
    _entry("Settings", "Configuración", "Configurações", "Настройки", "Налаштування", "Einstellungen"),
    _entry("General", "General", "Geral", "Общие", "Загальні", "Allgemein"),
    _entry("Appearance", "Apariencia", "Aparência", "Оформление", "Вигляд", "Darstellung"),
    _entry("Telemetry", "Telemetría", "Telemetria", "Телеметрия", "Телеметрія", "Telemetrie"),
    _entry("Notifications", "Notificaciones", "Notificações", "Уведомления", "Сповіщення", "Benachrichtigungen"),
    _entry("Security", "Seguridad", "Segurança", "Безопасность", "Безпека", "Sicherheit"),
    _entry("History & reports", "Historial e informes", "Histórico e relatórios", "История и отчёты", "Історія та звіти", "Verlauf und Berichte"),
    _entry("About", "Acerca de", "Sobre", "О программе", "Про програму", "Über"),
    _entry("Language", "Idioma", "Idioma", "Язык", "Мова", "Sprache"),
    _entry("Theme", "Tema", "Tema", "Тема", "Тема", "Design"),
    _entry("System", "Sistema", "Sistema", "Системная", "Системна", "System"),
    _entry("Light", "Claro", "Claro", "Светлая", "Світла", "Hell"),
    _entry("Dark", "Oscuro", "Escuro", "Тёмная", "Темна", "Dunkel"),
    _entry("Comfortable", "Cómoda", "Confortável", "Комфортная", "Комфортна", "Komfortabel"),
    _entry("Compact", "Compacta", "Compacta", "Компактная", "Компактна", "Kompakt"),
    _entry("Density", "Densidad", "Densidade", "Плотность", "Щільність", "Dichte"),
    _entry("Accent color", "Color de acento", "Cor de destaque", "Цвет акцента", "Колір акценту", "Akzentfarbe"),
    _entry("Blue", "Azul", "Azul", "Синий", "Синій", "Blau"),
    _entry("Violet", "Violeta", "Violeta", "Фиолетовый", "Фіолетовий", "Violett"),
    _entry("Cyan", "Cian", "Ciano", "Бирюзовый", "Бірюзовий", "Cyan"),
    _entry("Green", "Verde", "Verde", "Зелёный", "Зелений", "Grün"),
    _entry("Orange", "Naranja", "Laranja", "Оранжевый", "Помаранчевий", "Orange"),
    _entry("Automatic", "Automático", "Automático", "Автоматически", "Автоматично", "Automatisch"),
    _entry("Close", "Cerrar", "Fechar", "Закрыть", "Закрити", "Schließen"),
    _entry("Cancel", "Cancelar", "Cancelar", "Отмена", "Скасувати", "Abbrechen"),
    _entry("Confirm", "Confirmar", "Confirmar", "Подтвердить", "Підтвердити", "Bestätigen"),
    _entry("Back", "Volver", "Voltar", "Назад", "Назад", "Zurück"),
    _entry("Refresh", "Actualizar", "Atualizar", "Обновить", "Оновити", "Aktualisieren"),
    _entry("Refresh data", "Actualizar datos", "Atualizar dados", "Обновить данные", "Оновити дані", "Daten aktualisieren"),
    _entry("Move", "Mover", "Mover", "Переместить", "Перемістити", "Bewegen"),
    _entry("Sections", "Secciones", "Seções", "Разделы", "Розділи", "Bereiche"),
    _entry("Sidebar", "Barra lateral", "Barra lateral", "Боковая панель", "Бічна панель", "Seitenleiste"),
    _entry("Gamepad navigation", "Navegación con mando", "Navegação com controle", "Навигация с геймпадом", "Навігація геймпадом", "Gamepad-Navigation"),
    _entry("Detect controllers automatically and show controller hints while active.", "Detecta mandos automáticamente y muestra ayudas del control mientras esté activo.", "Detecta controles automaticamente e mostra dicas do controle enquanto estiver ativo.", "Автоматически обнаруживать геймпады и показывать подсказки контроллера, пока функция активна.", "Автоматично виявляти геймпади та показувати підказки контролера, доки функція активна.", "Controller automatisch erkennen und Controller-Hinweise anzeigen, solange die Funktion aktiv ist."),
    _entry("On-screen keypad", "Teclado numérico en pantalla", "Teclado numérico na tela", "Экранная цифровая клавиатура", "Екранна цифрова клавіатура", "Bildschirm-Ziffernblock"),
    _entry("Show a controller-friendly numeric pad for in-app number and text fields.", "Muestra un teclado numérico apto para mando en campos numéricos y de texto internos.", "Mostra um teclado numérico amigável ao controle em campos internos de número e texto.", "Показывать удобную для геймпада цифровую клавиатуру для внутренних числовых и текстовых полей.", "Показувати зручну для геймпада цифрову клавіатуру для внутрішніх числових і текстових полів.", "Zeigt einen controllerfreundlichen Ziffernblock für interne Zahlen- und Textfelder."),
    _entry("Show keypad automatically", "Mostrar teclado automáticamente", "Mostrar teclado automaticamente", "Показывать клавиатуру автоматически", "Показувати клавіатуру автоматично", "Tastatur automatisch anzeigen"),
    _entry("Open the numeric pad when a controller focuses an editable field.", "Abre el teclado numérico cuando el mando enfoca un campo editable.", "Abre o teclado numérico quando o controle foca um campo editável.", "Открывать цифровую клавиатуру, когда геймпад фокусирует редактируемое поле.", "Відкривати цифрову клавіатуру, коли геймпад фокусує редаговане поле.", "Öffnet den Ziffernblock, wenn der Controller ein editierbares Feld fokussiert."),
    _entry("Numeric pad", "Teclado numérico", "Teclado numérico", "Цифровая клавиатура", "Цифрова клавіатура", "Ziffernblock"),
    _entry("Keypad", "Teclado", "Teclado", "Клавиатура", "Клавіатура", "Tastatur"),
    _entry("Hide", "Ocultar", "Ocultar", "Скрыть", "Приховати", "Ausblenden"),
    _entry("Clear", "Limpiar", "Limpar", "Очистить", "Очистити", "Leeren"),
    _entry("Open", "Abrir", "Abrir", "Открыть", "Відкрити", "Öffnen"),
    _entry("Enabled", "Activado", "Ativado", "Включено", "Увімкнено", "Aktiviert"),
    _entry("Disabled", "Desactivado", "Desativado", "Отключено", "Вимкнено", "Deaktiviert"),
    _entry("Active", "Activo", "Ativo", "Активно", "Активно", "Aktiv"),
    _entry("Inactive", "Inactivo", "Inativo", "Неактивно", "Неактивно", "Inaktiv"),
    _entry("Unknown", "Desconocido", "Desconhecido", "Неизвестно", "Невідомо", "Unbekannt"),
    _entry("Live", "En vivo", "Ao vivo", "В реальном времени", "Наживо", "Live"),
    _entry("Valid", "Válido", "Válido", "Допустимо", "Дійсно", "Gültig"),
    _entry("Validated", "Validado", "Validado", "Проверено", "Перевірено", "Validiert"),
    _entry("Working", "Trabajando", "Trabalhando", "Выполняется", "Виконується", "Wird ausgeführt"),
    _entry("Completed", "Completado", "Concluído", "Завершено", "Завершено", "Abgeschlossen"),
    _entry("Failed", "Falló", "Falhou", "Ошибка", "Помилка", "Fehlgeschlagen"),
    _entry("Running", "Ejecutándose", "Em execução", "Выполняется", "Виконується", "Läuft"),
    _entry("Paused", "Pausado", "Pausado", "Приостановлено", "Призупинено", "Pausiert"),
    _entry("Read error", "Error de lectura", "Erro de leitura", "Ошибка чтения", "Помилка читання", "Lesefehler"),
    _entry("Hidden", "Oculto", "Oculto", "Скрыто", "Приховано", "Ausgeblendet"),
    _entry("Saved", "Guardado", "Salvo", "Сохранено", "Збережено", "Gespeichert"),
    _entry("Pending", "Pendiente", "Pendente", "Ожидает", "Очікує", "Ausstehend"),
    _entry("Not saved", "No guardado", "Não salvo", "Не сохранено", "Не збережено", "Nicht gespeichert"),
    _entry("Dashboard", "Dashboard", "Dashboard", "Панель", "Панель", "Dashboard"),
    _entry("CPU / SMU", "CPU / SMU", "CPU / SMU", "CPU / SMU", "CPU / SMU", "CPU / SMU"),
    _entry("GPU Governor", "Governor de GPU", "Governor da GPU", "Governor GPU", "Governor GPU", "GPU-Governor"),
    _entry("Compute Units", "Unidades de cómputo", "Unidades de computação", "Вычислительные блоки", "Обчислювальні блоки", "Compute Units"),
    _entry("Performance", "Rendimiento", "Desempenho", "Производительность", "Продуктивність", "Leistung"),
    _entry("Fans", "Ventiladores", "Ventiladores", "Вентиляторы", "Вентилятори", "Lüfter"),
    _entry("Processes", "Procesos", "Processos", "Процессы", "Процеси", "Prozesse"),
    _entry("Task Manager", "Administrador de tareas", "Gerenciador de tarefas", "Диспетчер задач", "Диспетчер завдань", "Task-Manager"),
    _entry("System protected", "Sistema protegido", "Sistema protegido", "Система защищена", "Систему захищено", "System geschützt"),
    _entry("BC250 services ready", "Servicios BC250 listos", "Serviços BC250 prontos", "Службы BC250 готовы", "Служби BC250 готові", "BC250-Dienste bereit"),
    _entry("Collapse sidebar", "Contraer barra lateral", "Recolher barra lateral", "Свернуть боковую панель", "Згорнути бічну панель", "Seitenleiste einklappen"),
    _entry("Expand sidebar", "Expandir barra lateral", "Expandir barra lateral", "Развернуть боковую панель", "Розгорнути бічну панель", "Seitenleiste ausklappen"),
    _entry("Workspace", "Espacio de trabajo", "Área de trabalho", "Рабочая область", "Робоча область", "Arbeitsbereich"),
    _entry("Start page", "Página inicial", "Página inicial", "Начальная страница", "Початкова сторінка", "Startseite"),
    _entry("Choose the module to open by default.", "Elige el módulo que se abrirá de forma predeterminada.", "Escolha o módulo que será aberto por padrão.", "Выберите модуль, открываемый по умолчанию.", "Виберіть модуль, який відкриватиметься за замовчуванням.", "Wähle das Modul, das standardmäßig geöffnet wird."),
    _entry("Reopen last module", "Reabrir el último módulo", "Reabrir o último módulo", "Открывать последний модуль", "Відкривати останній модуль", "Letztes Modul erneut öffnen"),
    _entry("Restore the last visited module when the application starts.", "Restaura el último módulo visitado al iniciar la aplicación.", "Restaura o último módulo visitado ao iniciar o aplicativo.", "Восстанавливает последний открытый модуль при запуске.", "Відновлює останній відкритий модуль під час запуску.", "Stellt beim Start das zuletzt besuchte Modul wieder her."),
    _entry("Collapsed sidebar at launch", "Barra lateral contraída al iniciar", "Barra lateral recolhida ao iniciar", "Сворачивать боковую панель при запуске", "Згортати бічну панель під час запуску", "Seitenleiste beim Start eingeklappt"),
    _entry("Open the main navigation in compact mode.", "Abre la navegación principal en modo compacto.", "Abre a navegação principal no modo compacto.", "Открывает основную навигацию в компактном режиме.", "Відкриває основну навігацію в компактному режимі.", "Öffnet die Hauptnavigation im kompakten Modus."),
    _entry("Interface", "Interfaz", "Interface", "Интерфейс", "Інтерфейс", "Oberfläche"),
    _entry("Use the operating-system color preference, the light interface, or the graphite developer dark theme.", "Usa la preferencia de color del sistema, la interfaz clara o el tema oscuro grafito para desarrolladores.", "Use a preferência de cor do sistema, a interface clara ou o tema escuro grafite para desenvolvedores.", "Используйте системную тему, светлый интерфейс или графитовую тёмную тему для разработчиков.", "Використовуйте системну тему, світлий інтерфейс або графітову темну тему для розробників.", "Nutze die Systemeinstellung, die helle Oberfläche oder das graphitfarbene Entwickler-Dunkeldesign."),
    _entry("Adjust spacing and row compactness for technical panels.", "Ajusta el espaciado y la densidad de filas de los paneles técnicos.", "Ajusta o espaçamento e a compactação das linhas nos painéis técnicos.", "Настройте интервалы и плотность строк технических панелей.", "Налаштуйте відступи та щільність рядків технічних панелей.", "Passt Abstände und Zeilendichte technischer Bereiche an."),
    _entry("Select the main interface accent used across modules.", "Selecciona el acento principal utilizado en todos los módulos.", "Selecione o destaque principal usado em todos os módulos.", "Выберите основной акцент интерфейса для всех модулей.", "Виберіть основний акцент інтерфейсу для всіх модулів.", "Wähle die primäre Akzentfarbe für alle Module."),
    _entry("Set the interface language. The change is applied immediately to the interface and its dialogs.", "Configura el idioma. El cambio se aplica de inmediato a la interfaz y sus diálogos.", "Define o idioma. A alteração é aplicada imediatamente à interface e aos seus diálogos.", "Выберите язык. Изменение сразу применяется к интерфейсу и его диалогам.", "Виберіть мову. Зміна одразу застосовується до інтерфейсу та його діалогів.", "Lege die Sprache fest. Die Änderung gilt sofort für die Oberfläche und ihre Dialoge."),
    _entry("Monitoring", "Supervisión", "Monitoramento", "Мониторинг", "Моніторинг", "Überwachung"),
    _entry("Performance sample cadence", "Intervalo de muestreo de rendimiento", "Intervalo de amostragem de desempenho", "Интервал выборки производительности", "Інтервал вибірки продуктивності", "Leistungs-Abtastrate"),
    _entry("The Performance module currently samples once per second.", "El módulo Rendimiento toma una muestra por segundo.", "O módulo Desempenho coleta uma amostra por segundo.", "Модуль производительности выполняет выборку раз в секунду.", "Модуль продуктивності виконує вибірку раз на секунду.", "Das Leistungsmodul erfasst derzeit einmal pro Sekunde."),
    _entry("Sample only visible pages", "Muestrear solo páginas visibles", "Amostrar apenas páginas visíveis", "Обновлять только видимые страницы", "Оновлювати лише видимі сторінки", "Nur sichtbare Seiten erfassen"),
    _entry("Only active telemetry pages refresh in the background.", "Solo las páginas activas de telemetría se actualizan en segundo plano.", "Apenas as páginas ativas de telemetria são atualizadas em segundo plano.", "В фоне обновляются только активные страницы телеметрии.", "У фоні оновлюються лише активні сторінки телеметрії.", "Nur aktive Telemetrieseiten werden im Hintergrund aktualisiert."),
    _entry("History window", "Ventana del historial", "Janela do histórico", "Окно истории", "Вікно історії", "Verlaufsfenster"),
    _entry("Length of the retained history shown in the Performance graphs.", "Duración del historial conservado en las gráficas de Rendimiento.", "Duração do histórico mantido nos gráficos de Desempenho.", "Длина сохраняемой истории на графиках производительности.", "Тривалість історії, що зберігається на графіках продуктивності.", "Länge des in den Leistungsdiagrammen angezeigten Verlaufs."),
    _entry("Sidebar status card", "Tarjeta de estado lateral", "Cartão de status lateral", "Карточка состояния в боковой панели", "Картка стану на бічній панелі", "Statuskarte in der Seitenleiste"),
    _entry("Show the small system status card in the main navigation rail.", "Muestra la tarjeta compacta de estado del sistema en la navegación principal.", "Mostra o pequeno cartão de status do sistema na navegação principal.", "Показывает компактную карточку состояния системы в навигации.", "Показує компактну картку стану системи в навігації.", "Zeigt die kompakte Systemstatuskarte in der Hauptnavigation."),
    _entry("Optional daemon", "Daemon opcional", "Daemon opcional", "Необязательный демон", "Необов'язковий демон", "Optionaler Daemon"),
    _entry("Daemon status", "Estado del daemon", "Status do daemon", "Состояние демона", "Стан демона", "Daemon-Status"),
    _entry("Refresh status", "Actualizar estado", "Atualizar status", "Обновить состояние", "Оновити стан", "Status aktualisieren"),
    _entry("Enable daemon", "Activar daemon", "Ativar daemon", "Включить демон", "Увімкнути демон", "Daemon aktivieren"),
    _entry("Disable daemon", "Desactivar daemon", "Desativar daemon", "Отключить демон", "Вимкнути демон", "Daemon deaktivieren"),
    _entry("View daemon details", "Ver detalles del daemon", "Ver detalhes do daemon", "Сведения о демоне", "Відомості про демон", "Daemon-Details anzeigen"),
    _entry("Sampling interval", "Intervalo de muestreo", "Intervalo de amostragem", "Интервал опроса", "Інтервал опитування", "Abtastintervall"),
    _entry("The optional user daemon records JSONL metrics and can continue the saved GPU fan curve while the GUI is closed. It never applies CPU or GPU overclock automatically.", "El daemon de usuario opcional registra métricas JSONL y puede mantener la curva de ventilador GPU guardada con la GUI cerrada. Nunca aplica overclock de CPU o GPU automáticamente.", "O daemon de usuário opcional registra métricas JSONL e pode manter a curva salva da ventoinha da GPU com a GUI fechada. Ele nunca aplica overclock de CPU ou GPU automaticamente.", "Необязательный пользовательский демон записывает метрики JSONL и может продолжать сохранённую кривую вентилятора GPU при закрытом интерфейсе. Он никогда не применяет разгон CPU или GPU автоматически.", "Необов'язковий користувацький демон записує метрики JSONL і може продовжувати збережену криву вентилятора GPU, коли інтерфейс закрито. Він ніколи не застосовує розгін CPU або GPU автоматично.", "Der optionale Benutzer-Daemon protokolliert JSONL-Metriken und kann die gespeicherte GPU-Lüfterkurve bei geschlossener GUI weiterführen. Er wendet niemals automatisch CPU- oder GPU-Overclocking an."),
    _entry("Session feedback", "Información de sesión", "Retorno da sessão", "Обратная связь сеанса", "Зворотний зв'язок сеансу", "Sitzungsrückmeldung"),
    _entry("Completion notices", "Avisos de finalización", "Avisos de conclusão", "Уведомления о завершении", "Сповіщення про завершення", "Abschlussmeldungen"),
    _entry("Background refresh alerts", "Alertas de actualización en segundo plano", "Alertas de atualização em segundo plano", "Оповещения об ошибках фонового обновления", "Сповіщення про помилки фонового оновлення", "Warnungen bei Hintergrundaktualisierung"),
    _entry("Protection policy", "Política de protección", "Política de proteção", "Политика защиты", "Політика захисту", "Schutzrichtlinie"),
    _entry("Confirm CPU apply", "Confirmar cambios de CPU", "Confirmar alterações da CPU", "Подтверждать изменения CPU", "Підтверджувати зміни CPU", "CPU-Änderungen bestätigen"),
    _entry("Confirm GPU apply", "Confirmar cambios de GPU", "Confirmar alterações da GPU", "Подтверждать изменения GPU", "Підтверджувати зміни GPU", "GPU-Änderungen bestätigen"),
    _entry("Confirm fan writes", "Confirmar escrituras de ventilador", "Confirmar gravações da ventoinha", "Подтверждать запись PWM", "Підтверджувати запис PWM", "Lüfter-Schreibzugriffe bestätigen"),
    _entry("Confirm process termination", "Confirmar cierre de procesos", "Confirmar encerramento de processos", "Подтверждать завершение процессов", "Підтверджувати завершення процесів", "Prozessbeendigung bestätigen"),
    _entry("Ask before sending a CPU frequency or voltage change.", "Pregunta antes de enviar un cambio de frecuencia o voltaje de CPU.", "Pergunta antes de enviar uma alteração de frequência ou voltagem da CPU.", "Запрашивает подтверждение перед изменением частоты или напряжения CPU.", "Запитує підтвердження перед зміною частоти або напруги CPU.", "Fragt vor einer Änderung von CPU-Frequenz oder -Spannung nach."),
    _entry("Ask before applying a GPU range, service action, or voltage curve.", "Pregunta antes de aplicar un rango GPU, una acción de servicio o una curva de voltaje.", "Pergunta antes de aplicar uma faixa da GPU, ação de serviço ou curva de voltagem.", "Запрашивает подтверждение перед диапазоном GPU, действием службы или кривой напряжения.", "Запитує підтвердження перед діапазоном GPU, дією служби або кривою напруги.", "Fragt vor GPU-Bereich, Dienstaktion oder Spannungskurve nach."),
    _entry("Ask before authorizing explicit PWM writes to the cooling controller.", "Pregunta antes de autorizar escrituras PWM explícitas en el controlador de refrigeración.", "Pergunta antes de autorizar gravações PWM explícitas no controlador de refrigeração.", "Запрашивает подтверждение явной записи PWM в контроллер охлаждения.", "Запитує підтвердження явного запису PWM у контролер охолодження.", "Fragt vor expliziten PWM-Schreibzugriffen auf den Kühlungscontroller nach."),
    _entry("Ask before closing selected application workloads.", "Pregunta antes de cerrar las aplicaciones seleccionadas.", "Pergunta antes de fechar as aplicações selecionadas.", "Запрашивает подтверждение перед закрытием выбранных приложений.", "Запитує підтвердження перед закриттям вибраних програм.", "Fragt vor dem Schließen ausgewählter Anwendungen nach."),
    _entry("Local activity history", "Historial local de actividad", "Histórico local de atividade", "Локальная история действий", "Локальна історія дій", "Lokaler Aktivitätsverlauf"),
    _entry("The existing JSONL event history is shown here in a compact table. Hardware commands and safety limits are not changed.", "El historial JSONL existente se muestra aquí en una tabla compacta. No se modifican comandos de hardware ni límites de seguridad.", "O histórico JSONL existente é mostrado aqui em uma tabela compacta. Comandos de hardware e limites de segurança não são alterados.", "Существующая история событий JSONL показана здесь в компактной таблице. Команды оборудования и пределы безопасности не изменяются.", "Наявну історію подій JSONL показано тут у компактній таблиці. Команди обладнання та межі безпеки не змінюються.", "Der vorhandene JSONL-Ereignisverlauf wird hier kompakt angezeigt. Hardwarebefehle und Sicherheitsgrenzen bleiben unverändert."),
    _entry("Clear history", "Limpiar historial", "Limpar histórico", "Очистить историю", "Очистити історію", "Verlauf löschen"),
    _entry("Open history folder", "Abrir carpeta del historial", "Abrir pasta do histórico", "Открыть папку истории", "Відкрити папку історії", "Verlaufsordner öffnen"),
    _entry("Date", "Fecha", "Data", "Дата", "Дата", "Datum"),
    _entry("Level", "Nivel", "Nível", "Уровень", "Рівень", "Stufe"),
    _entry("Event", "Evento", "Evento", "Событие", "Подія", "Ereignis"),
    _entry("Details", "Detalles", "Detalhes", "Подробности", "Подробиці", "Details"),
    _entry("No local events have been recorded yet.", "Todavía no se han registrado eventos locales.", "Ainda não há eventos locais registrados.", "Локальные события ещё не записаны.", "Локальні події ще не записані.", "Es wurden noch keine lokalen Ereignisse aufgezeichnet."),
    _entry("Clear local history", "Limpiar historial local", "Limpar histórico local", "Очистить локальную историю", "Очистити локальну історію", "Lokalen Verlauf löschen"),
    _entry("The JSONL history file will be emptied. This cannot be undone.", "El archivo de historial JSONL será vaciado. Esta acción no se puede deshacer.", "O arquivo de histórico JSONL será esvaziado. Esta ação não pode ser desfeita.", "Файл истории JSONL будет очищен. Это действие нельзя отменить.", "Файл історії JSONL буде очищено. Цю дію не можна скасувати.", "Die JSONL-Verlaufsdatei wird geleert. Dies kann nicht rückgängig gemacht werden."),
    _entry("History cleared", "Historial limpiado", "Histórico limpo", "История очищена", "Історію очищено", "Verlauf gelöscht"),
    _entry("Application", "Aplicación", "Aplicativo", "Приложение", "Програма", "Anwendung"),
    _entry("Runtime mode", "Modo de ejecución", "Modo de execução", "Режим работы", "Режим роботи", "Laufzeitmodus"),
    _entry("Platform", "Plataforma", "Plataforma", "Платформа", "Платформа", "Plattform"),
    _entry("Configuration folder", "Carpeta de configuración", "Pasta de configuração", "Папка конфигурации", "Папка конфігурації", "Konfigurationsordner"),
    _entry("Open settings folder", "Abrir carpeta de configuración", "Abrir pasta de configurações", "Открыть папку настроек", "Відкрити папку налаштувань", "Einstellungsordner öffnen"),
    _entry("Official repositories", "Repositorios oficiales", "Repositórios oficiais", "Официальные репозитории", "Офіційні репозиторії", "Offizielle Repositorys"),
    _entry("Project overview", "Presentación del proyecto", "Visão geral do projeto", "О проекте", "Огляд проєкту", "Projektübersicht"),
    _entry("Reset interface preferences", "Restablecer preferencias de interfaz", "Redefinir preferências da interface", "Сбросить настройки интерфейса", "Скинути налаштування інтерфейсу", "Oberflächeneinstellungen zurücksetzen"),
    _entry("BC250 Control Center does not own these tools. They are cloned or installed from their official repositories and retain their upstream credits and licenses.", "BC250 Control Center no es propietario de estas herramientas. Se clonan o instalan desde sus repositorios oficiales y conservan sus créditos y licencias upstream.", "O BC250 Control Center não é proprietário dessas ferramentas. Elas são clonadas ou instaladas de seus repositórios oficiais e mantêm os créditos e licenças upstream.", "BC250 Control Center не владеет этими инструментами. Они клонируются или устанавливаются из официальных репозиториев и сохраняют авторство и лицензии исходных проектов.", "BC250 Control Center не володіє цими інструментами. Вони клонуються або встановлюються з офіційних репозиторіїв і зберігають авторство та ліцензії вихідних проєктів.", "BC250 Control Center besitzt diese Werkzeuge nicht. Sie werden aus ihren offiziellen Repositorys geklont oder installiert und behalten ihre Upstream-Credits und Lizenzen."),
    _entry("If Firefox reports a locked profile when opened from a terminal, use the buttons in this window or copy the URL into the browser that is already running.", "Si Firefox informa que el perfil está bloqueado al abrirlo desde una terminal, usa los botones de esta ventana o copia la URL en el navegador que ya está abierto.", "Se o Firefox informar que o perfil está bloqueado quando aberto pelo terminal, use os botões desta janela ou copie a URL no navegador já aberto.", "Если Firefox сообщает о заблокированном профиле при запуске из терминала, используйте кнопки в этом окне или скопируйте URL в уже запущенный браузер.", "Якщо Firefox повідомляє про заблокований профіль під час запуску з термінала, скористайтеся кнопками в цьому вікні або скопіюйте URL у вже відкритий браузер.", "Falls Firefox beim Start aus einem Terminal ein gesperrtes Profil meldet, nutze die Schaltflächen in diesem Fenster oder kopiere die URL in den bereits geöffneten Browser."),
    _entry("Daemon details", "Detalles del daemon", "Detalhes do daemon", "Сведения о демоне", "Відомості про демон", "Daemon-Details"),
    _entry("Enable optional daemon", "Activar daemon opcional", "Ativar daemon opcional", "Включить необязательный демон", "Увімкнути необов'язковий демон", "Optionalen Daemon aktivieren"),
    _entry("This runs systemctl --user enable --now bc250-control-centerd.service. The daemon records telemetry and can apply the saved fan curve; it does not apply overclock automatically.", "Esto ejecuta systemctl --user enable --now bc250-control-centerd.service. El daemon registra telemetría y puede aplicar la curva de ventilador guardada; no aplica overclock automáticamente.", "Isto executa systemctl --user enable --now bc250-control-centerd.service. O daemon registra telemetria e pode aplicar a curva de ventoinha salva; ele não aplica overclock automaticamente.", "Будет выполнено systemctl --user enable --now bc250-control-centerd.service. Демон записывает телеметрию и может применять сохранённую кривую вентилятора; разгон автоматически не применяется.", "Буде виконано systemctl --user enable --now bc250-control-centerd.service. Демон записує телеметрію та може застосовувати збережену криву вентилятора; розгін автоматично не застосовується.", "Es wird systemctl --user enable --now bc250-control-centerd.service ausgeführt. Der Daemon protokolliert Telemetrie und kann die gespeicherte Lüfterkurve anwenden; Overclocking wird nicht automatisch angewendet."),
    _entry("Disable optional daemon", "Desactivar daemon opcional", "Desativar daemon opcional", "Отключить необязательный демон", "Вимкнути необов'язковий демон", "Optionalen Daemon deaktivieren"),
    _entry("This stops and disables bc250-control-centerd.service for the current user. Saved configuration and history files are preserved.", "Esto detiene y desactiva bc250-control-centerd.service para el usuario actual. Se conservan la configuración y los archivos de historial.", "Isto para e desativa bc250-control-centerd.service para o usuário atual. A configuração e os arquivos de histórico são preservados.", "Служба bc250-control-centerd.service будет остановлена и отключена для текущего пользователя. Конфигурация и история сохраняются.", "Службу bc250-control-centerd.service буде зупинено й вимкнено для поточного користувача. Конфігурація та історія зберігаються.", "bc250-control-centerd.service wird für den aktuellen Benutzer gestoppt und deaktiviert. Konfiguration und Verlauf bleiben erhalten."),
    _entry("Command completed", "Comando completado", "Comando concluído", "Команда выполнена", "Команду виконано", "Befehl abgeschlossen"),
    _entry("Command failed", "El comando falló", "O comando falhou", "Команда завершилась с ошибкой", "Команда завершилася з помилкою", "Befehl fehlgeschlagen"),
    _entry("Folder could not be opened", "No se pudo abrir la carpeta", "Não foi possível abrir a pasta", "Не удалось открыть папку", "Не вдалося відкрити папку", "Ordner konnte nicht geöffnet werden"),
    _entry("Module not available", "Módulo no disponible", "Módulo indisponível", "Модуль недоступен", "Модуль недоступний", "Modul nicht verfügbar"),
    _entry("Dependency preparation failed", "Falló la preparación de dependencias", "Falha ao preparar dependências", "Не удалось подготовить зависимости", "Не вдалося підготувати залежності", "Vorbereitung der Abhängigkeiten fehlgeschlagen"),
    _entry("Prepare BC250 dependencies", "Preparar dependencias BC250", "Preparar dependências BC250", "Подготовить зависимости BC250", "Підготувати залежності BC250", "BC250-Abhängigkeiten vorbereiten"),
    _entry("Prepare dependencies", "Preparar dependencias", "Preparar dependências", "Подготовить зависимости", "Підготувати залежності", "Abhängigkeiten vorbereiten"),
    _entry("Prepare Dependencies", "Preparar dependencias", "Preparar dependências", "Подготовить зависимости", "Підготувати залежності", "Abhängigkeiten vorbereiten"),
    _entry("BC250 setup", "Preparación BC250", "Preparação BC250", "Настройка BC250", "Налаштування BC250", "BC250-Einrichtung"),
    _entry("Installs required BC250 tools", "Instala las herramientas BC250 necesarias", "Instala as ferramentas BC250 necessárias", "Устанавливает необходимые инструменты BC250", "Встановлює необхідні інструменти BC250", "Installiert erforderliche BC250-Werkzeuge"),
    _entry("Return to GPU control", "Volver al control de GPU", "Voltar ao controle da GPU", "Вернуться к управлению GPU", "Повернутися до керування GPU", "Zur GPU-Steuerung zurückkehren"),
    _entry("Voltage laboratory", "Laboratorio de voltaje", "Laboratório de voltagem", "Лаборатория напряжения", "Лабораторія напруги", "Spannungslabor"),
    _entry("Voltage map", "Mapa de voltaje", "Mapa de voltagem", "Карта напряжения", "Карта напруги", "Spannungskarte"),
    _entry("Voltage profiles", "Perfiles de voltaje", "Perfis de voltagem", "Профили напряжения", "Профілі напруги", "Spannungsprofile"),
    _entry("Added voltage", "Voltaje agregado", "Voltagem adicionada", "Добавленное напряжение", "Додана напруга", "Zusätzliche Spannung"),
    _entry("Current voltage", "Voltaje actual", "Voltagem atual", "Текущее напряжение", "Поточна напруга", "Aktuelle Spannung"),
    _entry("Proposed voltage", "Voltaje propuesto", "Voltagem proposta", "Предлагаемое напряжение", "Запропонована напруга", "Vorgeschlagene Spannung"),
    _entry("Frequency", "Frecuencia", "Frequência", "Частота", "Частота", "Frequenz"),
    _entry("Custom", "Personalizado", "Personalizado", "Пользовательский", "Користувацький", "Benutzerdefiniert"),
    _entry("Operating profile", "Perfil operativo", "Perfil operacional", "Рабочий профиль", "Робочий профіль", "Betriebsprofil"),
    _entry("Quick frequency floor", "Piso rápido de frecuencia", "Piso rápido de frequência", "Быстрый минимум частоты", "Швидкий мінімум частоти", "Schneller Frequenzboden"),
    _entry("Governor service actions", "Acciones del servicio governor", "Ações do serviço governor", "Действия службы governor", "Дії служби governor", "Governor-Dienstaktionen"),
    _entry("Advanced diagnostics", "Diagnósticos avanzados", "Diagnósticos avançados", "Расширенная диагностика", "Розширена діагностика", "Erweiterte Diagnose"),
    _entry("Live GPU telemetry", "Telemetría GPU en vivo", "Telemetria da GPU ao vivo", "Телеметрия GPU в реальном времени", "Телеметрія GPU наживо", "Live-GPU-Telemetrie"),
    _entry("Core clock", "Frecuencia del núcleo", "Clock do núcleo", "Частота ядра", "Частота ядра", "Kerntakt"),
    _entry("GPU voltage", "Voltaje GPU", "Voltagem da GPU", "Напряжение GPU", "Напруга GPU", "GPU-Spannung"),
    _entry("Temperature", "Temperatura", "Temperatura", "Температура", "Температура", "Temperatur"),
    _entry("GPU load", "Carga GPU", "Carga da GPU", "Нагрузка GPU", "Навантаження GPU", "GPU-Last"),
    _entry("Memory clock", "Frecuencia de memoria", "Clock da memória", "Частота памяти", "Частота пам'яті", "Speichertakt"),
    _entry("VRAM usage", "Uso de VRAM", "Uso de VRAM", "Использование VRAM", "Використання VRAM", "VRAM-Nutzung"),
    _entry("Board power", "Consumo de la placa", "Consumo da placa", "Потребление платы", "Споживання плати", "Board-Leistung"),
    _entry("Review and apply", "Revisar y aplicar", "Revisar e aplicar", "Проверить и применить", "Перевірити й застосувати", "Prüfen und anwenden"),
    _entry("Review and apply range", "Revisar y aplicar rango", "Revisar e aplicar faixa", "Проверить и применить диапазон", "Перевірити й застосувати діапазон", "Bereich prüfen und anwenden"),
    _entry("Review and apply voltage curve", "Revisar y aplicar curva de voltaje", "Revisar e aplicar curva de voltagem", "Проверить и применить кривую напряжения", "Перевірити й застосувати криву напруги", "Spannungskurve prüfen und anwenden"),
    _entry("Review and apply session", "Revisar y aplicar sesión", "Revisar e aplicar sessão", "Проверить и применить сеанс", "Перевірити й застосувати сеанс", "Sitzung prüfen und anwenden"),
    _entry("Prepare tools", "Preparar herramientas", "Preparar ferramentas", "Подготовить инструменты", "Підготувати інструменти", "Werkzeuge vorbereiten"),
    _entry("View persistence status", "Ver estado de persistencia", "Ver status de persistência", "Состояние постоянного профиля", "Стан постійного профілю", "Persistenzstatus anzeigen"),
    _entry("Enable / update persistence", "Activar / actualizar persistencia", "Ativar / atualizar persistência", "Включить / обновить постоянный профиль", "Увімкнути / оновити постійний профіль", "Persistenz aktivieren / aktualisieren"),
    _entry("Disable persistence", "Desactivar persistencia", "Desativar persistência", "Отключить постоянный профиль", "Вимкнути постійний профіль", "Persistenz deaktivieren"),
    _entry("Read details", "Leer detalles", "Ler detalhes", "Прочитать сведения", "Прочитати відомості", "Details lesen"),
    _entry("Advanced details", "Detalles avanzados", "Detalhes avançados", "Расширенные сведения", "Розширені відомості", "Erweiterte Details"),
    _entry("Session console", "Consola de sesión", "Console da sessão", "Консоль сеанса", "Консоль сеансу", "Sitzungskonsole"),
    _entry("Register diagnostics", "Diagnóstico de registros", "Diagnóstico de registradores", "Диагностика регистров", "Діагностика регістрів", "Registerdiagnose"),
    _entry("Discard edits", "Descartar cambios", "Descartar alterações", "Отменить изменения", "Скасувати зміни", "Änderungen verwerfen"),
    _entry("Review and apply live", "Revisar y aplicar en vivo", "Revisar e aplicar ao vivo", "Проверить и применить в реальном времени", "Перевірити й застосувати наживо", "Live prüfen und anwenden"),
    _entry("Current selection", "Selección actual", "Seleção atual", "Текущий выбор", "Поточний вибір", "Aktuelle Auswahl"),
    _entry("Close", "Cerrar", "Fechar", "Закрыть", "Закрити", "Schließen"),
    _entry("Search application, PID, or command", "Buscar aplicación, PID o comando", "Buscar aplicativo, PID ou comando", "Поиск приложения, PID или команды", "Пошук програми, PID або команди", "Anwendung, PID oder Befehl suchen"),
    _entry("Hide system", "Ocultar sistema", "Ocultar sistema", "Скрыть системные", "Приховати системні", "Systemprozesse ausblenden"),
    _entry("Group apps", "Agrupar aplicaciones", "Agrupar aplicativos", "Группировать приложения", "Групувати програми", "Anwendungen gruppieren"),
    _entry("No applications selected", "No hay aplicaciones seleccionadas", "Nenhum aplicativo selecionado", "Приложения не выбраны", "Програми не вибрано", "Keine Anwendungen ausgewählt"),
    _entry("Select safe visible", "Seleccionar visibles seguras", "Selecionar visíveis seguras", "Выбрать безопасные видимые", "Вибрати безпечні видимі", "Sichtbare sichere auswählen"),
    _entry("Clear selection", "Quitar selección", "Limpar seleção", "Снять выбор", "Скасувати вибір", "Auswahl aufheben"),
    _entry("Release page cache", "Liberar caché de páginas", "Liberar cache de páginas", "Освободить файловый кэш", "Звільнити файловий кеш", "Seitencache freigeben"),
    _entry("End selected tasks", "Finalizar tareas seleccionadas", "Encerrar tarefas selecionadas", "Завершить выбранные задачи", "Завершити вибрані завдання", "Ausgewählte Aufgaben beenden"),
    _entry("Prepare PWM driver", "Preparar controlador PWM", "Preparar driver PWM", "Подготовить драйвер PWM", "Підготувати драйвер PWM", "PWM-Treiber vorbereiten"),
    _entry("Use read-only monitoring", "Usar supervisión de solo lectura", "Usar monitoramento somente leitura", "Использовать мониторинг только для чтения", "Використовувати моніторинг лише для читання", "Schreibgeschützte Überwachung verwenden"),
    _entry("Disable PWM setup", "Desactivar configuración PWM", "Desativar configuração PWM", "Отключить настройку PWM", "Вимкнути налаштування PWM", "PWM-Einrichtung deaktivieren"),
    _entry("PWM paths by OS", "Rutas PWM por sistema", "Rotas PWM por sistema", "Пути PWM по системе", "Шляхи PWM за системою", "PWM-Pfade nach Betriebssystem"),
    _entry("Raw chip status", "Estado bruto del chip", "Status bruto do chip", "Необработанное состояние чипа", "Необроблений стан чипа", "Chip-Rohstatus"),
    _entry("Enable automatic curve", "Activar curva automática", "Ativar curva automática", "Включить автоматическую кривую", "Увімкнути автоматичну криву", "Automatische Kurve aktivieren"),
    _entry("Save curve", "Guardar curva", "Salvar curva", "Сохранить кривую", "Зберегти криву", "Kurve speichern"),
    _entry("Apply curve now", "Aplicar curva ahora", "Aplicar curva agora", "Применить кривую сейчас", "Застосувати криву зараз", "Kurve jetzt anwenden"),
    _entry("Use live duty", "Usar ciclo en vivo", "Usar ciclo ao vivo", "Использовать текущее заполнение", "Використати поточний цикл", "Live-Tastgrad verwenden"),
    _entry("Review and apply PWM", "Revisar y aplicar PWM", "Revisar e aplicar PWM", "Проверить и применить PWM", "Перевірити й застосувати PWM", "PWM prüfen und anwenden"),
    _entry("Waiting for GPU temperature", "Esperando temperatura GPU", "Aguardando temperatura da GPU", "Ожидание температуры GPU", "Очікування температури GPU", "Warte auf GPU-Temperatur"),
    _entry("Waiting for process inventory", "Esperando inventario de procesos", "Aguardando inventário de processos", "Ожидание списка процессов", "Очікування списку процесів", "Warte auf Prozessliste"),
    _entry("Waiting for first sample", "Esperando la primera muestra", "Aguardando a primeira amostra", "Ожидание первой выборки", "Очікування першої вибірки", "Warte auf erste Messung"),
    _entry("Waiting for sample", "Esperando muestra", "Aguardando amostra", "Ожидание выборки", "Очікування вибірки", "Warte auf Messung"),
    _entry("Sampling", "Muestreando", "Amostrando", "Сбор данных", "Збір даних", "Abtastung"),

])

# Additional exact strings used by the complete Settings implementation.
_EXACT.update(dict([
    _entry("Visual density, color, and language preferences for the interface.", "Preferencias de densidad, color e idioma de la interfaz.", "Preferências de densidade, cor e idioma da interface.", "Параметры плотности, цвета и языка интерфейса.", "Параметри щільності, кольору й мови інтерфейсу.", "Dichte-, Farb- und Spracheinstellungen der Oberfläche."),
    _entry("Sampling, refresh cadence, passive monitoring, and the optional user daemon.", "Muestreo, frecuencia de actualización, supervisión pasiva y daemon de usuario opcional.", "Amostragem, frequência de atualização, monitoramento passivo e daemon de usuário opcional.", "Выборка, частота обновления, пассивный мониторинг и необязательный пользовательский демон.", "Вибірка, частота оновлення, пасивний моніторинг і необов'язковий користувацький демон.", "Abtastung, Aktualisierungsrate, passive Überwachung und optionaler Benutzer-Daemon."),
    _entry("Current user-service state for bc250-control-centerd.", "Estado actual del servicio de usuario bc250-control-centerd.", "Status atual do serviço de usuário bc250-control-centerd.", "Текущее состояние пользовательской службы bc250-control-centerd.", "Поточний стан користувацької служби bc250-control-centerd.", "Aktueller Status des Benutzerdienstes bc250-control-centerd."),
    _entry("Daemon interval", "Intervalo del daemon", "Intervalo do daemon", "Интервал демона", "Інтервал демона", "Daemon-Intervall"),
    _entry("Controls the conservative monitoring loop used while the optional service is running.", "Controla el ciclo de supervisión conservador mientras se ejecuta el servicio opcional.", "Controla o ciclo conservador de monitoramento enquanto o serviço opcional está em execução.", "Управляет консервативным циклом мониторинга во время работы необязательной службы.", "Керує консервативним циклом моніторингу під час роботи необов'язкової служби.", "Steuert die konservative Überwachungsschleife, während der optionale Dienst läuft."),
    _entry("1 second (fixed)", "1 segundo (fijo)", "1 segundo (fixo)", "1 секунда (фиксировано)", "1 секунда (фіксовано)", "1 Sekunde (fest)"),
    _entry("Checking…", "Comprobando…", "Verificando…", "Проверка…", "Перевірка…", "Prüfung…"),
    _entry("Build information, local paths, project scope, and official repositories.", "Información de compilación, rutas locales, alcance del proyecto y repositorios oficiales.", "Informações de compilação, caminhos locais, escopo do projeto e repositórios oficiais.", "Сведения о сборке, локальные пути, область проекта и официальные репозитории.", "Відомості про збірку, локальні шляхи, область проєкту й офіційні репозиторії.", "Build-Informationen, lokale Pfade, Projektumfang und offizielle Repositorys."),
    _entry("Product name of the current interface.", "Nombre del producto de la interfaz actual.", "Nome do produto da interface atual.", "Название продукта текущего интерфейса.", "Назва продукту поточного інтерфейсу.", "Produktname der aktuellen Oberfläche."),
    _entry("Indicates whether the validated hardware backend is connected.", "Indica si el backend de hardware validado está conectado.", "Indica se o backend de hardware validado está conectado.", "Показывает, подключён ли проверенный аппаратный backend.", "Показує, чи підключено перевірений апаратний backend.", "Zeigt an, ob das validierte Hardware-Backend verbunden ist."),
    _entry("Detected operating system for this session.", "Sistema operativo detectado para esta sesión.", "Sistema operacional detectado nesta sessão.", "Операционная система, обнаруженная в этом сеансе.", "Операційна система, виявлена в цьому сеансі.", "Für diese Sitzung erkanntes Betriebssystem."),
    _entry("Runtime used by the current application process.", "Entorno de ejecución usado por el proceso actual de la aplicación.", "Runtime usado pelo processo atual do aplicativo.", "Среда выполнения текущего процесса приложения.", "Середовище виконання поточного процесу програми.", "Laufzeitumgebung des aktuellen Anwendungsprozesses."),
    _entry("BC250 Control Center is a graphical interface for managing, preparing, and monitoring community tools for the AMD BC-250 board.", "BC250 Control Center es una interfaz gráfica para administrar, preparar y supervisar herramientas comunitarias de la placa AMD BC-250.", "O BC250 Control Center é uma interface gráfica para gerenciar, preparar e monitorar ferramentas comunitárias da placa AMD BC-250.", "BC250 Control Center — графический интерфейс для управления, подготовки и мониторинга инструментов сообщества для платы AMD BC-250.", "BC250 Control Center — графічний інтерфейс для керування, підготовки й моніторингу інструментів спільноти для плати AMD BC-250.", "BC250 Control Center ist eine grafische Oberfläche zum Verwalten, Vorbereiten und Überwachen von Community-Werkzeugen für das AMD-BC-250-Board."),
    _entry("Settings folder", "Carpeta de configuración", "Pasta de configurações", "Папка настроек", "Папка налаштувань", "Einstellungsordner"),
    _entry("History folder", "Carpeta del historial", "Pasta do histórico", "Папка истории", "Папка історії", "Verlaufsordner"),
    _entry("The desktop could not open this folder.", "El escritorio no pudo abrir esta carpeta.", "O ambiente de trabalho não conseguiu abrir esta pasta.", "Среда рабочего стола не смогла открыть эту папку.", "Середовище стільниці не змогло відкрити цю папку.", "Die Desktop-Umgebung konnte diesen Ordner nicht öffnen."),
    _entry("Settings could not be saved", "No se pudo guardar la configuración", "Não foi possível salvar as configurações", "Не удалось сохранить настройки", "Не вдалося зберегти налаштування", "Einstellungen konnten nicht gespeichert werden"),
    _entry("Command completed", "Comando completado", "Comando concluído", "Команда выполнена", "Команду виконано", "Befehl abgeschlossen"),
    _entry("Command failed", "El comando falló", "O comando falhou", "Команда завершилась с ошибкой", "Команда завершилася з помилкою", "Befehl fehlgeschlagen"),
    _entry("The optional daemon is enabled.", "El daemon opcional está activado.", "O daemon opcional está ativado.", "Необязательный демон включён.", "Необов'язковий демон увімкнено.", "Der optionale Daemon ist aktiviert."),
    _entry("The optional daemon is disabled.", "El daemon opcional está desactivado.", "O daemon opcional está desativado.", "Необязательный демон отключён.", "Необов'язковий демон вимкнено.", "Der optionale Daemon ist deaktiviert."),
    _entry("No CPU or GPU overclock was applied.", "No se aplicó overclock de CPU ni GPU.", "Nenhum overclock de CPU ou GPU foi aplicado.", "Разгон CPU или GPU не применялся.", "Розгін CPU або GPU не застосовувався.", "Es wurde kein CPU- oder GPU-Overclocking angewendet."),
    _entry("Monitoring, JSONL metrics, and saved GPU fan curve", "Supervisión, métricas JSONL y curva de ventilador GPU guardada", "Monitoramento, métricas JSONL e curva salva da ventoinha da GPU", "Мониторинг, метрики JSONL и сохранённая кривая вентилятора GPU", "Моніторинг, метрики JSONL і збережена крива вентилятора GPU", "Überwachung, JSONL-Metriken und gespeicherte GPU-Lüfterkurve"),
    _entry("Preferences restored", "Preferencias restauradas", "Preferências restauradas", "Настройки восстановлены", "Налаштування відновлено", "Einstellungen wiederhergestellt"),
    _entry("Reset preferences", "Restablecer preferencias", "Redefinir preferências", "Сбросить настройки", "Скинути налаштування", "Einstellungen zurücksetzen"),
    _entry("Preserved", "Conservado", "Preservado", "Сохраняется", "Зберігається", "Beibehalten"),
    _entry("Hardware profiles, voltage limits, commands, and history", "Perfiles de hardware, límites de voltaje, comandos e historial", "Perfis de hardware, limites de voltagem, comandos e histórico", "Аппаратные профили, пределы напряжения, команды и история", "Апаратні профілі, межі напруги, команди й історія", "Hardwareprofile, Spannungsgrenzen, Befehle und Verlauf"),
    _entry("Interface preferences were restored. Hardware profiles, limits, commands, and history were not changed.", "Se restauraron las preferencias de interfaz. No se modificaron los perfiles de hardware, límites, comandos ni el historial.", "As preferências da interface foram restauradas. Perfis de hardware, limites, comandos e histórico não foram alterados.", "Настройки интерфейса восстановлены. Аппаратные профили, пределы, команды и история не изменены.", "Налаштування інтерфейсу відновлено. Апаратні профілі, межі, команди й історію не змінено.", "Die Oberflächeneinstellungen wurden wiederhergestellt. Hardwareprofile, Grenzen, Befehle und Verlauf blieben unverändert."),
    _entry("Display a confirmation when longer maintenance actions finish.", "Muestra una confirmación cuando terminan las acciones de mantenimiento prolongadas.", "Exibe uma confirmação quando ações de manutenção mais longas terminam.", "Показывает подтверждение после завершения длительных операций обслуживания.", "Показує підтвердження після завершення тривалих дій обслуговування.", "Zeigt nach längeren Wartungsaktionen eine Bestätigung an."),
    _entry("Inform when a live page cannot refresh due to a read error.", "Informa cuando una página en vivo no puede actualizarse por un error de lectura.", "Informa quando uma página ao vivo não pode ser atualizada devido a erro de leitura.", "Сообщает, когда страница реального времени не обновляется из-за ошибки чтения.", "Повідомляє, коли сторінка наживо не оновлюється через помилку читання.", "Informiert, wenn eine Live-Seite wegen eines Lesefehlers nicht aktualisiert werden kann."),
    _entry("Confirmation policy for privileged or hardware-impacting actions.", "Política de confirmación para acciones privilegiadas o que afectan al hardware.", "Política de confirmação para ações privilegiadas ou que afetam o hardware.", "Политика подтверждения привилегированных или влияющих на оборудование действий.", "Політика підтвердження привілейованих дій або дій, що впливають на обладнання.", "Bestätigungsrichtlinie für privilegierte oder hardwarewirksame Aktionen."),
    _entry("Scope", "Alcance", "Escopo", "Область", "Область", "Umfang"),
    _entry("File", "Archivo", "Arquivo", "Файл", "Файл", "Datei"),
    _entry("Python", "Python", "Python", "Python", "Python", "Python"),
    _entry("HISTORY", "HISTORIAL", "HISTÓRICO", "ИСТОРИЯ", "ІСТОРІЯ", "VERLAUF"),
    _entry("SETTINGS", "CONFIGURACIÓN", "CONFIGURAÇÕES", "НАСТРОЙКИ", "НАЛАШТУВАННЯ", "EINSTELLUNGEN"),
    _entry("LOCAL PATH", "RUTA LOCAL", "CAMINHO LOCAL", "ЛОКАЛЬНЫЙ ПУТЬ", "ЛОКАЛЬНИЙ ШЛЯХ", "LOKALER PFAD"),
    _entry("OPTIONAL DAEMON", "DAEMON OPCIONAL", "DAEMON OPCIONAL", "НЕОБЯЗАТЕЛЬНЫЙ ДЕМОН", "НЕОБОВ'ЯЗКОВИЙ ДЕМОН", "OPTIONALER DAEMON"),
    _entry("PWM paths and distribution layout", "Rutas PWM y estructura por distribución", "Rotas PWM e estrutura por distribuição", "Пути PWM и структура по дистрибутивам", "Шляхи PWM і структура за дистрибутивами", "PWM-Pfade und Distributionsstruktur"),
    _entry("FAN DRIVER INTEGRATION", "INTEGRACIÓN DEL CONTROLADOR DE VENTILADORES", "INTEGRAÇÃO DO DRIVER DE VENTOINHAS", "ИНТЕГРАЦИЯ ДРАЙВЕРА ВЕНТИЛЯТОРОВ", "ІНТЕГРАЦІЯ ДРАЙВЕРА ВЕНТИЛЯТОРІВ", "LÜFTERTREIBER-INTEGRATION"),
    _entry("PWM paths by distribution", "Rutas PWM por distribución", "Rotas PWM por distribuição", "Пути PWM по дистрибутивам", "Шляхи PWM за дистрибутивами", "PWM-Pfade nach Distribution"),
    _entry("Live hwmon routes, installed driver locations, persistence files, and useful verification commands.", "Rutas hwmon en vivo, ubicaciones del controlador, archivos de persistencia y comandos útiles de verificación.", "Rotas hwmon ao vivo, locais do driver, arquivos de persistência e comandos úteis de verificação.", "Текущие пути hwmon, расположение драйвера, файлы постоянной настройки и полезные команды проверки.", "Поточні шляхи hwmon, розташування драйвера, файли постійних налаштувань і корисні команди перевірки.", "Live-hwmon-Pfade, Treiberorte, Persistenzdateien und nützliche Prüfkommandos."),
    _entry("Paths are informational. Driver installation and module changes remain explicit, authenticated actions.", "Las rutas son informativas. La instalación del controlador y los cambios de módulos siguen siendo acciones explícitas y autenticadas.", "As rotas são informativas. A instalação do driver e as alterações de módulos continuam sendo ações explícitas e autenticadas.", "Пути приведены для справки. Установка драйвера и изменение модулей остаются явными действиями с аутентификацией.", "Шляхи наведено для довідки. Встановлення драйвера й зміни модулів залишаються явними автентифікованими діями.", "Die Pfade dienen zur Information. Treiberinstallation und Moduländerungen bleiben ausdrückliche, authentifizierte Aktionen."),
    _entry("Detected", "Detectado", "Detectado", "Обнаружено", "Виявлено", "Erkannt"),
    _entry("Arch family", "Familia Arch", "Família Arch", "Семейство Arch", "Сімейство Arch", "Arch-Familie"),
    _entry("Live Linux detection", "Detección activa de Linux", "Detecção ativa do Linux", "Текущее обнаружение Linux", "Поточне виявлення Linux", "Live-Linux-Erkennung"),
    _entry("These values are read from the current NCT hwmon device and loaded kernel modules.", "Estos valores se leen del dispositivo NCT hwmon actual y de los módulos del kernel cargados.", "Esses valores são lidos do dispositivo NCT hwmon atual e dos módulos do kernel carregados.", "Эти значения считываются из текущего устройства NCT hwmon и загруженных модулей ядра.", "Ці значення зчитуються з поточного пристрою NCT hwmon і завантажених модулів ядра.", "Diese Werte werden vom aktuellen NCT-hwmon-Gerät und den geladenen Kernelmodulen gelesen."),
    _entry("Verification commands", "Comandos de verificación", "Comandos de verificação", "Команды проверки", "Команди перевірки", "Prüfkommandos"),
    _entry("The application uses the Arch repository strategy and an AUR helper when nct6687d-dkms-git is available.", "La aplicación usa la estrategia de repositorios de Arch y un ayudante de AUR cuando nct6687d-dkms-git está disponible.", "O aplicativo usa a estratégia de repositórios do Arch e um auxiliar do AUR quando nct6687d-dkms-git está disponível.", "Приложение использует стратегию репозиториев Arch и помощник AUR, когда доступен nct6687d-dkms-git.", "Програма використовує стратегію репозиторіїв Arch і помічник AUR, коли доступний nct6687d-dkms-git.", "Die Anwendung nutzt die Arch-Repository-Strategie und einen AUR-Helfer, wenn nct6687d-dkms-git verfügbar ist."),
    _entry("Mutable Fedora systems compile the module for the active kernel and install it in the normal module tree.", "Los sistemas Fedora mutables compilan el módulo para el kernel activo y lo instalan en el árbol normal de módulos.", "Sistemas Fedora mutáveis compilam o módulo para o kernel ativo e o instalam na árvore normal de módulos.", "Изменяемые системы Fedora собирают модуль для активного ядра и устанавливают его в обычное дерево модулей.", "Змінювані системи Fedora збирають модуль для активного ядра й встановлюють його до звичайного дерева модулів.", "Veränderbare Fedora-Systeme kompilieren das Modul für den aktiven Kernel und installieren es im normalen Modulbaum."),
    _entry("The immutable strategy stores a kernel-specific module under /var and loads the exact file through systemd.", "La estrategia inmutable guarda un módulo específico del kernel en /var y carga ese archivo exacto mediante systemd.", "A estratégia imutável armazena um módulo específico do kernel em /var e carrega o arquivo exato pelo systemd.", "Неизменяемая стратегия хранит модуль для конкретного ядра в /var и загружает точный файл через systemd.", "Незмінна стратегія зберігає модуль для конкретного ядра у /var і завантажує точний файл через systemd.", "Die unveränderliche Strategie speichert ein kernelspezifisches Modul unter /var und lädt genau diese Datei über systemd."),
    _entry("The Debian strategy installs matching kernel headers, builds nct6687d, runs depmod, and updates initramfs when available.", "La estrategia de Debian instala las cabeceras del kernel correspondientes, compila nct6687d, ejecuta depmod y actualiza initramfs cuando está disponible.", "A estratégia Debian instala os headers correspondentes do kernel, compila nct6687d, executa depmod e atualiza o initramfs quando disponível.", "Стратегия Debian устанавливает подходящие заголовки ядра, собирает nct6687d, запускает depmod и обновляет initramfs, если он доступен.", "Стратегія Debian встановлює відповідні заголовки ядра, збирає nct6687d, запускає depmod і оновлює initramfs, якщо він доступний.", "Die Debian-Strategie installiert passende Kernel-Header, baut nct6687d, führt depmod aus und aktualisiert initramfs, sofern verfügbar."),
    _entry("SteamOS uses its own strategy because read-only root handling, pacman keyring setup, and Neptune kernel headers are not standard Arch behavior.", "SteamOS usa su propia estrategia porque el manejo de la raíz de solo lectura, la configuración del llavero de pacman y las cabeceras Neptune no siguen el comportamiento estándar de Arch.", "O SteamOS usa uma estratégia própria porque o tratamento da raiz somente leitura, a configuração do chaveiro do pacman e os headers Neptune não seguem o comportamento padrão do Arch.", "SteamOS использует отдельную стратегию, поскольку работа с корнем только для чтения, настройка связки ключей pacman и заголовки ядра Neptune отличаются от стандартного Arch.", "SteamOS використовує окрему стратегію, оскільки робота з коренем лише для читання, налаштування сховища ключів pacman і заголовки ядра Neptune відрізняються від стандартного Arch.", "SteamOS verwendet eine eigene Strategie, da schreibgeschützte Root-Behandlung, pacman-Schlüsselbund und Neptune-Kernel-Header nicht dem Standardverhalten von Arch entsprechen."),
    _entry("Chip", "Chip", "Chip", "Чип", "Чип", "Chip"),
    _entry("Hwmon root", "Raíz de hwmon", "Raiz do hwmon", "Корень hwmon", "Корінь hwmon", "hwmon-Stammverzeichnis"),
    _entry("PWM files", "Archivos PWM", "Arquivos PWM", "Файлы PWM", "Файли PWM", "PWM-Dateien"),
    _entry("GUI helper", "Auxiliar de la GUI", "Auxiliar da GUI", "Помощник интерфейса", "Помічник інтерфейсу", "GUI-Hilfsprogramm"),
    _entry("Configuration", "Configuración", "Configuração", "Конфигурация", "Конфігурація", "Konfiguration"),
    _entry("Persistence", "Persistencia", "Persistência", "Постоянная настройка", "Постійні налаштування", "Persistenz"),
    _entry("Build cache", "Caché de compilación", "Cache de compilação", "Кэш сборки", "Кеш збирання", "Build-Cache"),
    _entry("Kernel module", "Módulo del kernel", "Módulo do kernel", "Модуль ядра", "Модуль ядра", "Kernelmodul"),
    _entry("Source cache", "Caché de fuentes", "Cache de fontes", "Кэш исходников", "Кеш вихідних файлів", "Quellcode-Cache"),
    _entry("Persistent state", "Estado persistente", "Estado persistente", "Постоянное состояние", "Постійний стан", "Persistenter Zustand"),
    _entry("Compatibility path", "Ruta de compatibilidad", "Caminho de compatibilidade", "Путь совместимости", "Шлях сумісності", "Kompatibilitätspfad"),
    _entry("Kernel headers", "Cabeceras del kernel", "Headers do kernel", "Заголовки ядра", "Заголовки ядра", "Kernel-Header"),
    _entry("Application sources", "Fuentes de la aplicación", "Fontes do aplicativo", "Исходники приложения", "Вихідні файли програми", "Anwendungsquellen"),
    _entry("Kernel tree", "Árbol del kernel", "Árvore do kernel", "Дерево ядра", "Дерево ядра", "Kernelbaum"),
    _entry("Driver metadata", "Metadatos del controlador", "Metadados do driver", "Метаданные драйвера", "Метадані драйвера", "Treiber-Metadaten"),
    _entry("Sensors", "Sensores", "Sensores", "Датчики", "Датчики", "Sensoren"),
    _entry("Packages", "Paquetes", "Pacotes", "Пакеты", "Пакунки", "Pakete"),
    _entry("Driver", "Controlador", "Driver", "Драйвер", "Драйвер", "Treiber"),
    _entry("Not detected", "No detectado", "Não detectado", "Не обнаружено", "Не виявлено", "Nicht erkannt"),
    _entry("Compute Units raw status", "Estado bruto de Compute Units", "Status bruto das Compute Units", "Необработанное состояние Compute Units", "Необроблений стан Compute Units", "Compute-Units-Rohstatus"),
]))


# Dialog-specific messages. These are kept exact so confirmation and warning
# wording remains clear in every supported language instead of relying on the
# generic phrase fallback.
_EXACT.update(dict([
    _entry("The original protected workflow will request a graceful SIGTERM first, wait 1.5 seconds, and force-close only remaining unprotected processes.", "El flujo protegido original solicitará primero un SIGTERM normal, esperará 1,5 segundos y forzará el cierre únicamente de los procesos no protegidos que sigan activos.", "O fluxo protegido original solicitará primeiro um SIGTERM normal, aguardará 1,5 segundos e forçará o encerramento apenas dos processos não protegidos que permanecerem ativos.", "Исходный защищённый процесс сначала отправит обычный SIGTERM, подождёт 1,5 секунды и принудительно завершит только оставшиеся незащищённые процессы.", "Початковий захищений процес спочатку надішле звичайний SIGTERM, зачекає 1,5 секунди й примусово завершить лише решту незахищених процесів.", "Der ursprüngliche geschützte Ablauf sendet zunächst ein reguläres SIGTERM, wartet 1,5 Sekunden und beendet nur verbleibende ungeschützte Prozesse zwangsweise."),
    _entry("Release Linux page cache", "Liberar la caché de páginas de Linux", "Liberar o cache de páginas do Linux", "Освободить страничный кэш Linux", "Звільнити сторінковий кеш Linux", "Linux-Seitencache freigeben"),
    _entry("This starts the existing pkexec workflow: sync, then write 3 to /proc/sys/vm/drop_caches. It can make applications reload data from disk and is not a substitute for closing heavy workloads.", "Esto inicia el flujo pkexec existente: ejecuta sync y después escribe 3 en /proc/sys/vm/drop_caches. Puede hacer que las aplicaciones vuelvan a cargar datos del disco y no sustituye el cierre de cargas pesadas.", "Isso inicia o fluxo pkexec existente: executa sync e depois grava 3 em /proc/sys/vm/drop_caches. Pode fazer os aplicativos recarregarem dados do disco e não substitui o encerramento de cargas pesadas.", "Это запускает существующий процесс pkexec: sync, затем запись 3 в /proc/sys/vm/drop_caches. Приложения могут повторно загружать данные с диска; это не заменяет закрытие тяжёлых задач.", "Це запускає наявний процес pkexec: sync, а потім запис 3 до /proc/sys/vm/drop_caches. Програми можуть повторно завантажувати дані з диска; це не замінює закриття важких завдань.", "Dies startet den vorhandenen pkexec-Ablauf: sync und anschließend das Schreiben von 3 nach /proc/sys/vm/drop_caches. Anwendungen müssen dadurch eventuell Daten neu von der Festplatte laden; dies ersetzt nicht das Schließen hoher Arbeitslasten."),
    _entry("Request cache release", "Solicitar liberación de caché", "Solicitar liberação do cache", "Запросить освобождение кэша", "Запросити звільнення кешу", "Cache-Freigabe anfordern"),
    _entry("Process operation failed", "Falló la operación de procesos", "A operação de processos falhou", "Операция с процессами завершилась ошибкой", "Операція з процесами завершилася помилкою", "Prozessvorgang fehlgeschlagen"),
    _entry("TASK MANAGER", "ADMINISTRADOR DE TAREAS", "GERENCIADOR DE TAREFAS", "ДИСПЕТЧЕР ЗАДАЧ", "ДИСПЕТЧЕР ЗАВДАНЬ", "TASK-MANAGER"),
    _entry("No additional action will be attempted automatically.", "No se intentará ninguna acción adicional automáticamente.", "Nenhuma ação adicional será tentada automaticamente.", "Дополнительные действия автоматически выполняться не будут.", "Додаткові дії автоматично не виконуватимуться.", "Es wird keine weitere Aktion automatisch versucht."),
    _entry("Select one or more unprotected application rows before ending tasks.", "Selecciona una o más filas de aplicaciones no protegidas antes de finalizar tareas.", "Selecione uma ou mais linhas de aplicativos não protegidos antes de encerrar tarefas.", "Перед завершением задач выберите одну или несколько строк незащищённых приложений.", "Перед завершенням завдань виберіть один або кілька рядків незахищених програм.", "Wähle vor dem Beenden von Aufgaben eine oder mehrere ungeschützte Anwendungszeilen aus."),
    _entry("Protected rows are never sent to the close backend.", "Las filas protegidas nunca se envían al backend de cierre.", "As linhas protegidas nunca são enviadas ao backend de encerramento.", "Защищённые строки никогда не передаются механизму завершения.", "Захищені рядки ніколи не передаються механізму завершення.", "Geschützte Zeilen werden niemals an das Beenden-Backend gesendet."),
    _entry("No process was signaled.", "No se envió ninguna señal a procesos.", "Nenhum processo recebeu sinal.", "Ни одному процессу не был отправлен сигнал.", "Жодному процесу не було надіслано сигнал.", "An keinen Prozess wurde ein Signal gesendet."),
    _entry("ADVANCED MEMORY ACTION", "ACCIÓN AVANZADA DE MEMORIA", "AÇÃO AVANÇADA DE MEMÓRIA", "РАСШИРЕННАЯ ОПЕРАЦИЯ С ПАМЯТЬЮ", "РОЗШИРЕНА ДІЯ З ПАМ'ЯТТЮ", "ERWEITERTE SPEICHERAKTION"),
    _entry("No privileged command was started.", "No se inició ningún comando privilegiado.", "Nenhum comando privilegiado foi iniciado.", "Привилегированные команды не запускались.", "Привілейовані команди не запускалися.", "Es wurde kein privilegierter Befehl gestartet."),
    _entry("Page cache request started", "Solicitud de caché de páginas iniciada", "Solicitação do cache de páginas iniciada", "Запрос страничного кэша запущен", "Запит сторінкового кешу запущено", "Seitencache-Anforderung gestartet"),
    _entry("The existing pkexec workflow was launched. If an authentication prompt appears, the cache action is applied only after it is accepted.", "Se inició el flujo pkexec existente. Si aparece una solicitud de autenticación, la acción de caché solo se aplica después de aceptarla.", "O fluxo pkexec existente foi iniciado. Se uma solicitação de autenticação aparecer, a ação de cache só será aplicada depois de aceita.", "Запущен существующий процесс pkexec. Если появится запрос аутентификации, действие с кэшем будет выполнено только после подтверждения.", "Запущено наявний процес pkexec. Якщо з'явиться запит автентифікації, дію з кешем буде виконано лише після підтвердження.", "Der vorhandene pkexec-Ablauf wurde gestartet. Falls eine Authentifizierungsabfrage erscheint, wird die Cache-Aktion erst nach deren Bestätigung ausgeführt."),
    _entry("Applications were not closed by this action.", "Esta acción no cerró aplicaciones.", "Esta ação não encerrou aplicativos.", "Это действие не закрывало приложения.", "Ця дія не закривала програми.", "Durch diese Aktion wurden keine Anwendungen geschlossen."),
    _entry("This opens the existing distribution-aware R64 workflow. It can install or update the governor, bc250_smu_oc, UMR, and the compute-unit live manager in a visible terminal.", "Esto abre el flujo R64 existente adaptado a la distribución. Puede instalar o actualizar el governor, bc250_smu_oc, UMR y el administrador en vivo de Compute Units en una terminal visible.", "Isso abre o fluxo R64 existente adaptado à distribuição. Ele pode instalar ou atualizar o governor, bc250_smu_oc, UMR e o gerenciador ao vivo de Compute Units em um terminal visível.", "Открывается существующий процесс R64 с учётом дистрибутива. В видимом терминале он может установить или обновить governor, bc250_smu_oc, UMR и live-менеджер Compute Units.", "Відкривається наявний процес R64 з урахуванням дистрибутива. У видимому терміналі він може встановити або оновити governor, bc250_smu_oc, UMR і live-менеджер Compute Units.", "Dies öffnet den vorhandenen distributionsabhängigen R64-Ablauf. In einem sichtbaren Terminal können Governor, bc250_smu_oc, UMR und der Live-Manager für Compute Units installiert oder aktualisiert werden."),
    _entry("GPU GOVERNOR", "GOVERNOR DE GPU", "GOVERNOR DA GPU", "GOVERNOR GPU", "GOVERNOR GPU", "GPU-GOVERNOR"),
    _entry("THERMAL CONTROL", "CONTROL TÉRMICO", "CONTROLE TÉRMICO", "ТЕРМОУПРАВЛЕНИЕ", "ТЕРМОКЕРУВАННЯ", "THERMISCHE STEUERUNG"),
    _entry("No additional hardware command will run automatically.", "No se ejecutará automáticamente ningún comando adicional de hardware.", "Nenhum comando adicional de hardware será executado automaticamente.", "Дополнительные аппаратные команды автоматически запускаться не будут.", "Додаткові апаратні команди автоматично не запускатимуться.", "Es wird kein weiterer Hardwarebefehl automatisch ausgeführt."),
    _entry("The existing distribution-specific dependency workflow will prepare UMR and bc250-cu-live-manager. Package installation may open a visible terminal and request administrator authentication.", "El flujo de dependencias específico de la distribución preparará UMR y bc250-cu-live-manager. La instalación de paquetes puede abrir una terminal visible y solicitar autenticación de administrador.", "O fluxo de dependências específico da distribuição preparará o UMR e o bc250-cu-live-manager. A instalação de pacotes pode abrir um terminal visível e solicitar autenticação de administrador.", "Существующий процесс зависимостей для данного дистрибутива подготовит UMR и bc250-cu-live-manager. Установка пакетов может открыть видимый терминал и запросить аутентификацию администратора.", "Наявний процес залежностей для цього дистрибутива підготує UMR і bc250-cu-live-manager. Встановлення пакунків може відкрити видимий термінал і запросити автентифікацію адміністратора.", "Der vorhandene distributionsspezifische Abhängigkeitsablauf bereitet UMR und bc250-cu-live-manager vor. Die Paketinstallation kann ein sichtbares Terminal öffnen und eine Administrator-Authentifizierung anfordern."),
    _entry("Install UMR", "Instalar UMR", "Instalar UMR", "Установить UMR", "Встановити UMR", "UMR installieren"),
    _entry("UMR is required to read and write the BC250 registers used by the WGP table. The distribution-specific installer may open a terminal and request administrator authentication.", "UMR es necesario para leer y escribir los registros de la BC250 que usa la tabla WGP. El instalador específico de la distribución puede abrir una terminal y solicitar autenticación de administrador.", "O UMR é necessário para ler e gravar os registradores da BC250 usados pela tabela WGP. O instalador específico da distribuição pode abrir um terminal e solicitar autenticação de administrador.", "UMR необходим для чтения и записи регистров BC250, используемых таблицей WGP. Установщик для дистрибутива может открыть терминал и запросить аутентификацию администратора.", "UMR потрібен для читання й запису регістрів BC250, які використовує таблиця WGP. Інсталятор для дистрибутива може відкрити термінал і запросити автентифікацію адміністратора.", "UMR wird zum Lesen und Schreiben der von der WGP-Tabelle verwendeten BC250-Register benötigt. Das distributionsspezifische Installationsprogramm kann ein Terminal öffnen und eine Administrator-Authentifizierung anfordern."),
    _entry("COMPUTE UNITS", "UNIDADES DE CÓMPUTO", "UNIDADES DE COMPUTAÇÃO", "ВЫЧИСЛИТЕЛЬНЫЕ БЛОКИ", "ОБЧИСЛЮВАЛЬНІ БЛОКИ", "COMPUTE UNITS"),
    _entry("The application did not report this operation as successful.", "La aplicación no informó que esta operación se completara correctamente.", "O aplicativo não informou que esta operação foi concluída com sucesso.", "Приложение не сообщило об успешном выполнении этой операции.", "Програма не повідомила про успішне виконання цієї операції.", "Die Anwendung hat diesen Vorgang nicht als erfolgreich gemeldet."),
    _entry("Game Mode was verified; the CU-specific UMR backend failed.", "Game Mode se verificó correctamente; falló el backend UMR específico de las unidades de cómputo.", "O Game Mode foi verificado; o backend UMR específico das unidades de computação falhou.", "Game Mode подтверждён; произошёл сбой UMR-бэкенда для вычислительных блоков.", "Game Mode підтверджено; сталася помилка UMR-бекенда для обчислювальних блоків.", "Game Mode wurde bestätigt; das CU-spezifische UMR-Backend ist fehlgeschlagen."),
    _entry("The helper could not verify the Game Mode launch context.", "El helper no pudo verificar el contexto de inicio de Game Mode.", "O helper não conseguiu verificar o contexto de inicialização do Game Mode.", "Помощник не смог подтвердить контекст запуска Game Mode.", "Помічник не зміг підтвердити контекст запуску Game Mode.", "Der Helper konnte den Game-Mode-Startkontext nicht bestätigen."),
    _entry("The installed privileged helper does not match this application build.", "El helper privilegiado instalado no corresponde a esta compilación de la aplicación.", "O helper privilegiado instalado não corresponde a esta compilação do aplicativo.", "Установленный привилегированный помощник не соответствует этой сборке приложения.", "Установлений привілейований помічник не відповідає цій збірці програми.", "Der installierte privilegierte Helper entspricht nicht diesem Anwendungs-Build."),
    _entry("A Compute Units dependency is missing or unavailable.", "Falta una dependencia de Unidades de Cómputo o no está disponible.", "Uma dependência das unidades de computação está ausente ou indisponível.", "Зависимость вычислительных блоков отсутствует или недоступна.", "Залежність обчислювальних блоків відсутня або недоступна.", "Eine Compute-Units-Abhängigkeit fehlt oder ist nicht verfügbar."),
    _entry("Authenticate and apply", "Autenticar y aplicar", "Autenticar e aplicar", "Аутентифицироваться и применить", "Автентифікуватися й застосувати", "Authentifizieren und anwenden"),
    _entry("Install and enable persistence", "Instalar y activar persistencia", "Instalar e ativar persistência", "Установить и включить постоянное применение", "Встановити й увімкнути постійне застосування", "Installieren und Persistenz aktivieren"),
    _entry("CPU runtime details", "Detalles de ejecución de CPU", "Detalhes de execução da CPU", "Сведения о работе CPU", "Відомості про роботу CPU", "CPU-Laufzeitdetails"),
    _entry("CPU / SMU", "CPU / SMU", "CPU / SMU", "CPU / SMU", "CPU / SMU", "CPU / SMU"),
    _entry("This view is informational only. No new hardware command was executed.", "Esta vista es únicamente informativa. No se ejecutó ningún comando nuevo de hardware.", "Esta visualização é apenas informativa. Nenhum novo comando de hardware foi executado.", "Это представление носит только информационный характер. Новые аппаратные команды не выполнялись.", "Це подання має лише інформаційний характер. Нові апаратні команди не виконувалися.", "Diese Ansicht dient nur zur Information. Es wurde kein neuer Hardwarebefehl ausgeführt."),
    _entry("No additional hardware command was executed.", "No se ejecutó ningún comando adicional de hardware.", "Nenhum comando adicional de hardware foi executado.", "Дополнительные аппаратные команды не выполнялись.", "Додаткові апаратні команди не виконувалися.", "Es wurde kein zusätzlicher Hardwarebefehl ausgeführt."),
    _entry("This reuses the existing distribution-specific R64 workflow in a visible terminal. It may install packages or stage an immutable-system reboot.", "Esto reutiliza el flujo R64 existente específico de la distribución en una terminal visible. Puede instalar paquetes o preparar el reinicio de un sistema inmutable.", "Isso reutiliza o fluxo R64 existente específico da distribuição em um terminal visível. Ele pode instalar pacotes ou preparar a reinicialização de um sistema imutável.", "В видимом терминале повторно используется существующий процесс R64 для данного дистрибутива. Он может установить пакеты или подготовить перезагрузку неизменяемой системы.", "У видимому терміналі повторно використовується наявний процес R64 для цього дистрибутива. Він може встановити пакунки або підготувати перезавантаження незмінної системи.", "Dies verwendet den vorhandenen distributionsspezifischen R64-Ablauf in einem sichtbaren Terminal. Er kann Pakete installieren oder einen Neustart eines unveränderlichen Systems vorbereiten."),
    _entry("This module is not available in this installation.", "Este módulo no está disponible en esta instalación.", "Este módulo não está disponível nesta instalação.", "Этот модуль недоступен в этой установке.", "Цей модуль недоступний у цій інсталяції.", "Dieses Modul ist in dieser Installation nicht verfügbar."),
    _entry("MODULE", "MÓDULO", "MÓDULO", "МОДУЛЬ", "МОДУЛЬ", "MODUL"),
    _entry("Back to Dashboard", "Volver al Dashboard", "Voltar ao Dashboard", "Вернуться на панель", "Повернутися на панель", "Zurück zum Dashboard"),
    _entry("SYSTEM READINESS", "PREPARACIÓN DEL SISTEMA", "PREPARAÇÃO DO SISTEMA", "ГОТОВНОСТЬ СИСТЕМЫ", "ГОТОВНІСТЬ СИСТЕМИ", "SYSTEMBEREITSCHAFT"),
]))


_EXACT.update(dict([
    _entry("Inspect shared application paths or run the existing read-only memory-pressure evaluation.", "Inspecciona las rutas compartidas de la aplicación o ejecuta la evaluación existente de presión de memoria en modo de solo lectura.", "Inspecione os caminhos compartilhados do aplicativo ou execute a avaliação existente de pressão de memória em modo somente leitura.", "Просмотрите общие пути приложения или выполните существующую оценку давления памяти только для чтения.", "Перегляньте спільні шляхи програми або виконайте наявну оцінку тиску пам'яті лише для читання.", "Prüfe die gemeinsam genutzten Anwendungspfade oder führe die vorhandene schreibgeschützte Speicherlastanalyse aus."),
    _entry("View local paths", "Ver rutas locales", "Ver caminhos locais", "Показать локальные пути", "Показати локальні шляхи", "Lokale Pfade anzeigen"),
    _entry("Evaluate memory pressure", "Evaluar presión de memoria", "Avaliar pressão de memória", "Оценить нагрузку на память", "Оцінити навантаження на пам'ять", "Speicherdruck bewerten"),
    _entry("Open settings folder", "Abrir carpeta de configuración", "Abrir pasta de configurações", "Открыть папку настроек", "Відкрити папку налаштувань", "Einstellungsordner öffnen"),
    _entry("Local paths", "Rutas locales", "Caminhos locais", "Локальные пути", "Локальні шляхи", "Lokale Pfade"),
    _entry("Local paths unavailable", "Rutas locales no disponibles", "Caminhos locais indisponíveis", "Локальные пути недоступны", "Локальні шляхи недоступні", "Lokale Pfade nicht verfügbar"),
    _entry("The application backend did not return its shared configuration paths.", "El backend de la aplicación no devolvió sus rutas de configuración compartidas.", "O backend do aplicativo não retornou seus caminhos de configuração compartilhados.", "Backend приложения не вернул общие пути конфигурации.", "Backend програми не повернув спільні шляхи конфігурації.", "Das Anwendungs-Backend hat seine gemeinsam genutzten Konfigurationspfade nicht zurückgegeben."),
    _entry("Profiles", "Perfiles", "Perfis", "Профили", "Профілі", "Profile"),
    _entry("Stability data", "Datos de estabilidad", "Dados de estabilidade", "Данные стабильности", "Дані стабільності", "Stabilitätsdaten"),
    _entry("Runtime metrics", "Métricas de ejecución", "Métricas de execução", "Метрики выполнения", "Метрики виконання", "Laufzeitmetriken"),
    _entry("Installed tools", "Herramientas instaladas", "Ferramentas instaladas", "Установленные инструменты", "Встановлені інструменти", "Installierte Werkzeuge"),
    _entry("Application data", "Datos de la aplicación", "Dados do aplicativo", "Данные приложения", "Дані програми", "Anwendungsdaten"),
    _entry("Bundled tool sources", "Fuentes incluidas de herramientas", "Fontes incluídas das ferramentas", "Включённые исходники инструментов", "Включені вихідні файли інструментів", "Mitgelieferte Werkzeugquellen"),
    _entry("Level", "Nivel", "Nível", "Уровень", "Рівень", "Stufe"),
    _entry("RAM used", "RAM usada", "RAM usada", "Использовано RAM", "Використано RAM", "RAM belegt"),
    _entry("RAM available", "RAM disponible", "RAM disponível", "Доступно RAM", "Доступно RAM", "RAM verfügbar"),
    _entry("Swap used", "Swap usada", "Swap usada", "Использовано swap", "Використано swap", "Swap belegt"),
    _entry("Detected games", "Juegos detectados", "Jogos detectados", "Обнаруженные игры", "Виявлені ігри", "Erkannte Spiele"),
    _entry("Suggested applications", "Aplicaciones sugeridas", "Aplicativos sugeridos", "Предлагаемые приложения", "Запропоновані програми", "Vorgeschlagene Anwendungen"),
    _entry("This evaluation is read-only. No process was closed and no cache command was executed.", "Esta evaluación es de solo lectura. No se cerró ningún proceso ni se ejecutó ningún comando de caché.", "Esta avaliação é somente leitura. Nenhum processo foi encerrado e nenhum comando de cache foi executado.", "Эта оценка выполняется только для чтения. Процессы не закрывались, команды кэша не выполнялись.", "Ця оцінка виконується лише для читання. Процеси не закривалися, команди кешу не виконувалися.", "Diese Auswertung ist schreibgeschützt. Es wurde kein Prozess geschlossen und kein Cache-Befehl ausgeführt."),
    _entry("Largest suggested applications:", "Aplicaciones sugeridas de mayor consumo:", "Aplicativos sugeridos de maior consumo:", "Крупнейшие предлагаемые приложения:", "Найбільші запропоновані програми:", "Größte vorgeschlagene Anwendungen:"),
    _entry("Memory pressure", "Presión de memoria", "Pressão de memória", "Нагрузка на память", "Навантаження на пам'ять", "Speicherdruck"),
    _entry("Memory evaluation failed", "Falló la evaluación de memoria", "A avaliação de memória falhou", "Оценка памяти завершилась ошибкой", "Оцінка пам'яті завершилася помилкою", "Speicherauswertung fehlgeschlagen"),
    _entry("No process was closed and no cache command was executed.", "No se cerró ningún proceso ni se ejecutó ningún comando de caché.", "Nenhum processo foi encerrado e nenhum comando de cache foi executado.", "Процессы не закрывались, команды кэша не выполнялись.", "Процеси не закривалися, команди кешу не виконувалися.", "Es wurde kein Prozess geschlossen und kein Cache-Befehl ausgeführt."),
    _entry("MEMORY", "MEMORIA", "MEMÓRIA", "ПАМЯТЬ", "ПАМ'ЯТЬ", "SPEICHER"),
]))


_EXACT.update(dict([
    _entry("Repository could not be opened", "No se pudo abrir el repositorio", "Não foi possível abrir o repositório", "Не удалось открыть репозиторий", "Не вдалося відкрити репозиторій", "Repository konnte nicht geöffnet werden"),
    _entry("OFFICIAL REPOSITORY", "REPOSITORIO OFICIAL", "REPOSITÓRIO OFICIAL", "ОФИЦИАЛЬНЫЙ РЕПОЗИТОРИЙ", "ОФІЦІЙНИЙ РЕПОЗИТОРІЙ", "OFFIZIELLES REPOSITORY"),
    _entry("Copy the repository address into the browser that is already running.", "Copia la dirección del repositorio en el navegador que ya está abierto.", "Copie o endereço do repositório no navegador que já está aberto.", "Скопируйте адрес репозитория в уже запущенный браузер.", "Скопіюйте адресу репозиторію у вже запущений браузер.", "Kopiere die Repository-Adresse in den bereits geöffneten Browser."),
    _entry("Restore language, theme, density, accent, startup behavior, and sidebar preferences to their defaults? Hardware profiles and history are preserved.", "¿Restaurar el idioma, tema, densidad, acento, comportamiento de inicio y preferencias de la barra lateral a sus valores predeterminados? Los perfiles de hardware y el historial se conservarán.", "Restaurar idioma, tema, densidade, destaque, comportamento de inicialização e preferências da barra lateral para os padrões? Perfis de hardware e histórico serão preservados.", "Восстановить значения по умолчанию для языка, темы, плотности, акцента, запуска и боковой панели? Аппаратные профили и история будут сохранены.", "Відновити стандартні значення для мови, теми, щільності, акценту, запуску й бічної панелі? Апаратні профілі та історію буде збережено.", "Sprache, Design, Dichte, Akzent, Startverhalten und Seitenleisteneinstellungen auf Standardwerte zurücksetzen? Hardwareprofile und Verlauf bleiben erhalten."),
]))


_EXACT.update(dict([
    _entry("Warnings, confirmations, and long-running task notices used by the application.", "Advertencias, confirmaciones y avisos de tareas prolongadas usados por la aplicación.", "Avisos, confirmações e notificações de tarefas longas usados pelo aplicativo.", "Предупреждения, подтверждения и уведомления о длительных задачах приложения.", "Попередження, підтвердження й сповіщення про тривалі завдання застосунку.", "Warnungen, Bestätigungen und Hinweise zu länger laufenden Aufgaben der Anwendung."),
    _entry("Session feedback", "Información de la sesión", "Retorno da sessão", "Обратная связь сеанса", "Зворотний зв'язок сеансу", "Sitzungsrückmeldung"),
    _entry("Shown whenever a hardware action is blocked because live mode is not authorized.", "Se muestran cuando una acción de hardware se bloquea porque el modo en vivo no está autorizado.", "Exibidos sempre que uma ação de hardware é bloqueada porque o modo ao vivo não está autorizado.", "Показываются, когда аппаратное действие заблокировано из-за отсутствия разрешения режима реального времени.", "Показуються, коли апаратну дію заблоковано через відсутність дозволу режиму наживо.", "Wird angezeigt, wenn eine Hardwareaktion blockiert ist, weil der Live-Modus nicht autorisiert wurde."),
    _entry("Operation results", "Resultados de operaciones", "Resultados das operações", "Результаты операций", "Результати операцій", "Vorgangsergebnisse"),
    _entry("Success and error dialogs remain enabled for authenticated maintenance actions.", "Los diálogos de éxito y error permanecen activados para las acciones de mantenimiento autenticadas.", "Os diálogos de sucesso e erro permanecem ativados para ações de manutenção autenticadas.", "Диалоги успеха и ошибки остаются включёнными для аутентифицированных операций обслуживания.", "Діалоги успіху й помилки залишаються увімкненими для автентифікованих дій обслуговування.", "Erfolgs- und Fehlerdialoge bleiben für authentifizierte Wartungsaktionen aktiviert."),
    _entry("Always shown", "Siempre visible", "Sempre exibido", "Всегда показывается", "Завжди показується", "Immer angezeigt"),
    _entry("Protection policy", "Política de protección", "Política de proteção", "Политика защиты", "Політика захисту", "Schutzrichtlinie"),
    _entry("CPU changes", "Cambios de CPU", "Alterações da CPU", "Изменения CPU", "Зміни CPU", "CPU-Änderungen"),
    _entry("A confirmation is required before sending CPU frequency or voltage changes.", "Se requiere confirmación antes de enviar cambios de frecuencia o voltaje de CPU.", "É necessária uma confirmação antes de enviar alterações de frequência ou voltagem da CPU.", "Перед изменением частоты или напряжения CPU требуется подтверждение.", "Перед зміною частоти або напруги CPU потрібне підтвердження.", "Vor Änderungen an CPU-Frequenz oder -Spannung ist eine Bestätigung erforderlich."),
    _entry("GPU changes", "Cambios de GPU", "Alterações da GPU", "Изменения GPU", "Зміни GPU", "GPU-Änderungen"),
    _entry("A confirmation is required before GPU ranges, service actions, or voltage curves are applied.", "Se requiere confirmación antes de aplicar rangos GPU, acciones de servicio o curvas de voltaje.", "É necessária uma confirmação antes de aplicar faixas da GPU, ações de serviço ou curvas de voltagem.", "Перед применением диапазонов GPU, действий служб или кривых напряжения требуется подтверждение.", "Перед застосуванням діапазонів GPU, дій служб або кривих напруги потрібне підтвердження.", "Vor dem Anwenden von GPU-Bereichen, Dienstaktionen oder Spannungskurven ist eine Bestätigung erforderlich."),
    _entry("Fan writes", "Escrituras de ventilador", "Gravações de ventoinha", "Запись вентилятора", "Запис вентилятора", "Lüfter-Schreibzugriffe"),
    _entry("A confirmation is required before explicit PWM writes are authorized.", "Se requiere confirmación antes de autorizar escrituras PWM explícitas.", "É necessária uma confirmação antes de autorizar gravações PWM explícitas.", "Перед явной записью PWM требуется подтверждение.", "Перед явним записом PWM потрібне підтвердження.", "Vor ausdrücklichen PWM-Schreibzugriffen ist eine Bestätigung erforderlich."),
    _entry("Process termination", "Finalización de procesos", "Encerramento de processos", "Завершение процессов", "Завершення процесів", "Prozessbeendigung"),
    _entry("A confirmation is required before selected workloads are closed.", "Se requiere confirmación antes de cerrar las cargas de trabajo seleccionadas.", "É necessária uma confirmação antes de encerrar as cargas de trabalho selecionadas.", "Перед закрытием выбранных рабочих нагрузок требуется подтверждение.", "Перед закриттям вибраних робочих навантажень потрібне підтвердження.", "Vor dem Schließen ausgewählter Arbeitslasten ist eine Bestätigung erforderlich."),
    _entry("Required", "Obligatorio", "Obrigatório", "Обязательно", "Обов'язково", "Erforderlich"),
]))


# Exact labels from the remaining interface pages. Product names, units, hardware
# paths, style tokens, and chip/channel identifiers intentionally stay unchanged.
_EXACT.update(dict([
    _entry("120 samples · 1 s cadence · 2 minute window", "120 muestras · cadencia de 1 s · ventana de 2 minutos", "120 amostras · cadência de 1 s · janela de 2 minutos", "120 образцов · интервал 1 с · окно 2 минуты", "120 зразків · інтервал 1 с · вікно 2 хвилини", "120 Messwerte · 1-s-Takt · 2-Minuten-Fenster"),
    _entry("Access unavailable", "Acceso no disponible", "Acesso indisponível", "Доступ недоступен", "Доступ недоступний", "Zugriff nicht verfügbar"),
    _entry("Blocked", "Bloqueado", "Bloqueado", "Заблокировано", "Заблоковано", "Blockiert"),
    _entry("CONTROLLED CHANNEL", "CANAL CONTROLADO", "CANAL CONTROLADO", "УПРАВЛЯЕМЫЙ КАНАЛ", "КЕРОВАНИЙ КАНАЛ", "GESTEUERTER KANAL"),
    _entry("CURRENT", "ACTUAL", "ATUAL", "ТЕКУЩЕЕ", "ПОТОЧНЕ", "AKTUELL"),
    _entry("Common controls and diagnostics", "Controles y diagnósticos comunes", "Controles e diagnósticos comuns", "Общие элементы управления и диагностика", "Спільні елементи керування та діагностика", "Gemeinsame Steuerung und Diagnose"),
    _entry("Curve not loaded", "Curva no cargada", "Curva não carregada", "Кривая не загружена", "Криву не завантажено", "Kurve nicht geladen"),
    _entry("Detecting controller", "Detectando controlador", "Detectando controlador", "Обнаружение контроллера", "Виявлення контролера", "Controller wird erkannt"),
    _entry("Governor and hardware contract", "Contrato del governor y hardware", "Contrato do governor e hardware", "Контракт governor и оборудования", "Контракт governor та обладнання", "Governor- und Hardwarevertrag"),
    _entry("Governor console", "Consola del governor", "Console do governor", "Консоль governor", "Консоль governor", "Governor-Konsole"),
    _entry("Idle", "Inactivo", "Ocioso", "Ожидание", "Очікування", "Leerlauf"),
    _entry("Known floor", "Piso conocido", "Piso conhecido", "Известный минимум", "Відомий мінімум", "Bekannter Mindestwert"),
    _entry("LIVE HISTORY", "HISTORIAL EN VIVO", "HISTÓRICO AO VIVO", "ИСТОРИЯ В РЕАЛЬНОМ ВРЕМЕНИ", "ІСТОРІЯ НАЖИВО", "LIVE-VERLAUF"),
    _entry("LIVE RESPONSE MAP", "MAPA DE RESPUESTA EN VIVO", "MAPA DE RESPOSTA AO VIVO", "КАРТА ОТКЛИКА В РЕАЛЬНОМ ВРЕМЕНИ", "КАРТА ВІДГУКУ НАЖИВО", "LIVE-REAKTIONSKARTE"),
    _entry("Lab mode", "Modo laboratorio", "Modo laboratório", "Лабораторный режим", "Лабораторний режим", "Labormodus"),
    _entry("Last refresh --:--:--", "Última actualización --:--:--", "Última atualização --:--:--", "Последнее обновление --:--:--", "Останнє оновлення --:--:--", "Letzte Aktualisierung --:--:--"),
    _entry("Last sample --:--:--", "Última muestra --:--:--", "Última amostra --:--:--", "Последний образец --:--:--", "Останній зразок --:--:--", "Letzter Messwert --:--:--"),
    _entry("Locked", "Bloqueado", "Bloqueado", "Заблокировано", "Заблоковано", "Gesperrt"),
    _entry("No NCT hwmon route has been authorized yet.", "Todavía no se ha autorizado ninguna ruta hwmon NCT.", "Nenhuma rota hwmon NCT foi autorizada ainda.", "Путь NCT hwmon ещё не авторизован.", "Шлях NCT hwmon ще не авторизовано.", "Es wurde noch kein NCT-hwmon-Pfad autorisiert."),
    _entry("No channel detected", "No se detectó ningún canal", "Nenhum canal detectado", "Канал не обнаружен", "Канал не виявлено", "Kein Kanal erkannt"),
    _entry("No pending WGP changes.", "No hay cambios WGP pendientes.", "Não há alterações WGP pendentes.", "Нет ожидающих изменений WGP.", "Немає очікуваних змін WGP.", "Keine ausstehenden WGP-Änderungen."),
    _entry("Offline", "Sin conexión", "Offline", "Не в сети", "Не в мережі", "Offline"),
    _entry("Original GUI function: raise the minimum clock when a light game does not wake the governor correctly.", "Función de la GUI original: elevar la frecuencia mínima cuando un juego ligero no activa correctamente el governor.", "Função da GUI original: elevar o clock mínimo quando um jogo leve não ativa corretamente o governor.", "Функция исходного интерфейса: повысить минимальную частоту, когда лёгкая игра неправильно активирует governor.", "Функція оригінального інтерфейсу: підвищити мінімальну частоту, коли легка гра неправильно активує governor.", "Funktion der ursprünglichen GUI: den Mindesttakt anheben, wenn ein leichtes Spiel den Governor nicht richtig aktiviert."),
    _entry("PWM splitters and hubs normally share one control signal and expose only one tach/RPM signal.", "Los divisores y hubs PWM normalmente comparten una señal de control y exponen una sola señal de tacómetro/RPM.", "Divisores e hubs PWM normalmente compartilham um sinal de controle e expõem apenas um sinal de tacômetro/RPM.", "PWM-разветвители и хабы обычно используют общий управляющий сигнал и предоставляют только один сигнал тахометра/RPM.", "PWM-розгалужувачі та хаби зазвичай використовують спільний керувальний сигнал і надають лише один сигнал тахометра/RPM.", "PWM-Splitter und -Hubs teilen normalerweise ein Steuersignal und stellen nur ein Tacho-/RPM-Signal bereit."),
    _entry("Pump Fan / J4003 will be used for every staged write.", "Pump Fan / J4003 se usará para cada escritura preparada.", "Pump Fan / J4003 será usado em cada gravação preparada.", "Pump Fan / J4003 будет использоваться для каждой подготовленной записи.", "Pump Fan / J4003 використовуватиметься для кожного підготовленого запису.", "Pump Fan / J4003 wird für jeden vorbereiteten Schreibvorgang verwendet."),
    _entry("Quick Actions", "Acciones rápidas", "Ações rápidas", "Быстрые действия", "Швидкі дії", "Schnellaktionen"),
    _entry("Recent Activity", "Actividad reciente", "Atividade recente", "Недавняя активность", "Нещодавня активність", "Letzte Aktivität"),
    _entry("Role / validation", "Función / validación", "Função / validação", "Роль / проверка", "Роль / перевірка", "Rolle / Prüfung"),
    _entry("SELECTION", "SELECCIÓN", "SELEÇÃO", "ВЫБОР", "ВИБІР", "AUSWAHL"),
    _entry("Show high OC points (2050+ MHz)", "Mostrar puntos de OC alto (2050+ MHz)", "Mostrar pontos de OC alto (2050+ MHz)", "Показать точки высокого OC (2050+ МГц)", "Показати точки високого OC (2050+ МГц)", "Hohe OC-Punkte anzeigen (2050+ MHz)"),
    _entry("Target: 24 / 40 CUs", "Objetivo: 24 / 40 CU", "Alvo: 24 / 40 CUs", "Цель: 24 / 40 CU", "Ціль: 24 / 40 CU", "Ziel: 24 / 40 CUs"),
    _entry("The optional daemon can continue applying the saved curve after the GUI closes.", "El daemon opcional puede continuar aplicando la curva guardada después de cerrar la GUI.", "O daemon opcional pode continuar aplicando a curva salva depois que a GUI for fechada.", "Необязательный демон может продолжать применять сохранённую кривую после закрытия интерфейса.", "Необов'язковий демон може продовжувати застосовувати збережену криву після закриття інтерфейсу.", "Der optionale Daemon kann die gespeicherte Kurve nach dem Schließen der GUI weiter anwenden."),
    _entry("View All", "Ver todo", "Ver tudo", "Показать все", "Показати все", "Alle anzeigen"),
    _entry("threshold / duty", "umbral / ciclo", "limiar / ciclo", "порог / заполнение", "поріг / цикл", "Schwelle / Tastgrad"),
    _entry("Target -- %", "Objetivo -- %", "Alvo -- %", "Цель -- %", "Ціль -- %", "Ziel -- %"),
    _entry("Live CU topology refreshed", "Topología CU en vivo actualizada", "Topologia CU ao vivo atualizada", "Топология CU в реальном времени обновлена", "Топологію CU наживо оновлено", "Live-CU-Topologie aktualisiert"),
    _entry("SPI masks and amdgpu driver topology were read successfully.", "Las máscaras SPI y la topología del controlador amdgpu se leyeron correctamente.", "As máscaras SPI e a topologia do driver amdgpu foram lidas com sucesso.", "Маски SPI и топология драйвера amdgpu успешно прочитаны.", "Маски SPI й топологію драйвера amdgpu успішно прочитано.", "SPI-Masken und amdgpu-Treibertopologie wurden erfolgreich gelesen."),
]))


_EXACT.update(EXTRA_TRANSLATIONS)
_EXACT.update(INTERFACE_TRANSLATIONS)

# Reverse exact indexes let widgets created in a non-English startup language
# retain their canonical source text. This is required for reliable live
# switching between any two non-English languages. Unknown command output and
# hardware identifiers remain untouched.
_REVERSE_EXACT: dict[str, dict[str, str]] = {language: {} for language in SUPPORTED_LANGUAGES}
for _source, _mapping in _EXACT.items():
    for _language in SUPPORTED_LANGUAGES:
        _translated = _mapping.get(_language)
        if isinstance(_translated, str) and _translated:
            _REVERSE_EXACT[_language].setdefault(_translated, _source)
for _language in SUPPORTED_LANGUAGES:
    _target_catalog = BASE_TRANSLATIONS.get(_language, {})
    _english_catalog = BASE_TRANSLATIONS.get("en", {})
    for _legacy_source, _english_text in _english_catalog.items():
        _translated = _target_catalog.get(_legacy_source)
        if isinstance(_translated, str) and _translated and isinstance(_english_text, str):
            _REVERSE_EXACT[_language].setdefault(_translated, _english_text)


@lru_cache(maxsize=16384)
def _canonical_source_cached(source: str, lang: str) -> str:
    if lang == "en" or not source:
        return source
    return _REVERSE_EXACT.get(lang, {}).get(source, source)


def canonical_source(text: object, language: str | None = None) -> str:
    """Return the canonical English key for one exact translated value."""
    source = str(text or "")
    lang = resolve_language(language or _CURRENT_LANGUAGE)
    return _canonical_source_cached(source, lang)


PROJECT_OVERVIEW = {
    "es": """BC250 Control Center es una interfaz gráfica para administrar, preparar y supervisar herramientas comunitarias de la placa AMD BC-250.\n\nQué hace la aplicación:\n• Reúne en una sola ventana funciones de GPU, CPU, 40CU, procesos, memoria, sensores e historial.\n• Prepara dependencias en distribuciones compatibles para que una instalación reciente quede lista sin buscar comandos por internet.\n• Permite usar perfiles y acciones con advertencias, validaciones y límites visuales.\n• Muestra rutas, estado de servicios y salidas importantes para que el usuario entienda qué está ocurriendo.\n\nQué usa internamente:\n• cyan-skillfish-governor-smu para controlar rangos GPU mediante governor/D-Bus.\n• bc250_smu_oc para CPU OC temporal o persistente cuando el usuario lo decide.\n• bc250-cu-live-manager para dashboard live y acciones 40CU/24CU.\n• nct6687d para control PWM experimental de ventiladores cuando el usuario prepara ese módulo.\n• UMR, lm_sensors, systemd, Polkit y herramientas del sistema cuando hacen falta.\n\nCrédito y alcance del proyecto:\n• Nuestro trabajo es crear un centro de control gráfico que integra, organiza y administra estos repositorios de forma más accesible.\n• No reclamamos autoría sobre herramientas comunitarias externas; cada una conserva sus créditos, licencia y repositorio oficial.\n• El controlador nct6687d conserva sus créditos y licencia upstream en Fred78290/nct6687d.\n• El objetivo es que el usuario se sienta cómodo usando la BC-250 sin depender tanto de la terminal ni navegar entre múltiples repositorios.\n\nImportante:\n• Overclock, 40CU y cambios de frecuencia pueden causar cuelgues, apagones, pérdida de datos o daño de hardware.\n• Cada BC-250 es distinta; prueba por pasos y bajo tu responsabilidad.""",
    "en": """BC250 Control Center is a graphical interface for managing, preparing, and monitoring community tools for the AMD BC-250 board.\n\nWhat the application does:\n• Brings GPU, CPU, 40CU, processes, memory, sensors, and history into one window.\n• Prepares dependencies on supported distributions so a fresh installation is ready without searching the internet for commands.\n• Provides profiles and actions with warnings, validation, and visible limits.\n• Shows paths, service state, and important output so the user understands what is happening.\n\nWhat it uses internally:\n• cyan-skillfish-governor-smu to control GPU ranges through the governor/D-Bus interface.\n• bc250_smu_oc for temporary or persistent CPU OC when the user explicitly chooses it.\n• bc250-cu-live-manager for the live dashboard and 40CU/24CU actions.\n• nct6687d for experimental fan PWM control after that module is prepared.\n• UMR, lm_sensors, systemd, Polkit, and system tools when required.\n\nProject credit and scope:\n• Our work is a graphical launcher/control center that integrates, organizes, and manages these repositories in a friendlier way.\n• We do not claim authorship of external community tools; each retains its credits, license, and official repository.\n• The nct6687d driver retains its upstream credits and license at Fred78290/nct6687d.\n• The goal is to make the BC-250 comfortable to use without relying as much on the terminal or navigating between multiple repositories.\n\nImportant:\n• Overclocking, 40CU, and frequency changes can cause freezes, shutdowns, data loss, or hardware damage.\n• Every BC-250 is different; test gradually and at your own risk.""",
    "pt": """BC250 Control Center é uma interface gráfica para administrar, preparar e monitorar ferramentas comunitárias da placa AMD BC-250.\n\nO que o aplicativo faz:\n• Reúne em uma só janela funções de GPU, CPU, 40CU, processos, memória, sensores e histórico.\n• Prepara dependências em distribuições compatíveis para que uma instalação nova fique pronta sem procurar comandos na internet.\n• Permite usar perfis e ações com avisos, validações e limites visuais.\n• Mostra caminhos, status de serviços e saídas importantes para que o usuário entenda o que está acontecendo.\n\nO que usa internamente:\n• cyan-skillfish-governor-smu para controlar faixas da GPU por governor/D-Bus.\n• bc250_smu_oc para OC temporário ou persistente da CPU quando o usuário decide.\n• bc250-cu-live-manager para dashboard ao vivo e ações 40CU/24CU.\n• nct6687d para controle PWM experimental das ventoinhas quando o módulo é preparado.\n• UMR, lm_sensors, systemd, Polkit e ferramentas do sistema quando necessárias.\n\nCrédito e escopo do projeto:\n• Nosso trabalho é criar um centro de controle gráfico que integra, organiza e administra esses repositórios de forma mais acessível.\n• Não reivindicamos autoria das ferramentas comunitárias externas; cada uma mantém seus créditos, licença e repositório oficial.\n• O driver nct6687d mantém seus créditos e licença upstream em Fred78290/nct6687d.\n• O objetivo é tornar confortável o uso da BC-250 sem depender tanto do terminal nem navegar entre vários repositórios.\n\nImportante:\n• Overclock, 40CU e mudanças de frequência podem causar travamentos, desligamentos, perda de dados ou dano ao hardware.\n• Cada BC-250 é diferente; teste por etapas e por sua conta e risco.""",
    "ru": """BC250 Control Center — графический интерфейс для управления, подготовки и мониторинга инструментов сообщества для платы AMD BC-250.\n\nЧто делает приложение:\n• Объединяет в одном окне GPU, CPU, 40CU, процессы, память, датчики и историю.\n• Подготавливает зависимости в поддерживаемых дистрибутивах, чтобы новая установка была готова без поиска команд в интернете.\n• Предоставляет профили и действия с предупреждениями, проверками и наглядными пределами.\n• Показывает пути, состояние служб и важный вывод, чтобы пользователь понимал происходящее.\n\nЧто используется внутри:\n• cyan-skillfish-governor-smu для управления диапазонами GPU через governor/D-Bus.\n• bc250_smu_oc для временного или постоянного разгона CPU по явному выбору пользователя.\n• bc250-cu-live-manager для живой панели и действий 40CU/24CU.\n• nct6687d для экспериментального управления PWM вентиляторов после подготовки модуля.\n• UMR, lm_sensors, systemd, Polkit и системные инструменты при необходимости.\n\nАвторство и рамки проекта:\n• Наша работа — графический центр управления, который объединяет, упорядочивает и администрирует эти репозитории в более удобном виде.\n• Мы не заявляем авторство сторонних инструментов сообщества; каждый проект сохраняет своих авторов, лицензию и официальный репозиторий.\n• Драйвер nct6687d сохраняет исходное авторство и лицензию в Fred78290/nct6687d.\n• Цель — сделать использование BC-250 удобным без постоянной зависимости от терминала и множества репозиториев.\n\nВажно:\n• Разгон, 40CU и изменение частот могут вызвать зависания, выключения, потерю данных или повреждение оборудования.\n• Каждая BC-250 отличается; проверяйте поэтапно и на свой риск.""",
    "uk": """BC250 Control Center — графічний інтерфейс для керування, підготовки та моніторингу інструментів спільноти для плати AMD BC-250.\n\nЩо робить програма:\n• Об'єднує в одному вікні GPU, CPU, 40CU, процеси, пам'ять, датчики та історію.\n• Готує залежності в підтримуваних дистрибутивах, щоб нова інсталяція була готова без пошуку команд в інтернеті.\n• Надає профілі та дії з попередженнями, перевірками й наочними межами.\n• Показує шляхи, стан служб і важливий вивід, щоб користувач розумів, що відбувається.\n\nЩо використовується всередині:\n• cyan-skillfish-governor-smu для керування діапазонами GPU через governor/D-Bus.\n• bc250_smu_oc для тимчасового або постійного розгону CPU за явним вибором користувача.\n• bc250-cu-live-manager для live-панелі та дій 40CU/24CU.\n• nct6687d для експериментального керування PWM вентиляторів після підготовки модуля.\n• UMR, lm_sensors, systemd, Polkit і системні інструменти за потреби.\n\nАвторство та межі проєкту:\n• Наша робота — графічний центр керування, який інтегрує, упорядковує й адмініструє ці репозиторії у зручнішому вигляді.\n• Ми не заявляємо авторство зовнішніх інструментів спільноти; кожен зберігає свої права, ліцензію й офіційний репозиторій.\n• Драйвер nct6687d зберігає вихідне авторство та ліцензію у Fred78290/nct6687d.\n• Мета — зробити використання BC-250 комфортним без постійної залежності від термінала та переходів між багатьма репозиторіями.\n\nВажливо:\n• Розгін, 40CU та зміни частот можуть спричинити зависання, вимкнення, втрату даних або пошкодження обладнання.\n• Кожна BC-250 відрізняється; перевіряйте поетапно й на власний ризик.""",
    "de": """BC250 Control Center ist eine grafische Oberfläche zum Verwalten, Vorbereiten und Überwachen von Community-Werkzeugen für das AMD-BC-250-Board.\n\nWas die Anwendung macht:\n• Vereint GPU, CPU, 40CU, Prozesse, Speicher, Sensoren und Verlauf in einem Fenster.\n• Bereitet Abhängigkeiten auf unterstützten Distributionen vor, damit eine frische Installation ohne Suche nach Befehlen einsatzbereit ist.\n• Bietet Profile und Aktionen mit Warnungen, Prüfungen und sichtbaren Grenzen.\n• Zeigt Pfade, Dienststatus und wichtige Ausgaben, damit der Benutzer versteht, was geschieht.\n\nWas intern verwendet wird:\n• cyan-skillfish-governor-smu zur Steuerung der GPU-Bereiche über governor/D-Bus.\n• bc250_smu_oc für temporären oder dauerhaften CPU-OC nach ausdrücklicher Benutzerentscheidung.\n• bc250-cu-live-manager für das Live-Dashboard und 40CU/24CU-Aktionen.\n• nct6687d für experimentelle Lüfter-PWM-Steuerung nach Vorbereitung dieses Moduls.\n• UMR, lm_sensors, systemd, Polkit und Systemwerkzeuge bei Bedarf.\n\nCredits und Projektumfang:\n• Unsere Arbeit ist ein grafischer Launcher/ein Kontrollzentrum, das diese Repositorys benutzerfreundlicher integriert, organisiert und verwaltet.\n• Wir beanspruchen keine Urheberschaft an externen Community-Werkzeugen; jedes behält Credits, Lizenz und offizielles Repository.\n• Der nct6687d-Treiber behält seine Upstream-Credits und Lizenz bei Fred78290/nct6687d.\n• Ziel ist eine komfortable Nutzung der BC-250 ohne starke Abhängigkeit vom Terminal oder Wechsel zwischen vielen Repositorys.\n\nWichtig:\n• Overclocking, 40CU und Frequenzänderungen können Freezes, Abschaltungen, Datenverlust oder Hardwareschäden verursachen.\n• Jede BC-250 ist anders; teste schrittweise und auf eigenes Risiko.""",
}

DAEMON_DETAILS = {
    "en": """The bc250-control-centerd user daemon is optional. It monitors temperature, RAM, swap, governor state, and records JSONL metrics even when the GUI is closed.\n\nEnable:\nsystemctl --user enable --now bc250-control-centerd.service\n\nDisable:\nsystemctl --user disable --now bc250-control-centerd.service\n\nView status:\nsystemctl --user status bc250-control-centerd.service --no-pager\n\nIt can also apply the saved fan curve while the GUI is closed after PWM support has been prepared. It does not apply CPU or GPU overclock automatically.""",
    "es": """El daemon de usuario bc250-control-centerd es opcional. Supervisa temperatura, RAM, swap y estado del governor, y registra métricas JSONL aunque la GUI esté cerrada.\n\nActivar:\nsystemctl --user enable --now bc250-control-centerd.service\n\nDesactivar:\nsystemctl --user disable --now bc250-control-centerd.service\n\nVer estado:\nsystemctl --user status bc250-control-centerd.service --no-pager\n\nTambién puede aplicar la curva de ventilador guardada con la GUI cerrada después de preparar el soporte PWM. No aplica overclock de CPU o GPU automáticamente.""",
    "pt": """O daemon de usuário bc250-control-centerd é opcional. Ele monitora temperatura, RAM, swap e estado do governor, e registra métricas JSONL mesmo com a GUI fechada.\n\nAtivar:\nsystemctl --user enable --now bc250-control-centerd.service\n\nDesativar:\nsystemctl --user disable --now bc250-control-centerd.service\n\nVer status:\nsystemctl --user status bc250-control-centerd.service --no-pager\n\nEle também pode aplicar a curva de ventoinha salva com a GUI fechada depois que o suporte PWM for preparado. Não aplica overclock de CPU ou GPU automaticamente.""",
    "ru": """Пользовательский демон bc250-control-centerd необязателен. Он отслеживает температуру, RAM, swap и состояние governor, а также записывает метрики JSONL при закрытом интерфейсе.\n\nВключить:\nsystemctl --user enable --now bc250-control-centerd.service\n\nОтключить:\nsystemctl --user disable --now bc250-control-centerd.service\n\nСостояние:\nsystemctl --user status bc250-control-centerd.service --no-pager\n\nПосле подготовки PWM он также может применять сохранённую кривую вентилятора при закрытом интерфейсе. Автоматический разгон CPU или GPU не выполняется.""",
    "uk": """Користувацький демон bc250-control-centerd є необов'язковим. Він відстежує температуру, RAM, swap і стан governor, а також записує метрики JSONL, коли інтерфейс закрито.\n\nУвімкнути:\nsystemctl --user enable --now bc250-control-centerd.service\n\nВимкнути:\nsystemctl --user disable --now bc250-control-centerd.service\n\nСтан:\nsystemctl --user status bc250-control-centerd.service --no-pager\n\nПісля підготовки PWM він також може застосовувати збережену криву вентилятора, коли інтерфейс закрито. Автоматичний розгін CPU або GPU не виконується.""",
    "de": """Der Benutzer-Daemon bc250-control-centerd ist optional. Er überwacht Temperatur, RAM, Swap und Governor-Status und schreibt JSONL-Metriken, auch wenn die GUI geschlossen ist.\n\nAktivieren:\nsystemctl --user enable --now bc250-control-centerd.service\n\nDeaktivieren:\nsystemctl --user disable --now bc250-control-centerd.service\n\nStatus anzeigen:\nsystemctl --user status bc250-control-centerd.service --no-pager\n\nNach Vorbereitung der PWM-Unterstützung kann er bei geschlossener GUI auch die gespeicherte Lüfterkurve anwenden. CPU- oder GPU-Overclocking wird nicht automatisch angewendet.""",
}

# Ordered phrase replacements make dynamic status sentences and technical cards
# understandable even when their exact runtime value was not known at build time.
_PHRASES = {
    "es": {
        "No hardware changes will be made.": "No se realizarán cambios de hardware.",
        "No hardware command was executed.": "No se ejecutó ningún comando de hardware.",
        "No additional command will be attempted automatically.": "No se intentará ningún comando adicional automáticamente.",
        "Start the application with": "Inicia la aplicación con", "to": "para", "and": "y", "or": "o",
        "Current": "Actual", "current": "actual", "Active": "Activo", "active": "activo", "Default": "Predeterminado", "default": "predeterminado",
        "Service": "Servicio", "service": "servicio", "Status": "Estado", "status": "estado", "Range": "Rango", "range": "rango",
        "Frequency": "Frecuencia", "frequency": "frecuencia", "Voltage": "Voltaje", "voltage": "voltaje", "Temperature": "Temperatura", "temperature": "temperatura",
        "Profile": "Perfil", "profile": "perfil", "Selected": "Seleccionado", "selected": "seleccionado", "Safe": "Seguro", "safe": "seguro",
        "Apply": "Aplicar", "Review": "Revisar", "Prepare": "Preparar", "Enable": "Activar", "Disable": "Desactivar", "Restart": "Reiniciar",
        "Open": "Abrir", "Close": "Cerrar", "Refresh": "Actualizar", "Read": "Leer", "Write": "Escribir", "Save": "Guardar", "Clear": "Limpiar",
        "Warning": "Advertencia", "Error": "Error", "Available": "Disponible", "Unavailable": "No disponible", "Waiting": "Esperando",
        "Live": "En vivo", "Custom": "Personalizado", "Automatic": "Automático", "Manual": "Manual",
        "Memory": "Memoria", "Power": "Consumo", "Load": "Carga", "Core": "Núcleo", "Board": "Placa", "History": "Historial",
        "Details": "Detalles", "Tools": "Herramientas", "Dependencies": "Dependencias", "Diagnostics": "Diagnósticos", "Console": "Consola",
    },
    "pt": {
        "No hardware changes will be made.": "Nenhuma alteração de hardware será feita.",
        "No hardware command was executed.": "Nenhum comando de hardware foi executado.",
        "No additional command will be attempted automatically.": "Nenhum comando adicional será tentado automaticamente.",
        "Current": "Atual", "current": "atual", "Active": "Ativo", "active": "ativo", "Default": "Padrão", "default": "padrão",
        "Service": "Serviço", "service": "serviço", "Status": "Status", "status": "status", "Range": "Faixa", "range": "faixa",
        "Frequency": "Frequência", "frequency": "frequência", "Voltage": "Voltagem", "voltage": "voltagem", "Temperature": "Temperatura", "temperature": "temperatura",
        "Profile": "Perfil", "profile": "perfil", "Selected": "Selecionado", "selected": "selecionado", "Safe": "Seguro", "safe": "seguro",
        "Apply": "Aplicar", "Review": "Revisar", "Prepare": "Preparar", "Enable": "Ativar", "Disable": "Desativar", "Restart": "Reiniciar",
        "Open": "Abrir", "Close": "Fechar", "Refresh": "Atualizar", "Read": "Ler", "Write": "Gravar", "Save": "Salvar", "Clear": "Limpar",
        "Warning": "Aviso", "Error": "Erro", "Available": "Disponível", "Unavailable": "Indisponível", "Waiting": "Aguardando",
        "Live": "Ao vivo", "Custom": "Personalizado", "Automatic": "Automático", "Manual": "Manual",
        "Memory": "Memória", "Power": "Consumo", "Load": "Carga", "Core": "Núcleo", "Board": "Placa", "History": "Histórico",
        "Details": "Detalhes", "Tools": "Ferramentas", "Dependencies": "Dependências", "Diagnostics": "Diagnósticos", "Console": "Console",
    },
    "ru": {
        "No hardware changes will be made.": "Изменения оборудования не выполняются.",
        "No hardware command was executed.": "Команды оборудования не выполнялись.",
        "No additional command will be attempted automatically.": "Дополнительные команды автоматически выполняться не будут.",
        "Current": "Текущий", "current": "текущий", "Active": "Активный", "active": "активный", "Default": "По умолчанию", "default": "по умолчанию",
        "Service": "Служба", "service": "служба", "Status": "Состояние", "status": "состояние", "Range": "Диапазон", "range": "диапазон",
        "Frequency": "Частота", "frequency": "частота", "Voltage": "Напряжение", "voltage": "напряжение", "Temperature": "Температура", "temperature": "температура",
        "Profile": "Профиль", "profile": "профиль", "Selected": "Выбрано", "selected": "выбрано", "Safe": "Безопасный", "safe": "безопасный",
        "Apply": "Применить", "Review": "Проверить", "Prepare": "Подготовить", "Enable": "Включить", "Disable": "Отключить", "Restart": "Перезапустить",
        "Open": "Открыть", "Close": "Закрыть", "Refresh": "Обновить", "Read": "Прочитать", "Write": "Записать", "Save": "Сохранить", "Clear": "Очистить",
        "Warning": "Предупреждение", "Error": "Ошибка", "Available": "Доступно", "Unavailable": "Недоступно", "Waiting": "Ожидание",
        "Live": "В реальном времени", "Custom": "Пользовательский", "Automatic": "Автоматический", "Manual": "Ручной",
        "Memory": "Память", "Power": "Мощность", "Load": "Нагрузка", "Core": "Ядро", "Board": "Плата", "History": "История",
        "Details": "Подробности", "Tools": "Инструменты", "Dependencies": "Зависимости", "Diagnostics": "Диагностика", "Console": "Консоль",
    },
    "uk": {
        "No hardware changes will be made.": "Зміни обладнання не виконуються.",
        "No hardware command was executed.": "Команди обладнання не виконувалися.",
        "No additional command will be attempted automatically.": "Додаткові команди автоматично не виконуватимуться.",
        "Current": "Поточний", "current": "поточний", "Active": "Активний", "active": "активний", "Default": "За замовчуванням", "default": "за замовчуванням",
        "Service": "Служба", "service": "служба", "Status": "Стан", "status": "стан", "Range": "Діапазон", "range": "діапазон",
        "Frequency": "Частота", "frequency": "частота", "Voltage": "Напруга", "voltage": "напруга", "Temperature": "Температура", "temperature": "температура",
        "Profile": "Профіль", "profile": "профіль", "Selected": "Вибрано", "selected": "вибрано", "Safe": "Безпечний", "safe": "безпечний",
        "Apply": "Застосувати", "Review": "Перевірити", "Prepare": "Підготувати", "Enable": "Увімкнути", "Disable": "Вимкнути", "Restart": "Перезапустити",
        "Open": "Відкрити", "Close": "Закрити", "Refresh": "Оновити", "Read": "Прочитати", "Write": "Записати", "Save": "Зберегти", "Clear": "Очистити",
        "Warning": "Попередження", "Error": "Помилка", "Available": "Доступно", "Unavailable": "Недоступно", "Waiting": "Очікування",
        "Live": "Наживо", "Custom": "Користувацький", "Automatic": "Автоматичний", "Manual": "Ручний",
        "Memory": "Пам'ять", "Power": "Потужність", "Load": "Навантаження", "Core": "Ядро", "Board": "Плата", "History": "Історія",
        "Details": "Подробиці", "Tools": "Інструменти", "Dependencies": "Залежності", "Diagnostics": "Діагностика", "Console": "Консоль",
    },
    "de": {
        "No hardware changes will be made.": "Es werden keine Hardwareänderungen vorgenommen.",
        "No hardware command was executed.": "Es wurde kein Hardwarebefehl ausgeführt.",
        "No additional command will be attempted automatically.": "Es wird kein weiterer Befehl automatisch versucht.",
        "Current": "Aktuell", "current": "aktuell", "Active": "Aktiv", "active": "aktiv", "Default": "Standard", "default": "Standard",
        "Service": "Dienst", "service": "Dienst", "Status": "Status", "status": "Status", "Range": "Bereich", "range": "Bereich",
        "Frequency": "Frequenz", "frequency": "Frequenz", "Voltage": "Spannung", "voltage": "Spannung", "Temperature": "Temperatur", "temperature": "Temperatur",
        "Profile": "Profil", "profile": "Profil", "Selected": "Ausgewählt", "selected": "ausgewählt", "Safe": "Sicher", "safe": "sicher",
        "Apply": "Anwenden", "Review": "Prüfen", "Prepare": "Vorbereiten", "Enable": "Aktivieren", "Disable": "Deaktivieren", "Restart": "Neustarten",
        "Open": "Öffnen", "Close": "Schließen", "Refresh": "Aktualisieren", "Read": "Lesen", "Write": "Schreiben", "Save": "Speichern", "Clear": "Löschen",
        "Warning": "Warnung", "Error": "Fehler", "Available": "Verfügbar", "Unavailable": "Nicht verfügbar", "Waiting": "Warten",
        "Live": "Live", "Custom": "Benutzerdefiniert", "Automatic": "Automatisch", "Manual": "Manuell",
        "Memory": "Speicher", "Power": "Leistung", "Load": "Last", "Core": "Kern", "Board": "Board", "History": "Verlauf",
        "Details": "Details", "Tools": "Werkzeuge", "Dependencies": "Abhängigkeiten", "Diagnostics": "Diagnose", "Console": "Konsole",
    },
}


def _looks_technical_line(line: str) -> bool:
    stripped = line.strip()
    if not stripped:
        return False
    return bool(
        stripped.startswith(("/", "~/", "systemctl ", "journalctl ", "sudo ", "pkexec ", "cat ", "ls ", "modinfo ", "rpm-ostree ", "pacman ", "dpkg "))
        or re.match(r"^[A-Z0-9_./:+-]{2,}$", stripped)
    )


def _phrase_translate(text: str, language: str) -> str:
    phrases = _PHRASES.get(language, {})
    if not phrases:
        return text
    output_lines: list[str] = []
    ordered = sorted(phrases.items(), key=lambda item: len(item[0]), reverse=True)
    for line in text.splitlines():
        if _looks_technical_line(line):
            output_lines.append(line)
            continue
        result = line
        for source, target in ordered:
            if source in result:
                result = result.replace(source, target)
        output_lines.append(result)
    return "\n".join(output_lines)


def _legacy_exact(source: str, language: str) -> str:
    """Resolve legacy catalog entries exactly; never translate substrings."""
    target_catalog = BASE_TRANSLATIONS.get(language, {})
    direct = target_catalog.get(source)
    if isinstance(direct, str) and direct:
        return direct
    english_catalog = BASE_TRANSLATIONS.get("en", {})
    for legacy_source, english_text in english_catalog.items():
        if english_text == source:
            translated = target_catalog.get(legacy_source)
            if isinstance(translated, str) and translated:
                return translated
            break
    return source


def _short_count_form(count: int, unit: str, language: str) -> str:
    forms = {
        "event": {
            "en": ("event", "events", "events"), "es": ("evento", "eventos", "eventos"),
            "pt": ("evento", "eventos", "eventos"), "ru": ("событие", "события", "событий"),
            "uk": ("подія", "події", "подій"), "de": ("Ereignis", "Ereignisse", "Ereignisse"),
        },
        "second": {
            "en": ("second", "seconds", "seconds"), "es": ("segundo", "segundos", "segundos"),
            "pt": ("segundo", "segundos", "segundos"), "ru": ("секунда", "секунды", "секунд"),
            "uk": ("секунда", "секунди", "секунд"), "de": ("Sekunde", "Sekunden", "Sekunden"),
        },
        "minute": {
            "en": ("minute", "minutes", "minutes"), "es": ("minuto", "minutos", "minutos"),
            "pt": ("minuto", "minutos", "minutos"), "ru": ("минута", "минуты", "минут"),
            "uk": ("хвилина", "хвилини", "хвилин"), "de": ("Minute", "Minuten", "Minuten"),
        },
    }
    if language in {"ru", "uk"}:
        last_two = abs(count) % 100
        last = abs(count) % 10
        index = 0 if last == 1 and last_two != 11 else 1 if 2 <= last <= 4 and not 12 <= last_two <= 14 else 2
    else:
        index = 0 if abs(count) == 1 else 1
    words = forms.get(unit, {}).get(language) or forms.get(unit, {}).get("en") or (unit, unit + "s", unit + "s")
    return f"{count} {words[index]}"


@lru_cache(maxsize=32768)
def _tr_cached(source: str, lang: str) -> str:
    if lang == "en":
        return source
    count_match = re.fullmatch(r"(\d+) events?", source)
    if count_match:
        return _short_count_form(int(count_match.group(1)), "event", lang)
    second_match = re.fullmatch(r"(\d+) seconds?", source)
    if second_match:
        return _short_count_form(int(second_match.group(1)), "second", lang)
    minute_match = re.fullmatch(r"(\d+) minutes?", source)
    if minute_match:
        return _short_count_form(int(minute_match.group(1)), "minute", lang)
    exact = _EXACT.get(source)
    if exact:
        return exact.get(lang, source)
    return _legacy_exact(source, lang)


def tr(text: object, language: str | None = None) -> str:
    if text is None:
        return ""
    source = str(text)
    lang = resolve_language(language or _CURRENT_LANGUAGE)
    return _tr_cached(source, lang)



_HISTORY_TITLES = {
    "Manual fan speed applied": "Manual fan speed applied",
    "Fan curve daemon applied": "Fan curve daemon applied",
    "Fan curve daemon error": "Fan curve daemon error",
    "GPU caliente": "GPU temperature warning",
    "CPU caliente": "CPU temperature warning",
    "Governor no activo": "Governor is not active",
    "Acción 40CU": "40CU action",
    "Mapa CU actualizado": "CU map updated",
    "Dashboard 40CU actualizado": "40CU dashboard updated",
    "Preparar dependencias BC250": "Prepare BC250 dependencies",
    "Preparar bc250-detect": "Prepare bc250-detect",
    "Instalar UMR": "Install UMR",
    "Lab voltaje personalizado": "Custom voltage laboratory",
    "Lab voltaje aplicado": "Voltage laboratory applied",
    "CPU OC temporal": "Temporary CPU overclock",
    "CPU OC persistente": "Persistent CPU overclock",
    "Fan read-only setup": "Read-only fan setup",
    "Fan PWM setup": "Fan PWM setup",
    "Fan PWM disabled": "Fan PWM disabled",
    "Perfil GPU aplicado": "GPU profile applied",
    "Perfil inteligente seleccionado": "Smart profile selected",
    "Mínimo GPU aplicado": "GPU minimum applied",
    "Alertas inteligentes": "Smart alerts",
    "bc250-control-centerd iniciado": "BC250 daemon started",
    "bc250-control-centerd detenido": "BC250 daemon stopped",
    "Error en daemon": "Daemon error",
    "Selected tasks ended": "Selected tasks ended",
    "Page cache release requested": "Page cache release requested",
    "Page cache released": "Page cache released",
    "Linea de historial invalida": "Invalid history line",
    "Presion de memoria detectada": "Memory pressure detected",
}


def _translate_history_detail(detail: str, language: str) -> str:
    source = str(detail or "")
    if not source:
        return ""

    pwm = re.fullmatch(r"PWM (\d+) set to (\d+)% \((\d+)/255\)\.", source)
    if pwm:
        channel, percent, raw = pwm.groups()
        templates = {
            "es": "PWM {0} ajustado al {1}% ({2}/255).",
            "pt": "PWM {0} ajustado para {1}% ({2}/255).",
            "ru": "PWM {0} установлен на {1}% ({2}/255).",
            "uk": "PWM {0} встановлено на {1}% ({2}/255).",
            "de": "PWM {0} auf {1}% ({2}/255) gesetzt.",
        }
        return templates.get(language, "PWM {0} set to {1}% ({2}/255).").format(channel, percent, raw)

    pwm_short = re.fullmatch(r"PWM (\d+) set to (\d+)%\.", source)
    if pwm_short:
        channel, percent = pwm_short.groups()
        templates = {
            "es": "PWM {0} ajustado al {1}%.",
            "pt": "PWM {0} ajustado para {1}%.",
            "ru": "PWM {0} установлен на {1}%.",
            "uk": "PWM {0} встановлено на {1}%.",
            "de": "PWM {0} auf {1}% gesetzt.",
        }
        return templates.get(language, "PWM {0} set to {1}%.").format(channel, percent)

    verified = re.fullmatch(r"Verified target: (\d+) / (\d+) CUs\.", source)
    if verified:
        selected, total = verified.groups()
        templates = {
            "es": "Objetivo verificado: {0} / {1} CU.",
            "pt": "Destino verificado: {0} / {1} CUs.",
            "ru": "Цель проверена: {0} / {1} CU.",
            "uk": "Ціль перевірено: {0} / {1} CU.",
            "de": "Ziel geprüft: {0} / {1} CUs.",
        }
        return templates.get(language, "Verified target: {0} / {1} CUs.").format(selected, total)

    curve = re.fullmatch(r"GPU ([0-9.]+) C -> PWM (\d+) (\d+)%", source)
    if curve:
        temperature, channel, percent = curve.groups()
        templates = {
            "es": "GPU {0} °C → PWM {1} al {2}%",
            "pt": "GPU {0} °C → PWM {1} a {2}%",
            "ru": "GPU {0} °C → PWM {1} на {2}%",
            "uk": "GPU {0} °C → PWM {1} на {2}%",
            "de": "GPU {0} °C → PWM {1} bei {2}%",
        }
        return templates.get(language, "GPU {0} °C → PWM {1} at {2}%").format(temperature, channel, percent)

    range_match = re.fullmatch(r"Rango GPU actualizado a (\d+)-(\d+) MHz\.", source)
    if range_match:
        minimum, maximum = range_match.groups()
        templates = {
            "es": "Rango de GPU actualizado a {0}–{1} MHz.",
            "pt": "Faixa da GPU atualizada para {0}–{1} MHz.",
            "ru": "Диапазон GPU обновлён до {0}–{1} МГц.",
            "uk": "Діапазон GPU оновлено до {0}–{1} МГц.",
            "de": "GPU-Bereich auf {0}–{1} MHz aktualisiert.",
        }
        return templates.get(language, "GPU range updated to {0}–{1} MHz.").format(minimum, maximum)

    exact_details = {
        "menu": {"es": "menú", "pt": "menu", "ru": "меню", "uk": "меню", "de": "Menü"},
        "Monitor conservador activo": {"es": "Supervisión conservadora activa", "pt": "Monitoramento conservador ativo", "ru": "Консервативный мониторинг активен", "uk": "Консервативний моніторинг активний", "de": "Konservative Überwachung aktiv"},
        "Monitor apagado": {"es": "Supervisión detenida", "pt": "Monitoramento interrompido", "ru": "Мониторинг остановлен", "uk": "Моніторинг зупинено", "de": "Überwachung gestoppt"},
        "CPU / SMU operation completed": {"es": "Operación de CPU / SMU completada", "pt": "Operação de CPU / SMU concluída", "ru": "Операция CPU / SMU завершена", "uk": "Операцію CPU / SMU завершено", "de": "CPU-/SMU-Vorgang abgeschlossen"},
        "The privileged sync/drop_caches workflow completed successfully.": {"es": "El flujo privilegiado sync/drop_caches finalizó correctamente.", "pt": "O fluxo privilegiado sync/drop_caches foi concluído com sucesso.", "ru": "Привилегированная операция sync/drop_caches успешно завершена.", "uk": "Привілейовану операцію sync/drop_caches успішно завершено.", "de": "Der privilegierte sync/drop_caches-Ablauf wurde erfolgreich abgeschlossen."},
        "Opened terminal to configure nct6683 read-only monitoring.": {"es": "Se abrió una terminal para configurar la supervisión de solo lectura con nct6683.", "pt": "Um terminal foi aberto para configurar o monitoramento somente leitura com nct6683.", "ru": "Открыт терминал для настройки мониторинга nct6683 только для чтения.", "uk": "Відкрито термінал для налаштування моніторингу nct6683 лише для читання.", "de": "Ein Terminal zur Einrichtung der schreibgeschützten nct6683-Überwachung wurde geöffnet."},
        "Opened terminal to prepare nct6687 PWM driver.": {"es": "Se abrió una terminal para preparar el controlador PWM nct6687.", "pt": "Um terminal foi aberto para preparar o driver PWM nct6687.", "ru": "Открыт терминал для подготовки PWM-драйвера nct6687.", "uk": "Відкрито термінал для підготовки PWM-драйвера nct6687.", "de": "Ein Terminal zur Vorbereitung des nct6687-PWM-Treibers wurde geöffnet."},
        "Opened terminal to disable nct6687 PWM preference.": {"es": "Se abrió una terminal para desactivar la preferencia PWM nct6687.", "pt": "Um terminal foi aberto para desativar a preferência PWM nct6687.", "ru": "Открыт терминал для отключения настройки PWM nct6687.", "uk": "Відкрито термінал для вимкнення налаштування PWM nct6687.", "de": "Ein Terminal zum Deaktivieren der nct6687-PWM-Einstellung wurde geöffnet."},
        "Lectura de cu_map.sh completada": {"es": "Lectura de cu_map.sh completada", "pt": "Leitura de cu_map.sh concluída", "ru": "Чтение cu_map.sh завершено", "uk": "Читання cu_map.sh завершено", "de": "cu_map.sh wurde vollständig gelesen"},
        "Live-manager dashboard reading completed": {"es": "Lectura del dashboard del live manager completada", "pt": "Leitura do dashboard do live manager concluída", "ru": "Чтение панели live manager завершено", "uk": "Читання панелі live manager завершено", "de": "Live-Manager-Dashboard vollständig gelesen"},
        "Se abrió terminal para preparar dependencias faltantes.": {"es": "Se abrió una terminal para preparar las dependencias faltantes.", "pt": "Um terminal foi aberto para preparar as dependências ausentes.", "ru": "Открыт терминал для подготовки недостающих зависимостей.", "uk": "Відкрито термінал для підготовки відсутніх залежностей.", "de": "Ein Terminal zur Vorbereitung fehlender Abhängigkeiten wurde geöffnet."},
        "Se abrió terminal para preparar bc250_smu_oc/bc250-detect sin pip.": {"es": "Se abrió una terminal para preparar bc250_smu_oc/bc250-detect sin pip.", "pt": "Um terminal foi aberto para preparar bc250_smu_oc/bc250-detect sem pip.", "ru": "Открыт терминал для подготовки bc250_smu_oc/bc250-detect без pip.", "uk": "Відкрито термінал для підготовки bc250_smu_oc/bc250-detect без pip.", "de": "Ein Terminal zur Vorbereitung von bc250_smu_oc/bc250-detect ohne pip wurde geöffnet."},
        "Se abrió terminal para instalar UMR.": {"es": "Se abrió una terminal para instalar UMR.", "pt": "Um terminal foi aberto para instalar o UMR.", "ru": "Открыт терминал для установки UMR.", "uk": "Відкрито термінал для встановлення UMR.", "de": "Ein Terminal zur Installation von UMR wurde geöffnet."},
        "Instalacion de servicio bc250-smu-oc solicitada": {"es": "Se solicitó instalar el servicio bc250-smu-oc", "pt": "A instalação do serviço bc250-smu-oc foi solicitada", "ru": "Запрошена установка службы bc250-smu-oc", "uk": "Запитано встановлення служби bc250-smu-oc", "de": "Installation des Dienstes bc250-smu-oc angefordert"},
        "Desactivacion de servicio bc250-smu-oc solicitada": {"es": "Se solicitó desactivar el servicio bc250-smu-oc", "pt": "A desativação do serviço bc250-smu-oc foi solicitada", "ru": "Запрошено отключение службы bc250-smu-oc", "uk": "Запитано вимкнення служби bc250-smu-oc", "de": "Deaktivierung des Dienstes bc250-smu-oc angefordert"},
        "sigterm_conservador": {"es": "SIGTERM conservador", "pt": "SIGTERM conservador", "ru": "консервативный SIGTERM", "uk": "консервативний SIGTERM", "de": "konservatives SIGTERM"},
        "sin_cierres": {"es": "sin procesos cerrados", "pt": "sem processos encerrados", "ru": "процессы не завершены", "uk": "процеси не завершено", "de": "keine Prozesse beendet"},
        "sugerir_cierre": {"es": "se sugiere cerrar aplicaciones", "pt": "é recomendado encerrar aplicativos", "ru": "рекомендуется закрыть приложения", "uk": "рекомендовано закрити програми", "de": "Schließen von Anwendungen empfohlen"},
        "ninguna": {"es": "ninguna", "pt": "nenhuma", "ru": "нет", "uk": "немає", "de": "keine"},
    }
    translated = exact_details.get(source, {}).get(language)
    if translated:
        return translated

    # Command output and unrecognized backend details stay verbatim. Partial
    # phrase replacement can corrupt identifiers and is deliberately forbidden.
    return tr(source, language)


def translate_history_event(event: object, language: str | None = None) -> tuple[str, str]:
    data = event if isinstance(event, dict) else {"detalle": str(event)}
    lang = resolve_language(language or _CURRENT_LANGUAGE)
    metadata = data.get("datos") if isinstance(data.get("datos"), dict) else {}
    title_key = metadata.get("i18n_title")
    message_key = metadata.get("i18n_message")
    values = metadata.get("i18n_values")
    if isinstance(title_key, str) and isinstance(message_key, str):
        format_values = values if isinstance(values, dict) else {}
        return tr(title_key, lang), tr_format(message_key, lang, **format_values)

    raw_title = str(data.get("titulo") or data.get("tipo") or "Event")
    canonical_title = _HISTORY_TITLES.get(raw_title, raw_title)
    title = tr(canonical_title, lang)
    detail = _translate_history_detail(str(data.get("detalle") or ""), lang)
    return title, detail


_COUNT_FORMS = {
    "point": {
        "en": ("point", "points", "points"), "es": ("punto", "puntos", "puntos"),
        "pt": ("ponto", "pontos", "pontos"), "ru": ("точка", "точки", "точек"),
        "uk": ("точка", "точки", "точок"), "de": ("Punkt", "Punkte", "Punkte"),
    },
    "WGP pair": {
        "en": ("WGP pair", "WGP pairs", "WGP pairs"), "es": ("par WGP", "pares WGP", "pares WGP"),
        "pt": ("par WGP", "pares WGP", "pares WGP"), "ru": ("пара WGP", "пары WGP", "пар WGP"),
        "uk": ("пара WGP", "пари WGP", "пар WGP"), "de": ("WGP-Paar", "WGP-Paare", "WGP-Paare"),
    },
    "routed WGP": {
        "en": ("routed WGP", "routed WGPs", "routed WGPs"), "es": ("WGP enrutado", "WGP enrutados", "WGP enrutados"),
        "pt": ("WGP roteado", "WGPs roteados", "WGPs roteados"), "ru": ("маршрутизированный WGP", "маршрутизированных WGP", "маршрутизированных WGP"),
        "uk": ("маршрутизований WGP", "маршрутизовані WGP", "маршрутизованих WGP"), "de": ("gerouteter WGP", "geroutete WGPs", "geroutete WGPs"),
    },
    "row": {
        "en": ("row", "rows", "rows"), "es": ("fila", "filas", "filas"),
        "pt": ("linha", "linhas", "linhas"), "ru": ("строка", "строки", "строк"),
        "uk": ("рядок", "рядки", "рядків"), "de": ("Zeile", "Zeilen", "Zeilen"),
    },
    "process": {
        "en": ("process", "processes", "processes"), "es": ("proceso", "procesos", "procesos"),
        "pt": ("processo", "processos", "processos"), "ru": ("процесс", "процесса", "процессов"),
        "uk": ("процес", "процеси", "процесів"), "de": ("Prozess", "Prozesse", "Prozesse"),
    },
    "application": {
        "en": ("application", "applications", "applications"), "es": ("aplicación", "aplicaciones", "aplicaciones"),
        "pt": ("aplicativo", "aplicativos", "aplicativos"), "ru": ("приложение", "приложения", "приложений"),
        "uk": ("програма", "програми", "програм"), "de": ("Anwendung", "Anwendungen", "Anwendungen"),
    },
    "event": {
        "en": ("event", "events", "events"), "es": ("evento", "eventos", "eventos"),
        "pt": ("evento", "eventos", "eventos"), "ru": ("событие", "события", "событий"),
        "uk": ("подія", "події", "подій"), "de": ("Ereignis", "Ereignisse", "Ereignisse"),
    },
}


def _plural_form_index(count: int, language: str) -> int:
    if language in {"ru", "uk"}:
        last_two = count % 100
        last = count % 10
        if last == 1 and last_two != 11:
            return 0
        if 2 <= last <= 4 and not 12 <= last_two <= 14:
            return 1
        return 2
    return 0 if count == 1 else 1


def count_label(count: object, unit: str, language: str | None = None) -> str:
    try:
        number = int(count)
    except (TypeError, ValueError):
        number = 0
    lang = resolve_language(language or _CURRENT_LANGUAGE)
    forms = _COUNT_FORMS.get(unit, {}).get(lang) or _COUNT_FORMS.get(unit, {}).get("en")
    if not forms:
        return f"{number} {unit}"
    return f"{number} {forms[_plural_form_index(abs(number), lang)]}"


def tr_format(text: str, language: str | None = None, **values: object) -> str:
    translated = tr(text, language)
    try:
        return translated.format(**values)
    except (KeyError, ValueError, IndexError):
        return translated

def project_overview(language: str | None = None) -> str:
    return PROJECT_OVERVIEW.get(resolve_language(language or _CURRENT_LANGUAGE), PROJECT_OVERVIEW["en"])


def daemon_details(language: str | None = None) -> str:
    return DAEMON_DETAILS.get(resolve_language(language or _CURRENT_LANGUAGE), DAEMON_DETAILS["en"])


def language_name(code: str) -> str:
    normalized = normalize_language(code)
    for item_code, display in LANGUAGE_OPTIONS:
        if item_code == normalized:
            return display
    return "Automatic"


def _translated_source(widget, getter, setter, source_property: str, language: str) -> None:
    try:
        current = getter()
    except (AttributeError, RuntimeError, TypeError):
        logger.debug("Could not read a widget value during localization", exc_info=True)
        return
    if not isinstance(current, str) or not current:
        return
    old_source = widget.property(source_property)
    old_language = widget.property(source_property + "Language") or "en"
    if old_source is None:
        source = canonical_source(current, language)
    else:
        expected_old = tr(str(old_source), str(old_language))
        if current in {str(old_source), expected_old}:
            source = str(old_source)
        else:
            source = canonical_source(current, language)
            if source == current:
                source = canonical_source(current, str(old_language))
    translated = tr(source, language)
    try:
        if current != translated:
            setter(translated)
        widget.setProperty(source_property, source)
        widget.setProperty(source_property + "Language", language)
    except (AttributeError, RuntimeError, TypeError):
        logger.debug("Could not write a widget value during localization", exc_info=True)


def localize_widget_tree(root, language: str | None = None) -> None:
    """Translate a widget tree without requiring every legacy widget to be rebuilt.

    Original source strings are stored as dynamic properties, so switching between
    languages never translates an already translated string a second time. Runtime
    values set by telemetry are detected and become the next source value.
    """
    lang = resolve_language(language or _CURRENT_LANGUAGE)
    try:
        from PyQt6.QtWidgets import (
            QAbstractButton, QComboBox, QGroupBox, QLabel, QLineEdit, QTabWidget,
            QTableWidget, QWidget,
        )
    except ImportError:
        logger.debug("PyQt6 widgets are unavailable for runtime localization", exc_info=True)
        return

    widgets: list[QWidget] = [root]
    try:
        widgets.extend(root.findChildren(QWidget))
    except (RuntimeError, TypeError):
        logger.debug("Could not enumerate child widgets during localization", exc_info=True)
    for widget in widgets:
        if isinstance(widget, (QLabel, QAbstractButton, QGroupBox)):
            # A very small set of upstream command labels intentionally stays in
            # English so it matches the terminal UI exactly. Tooltips and every
            # surrounding string continue through the normal localization path.
            if not bool(widget.property("i18nLiteral")):
                explicit_source = getattr(widget, "source_text", None)
                if isinstance(explicit_source, str) and explicit_source:
                    try:
                        widget.setText("" if bool(widget.property("collapsed")) else tr(explicit_source, lang))
                        widget.setProperty("i18nSourceText", explicit_source)
                        widget.setProperty("i18nSourceTextLanguage", lang)
                    except (RuntimeError, TypeError):
                        logger.debug("Could not cache an explicit translation source on %r", widget, exc_info=True)
                else:
                    _translated_source(widget, widget.text, widget.setText, "i18nSourceText", lang)
        if isinstance(widget, QLineEdit):
            _translated_source(widget, widget.placeholderText, widget.setPlaceholderText, "i18nSourcePlaceholder", lang)
        try:
            _translated_source(widget, widget.toolTip, widget.setToolTip, "i18nSourceToolTip", lang)
        except (RuntimeError, TypeError):
            logger.debug("Could not update a widget tooltip during localization", exc_info=True)
        if isinstance(widget, QComboBox):
            sources = widget.property("i18nComboSources")
            if not isinstance(sources, list) or len(sources) != widget.count():
                sources = [widget.itemText(index) for index in range(widget.count())]
                widget.setProperty("i18nComboSources", sources)
            for index, source in enumerate(sources):
                translated = tr(source, lang)
                if widget.itemText(index) != translated:
                    widget.setItemText(index, translated)
        if isinstance(widget, QTabWidget):
            sources = widget.property("i18nTabSources")
            if not isinstance(sources, list) or len(sources) != widget.count():
                sources = [widget.tabText(index) for index in range(widget.count())]
                widget.setProperty("i18nTabSources", sources)
            for index, source in enumerate(sources):
                widget.setTabText(index, tr(source, lang))
        if isinstance(widget, QTableWidget):
            headers = widget.property("i18nHeaderSources")
            if not isinstance(headers, list) or len(headers) != widget.columnCount():
                headers = []
                for column in range(widget.columnCount()):
                    item = widget.horizontalHeaderItem(column)
                    headers.append(item.text() if item is not None else "")
                widget.setProperty("i18nHeaderSources", headers)
            for column, source in enumerate(headers):
                item = widget.horizontalHeaderItem(column)
                if item is not None and source:
                    item.setText(tr(source, lang))
    try:
        _translated_source(root, root.windowTitle, root.setWindowTitle, "i18nSourceWindowTitle", lang)
    except (RuntimeError, TypeError):
        logger.debug("Could not update the localized window title", exc_info=True)
    fit_to_content = getattr(root, "fit_to_content", None)
    if callable(fit_to_content):
        try:
            fit_to_content()
        except (RuntimeError, TypeError):
            logger.debug("Could not refit a dialog after localization", exc_info=True)


def localize_top_levels(language: str | None = None) -> None:
    try:
        from PyQt6.QtWidgets import QApplication
        app = QApplication.instance()
        if app is None:
            return
        for widget in app.topLevelWidgets():
            localize_widget_tree(widget, language)
    except (ImportError, AttributeError, RuntimeError, TypeError):
        logger.debug("Could not localize top-level dialogs", exc_info=True)


def translation_coverage(strings: Iterable[str], languages: Iterable[str] = ("es", "pt", "ru", "uk", "de")) -> dict[str, list[str]]:
    missing: dict[str, list[str]] = {}
    for source in strings:
        if not re.search(r"[A-Za-z]{3}", source):
            continue
        unresolved = [lang for lang in languages if tr(source, lang) == source]
        if unresolved:
            missing[source] = unresolved
    return missing


def strict_translation_coverage(strings: Iterable[str], languages: Iterable[str] = ("es", "pt", "ru", "uk", "de")) -> dict[str, list[str]]:
    """Report sources without an exact interface or backend translation."""
    missing: dict[str, list[str]] = {}
    for source in strings:
        source = str(source)
        if not re.search(r"[A-Za-z]{3}", source):
            continue
        unresolved: list[str] = []
        for language in languages:
            exact = _EXACT.get(source, {}).get(language)
            legacy = _legacy_exact(source, language)
            if not exact and legacy == source:
                unresolved.append(language)
        if unresolved:
            missing[source] = unresolved
    return missing
