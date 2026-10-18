import copy
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from flowchart_spec import SpecError, prepare
from render_flowchart import write_outputs
from layout_helpers import blocked


def sample():
    return {'canvas': {'width': 800, 'height': 600}, 'nodes': [
        {'id': 'a', 'x': 50, 'y': 100, 'width': 180, 'height': 100, 'lines': ['输入']},
        {'id': 'b', 'x': 550, 'y': 100, 'width': 180, 'height': 100, 'lines': ['输出']}],
        'edges': [{'id': 'ab', 'from': 'a', 'to': 'b', 'points': [[230, 150], [550, 150]]}]}


class SchemaTests(unittest.TestCase):
    def invalid(self, mutate, path):
        spec = sample(); mutate(spec)
        with self.assertRaises(SpecError) as error: prepare(spec)
        self.assertIn(path, str(error.exception))

    def test_field_errors_have_paths(self):
        for value in ('25', True, float('inf'), float('nan'), -1, 0):
            with self.subTest(value=value):
                self.invalid(lambda s: s['nodes'][0].update(font_size=value), '$.nodes[0].font_size')

    def test_missing_and_misspelled_fields(self):
        self.invalid(lambda s: s['nodes'][0].pop('width'), '$.nodes[0].width')
        self.invalid(lambda s: s['nodes'][0].update(font_szie=25), '$.nodes[0].font_szie')
        self.invalid(lambda s: s['nodes'][0].update(lines='a string'), '$.nodes[0].lines')
        self.invalid(lambda s: s['nodes'][0].update(shape='hexagon'), '$.nodes[0].shape')

    def test_bad_ids_and_references(self):
        self.invalid(lambda s: s['nodes'][1].update(id='a'), '$.nodes[1].id')
        self.invalid(lambda s: s['nodes'][0].update(id='bad id'), '$.nodes[0].id')
        self.invalid(lambda s: s['edges'][0].update(to='missing'), '$.edges[0].to')

    def test_bad_routes(self):
        self.invalid(lambda s: s['edges'][0].update(points=[[230,150],[550,160]]), '$.edges[0].points')
        self.invalid(lambda s: s['edges'][0].update(points=[[230,150],[230,150]]), '$.edges[0].points')
        self.invalid(lambda s: s['edges'][0].update(route={}), '$.edges[0]')
        self.invalid(lambda s: s['edges'][0].pop('points'), '$.edges[0]')
        self.invalid(lambda s: s.update(paths=[{'name':'bad','nodes':['missing']}]), '$.paths[0].nodes[0]')
        self.invalid(lambda s: s.update(paths=[{'name':'bad','nodes':['b','a']}]), '$.paths[0]')

    def test_parent_cycles_and_containment(self):
        self.invalid(lambda s: s.update(zones=[{'id':'z','parent':'z','x':0,'y':0,'width':800,'height':600,'title':'区'}]), '$.zones[0].parent')
        self.invalid(lambda s: s['nodes'][0].update(parent='unknown'), '$.nodes[0].parent')
        def outside(s):
            s['zones']=[{'id':'z','x':0,'y':0,'width':200,'height':200,'title':'区'}]
            s['nodes'][0]['parent']='z'
        self.invalid(outside, '$.nodes[0].parent')

    def test_invalid_sources(self):
        self.invalid(lambda s: s['nodes'][0].update(sources=[{'kind':'invented','document':'x'}]), '$.nodes[0].sources[0].kind')
        self.invalid(lambda s: s['nodes'][0].update(sources=[{'kind':'code','document':'x.py','line_start':20,'line_end':10}]), '.line_end')

    def test_canvas_and_shape_dimensions(self):
        self.invalid(lambda s: s['nodes'][0].update(x=790), '$.nodes[0]')
        self.invalid(lambda s: s['nodes'][0].update(shape='cylinder',ellipse_radius=40), '.ellipse_radius')
        self.invalid(lambda s: s['canvas'].update(width=10**400), '$.canvas.width')

    def test_all_examples_validate(self):
        paths = list((ROOT/'assets').glob('*.json')) + [ROOT/'example/paper-flowchart.json']
        for path in paths:
            with self.subTest(path=path.name): prepare(json.loads(path.read_text(encoding='utf-8')))


class LayoutTests(unittest.TestCase):
    def test_align_and_distribute_are_resolved_without_mutating_input(self):
        spec=sample(); spec['edges']=[]
        spec['layout']={'align':[{'nodes':['a','b'],'axis':'y','anchor':'center','value':300}], 'distribute':[{'nodes':['a','b'],'axis':'x','gap':75}]}
        before=copy.deepcopy(spec); result=prepare(spec)
        self.assertEqual(spec,before)
        self.assertEqual(result['nodes'][0]['y'],250)
        self.assertEqual(result['nodes'][1]['x'],305)
        self.assertNotIn('layout', result)

    def test_automatic_route_avoids_obstacle(self):
        spec=sample()
        spec['nodes'].append({'id':'obstacle','x':320,'y':80,'width':140,'height':190,'lines':['障碍']})
        spec['edges'][0].pop('points'); spec['edges'][0]['route']={'from_port':'right','to_port':'left'}
        resolved=prepare(spec); points=resolved['edges'][0]['points']
        self.assertEqual(points[0],[230,150]); self.assertEqual(points[-1],[550,150])
        self.assertGreater(len(points),2)
        self.assertFalse(any(blocked(a,b,[(320,80,460,270)]) for a,b in zip(points,points[1:])))

    def test_bad_alignment_references_are_actionable(self):
        spec=sample(); spec['layout']={'align':[{'nodes':['a','missing'],'axis':'y'}]}
        with self.assertRaisesRegex(SpecError,r'layout.align\[0\].nodes'):prepare(spec)

    def test_explicit_route_can_fail_cleanly(self):
        spec=sample();spec['nodes'][0]['x']=0
        spec['edges'][0].pop('points');spec['edges'][0]['route']={'from_port':'left','to_port':'left'}
        with self.assertRaisesRegex(SpecError,'no obstacle-free route'):prepare(spec)


class ArtifactTests(unittest.TestCase):
    def test_unicode_paths_svg_escaping_hashes_sources_and_overwrite(self):
        spec=sample();spec['nodes'][0]['lines']=['<script>&中文']
        spec['nodes'][0]['sources']=[{'kind':'code','document':'entry.py','symbol':'main','line_start':1}]
        with tempfile.TemporaryDirectory(prefix='流程图 test ') as directory:
            base=Path(directory)/'可编辑 示例'
            outputs=write_outputs(spec,base)
            svg,html,layout=[p.read_text(encoding='utf-8') for p in outputs]
            ET.fromstring(svg)
            self.assertIn('&lt;script&gt;&amp;中文',svg)
            self.assertIn('entry.py',html)
            self.assertIn(hashlib.sha256(layout.encode()).hexdigest(),svg)
            self.assertIn(svg,html)
            with self.assertRaises(FileExistsError):write_outputs(spec,base)
            write_outputs(spec,base,True)
            self.assertEqual(len(list(Path(directory).iterdir())),3)

    def test_shapes_are_svg_not_flattened_images(self):
        spec=sample();spec['nodes'][0]['shape']='diamond';spec['nodes'][1]['shape']='terminator'
        with tempfile.TemporaryDirectory() as directory:
            output=write_outputs(spec,Path(directory)/'shapes')[0].read_text(encoding='utf-8')
            self.assertIn('<polygon',output);self.assertIn('rx="50.0"',output)

    def test_cli_bad_input_exits_without_traceback(self):
        with tempfile.TemporaryDirectory() as directory:
            p=Path(directory)/'bad.json';p.write_text('{"canvas":{}}')
            result=subprocess.run([sys.executable,str(ROOT/'scripts/render_flowchart.py'),str(p),'--validate-only'],capture_output=True,text=True)
            self.assertNotEqual(result.returncode,0)
            self.assertIn('$.nodes',result.stderr)
            self.assertNotIn('Traceback',result.stderr)

    def test_cli_json_output_handles_unicode_paths(self):
        with tempfile.TemporaryDirectory(prefix='中文 path ') as directory:
            source=Path(directory)/'输入.json';source.write_text(json.dumps(sample()),encoding='utf-8')
            base=Path(directory)/'结果 示例'
            result=subprocess.run([sys.executable,str(ROOT/'scripts/render_flowchart.py'),str(source),'--output-base',str(base)],capture_output=True,encoding='utf-8')
            self.assertEqual(result.returncode,0,result.stderr)
            files=json.loads(result.stdout)['files']
            self.assertEqual(files[0],str(base)+'.svg')


if __name__=='__main__':unittest.main()
