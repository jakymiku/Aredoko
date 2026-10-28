"""Failure injection for owned audio/video startup, no workers or media decode."""
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
import sys
import unittest
from unittest.mock import Mock,patch

sys.path[:0]=[str(Path(__file__).resolve().parents[1]/'app'),str(Path(__file__).resolve().parent)]
import test_audio_direct_index as fixture
from test_audio_direct_jobs import Encoder
from ai_profiles import DEFAULT_PROFILE,audio_profile_for,video_profile_for
from ai_process import AIUnavailable
from audio_direct_feature import AudioDirectFeature
from video_direct_feature import VideoDirectFeature
from audio_direct_jobs import AudioDirectJobs
from video_direct_jobs import VideoDirectJobs
from inference_ownership import InferenceOwnership


class OwnedCleanupTests(unittest.TestCase):
    setUp=fixture.DirectAudioIndexTests.setUp

    def feature(self,kind,group=None):
        group=group or InferenceOwnership()
        if not group.owners:group.for_encoder(Encoder())
        image=SimpleNamespace(profile=replace(DEFAULT_PROFILE,dimension=3),inference_group=group)
        created=[]
        def factory(profile):
            encoder=Encoder();encoder.profile=profile;encoder.close=Mock(wraps=encoder.close);created.append(encoder);return encoder
        feature=(VideoDirectFeature if kind=='video' else AudioDirectFeature)(self.catalog,image,encoder_factory=factory,stage_parent=self.stage)
        self.addCleanup(feature.close)
        return feature,created[0],group

    def job(self,kind):
        encoder=Encoder();encoder.profile=replace((video_profile_for if kind=='video' else audio_profile_for)(),dimension=3)
        owner=(VideoDirectJobs if kind=='video' else AudioDirectJobs)(self.catalog,encoder,stage_parent=self.stage)
        self.addCleanup(owner.close)
        return owner,encoder

    def test_uninitialized_features_close_encoder_exactly_once(self):
        for kind in ('audio','video'):
            with self.subTest(kind=kind):
                feature,encoder,_=self.feature(kind)
                feature.close();feature.close();encoder.close.assert_called_once()

    def test_failed_role_registration_closes_only_rejected_encoder(self):
        for kind in ('audio','video'):
            with self.subTest(kind=kind):
                first,existing,group=self.feature(kind)
                image=SimpleNamespace(profile=replace(DEFAULT_PROFILE,dimension=3),inference_group=group)
                rejected=Encoder();rejected.profile=existing.profile
                with patch.object(rejected,'close',wraps=rejected.close) as closed,self.assertRaises(ValueError):
                    (VideoDirectFeature if kind=='video' else AudioDirectFeature)(self.catalog,image,encoder_factory=lambda profile:rejected)
                closed.assert_called_once();self.assertFalse(existing.closed);self.assertFalse(group.owners[0].encoder.closed)

    def test_job_start_failure_can_be_closed_without_joining_unstarted_thread(self):
        for kind in ('audio','video'):
            with self.subTest(kind=kind):
                owner,encoder=self.job(kind)
                failure=RuntimeError('generated job start failure')
                with patch('threading.Thread.start',side_effect=failure),self.assertRaises(RuntimeError) as caught:owner.start()
                self.assertIs(caught.exception,failure)
                with patch.object(owner.index.store,'checkpoint',wraps=owner.index.store.checkpoint) as checkpoint:
                    owner.close();self.assertTrue(encoder.closed);checkpoint.assert_called_once()

    def test_idle_start_failure_can_be_closed_without_losing_encoder_cleanup(self):
        for kind in ('audio','video'):
            with self.subTest(kind=kind):
                owner,encoder=self.job(kind)
                with patch('threading.Thread.start',side_effect=RuntimeError('generated idle start failure')),self.assertRaises(RuntimeError):
                    owner.configure(idle_release_seconds=1)
                owner.close();self.assertTrue(encoder.closed)

    def test_configuration_failure_is_terminal_and_never_publishes_partial_owner(self):
        for kind in ('audio','video'):
            with self.subTest(kind=kind):
                feature,encoder,_=self.feature(kind);jobs=VideoDirectJobs if kind=='video' else AudioDirectJobs
                failure=RuntimeError('generated configure failure')
                with patch.object(jobs,'configure',side_effect=failure),self.assertRaises(AIUnavailable) as caught:feature._ensure()
                self.assertIs(caught.exception.__cause__,failure);self.assertIsNone(feature.owner);self.assertIsNone(feature.monitor)
                self.assertTrue(feature.closed);encoder.close.assert_called_once()
                self.assertEqual(feature.status()['error_code'],kind+'_initialization_failed')
                self.assertEqual(feature.status()['state'],'failed')
                with self.assertRaises(AIUnavailable):feature._ensure()
                feature.close();encoder.close.assert_called_once()

    def test_monitor_failure_reaps_started_idle_owner_before_publication(self):
        for kind in ('audio','video'):
            with self.subTest(kind=kind):
                feature,encoder,_=self.feature(kind);feature.idle_seconds=1
                module='video_direct_feature' if kind=='video' else 'audio_direct_feature'
                failure=RuntimeError('generated monitor allocation failure')
                jobs=VideoDirectJobs if kind=='video' else AudioDirectJobs
                configure=jobs.configure;started=[]
                def configured(owner,**options):
                    configure(owner,**options);started.append(owner.idle_thread)
                with patch.object(jobs,'configure',autospec=True,side_effect=configured),patch(module+'.IndexStamp',side_effect=failure),self.assertRaises(AIUnavailable) as caught:feature._ensure()
                self.assertIs(caught.exception.__cause__,failure);self.assertIsNone(feature.owner);self.assertIsNone(feature.monitor)
                self.assertTrue(feature.closed);encoder.close.assert_called_once()
                self.assertEqual(feature.status()['error_code'],kind+'_initialization_failed')
                self.assertEqual(feature.status()['state'],'failed')
                self.assertEqual(len(started),1);self.assertIsNotNone(started[0]);self.assertFalse(started[0].is_alive())
                feature.close();encoder.close.assert_called_once()


if __name__=='__main__':unittest.main()
