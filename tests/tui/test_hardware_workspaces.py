"""Hardware workflows keep their actions together and their terminal targets visible."""
import unittest

from frontends.tui.content import Buttons, Choice, Panel, cell_width
from frontends.tui.i18n import set_language
from frontends.tui.layout import Glyphs, build_layout
from frontends.tui.pages import build_pages
from frontends.tui.screen import Screen
from tests.tui.fakes import FakeUI, make_context, CU_STATE


class HardwareWorkspaceTests(unittest.TestCase):
    def setUp(self):
        set_language('en')
        self.ctx,self.ui,self.pages=make_context(),FakeUI(),build_pages()
        self.ctx.state('system')['os']=('arch','Arch Linux')

    def layout(self,key,tab='',width=80):
        page=self.pages[key]
        return build_layout(page.build(self.ctx,page.load(self.ctx),tab,self.ui),width,Glyphs.for_terminal(unicode_ok=True))

    def choose(self,key,label,tab=''):
        return next(choice for choice in self.layout(key,tab).choices if choice.label==label)

    def test_cpu_profiles_apply_and_persistence_are_together(self):
        layout=self.layout('cpu')
        labels=[choice.label for choice in layout.choices]
        for label in ('Average board','Apply configuration + automatic scale','Save for startup','Review persistence','Remove from boot'):
            self.assertIn(label,labels)
        self.assertLess(labels.index('Apply configuration + automatic scale'),labels.index('Save for startup'))
        self.assertNotIn('boot',dict(self.pages['cpu'].tabs(self.ctx)))

    def test_cu_apply_and_boot_controls_are_in_the_routing_view(self):
        self.ctx.service.obtener_estado_cu_cache=lambda:dict(CU_STATE,privileged_backend_ready=True)
        labels=[choice.label for choice in self.layout('cu').choices]
        for label in ('Apply now','Save selection','Install service','Remove service'):
            self.assertIn(label,labels)
        self.assertNotIn('boot',dict(self.pages['cu'].tabs(self.ctx)))
        self.assertTrue(any(choice.pad for choice in self.layout('cu').choices))

    def test_gpu_selection_is_a_draft_until_apply(self):
        self.choose('gpu','Balanced').handler(self.ui)
        self.assertFalse(any(call[0].startswith('aplicar') for call in self.ctx.service.calls))
        self.assertFalse(self.choose('gpu','Save for boot').enabled)
        self.choose('gpu','Review and apply range').handler(self.ui)
        self.assertIn(('aplicar_perfil_gpu',(500,1500),{}),self.ctx.service.calls)
        self.assertTrue(self.ui.confirmations)

    def test_declining_gpu_apply_preserves_the_draft(self):
        self.choose('gpu','Balanced').handler(self.ui)
        self.ui.confirm_answer=False
        self.choose('gpu','Review and apply range').handler(self.ui)
        self.assertFalse(self.ctx.service.calls)
        self.assertEqual(self.ctx.state('gpu')['min'],500)

    def test_gpu_service_and_startup_stay_in_main_view(self):
        labels=[choice.label for choice in self.layout('gpu').choices]
        for label in ('Review and apply range','Save for boot','View status','Restart','Stop governor'):
            self.assertIn(label,labels)
        self.assertNotIn('service',dict(self.pages['gpu'].tabs(self.ctx)))

    def test_additional_settings_expand_one_group_without_actions_on_open(self):
        layout=self.layout('extras','compatibility')
        self.assertFalse(any(choice.label=='Install correction' for choice in layout.choices))
        toggle=next(choice for choice in layout.choices if choice.label.startswith('Configure · CPU power'))
        toggle.handler(self.ui)
        self.assertFalse(self.ctx.service.calls)
        self.assertTrue(any(choice.label=='Install correction' for choice in self.layout('extras','compatibility').choices))

    def test_buttons_keep_edges_in_colour_and_monochrome_layouts(self):
        for unicode_ok in (True,False):
            layout=build_layout([Buttons([Choice('Apply',lambda ui:None,tone='primary'),Choice('Remove',lambda ui:None,tone='bad')])],50,Glyphs.for_terminal(unicode_ok=unicode_ok))
            text=''.join(text for text,_ in layout.rows[0].spans)
            self.assertIn('[',text);self.assertIn(']',text)
            self.assertEqual(layout.choice_rows,[0,0])

    def test_arrow_keys_move_between_profiles_even_with_edit_buttons(self):
        layout=self.layout('cpu',width=120)
        screen=Screen.__new__(Screen)
        slot=('cpu','tuning')
        screen.cursor={slot:0};screen.scroll={};screen.focus='content'
        screen._slot=lambda:slot;screen.build=lambda:layout;screen._view=lambda:1000
        screen.current_choice=lambda:layout.choices[screen.cursor[slot]]
        first=next(i for i,choice in enumerate(layout.choices) if choice.label=='Average board')
        second=next(i for i,choice in enumerate(layout.choices) if choice.label=='Mid point')
        screen.cursor[slot]=first
        screen._content_key('right')
        self.assertEqual(screen.cursor[slot],second)
        screen._content_key('left')
        self.assertEqual(screen.cursor[slot],first)

    def test_focus_follows_visual_rows_and_skips_disabled_actions(self):
        layout=self.layout('cpu',width=120)
        self.assertEqual(layout.choice_rows,sorted(layout.choice_rows))
        screen=Screen.__new__(Screen)
        slot=('cpu','tuning')
        screen.cursor={slot:0};screen.scroll={};screen.focus='content'
        screen._slot=lambda:slot;screen.build=lambda:layout;screen._view=lambda:1000
        screen.current_choice=lambda:layout.choices[screen.cursor[slot]]
        first=next(i for i,choice in enumerate(layout.choices) if choice.label=='Mid point')
        screen.cursor[slot]=first
        screen._content_key('down')
        self.assertEqual(layout.choices[screen.cursor[slot]].label,'Edit: Mid point')
        for _ in range(len(layout.choices)):
            screen._content_key('down')
            self.assertTrue(layout.choices[screen.cursor[slot]].enabled)
        # Every framed mouse target still refers to an actual action after sorting.
        for row in layout.rows:
            for owner in row.owned():
                if owner is not None:
                    index=owner if owner>=0 else -1-owner
                    self.assertLess(index,len(layout.choices))

    def test_cpu_apply_still_requires_confirmation_and_runs_in_console(self):
        self.choose('cpu','Mid point').handler(self.ui)
        self.choose('cpu','Apply configuration + automatic scale').handler(self.ui)
        self.assertIn(('ejecutar_cpu_oc_temporal',(3850,1150,90),{}),self.ctx.service.calls)
        self.assertTrue(self.ui.ran)
        self.assertTrue(self.ui.confirmations[-1][1])

    def test_panels_remain_usable_at_multiple_widths_and_languages(self):
        try:
            for language in ('en','es'):
                set_language(language)
                for key in ('cpu','cu','gpu','extras'):
                    for tab,_ in self.pages[key].tabs(self.ctx):
                        for width in (32,35,52,80,120):
                            layout=self.layout(key,tab,width)
                            self.assertTrue(layout.rows,(key,tab))
                            for row in layout.rows:
                                self.assertLessEqual(sum(cell_width(text) for text,_ in row.spans),width,(key,tab,width,row.spans))
        finally:set_language('en')


if __name__=='__main__':unittest.main()
