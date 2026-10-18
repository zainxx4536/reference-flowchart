"""Cross-platform checks for native Visio XML; desktop tests are opt-in."""
import copy
import json
import math
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from flowchart_spec import SpecError, prepare
from export_visio import render_visio, write_visio

NS = {'v': 'http://schemas.microsoft.com/visio/2003/core'}


def sample():
    return {'canvas': {'width': 800, 'height': 600}, 'nodes': [
        {'id': 'a', 'x': 50, 'y': 100, 'width': 180, 'height': 100, 'lines': ['输入', 'S{t+1}']},
        {'id': 'b', 'x': 550, 'y': 100, 'width': 180, 'height': 100, 'lines': ['输出']}],
        'edges': [{'id': 'ab', 'from': 'a', 'to': 'b', 'points': [[230, 150], [550, 150]]}]}


def shapes(root):
    return {s.attrib['NameU']: s for s in root.findall('.//v:Page/v:Shapes/v:Shape', NS)}


def value(shape, path):
    return float(shape.find(path, NS).text)


class VisioTests(unittest.TestCase):
    def test_all_examples_have_native_shapes_and_glued_edges(self):
        for source in ('assets/example-flowchart.json', 'assets/branching-flowchart.json', 'example/paper-flowchart.json'):
            with self.subTest(source=source):
                spec = prepare(json.loads((ROOT / source).read_text(encoding='utf-8')))
                root = ET.fromstring(render_visio(spec))
                objects = shapes(root)
                self.assertFalse(root.findall('.//v:ForeignData', NS))
                self.assertFalse(root.findall('.//v:Foreign', NS))
                for node in spec['nodes']:
                    shape = objects['node-' + node['id']]
                    self.assertEqual(shape.attrib['Type'], 'Shape')
                    self.assertIsNotNone(shape.find('v:Text', NS))
                    self.assertIsNotNone(shape.find('v:Geom', NS))
                by_id = {s.attrib['ID']: s for s in objects.values()}
                connects = root.findall('.//v:Page/v:Connects/v:Connect', NS)
                self.assertEqual(len(connects), 2 * len(spec.get('edges', [])))
                for edge in spec.get('edges', []):
                    shape = objects['edge-' + edge['id']]
                    self.assertIsNotNone(shape.find('v:XForm1D', NS))
                    links = [c for c in connects if c.attrib['FromSheet'] == shape.attrib['ID']]
                    self.assertEqual({c.attrib['FromCell'] for c in links}, {'BeginX', 'EndX'})
                    for link in links:
                        target = by_id[link.attrib['ToSheet']]
                        self.assertTrue(target.findall('v:Connection', NS))
                        cell = shape.find('v:XForm1D/v:' + link.attrib['FromCell'], NS)
                        self.assertIn('Sheet.' + target.attrib['ID'] + '!', cell.attrib['F'])
                        self.assertIn('Connections.', link.attrib['ToCell'])

    def test_page_coordinates_and_font_scale_match_svg(self):
        spec = sample()
        root = ET.fromstring(render_visio(spec))
        objects = shapes(root)
        page = root.find('.//v:Page/v:PageSheet/v:PageProps', NS)
        self.assertAlmostEqual(value(page, 'v:PageWidth'), 800 / 96)
        self.assertAlmostEqual(value(page, 'v:PageHeight'), 600 / 96)
        shape = objects['node-a']
        for cell, expected in [('PinX', 140 / 96), ('PinY', 450 / 96), ('Width', 180 / 96), ('Height', 100 / 96)]:
            self.assertAlmostEqual(value(shape, 'v:XForm/v:' + cell), expected)
        self.assertAlmostEqual(value(shape, 'v:Char/v:Size'), 25 / 96)
        edge = objects['edge-ab']
        for cell, expected in [('BeginX', 230 / 96), ('BeginY', 450 / 96), ('EndX', 550 / 96), ('EndY', 450 / 96)]:
            self.assertAlmostEqual(value(edge, 'v:XForm1D/v:' + cell), expected)

    def test_connector_geometry_reconstructs_resolved_page_points(self):
        for source in ('assets/example-flowchart.json', 'assets/branching-flowchart.json', 'example/paper-flowchart.json'):
            spec = prepare(json.loads((ROOT / source).read_text(encoding='utf-8')))
            objects = shapes(ET.fromstring(render_visio(spec)))
            for edge in spec.get('edges', []):
                shape = objects['edge-' + edge['id']]
                x = value(shape, 'v:XForm/v:PinX')
                y = value(shape, 'v:XForm/v:PinY')
                angle = value(shape, 'v:XForm/v:Angle')
                rows = list(shape.find('v:Geom', NS))
                rows = [r for r in rows if r.tag.rsplit('}', 1)[-1] in ('MoveTo', 'LineTo')]
                self.assertEqual(len(rows), len(edge['points']))
                for row, expected in zip(rows, edge['points']):
                    u, v = value(row, 'v:X'), value(row, 'v:Y')
                    page_x = (x + u * math.cos(angle) - v * math.sin(angle)) * 96
                    page_y = spec['canvas']['height'] - (y + u * math.sin(angle) + v * math.cos(angle)) * 96
                    self.assertAlmostEqual(page_x, expected[0], places=6)
                    self.assertAlmostEqual(page_y, expected[1], places=6)

    def test_unstable_visio_ellipse_ratio_is_rejected(self):
        spec = sample()
        spec['nodes'][0].update(shape='cylinder', ellipse_radius=0.05)
        with self.assertRaisesRegex(ValueError, 'ellipse_radius is too small'):
            render_visio(spec)

    def test_raw_layout_is_resolved_without_mutation(self):
        spec = json.loads((ROOT / 'assets/branching-flowchart.json').read_text(encoding='utf-8'))
        original = copy.deepcopy(spec)
        raw = render_visio(spec)
        resolved = render_visio(prepare(spec))
        self.assertEqual(raw, resolved)
        self.assertEqual(spec, original)

    def test_text_remains_editable_with_unicode_escaping_and_subscripts(self):
        spec = sample()
        spec['nodes'][0]['lines'] = ['<输入>&测试', 'S{t+1}']
        spec['nodes'][0]['sources'] = [{'kind': 'code', 'document': '路径/entry.py', 'symbol': '<main>&'}]
        root = ET.fromstring(render_visio(spec))
        shape = shapes(root)['node-a']
        text = ''.join(shape.find('v:Text', NS).itertext())
        self.assertIn('<输入>&测试', text)
        self.assertIn('St+1', text)
        self.assertNotIn('{t+1}', text)
        self.assertTrue(any(c.find('v:Pos', NS) is not None and c.find('v:Pos', NS).text == '2' for c in shape.findall('v:Char', NS)))
        self.assertTrue(any(c.find('v:Style', NS) is not None and c.find('v:Style', NS).text == '1' for c in shape.findall('v:Char', NS)))
        self.assertIn('entry.py', ''.join(root.itertext()))

    def test_invalid_input_does_not_replace_existing_drawing(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / 'chart.vdx'
            write_visio(sample(), target)
            before = target.read_bytes()
            spec = sample()
            spec['edges'][0]['to'] = 'missing'
            with self.assertRaises(SpecError):
                write_visio(spec, target, overwrite=True)
            self.assertEqual(target.read_bytes(), before)
            self.assertEqual(list(Path(directory).iterdir()), [target])

    def test_unicode_paths_and_explicit_overwrite(self):
        with tempfile.TemporaryDirectory(prefix='Visio 中文 ') as directory:
            target = Path(directory) / '子目录' / '可编辑 图件.vdx'
            self.assertEqual(write_visio(sample(), target), target)
            before = target.read_bytes()
            changed = sample()
            changed['nodes'][1]['lines'] = ['新输出']
            with self.assertRaises(FileExistsError):
                write_visio(changed, target)
            self.assertEqual(target.read_bytes(), before)
            write_visio(changed, target, overwrite=True)
            self.assertIn('新输出', target.read_text(encoding='utf-8'))

    def test_xml_forbidden_characters_are_rejected_without_writing(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / 'control.vdx'
            spec = sample()
            spec['nodes'][0]['lines'] = ['bad' + chr(1) + 'text']
            with self.assertRaisesRegex(ValueError, 'XML 1.0'):
                write_visio(spec, target)
            self.assertFalse(target.exists())
            self.assertEqual(list(Path(directory).iterdir()), [])

    def test_vsdx_extension_is_not_used_for_unconverted_xml(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / 'not-a-package.vsdx'
            with self.assertRaisesRegex(ValueError, '.vdx'):
                write_visio(sample(), target)
            self.assertFalse(target.exists())

    def test_cli_returns_json_and_reports_validation_errors(self):
        with tempfile.TemporaryDirectory(prefix='Visio CLI 中文 ') as directory:
            source = Path(directory) / '输入.json'
            target = Path(directory) / '结果.vdx'
            source.write_text(json.dumps(sample(), ensure_ascii=False), encoding='utf-8-sig')
            command = [sys.executable, str(ROOT / 'scripts/export_visio.py'), str(source), '--output', str(target)]
            result = subprocess.run(command, capture_output=True, encoding='utf-8')
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIsInstance(json.loads(result.stdout), dict)
            ET.parse(target)
            source.write_text('{"canvas":{}}', encoding='utf-8')
            before = target.read_bytes()
            result = subprocess.run(command + ['--overwrite'], capture_output=True, encoding='utf-8')
            self.assertNotEqual(result.returncode, 0)
            self.assertIn('$.nodes', result.stderr)
            self.assertNotIn('Traceback', result.stderr)
            self.assertEqual(target.read_bytes(), before)


if __name__ == '__main__':
    unittest.main()
