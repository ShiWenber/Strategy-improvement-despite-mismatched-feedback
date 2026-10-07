"""Render a JSON analysis as Markdown without recomputing its results."""
import argparse
from html import escape
import json
from pathlib import Path


def cell(value):
    text = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False, allow_nan=False)
    text = escape(text, quote=False).replace('|', '&#124;')
    for character in ('\\', '`', '*', '_', '[', ']'):
        text = text.replace(character, '\\' + character)
    return text.replace('\r\n', '\n').replace('\r', '\n').replace('\n', '<br>')


def inline(value):
    if isinstance(value, dict):
        return not value
    if isinstance(value, list):
        return all(not isinstance(item, (dict, list)) for item in value)
    return True


def table(headers, rows):
    lines = ['| ' + ' | '.join(cell(header) for header in headers) + ' |',
             '| ' + ' | '.join('---' for _ in headers) + ' |']
    lines.extend('| ' + ' | '.join(cell(value) for value in row) + ' |' for row in rows)
    return '\n'.join(lines)


def section(label, value):
    return (f'<details open>\n<summary>{escape(str(label))}</summary>\n\n'
            + render(value) + '\n\n</details>')


def render(value):
    if inline(value):
        return table(['Value'], [[value]])
    if isinstance(value, dict):
        fields = [(key, item) for key, item in value.items() if inline(item)]
        parts = [table(['Field', 'Value'], fields)] if fields else []
        parts.extend(section(key, item) for key, item in value.items() if not inline(item))
        return '\n\n'.join(parts)
    if all(isinstance(row, dict) and row and row.keys() == value[0].keys()
           and all(inline(item) for item in row.values()) for row in value):
        headers = list(value[0])
        return table(headers, ([row[key] for key in headers] for row in value))
    return '\n\n'.join(section(f'Item {index}', item) for index, item in enumerate(value))


def render_report(data, source):
    return f'# JSON analysis report\n\nSource: {cell(source)}\n\n{render(data)}\n'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('input', type=Path, help='Existing analysis JSON; read only.')
    parser.add_argument('--output', type=Path, help='Markdown destination; defaults to the input stem with .md.')
    args = parser.parse_args()
    output = args.output or args.input.with_suffix('.md')
    if output.resolve() == args.input.resolve():
        parser.error('Output must differ from the input JSON.')
    try:
        data = json.loads(args.input.read_text(encoding='utf-8-sig'))
        report = render_report(data, args.input.as_posix())
    except (OSError, ValueError) as error:
        parser.error(str(error))
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(report, encoding='utf-8')
    print(output)


if __name__ == '__main__':
    main()
