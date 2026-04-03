#!/usr/bin/env python3
"""
box_table.py — Unicode box-drawing table generator and span analyzer

Generates aligned Unicode tables from data, with tools to analyze
character spans for debugging alignment issues.
"""

import unicodedata


def char_width(ch):
    """Return display width of a character (handles wide/emoji chars)."""
    cat = unicodedata.east_asian_width(ch)
    if cat in ('W', 'F'):
        return 2
    return 1


def display_width(s):
    """Return display width of a string (handles wide chars)."""
    return sum(char_width(ch) for ch in s)


def pad_to_width(s, width):
    """Pad string with spaces to reach target display width."""
    current = display_width(s)
    return s + ' ' * (width - current)


class BoxTable:
    """Generate Unicode box-drawing tables with automatic column sizing."""

    STYLES = {
        'single': {
            'tl': '┌', 'tr': '┐', 'bl': '└', 'br': '┘',
            'h': '─', 'v': '│',
            'lt': '├', 'rt': '┤', 'tt': '┬', 'bt': '┴',
            'x': '┼',
        },
        'double': {
            'tl': '╔', 'tr': '╗', 'bl': '╚', 'br': '╝',
            'h': '═', 'v': '║',
            'lt': '╠', 'rt': '╣', 'tt': '╦', 'bt': '╩',
            'x': '╬',
        },
        'rounded': {
            'tl': '╭', 'tr': '╮', 'bl': '╰', 'br': '╯',
            'h': '─', 'v': '│',
            'lt': '├', 'rt': '┤', 'tt': '┬', 'bt': '┴',
            'x': '┼',
        },
    }

    def __init__(self, headers, style='single', padding=1):
        self.headers = headers
        self.rows = []
        self.style = self.STYLES[style]
        self.padding = padding

    def add_row(self, cells):
        if len(cells) != len(self.headers):
            raise ValueError(f"Expected {len(self.headers)} cells, got {len(cells)}")
        self.rows.append(cells)

    def _col_widths(self):
        widths = [display_width(h) for h in self.headers]
        for row in self.rows:
            for i, cell in enumerate(row):
                widths[i] = max(widths[i], display_width(str(cell)))
        return [w + self.padding * 2 for w in widths]

    def _horizontal_line(self, widths, left, mid, right, fill):
        segments = [fill * w for w in widths]
        return left + mid.join(segments) + right

    def _data_line(self, cells, widths):
        s = self.style
        pad = ' ' * self.padding
        parts = []
        for cell, width in zip(cells, widths):
            content = str(cell)
            inner_width = width - self.padding * 2
            padded = pad_to_width(content, inner_width)
            parts.append(pad + padded + pad)
        return s['v'] + s['v'].join(parts) + s['v']

    def render(self):
        s = self.style
        widths = self._col_widths()
        lines = []
        lines.append(self._horizontal_line(widths, s['tl'], s['tt'], s['tr'], s['h']))
        lines.append(self._data_line(self.headers, widths))
        lines.append(self._horizontal_line(widths, s['lt'], s['x'], s['rt'], s['h']))
        for row in self.rows:
            lines.append(self._data_line(row, widths))
        lines.append(self._horizontal_line(widths, s['bl'], s['bt'], s['br'], s['h']))
        return '\n'.join(lines)

    def annotate_spans(self):
        rendered = self.render()
        lines = rendered.split('\n')
        result = []

        max_width = max(display_width(line) for line in lines)
        ruler_tens = ''.join(str(i // 10) if i % 10 == 0 and i > 0 else ' '
                            for i in range(max_width))
        ruler_ones = ''.join(str(i % 10) for i in range(max_width))

        result.append(f"  Ruler: {ruler_tens}")
        result.append(f"         {ruler_ones}")
        result.append(f"  Width: {max_width} display columns")
        result.append("")

        BOX_CHARS = set('─│┌┐└┘├┤┬┴┼═║╔╗╚╝╠╣╦╩╬╭╮╰╯')

        for line_num, line in enumerate(lines):
            result.append(f"  L{line_num:02d}: {line}")

            spans = []
            pos = 0
            current_type = None
            current_start = 0
            current_len = 0

            for ch in line:
                w = char_width(ch)
                if ch in BOX_CHARS:
                    ch_type = 'BOX'
                elif ch == ' ':
                    ch_type = 'SPC'
                else:
                    ch_type = 'TXT'

                if ch_type != current_type:
                    if current_type is not None:
                        spans.append((current_start, pos, current_type, current_len))
                    current_start = pos
                    current_type = ch_type
                    current_len = 0

                current_len += 1
                pos += w

            if current_type is not None:
                spans.append((current_start, pos, current_type, current_len))

            span_strs = [f"{s}-{e}:{t}({n})" for s, e, t, n in spans]
            result.append(f"       spans: {' '.join(span_strs)}")

        return '\n'.join(result)


def demo():
    print("=== Single Style ===\n")
    t = BoxTable(["ID", "Component", "Type", "Description"])
    t.add_row(["001", "SessionStart", "Hook", "Compaction detection + recovery"])
    t.add_row(["002", "PreToolUse", "Hook", "Policy injection gate"])
    t.add_row(["003", "demini-split", "CLI", "Module extraction from bundles"])
    t.add_row(["004", "BKG", "JSON", "Bundle Knowledge Graph format"])
    t.add_row(["005", "task scope", "CLI", "Scope-driven completion driver"])
    print(t.render())

    print("\n\n=== Span Analysis ===\n")
    print(t.annotate_spans())

    print("\n\n=== Rounded Style ===\n")
    t2 = BoxTable(["Phase", "Task", "Status"], style='rounded')
    t2.add_row(["1", "Policy improvements", "pending"])
    t2.add_row(["1.5", "Permission hardening", "pending"])
    t2.add_row(["2", "maceff-auto-mode skill", "pending"])
    print(t2.render())

    print("\n\n=== Double Style ===\n")
    t3 = BoxTable(["Key", "Value"], style='double')
    t3.add_row(["version", "2026.01.19"])
    t3.add_row(["backend", "Manifold"])
    t3.add_row(["headless", "EGL native"])
    print(t3.render())


if __name__ == '__main__':
    demo()
