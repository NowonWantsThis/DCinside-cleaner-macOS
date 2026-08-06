import sys
import os
from PyQt5 import QtGui


def macos_colors(widget):
    is_dark = widget.palette().color(QtGui.QPalette.Window).lightness() < 128
    if is_dark:
        return {
            'window': '#1c1c1e',
            'card': '#2c2c2e',
            'control': '#3a3a3c',
            'control_hover': '#48484a',
            'selected': '#636366',
            'separator': '#3a3a3c',
            'text': '#f2f2f7',
            'secondary_text': '#aeaeb2',
            'disabled_text': '#636366',
            'accent': '#0a84ff',
            'accent_pressed': '#0071e3',
            'field': '#1c1c1e',
        }

    return {
        'window': '#f2f2f7',
        'card': '#ffffff',
        'control': '#e5e5ea',
        'control_hover': '#d1d1d6',
        'selected': '#ffffff',
        'separator': '#d1d1d6',
        'text': '#1c1c1e',
        'secondary_text': '#6c6c70',
        'disabled_text': '#aeaeb2',
        'accent': '#007aff',
        'accent_pressed': '#0062cc',
        'field': '#ffffff',
    }


def macos_control_style(widget):
    colors = macos_colors(widget)
    arrow_asset = resource_path(
        './resources/icon/chevron_down_dark.png'
        if widget.palette().color(QtGui.QPalette.Window).lightness() < 128
        else './resources/icon/chevron_down_light.png')
    return f'''
        QGroupBox {{
            background-color: {colors['card']};
            border: 0;
            border-radius: 8px;
            margin-top: 24px;
        }}
        QGroupBox::title {{
            subcontrol-origin: margin;
            subcontrol-position: top left;
            left: 4px;
            top: 2px;
            padding: 0;
            background: transparent;
            color: {colors['text']};
            font-weight: 600;
        }}
        QLineEdit, QComboBox, QPlainTextEdit, QTextBrowser {{
            background-color: {colors['field']};
            color: {colors['text']};
            border: 1px solid {colors['separator']};
            border-radius: 6px;
            selection-background-color: {colors['accent']};
            min-height: 28px;
        }}
        QLineEdit:focus, QComboBox:focus, QPlainTextEdit:focus, QTextBrowser:focus {{
            border: 1px solid {colors['accent']};
        }}
        QComboBox#combo_box_gall {{
            padding-left: 12px;
            padding-right: 34px;
        }}
        QComboBox#combo_box_gall::drop-down {{
            subcontrol-origin: border;
            subcontrol-position: top right;
            width: 34px;
            border: 0;
            background: transparent;
        }}
        QComboBox#combo_box_gall::down-arrow {{
            image: url("{arrow_asset}");
            width: 14px;
            height: 14px;
        }}
        QLineEdit:disabled, QComboBox:disabled, QPlainTextEdit:disabled {{
            background-color: {colors['card']};
            color: {colors['disabled_text']};
            border-color: {colors['separator']};
        }}
        QPushButton {{
            background-color: {colors['control']};
            color: {colors['text']};
            border: 0;
            border-radius: 7px;
            min-height: 30px;
            padding-left: 12px;
            padding-right: 12px;
        }}
        QPushButton:hover {{
            background-color: {colors['control_hover']};
        }}
        QPushButton:pressed {{
            background-color: {colors['selected']};
        }}
        QPushButton:disabled {{
            background-color: {colors['card']};
            color: {colors['disabled_text']};
        }}
        QPushButton#btn_start, QPushButton#btn_complete {{
            background-color: {colors['accent']};
            color: #ffffff;
            font-weight: 600;
        }}
        QPushButton#btn_start:pressed, QPushButton#btn_complete:pressed {{
            background-color: {colors['accent_pressed']};
        }}
        QLabel {{
            color: {colors['text']};
        }}
        QLabel:disabled, QCheckBox:disabled {{
            color: {colors['disabled_text']};
        }}
    '''


def resource_path(relative_path):
    """ Get absolute path to resource, works for dev and for PyInstaller """
    base_path = getattr(sys, '_MEIPASS', os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base_path, relative_path)
