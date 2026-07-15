from pathlib import Path

def obtener_estilo(tema):
    if tema == 'dark':
        root = '#111318'; panel = '#0b0d12'; panel2 = '#191c22'; text = '#f4f4f5'; muted = '#a1a1aa'
        border = '#344052'; hover = '#243044'; active = '#263a59'; active_text = '#ffffff'; header = '#202734'; table_alt = '#15181e'
        input_bg = '#111318'; disabled_bg = '#141820'; disabled_border = '#252c38'; button_bg = '#1f2937'; button_hover = '#26364f'; button_checked = '#27466f'
        warn_bg = '#33210f'; warn_border = '#a16207'; warn_text = '#fed7aa'; danger_bg = '#2a1118'; danger_border = '#7f1d1d'; danger_text = '#fecdd3'
        apply_bg = '#2563eb'; apply_hover = '#1d4ed8'; apply_text = '#ffffff'
    else:
        root = '#eef3f8'; panel = '#f8fbff'; panel2 = '#ffffff'; text = '#0f172a'; muted = '#64748b'
        border = '#d8e2ef'; hover = '#f1f7ff'; active = '#dcebff'; active_text = '#075985'; header = '#f1f5fa'; table_alt = '#f6f9fd'
        input_bg = '#ffffff'; disabled_bg = '#eef2f7'; disabled_border = '#cbd5e1'; button_bg = '#ffffff'; button_hover = '#f1f7ff'; button_checked = '#dcebff'
        warn_bg = '#fff7ed'; warn_border = '#fed7aa'; warn_text = '#9a3412'; danger_bg = '#fff1f2'; danger_border = '#fecdd3'; danger_text = '#be123c'
        apply_bg = '#eaf3ff'; apply_hover = '#dbeafe'; apply_text = '#0f172a'
    icon_dir = Path(__file__).resolve().parents[2] / 'Resources' / 'icons'
    check_icon = (icon_dir / 'checkbox-check.svg').as_posix()
    spin_up_icon = (icon_dir / 'spin-up.svg').as_posix()
    spin_down_icon = (icon_dir / 'spin-down.svg').as_posix()
    return f"""
        QMainWindow, QWidget#Root {{ background: {root}; color: {text}; font-family: "Segoe UI", "Inter", sans-serif; }}
        QLabel {{ background: transparent; color: {text}; }}
        QFrame#Sidebar {{ background: {panel}; border: 1px solid {border}; border-radius: 16px; }}
        #AppTitle {{ font-size: 18px; font-weight: 800; color: {text}; }}
        #PageTitle {{ font-size: 30px; font-weight: 800; color: {text}; }}
        #SectionTitle {{ font-size: 15px; font-weight: 800; color: {text}; }}
        #SectionTitleCompact {{ font-size: 13px; font-weight: 800; color: {text}; margin-top: 2px; }}
        #Muted {{ color: {muted}; font-size: 12px; }}
        #WarningText {{ color: {warn_text}; background: {warn_bg}; border: 1px solid {warn_border}; border-radius: 10px; padding: 8px 10px; font-weight: 700; }}
        #WarningTextCompact {{ color: {warn_text}; background: {warn_bg}; border: 1px solid {warn_border}; border-radius: 10px; padding: 5px 8px; font-weight: 700; font-size: 12px; }}
        #StatusBox, #InfoPill {{ background: {active}; border: 1px solid #3b82f6; border-radius: 12px; padding: 10px; color: {active_text}; font-weight: 700; }}
        QMenuBar {{ background: {panel}; color: {text}; border-bottom: 1px solid {border}; padding: 3px; }}
        QMenuBar::item {{ background: transparent; padding: 6px 10px; border-radius: 7px; }}
        QMenuBar::item:selected {{ background: {hover}; }}
        QMenu {{ background: {panel2}; color: {text}; border: 1px solid {border}; padding: 6px; }}
        QMenu::item {{ padding: 7px 24px; border-radius: 6px; }}
        QMenu::item:selected {{ background: {active}; color: {active_text}; }}
        QPushButton#ToggleSidebar {{ background: transparent; border: 0px; border-radius: 8px; padding: 8px; color: {text}; font-size: 18px; }}
        QPushButton#ToggleSidebar:hover {{ background: {hover}; }}
        QPushButton#NavButton {{ background: transparent; border: 0px; border-radius: 10px; padding: 10px 12px; text-align: left; font-weight: 700; color: {text}; }}
        QPushButton#NavButton:hover {{ background: {hover}; }}
        QPushButton#NavButton[active="true"] {{ background: {active}; color: {active_text}; }}
        QPushButton#NavButton[collapsed="true"] {{ padding: 0px; text-align: center; min-width: 42px; max-width: 42px; min-height: 42px; max-height: 42px; }}
        QStackedWidget#Stack {{ background: {panel}; border: 1px solid {border}; border-radius: 16px; padding: 14px; }}
        QFrame#MetricStrip, QFrame#CommandBar, QFrame#InfoBox, QFrame#PerformancePanel, QFrame#ResourceList, QFrame#BcHero, QFrame#BcPanel, QFrame#SegmentBar {{ background: {panel2}; border: 1px solid {border}; border-radius: 12px; }}
        QFrame#BcHero {{ background: {panel2}; border: 1px solid {border}; border-radius: 16px; }}
        QFrame#BcPanel {{ background: {panel2}; border: 1px solid {border}; border-radius: 14px; }}
        QFrame#BcDetailPanel {{ background: {panel2}; border: 1px solid {border}; border-radius: 14px; }}
        QFrame#DetailChip {{ background: {header}; border: 1px solid {border}; border-radius: 10px; }}
        QFrame#SegmentBar {{ background: {panel2}; border: 1px solid {border}; border-radius: 14px; }}
        QFrame#ResourceCard {{ background: {panel2}; border: 1px solid {border}; border-radius: 0px; }}
        QFrame#ResourceCard:hover {{ background: {hover}; }}
        QFrame#ResourceCard[active="true"] {{ background: {active}; border-left: 4px solid #60a5fa; }}
        QFrame#StatBox, QFrame#CompactStatBox {{ background: transparent; border: 0px; }}
        #MetricTitle, #ResourceTitle {{ color: {muted}; font-size: 12px; font-weight: 800; }}
        #MetricValue {{ color: {text}; font-size: 22px; font-weight: 850; }}
        #ResourceValue {{ color: {text}; font-size: 17px; font-weight: 750; }}
        #HeroTitle {{ color: {text}; font-size: 38px; font-weight: 500; }}
        #HeroValue {{ color: {text}; font-size: 26px; font-weight: 700; }}
        #HeroTitleCompact {{ color: {text}; font-size: 30px; font-weight: 650; }}
        #HeroValueCompact {{ color: {text}; font-size: 23px; font-weight: 800; }}
        #StatValue {{ color: {text}; font-size: 23px; font-weight: 500; }}
        #DetailValue {{ color: {text}; font-size: 13px; font-weight: 750; }}
        #CompactStatValue {{ color: {text}; font-size: 17px; font-weight: 750; }}
        QLineEdit#Search {{ background: {input_bg}; border: 1px solid {border}; border-radius: 10px; padding: 8px 11px; color: {text}; }}
        QLineEdit#Search:focus {{ border-color: #60a5fa; background: {panel2}; }}
        QLineEdit, QSpinBox, QDoubleSpinBox {{ background: {input_bg}; border: 1px solid {border}; border-radius: 9px; padding: 6px 26px 6px 9px; color: {text}; selection-background-color: {active}; }}
        QLineEdit:focus, QSpinBox:focus, QDoubleSpinBox:focus {{ border-color: #60a5fa; background: {panel2}; }}
        QLineEdit:disabled, QSpinBox:disabled, QDoubleSpinBox:disabled {{ background: {disabled_bg}; color: {muted}; border-color: {disabled_border}; }}
        QSpinBox::up-button, QDoubleSpinBox::up-button {{ subcontrol-origin: border; subcontrol-position: top right; width: 18px; min-height: 13px; background: {button_bg}; border-left: 1px solid {border}; border-bottom: 1px solid {border}; border-top-right-radius: 8px; }}
        QSpinBox::down-button, QDoubleSpinBox::down-button {{ subcontrol-origin: border; subcontrol-position: bottom right; width: 18px; min-height: 13px; background: {button_bg}; border-left: 1px solid {border}; border-bottom-right-radius: 8px; }}
        QSpinBox::up-button:hover, QSpinBox::down-button:hover, QDoubleSpinBox::up-button:hover, QDoubleSpinBox::down-button:hover {{ background: {button_hover}; }}
        QSpinBox::up-button:disabled, QSpinBox::down-button:disabled, QDoubleSpinBox::up-button:disabled, QDoubleSpinBox::down-button:disabled {{ background: {disabled_bg}; border-color: {disabled_border}; }}
        QSpinBox::up-arrow, QDoubleSpinBox::up-arrow {{ image: url({spin_up_icon}); width: 10px; height: 10px; }}
        QSpinBox::down-arrow, QDoubleSpinBox::down-arrow {{ image: url({spin_down_icon}); width: 10px; height: 10px; }}
        QSpinBox::up-arrow:disabled, QSpinBox::down-arrow:disabled, QDoubleSpinBox::up-arrow:disabled, QDoubleSpinBox::down-arrow:disabled {{ image: none; }}
        QSpinBox#PercentSpin {{ padding: 5px 18px 5px 8px; border-radius: 8px; font-weight: 800; }}
        QSlider::groove:horizontal {{ border: 1px solid {border}; height: 8px; background: {input_bg}; border-radius: 4px; }}
        QSlider::sub-page:horizontal {{ background: #2563eb; border: 1px solid #60a5fa; height: 8px; border-radius: 4px; }}
        QSlider::add-page:horizontal {{ background: {button_bg}; border: 1px solid {border}; height: 8px; border-radius: 4px; }}
        QSlider::handle:horizontal {{ background: #bfdbfe; border: 1px solid #60a5fa; width: 16px; height: 16px; margin: -5px 0; border-radius: 8px; }}
        QSlider::handle:horizontal:hover {{ background: #ffffff; border-color: #93c5fd; }}
        QComboBox#RiskCombo {{ background: {panel2}; border: 1px solid {border}; border-radius: 10px; padding: 7px 10px; color: {text}; font-weight: 800; }}
        QComboBox#RiskCombo:hover {{ background: {hover}; border-color: #93c5fd; }}
        QComboBox#RiskCombo::drop-down {{ border: 0px; width: 22px; }}
        QComboBox QAbstractItemView {{ background-color: {panel2}; color: {text}; border: 1px solid {border}; selection-background-color: {active}; selection-color: {active_text}; outline: 0px; }}
        QComboBox QAbstractItemView::item {{ background-color: {panel2}; color: {text}; min-height: 24px; padding: 4px 8px; }}
        QComboBox QAbstractItemView::item:selected {{ background-color: {active}; color: {active_text}; }}
        QAbstractItemView#RiskComboPopup, QListView#RiskComboPopup {{ background: {panel2}; background-color: {panel2}; color: {text}; border: 1px solid #60a5fa; outline: 0px; padding: 0px; margin: 0px; selection-background-color: {active}; selection-color: {active_text}; alternate-background-color: {panel2}; }}
        QListView#RiskComboPopup QWidget#RiskComboPopupViewport, QWidget#RiskComboPopupViewport {{ background: {panel2}; background-color: {panel2}; }}
        QAbstractItemView#RiskComboPopup::item, QListView#RiskComboPopup::item {{ background: {panel2}; background-color: {panel2}; color: {text}; min-height: 26px; padding: 4px 8px; border: 0px; }}
        QAbstractItemView#RiskComboPopup::item:hover, QListView#RiskComboPopup::item:hover {{ background: {hover}; background-color: {hover}; color: {text}; }}
        QAbstractItemView#RiskComboPopup::item:selected, QListView#RiskComboPopup::item:selected {{ background: {active}; background-color: {active}; color: {active_text}; }}
        QPushButton {{ background: {button_bg}; border: 1px solid {border}; border-radius: 10px; padding: 8px 11px; color: {text}; font-weight: 700; }}
        QPushButton:hover {{ background: {button_hover}; border-color: #60a5fa; }}
        QPushButton:checked {{ background: {button_checked}; border-color: #93c5fd; color: {active_text}; }}
        QPushButton#ApplyButton {{ background: {apply_bg}; border: 1px solid #60a5fa; border-radius: 10px; color: {apply_text}; font-weight: 850; padding: 8px 12px; }}
        QPushButton#ApplyButton:hover {{ background: {apply_hover}; border-color: #3b82f6; color: {apply_text}; }}
        QPushButton#ApplyButton:disabled {{ background: {disabled_bg}; border-color: {disabled_border}; color: {muted}; }}
        QPushButton#DangerButton {{ background: {danger_bg}; border-color: {danger_border}; color: {danger_text}; }}
        QPushButton#DangerButton:hover {{ background: {danger_bg}; border-color: #fb7185; }}
        QCheckBox {{ color: {text}; font-weight: 650; spacing: 8px; background: transparent; }}
        QCheckBox:disabled {{ color: {muted}; }}
        QCheckBox::indicator {{ width: 15px; height: 15px; border: 1px solid #64748b; border-radius: 4px; background: {input_bg}; }}
        QCheckBox::indicator:hover {{ border-color: #93c5fd; background: {hover}; }}
        QCheckBox::indicator:checked {{ background: #2563eb; border: 1px solid #93c5fd; image: url({check_icon}); }}
        QCheckBox::indicator:disabled {{ background: {panel}; border-color: {border}; }}
        QTableWidget {{ background: {panel2}; alternate-background-color: {table_alt}; color: {text}; border: 1px solid {border}; border-radius: 12px; selection-background-color: {active}; selection-color: {active_text}; gridline-color: {border}; }}
        QPlainTextEdit#DetailText {{ background: {input_bg}; color: {text}; border: 1px solid {border}; border-radius: 10px; padding: 8px; font-family: "JetBrainsMono Nerd Font", "Consolas", monospace; font-size: 12px; selection-background-color: {active}; }}
        QPlainTextEdit#TerminalText {{ background: {input_bg}; color: {text}; border: 1px solid {border}; border-radius: 10px; padding: 8px; font-family: "JetBrainsMono Nerd Font", "Consolas", monospace; font-size: 12px; selection-background-color: {active}; }}
        QPlainTextEdit#TerminalText:focus {{ border-color: #475569; }}
        QHeaderView::section {{ background: {header}; color: {muted}; padding: 8px 9px; border: 0px; border-right: 1px solid {border}; font-weight: 800; }}
        QTableCornerButton::section {{ background: {header}; border: 0px; }}
        QMessageBox, QDialog {{ background: {panel2}; color: {text}; }}
        QMessageBox QLabel, QDialog QLabel {{ color: {text}; background: transparent; font-size: 13px; }}
        QMessageBox QPushButton, QDialog QPushButton {{ min-width: 82px; background: {panel}; color: {text}; border: 1px solid {border}; border-radius: 8px; padding: 7px 12px; }}
        QScrollArea#FlatScroll {{ background: {panel2}; border: 0px; }}
        QScrollArea#FlatScroll > QWidget#qt_scrollarea_viewport {{ background: {panel2}; border: 0px; }}
        QWidget#ScrollOuter {{ background: {panel2}; }}
        QWidget#ScrollPage {{ background: {panel2}; }}
        QScrollBar:vertical {{ background: transparent; width: 10px; margin: 3px; }}
        QScrollBar::handle:vertical {{ background: #94a3b8; border-radius: 5px; min-height: 34px; }}
        QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0px; }}
    """
