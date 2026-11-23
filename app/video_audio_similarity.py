"""Explicit video-to-video PCM similarity using the shared bounded scorer.

No decoder, query embedding or RGB video namespace is used. Both the origin
and candidates must be registered videos with fresh direct-audio windows.
"""
from audio_direct_similarity import AudioDirectSimilarity


class VideoAudioSimilarity(AudioDirectSimilarity):
    SOURCE_KIND='video'
    RESULT_MODE='video-audio-similar'
    RESULT_SOURCE='video-audio-direct'
    EVIDENCE_SOURCE='video-audio'
