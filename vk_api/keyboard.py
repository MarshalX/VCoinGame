import json

from enum import Enum


class ButtonColor(Enum):
    DEFAULT = 'default'
    PRIMARY = 'primary'
    NEGATIVE = 'negative'
    POSITIVE = 'positive'


class Keyboard:
    __slots__ = ('one_time', 'lines', 'keyboard')

    def __init__(self, one_time=False):
        self.one_time = one_time
        self.lines = [[]]

        self.keyboard = {
            'one_time': self.one_time,
            'buttons': self.lines
        }

    def get_keyboard(self):
        return json.dumps(self.keyboard, ensure_ascii=False, separators=(',', ':'))

    @classmethod
    def get_empty_keyboard(cls):
        keyboard = cls()
        keyboard.keyboard['buttons'] = []

        return keyboard.get_keyboard()

    def add_button(self, label, color=ButtonColor.DEFAULT, payload=''):
        current_line = self.lines[-1]

        if len(current_line) >= 4:
            raise ValueError('Max 4 buttons on a line')

        current_line.append({
            'color': color.value,
            'action': {
                'type': 'text',
                'payload': payload,
                'label': label,
            }
        })

    def add_line(self):
        if len(self.lines) >= 10:
            raise ValueError('Max 10 lines')

        self.lines.append([])
