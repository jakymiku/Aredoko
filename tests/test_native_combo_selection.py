"""No GUI: fail closed on duplicate/stale UIA peers and never send End keys."""
import json
from pathlib import Path
import sys
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
from native_ui_tools import select_combo_item


class NativeComboSelectionTests(unittest.TestCase):
    def node(self,selector='item-a',**extra):
        return {'type':'ListItem','automationId':'ModeAudioContent','selector':selector,'isOffscreen':False,**extra}

    def ui(self,trees):
        calls=[];trees=iter(trees)
        def invoke(*args):
            calls.append(args)
            if args[0]=='inspect':return json.dumps(next(trees))
            return ''
        return invoke,calls

    def test_exact_audio_item_ignores_later_modes_text_and_hidden_peers(self):
        choice=self.node();visible={'type':'ComboBox','automationId':'CmbSearchMode','selector':'fresh-combo','isOffscreen':False}
        ui,calls=self.ui([[choice,choice,self.node('other',automationId='ModeVideoAudioContent'),self.node('text',type='Text'),self.node('hidden',isOffscreen=True)],[visible,visible]])
        select_combo_item(ui,'CmbSearchMode','ModeAudioContent')
        self.assertIn(('invoke','item-a','--action','select'),calls)
        self.assertEqual(calls[-1],('invoke','fresh-combo','--action','collapse'))
        self.assertFalse(any(c[0] in ('send-keys','click','focus') for c in calls))

    def test_ambiguous_missing_or_hidden_choice_never_falls_back_to_another_item(self):
        for nodes in ([],[self.node(isOffscreen=True)],[self.node('a'),self.node('b')]):
            with self.subTest(nodes=nodes):
                ui,calls=self.ui([nodes])
                with self.assertRaises(RuntimeError):select_combo_item(ui,'CmbSearchMode','ModeAudioContent')
                self.assertFalse(any(c[-1]=='select' for c in calls))

    def test_stale_or_ambiguous_combo_is_rejected_after_selection(self):
        for controls in ([],[self.node(type='ComboBox',automationId='CmbSearchMode',isOffscreen=True)],
                         [self.node('a',type='ComboBox',automationId='CmbSearchMode'),self.node('b',type='ComboBox',automationId='CmbSearchMode')]):
            with self.subTest(controls=controls):
                ui,calls=self.ui([[self.node()],controls])
                with self.assertRaises(RuntimeError):select_combo_item(ui,'CmbSearchMode','ModeAudioContent')
                self.assertFalse(any(c[-1]=='collapse' for c in calls))


if __name__=='__main__':unittest.main()
