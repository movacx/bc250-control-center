"""SteamOS providers presented with the app's existing compatibility rows."""
from PyQt6.QtCore import QObject, QTimer, pyqtSignal

from bc250cc.application.preparation.steamos_providers import ALTERNATIVE_ACTIONS
from bc250cc.application.preparation.toolkit_rows import (
    AC3_NEEDS_COMBINED_NOTE as AC3_NEEDS_COMBINED_NOTE,
)
from bc250cc.application.preparation.toolkit_rows import (
    ALTERNATIVE_SCOPE as ALTERNATIVE_SCOPE,
)
from bc250cc.application.preparation.toolkit_rows import (
    ALTERNATIVE_TOOLS as ALTERNATIVE_TOOLS,
)
from bc250cc.application.preparation.toolkit_rows import (
    COMBINED_GLIBC_NOTE as COMBINED_GLIBC_NOTE,
)
from bc250cc.application.preparation.toolkit_rows import (
    COMBINED_OTHER_ROUTE as COMBINED_OTHER_ROUTE,
)
from bc250cc.application.preparation.toolkit_rows import (
    FOREIGN_GRAPHICS_ACTIONS as FOREIGN_GRAPHICS_ACTIONS,
)
from bc250cc.application.preparation.toolkit_rows import (
    FOREIGN_GRAPHICS_NOTE as FOREIGN_GRAPHICS_NOTE,
)
from bc250cc.application.preparation.toolkit_rows import (
    LABELS as LABELS,
)
from bc250cc.application.preparation.toolkit_rows import (
    NATIVE_SCOPE as NATIVE_SCOPE,
)
from bc250cc.application.preparation.toolkit_rows import (
    REAL_TOOLKIT_SCOPE as REAL_TOOLKIT_SCOPE,
)
from bc250cc.application.preparation.toolkit_rows import (
    TOOLKIT_RADV_NOTE as TOOLKIT_RADV_NOTE,
)
from bc250cc.application.preparation.toolkit_rows import (
    TOOLS as TOOLS,
)
from bc250cc.application.preparation.toolkit_rows import (
    installed_status,
    is_removal,
    primary_label,
    toolkit_presentation,
)

from ..i18n import tr, tr_format


def _localized(pair):
    """The English source is the catalog key; the second item (Spanish) is only history.

    Every language reads the same ``locales/*.json`` as the rest of the interface.
    Product names that read the same everywhere have no entry and fall back to the source.
    """
    return tr(pair[0])


def _detail(note, descriptions):
    """A row's text: its note (one sentence, or several) or its description."""
    if not note:
        return _localized(descriptions)
    return ' '.join(tr(part) for part in ((note,) if isinstance(note, str) else note))


def action_label(key):
    return _localized(LABELS[key])


def action_question(key):
    """What a confirmation names: the row and what is about to run on it."""
    title = next(names for _category, names, _descriptions, keys in TOOLS if key in keys)
    return f'{_localized(title)}: {action_label(key)}'


def _primary_label(key):
    return tr(primary_label(key))


class ToolRows(QObject):
    """Provider components as ordinary Compatibility rows.

    The rows are not a separate browser: each card is handed to the page that
    owns its topic (System, Kernel and graphics, Video, Audio, Drivers), and the
    scope line under its title names the provider it comes from.
    """
    action_requested = pyqtSignal(object)

    def __init__(self, specifications, labels, namespace, scope_text, parent=None):
        super().__init__(parent)
        from PyQt6.QtWidgets import QWidget

        from .dashboard_widgets import PreparationInfoCard

        # A card without a parent is a top-level window, and showing it opens
        # one. Cards wait here, hidden, until a page places them in its list;
        # a page that never does (the Dashboard) must never show them.
        self._holder = QWidget()
        self._holder.hide()
        self._specifications, self._labels = specifications, labels
        self.namespace, self.scope_text = namespace, scope_text
        #: A row's explanation replacing its description while a state needs one.
        self._notes = {}
        self.buttons, self.cards, self.categories = {}, {}, {}
        for category, names, descriptions, keys in specifications:
            card = PreparationInfoCard(_localized(names), _localized(descriptions),
                                       status_text='', scope_text=scope_text)
            card.setParent(self._holder)
            card.status.hide()
            for index, key in enumerate(keys):
                label = _primary_label(key) if index == 0 else _localized(labels[key])
                button = card.add_action(label, {'action': namespace + ':' + key, 'governor': ''},
                                         danger=is_removal(key))
                button.setAutoDefault(False)
                self.buttons[key] = button
            card.add_action('Open upstream project', {
                'action': 'steamos_graphics_upstream' if namespace == 'real_toolkit' else 'steamos_alternative_upstream',
                'governor': '',
            }).setAutoDefault(False)
            if namespace == 'real_toolkit' and keys[0] == 'verify':
                card.add_action("What's new", {'action': 'steamos_toolkit_changelog',
                                              'governor': ''}).setAutoDefault(False)
            card.action_requested.connect(self.action_requested.emit)
            self.cards[keys[0]] = card
            self.categories[keys[0]] = category

    def cards_for(self, *categories):
        return [self.cards[keys[0]] for category, _n, _d, keys in self._specifications
                if category in categories]

    def all_cards(self):
        return list(self.cards.values())

    def retranslate_dynamic_copy(self):
        """Refresh component copy without rebuilding or dispatching."""
        for _category, names, descriptions, keys in self._specifications:
            card = self.cards[keys[0]]
            card.title.setText(tr(_localized(names)))
            card.detail.setText(_detail(self._notes.get(keys[0]), descriptions))
            for index, key in enumerate(keys):
                source = _primary_label(key) if index == 0 else _localized(self._labels[key])
                button = self.buttons[key]
                button.source_text = source
                button.setText(tr(source))

    def set_enabled(self, enabled):
        for card in self.cards.values():
            card.setEnabled(enabled)

    def set_visible(self, visible):
        for card in self.cards.values():
            card.setVisible(visible)


class RealToolkitRows(ToolRows):
    def __init__(self, parent=None):
        super().__init__(TOOLS, LABELS, 'real_toolkit', REAL_TOOLKIT_SCOPE, parent)
        self._root_status = None
        self.buttons['put-back'].hide()
        self._blocked = frozenset()
        self._running = ''
        # While an action runs, look for its end: the page's own refresh can be
        # minutes away, and the rows must not stay off that long.
        self._watch = QTimer(self)
        self._watch.setInterval(3000)
        self._watch.timeout.connect(self._look_again)

    def set_running(self, action):
        """Turn every toolkit button off while ``action`` runs ("" = none)."""
        self._running = str(action or '')
        tip = (tr_format('Another toolkit action is running: {name}',
                         name=_localized(LABELS[self._running]) if self._running in LABELS else self._running)
               if self._running else '')
        for key, button in self.buttons.items():
            button.setEnabled(not self._running and key not in self._blocked)
            button.setToolTip(tip)
        if self._running:
            self._watch.start()
        else:
            self._watch.stop()

    def _look_again(self):
        from bc250cc.application.preparation.steamos_providers import (
            real_toolkit_running,
        )

        if not real_toolkit_running():
            self.set_running('')

    def set_root_state(self, mode, *, running=False, interrupted=False, action=''):
        """Say on the management row whether the system files are locked right now.

        Every action unlocks them for the steps that need it and Control Center
        locks them again afterwards; this is the state the person is looking at.
        """
        text, tone = (('In use', 'blue') if running else ('Interrupted', 'orange') if interrupted
                      else {'enabled': ('Protected', 'green'), 'disabled': ('Writable', 'orange')}.get(mode, (None, None)))
        self._root_status = (text, tone) if text else None
        self._apply_root_status()
        self.set_running((action or 'toolkit') if running else '')

    def _apply_root_status(self):
        card = self.cards.get('verify')
        if card is None:
            return
        if self._root_status:
            card.set_status(*self._root_status)
        else:
            card.status.hide()

    def set_provider_state(self, state):
        presented = toolkit_presentation(state)
        protected, foreign = presented.protected, presented.foreign
        self._blocked, self._notes = presented.blocked, dict(presented.notes)
        self.buttons['put-back'].setVisible(bool(state.get('lost_after_update')))
        self.set_running(self._running)
        for _category, _names, descriptions, keys in self._specifications:
            card = self.cards[keys[0]]
            card.detail.setText(_detail(self._notes.get(keys[0]), descriptions))
            if keys[0] == 'verify':
                self._apply_root_status()  # this row reports the system's lock, not ownership
            elif any(key in protected for key in keys):
                card.set_status('BC250 Control Center', 'blue')
            elif keys[0] == 'combined-install' and foreign:
                card.set_status('keyboardspecialist', 'orange')
            elif (evidence := installed_status(keys[0], state)) is not None:
                card.set_status(*evidence)
            else:
                card.status.hide()


class SteamOSAlternativeRows(ToolRows):
    def __init__(self, parent=None):
        super().__init__(ALTERNATIVE_TOOLS, ALTERNATIVE_ACTIONS, 'steamos_alternative',
                         ALTERNATIVE_SCOPE, parent)

    def set_provider_state(self, state):
        labels = {'ready': 'Installed', 'invalid': 'Incomplete', 'not-installed': 'Not installed'}
        radv = dict(state.get('radv') or {})
        orphaned = bool(state.get('orphaned'))
        self.cards['graphics-install'].set_status(labels.get(radv.get('state'), 'Unknown'),
                                                 'blue' if radv.get('state') == 'ready'
                                                 else 'orange' if orphaned else 'gray')
        self._notes = {'graphics-install': ORPHANED_RUNTIME_NOTE} if orphaned else {}
        for _category, _names, descriptions, keys in self._specifications:
            self.cards[keys[0]].detail.setText(_detail(self._notes.get(keys[0]), descriptions))
        kernel = dict(state.get('kernel') or {})
        if kernel.get('reboot_pending'):
            self.cards['kernel-install'].set_status('Reboot required', 'orange')
        elif kernel.get('ready'):
            self.cards['kernel-install'].set_status('Installed', 'blue')
        elif kernel.get('installed'):
            self.cards['kernel-install'].set_status('Incomplete', 'orange')
        else:
            self.cards['kernel-install'].set_status('Not installed', 'gray')


ORPHANED_RUNTIME_NOTE = (
    "Its files are still in the system partition, but its install record in /home is gone "
    "(a SteamOS factory reset erases /home only). Remove Mesa / RADV checks those files and removes them."
)
