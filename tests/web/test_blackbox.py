"""Black box reads and finite controls keep session and parameter boundaries."""
import io
import json
import threading
import time
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from frontends.web import actions, server
from frontends.web.blackbox import BlackBox, MAX_ROWS
from bc250cc.infrastructure import report_attachments as attachments, system_diagnostics as diag


class BlackBoxTests(unittest.TestCase):
    def test_recording_is_bounded_and_only_reads(self):
        service = SimpleNamespace(blackbox_estado=lambda count: {
            'state':'cut-off', 'running':False, 'directory':'/private/path', 'pid':123,
            'rows':[{'time':str(i), 'clock':'1850MHz', 'secret':'not a sensor'} for i in range(MAX_ROWS+10)]})
        reader = BlackBox(service)
        result = reader.recording()
        self.assertEqual(len(result['rows']), MAX_ROWS)
        self.assertEqual(result['rows'][0]['clock'], '1850MHz')
        self.assertNotIn('directory', result)
        self.assertNotIn('secret', result['rows'][0])
        self.assertIn('freeze', result['message'])
        self.assertIs(reader.recording(), result)

    def test_controls_call_only_the_desktop_service_and_invalidate_status(self):
        calls=[]
        service=SimpleNamespace(blackbox_iniciar=lambda:calls.append('start'),blackbox_detener=lambda:calls.append('stop'),
                                blackbox_con_la_sesion=lambda enabled:calls.append(('autostart',enabled)))
        reader=BlackBox(service)
        for payload in ({'operation':'start'},{'operation':'stop'},{'operation':'autostart','enabled':True},{'operation':'autostart','enabled':False}):
            reader._status={'running':False}
            self.assertTrue(reader.control(payload)['ok'])
            self.assertIsNone(reader._status)
        self.assertEqual(calls,['start','stop',('autostart',True),('autostart',False)])
        for payload in ({'operation':'delete'},{'operation':[]},{'operation':'autostart','enabled':'true'},
                        {'operation':'start','path':'/tmp/anything'},{'operation':'stop','enabled':True}):
            with self.assertRaises(ValueError):
                reader.control(payload)
        self.assertEqual(len(calls),4)

    def finish(self, reader):
        deadline=time.monotonic()+3
        while time.monotonic()<deadline:
            with reader._lock:
                ready = not reader._diagnosis['loading']
            if ready:
                return reader.diagnosis()
            time.sleep(.005)
        self.fail('collection did not finish')

    def test_diagnosis_is_lazy_and_deduplicates_parallel_readers(self):
        gate=threading.Event()
        calls=[]
        def collect():
            calls.append(True)
            gate.wait(2)
            return [('GPU', '<script>alert(1)</script>'), ('Application log','test log')]
        reader=BlackBox(None, collect=collect)
        self.assertEqual(calls, [])
        for _ in range(10):
            self.assertTrue(reader.diagnosis()['loading'])
        gate.set()
        result=self.finish(reader)
        self.assertEqual(len(calls), 1)
        self.assertTrue(result['ready'])
        self.assertEqual([row['group'] for row in result['sections']], ['hardware','logs'])
        reader.diagnosis(refresh=True)
        self.assertEqual(len(calls), 1)

    def test_diagnosis_limits_and_redacts(self):
        reader=BlackBox(None, collect=lambda: [('GPU', 'ip 192.168.1.2 '+ 'x'*20000)]*80)
        reader.diagnosis()
        sections=self.finish(reader)['sections']
        self.assertLessEqual(len(sections), 64)
        self.assertLessEqual(sum(len(row['text']) for row in sections), 240000)
        self.assertTrue(all(len(row['text'])<=16000 for row in sections))
        self.assertNotIn('192.168.1.2', sections[0]['text'])

    def test_failed_collection_never_leaks_exception_details(self):
        def fail():
            raise OSError('/home/private/password')
        reader=BlackBox(None, collect=fail)
        reader.diagnosis()
        result=self.finish(reader)
        self.assertFalse(result['loading'])
        self.assertNotIn('/home/private', result['error'])
        self.assertTrue(result['error'])

    def test_unprivileged_kernel_read_never_calls_pkexec(self):
        commands=[]
        def run(args, **kwargs):
            commands.append(args[0]);return ''
        with patch.object(diag, '_run', side_effect=run):
            diag._kernel_text(allow_privileged=False)
        self.assertEqual(commands, ['journalctl','dmesg'])

    def test_desktop_keeps_its_explicit_privileged_kernel_fallback(self):
        commands=[]
        def run(args, **kwargs):
            commands.append(args[0])
            return 'desktop kernel log' if args[0]=='pkexec' else ''
        with patch.object(diag, '_run', side_effect=run):
            self.assertEqual(diag._kernel_text()[0], 'desktop kernel log')
        self.assertEqual(commands, ['journalctl','dmesg','pkexec'])

    def test_readonly_context_reaches_both_collectors_and_restores_desktop_cache(self):
        protected_cache={'0':('desktop privileged cache','polkit')}
        collect_state = attachments.collect_system_state
        with patch.object(diag, '_KERNEL_CACHE', protected_cache), \
             patch.object(diag, '_kernel_text', side_effect=lambda boot, **kw: ('unprivileged '+boot,'journal')), \
             patch.object(diag, 'SECTIONS', (('GPU',lambda:diag._kernel_cached('0')[0]),)), \
             patch.object(attachments, 'STATE_SECTIONS', (('Application log',lambda:diag._kernel_cached('-1')[0]),)), \
             patch.object(attachments, 'collect_system_state', side_effect=lambda: collect_state(attachments.STATE_SECTIONS)):
            result=dict(attachments.collect_readonly_attachments())
            self.assertEqual(result['GPU'], 'unprivileged 0')
            self.assertEqual(result['Application log'], 'unprivileged -1')
            self.assertEqual(diag._kernel_cached('0')[0], 'desktop privileged cache')
            self.assertIsNone(diag._READONLY_KERNEL_LOGS.get())


class BlackBoxRouteTests(unittest.TestCase):
    def request(self, method='GET', authenticated=True, query='', control=False, path='/api/blackbox', body=None, csrf='csrf'):
        self.mutations=[]
        self.reader=SimpleNamespace(recording=lambda:{'rows':[]},diagnosis=lambda **kw:{'loading':True},control=lambda payload:self.mutations.append(payload) or {'ok':True})
        web=SimpleNamespace(language='en', session=lambda token:'csrf' if authenticated else None, blackbox=self.reader)
        handler=server.Handler(SimpleNamespace(allowed_networks=[],web=web),
            {'REMOTE_ADDR':'127.0.0.1','HTTP_HOST':'localhost:8250','HTTP_COOKIE':'bc250_session=token',
             'HTTP_X_CSRF_TOKEN':csrf,'PATH_INFO':path,'QUERY_STRING':query,
             'CONTENT_LENGTH':str(len(json.dumps(body).encode())) if body is not None else '0',
             'wsgi.input':io.BytesIO(json.dumps(body).encode() if body is not None else b'')})
        with patch.object(server,'host_allowed',return_value=True), patch.object(server.web_devices,'session',return_value={'control':control}):
            handler.route(method)
        return handler, json.loads(handler.wfile.getvalue())

    def test_session_required(self):
        handler,_=self.request(authenticated=False)
        self.assertEqual(handler.response_status,401)

    def test_existing_monitoring_session_can_read(self):
        handler,body=self.request()
        self.assertEqual(handler.response_status,200)
        self.assertEqual(body,{'rows':[]})
        self.assertEqual(dict(handler.response_headers)['Cache-Control'],'no-store')

    def test_no_mutation_route_or_action(self):
        handler,_=self.request(method='POST', control=True)
        self.assertEqual(handler.response_status,404)
        self.assertFalse(any('blackbox' in key or 'black_box' in key for key in actions.ACTIONS))
        handler,_=self.request(query='view=/etc/passwd')
        self.assertEqual(handler.response_status,404)

    def test_controls_require_control_permission_and_csrf(self):
        for authenticated, control, csrf, expected in ((False,True,'csrf',401),(True,False,'csrf',403),(True,True,'wrong',403)):
            handler,_=self.request(method='POST',authenticated=authenticated,control=control,csrf=csrf,
                                   path='/api/blackbox/control',body={'operation':'start'})
            self.assertEqual(handler.response_status,expected)
            self.assertEqual(self.mutations,[])
        handler,body=self.request(method='POST',control=True,path='/api/blackbox/control',body={'operation':'start'})
        self.assertEqual(handler.response_status,200)
        self.assertTrue(body['ok'])
        self.assertEqual(self.mutations,[{'operation':'start'}])

    def test_diagnosis_is_also_authenticated(self):
        handler,body=self.request(query='view=diagnosis')
        self.assertEqual(handler.response_status,200)
        self.assertTrue(body['loading'])
