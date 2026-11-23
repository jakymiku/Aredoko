using Aredoko.Core;

static class AudioSpeechTests
{
    public static void Run(Action<bool, string> check)
    {
        // 1. Parsing audio_match_ms and audio_match_snippet from search response
        var jsonWithSnippet = """
        {
            "total": 1,
            "items": [
                {
                    "id": 42,
                    "title": "meeting_recording.mp3",
                    "kind": "audio",
                    "tags": ["会議", "録音"],
                    "shelf": "",
                    "favorite": false,
                    "reviewed": true,
                    "semantic_score": 0.892,
                    "score_kind": "cosine",
                    "audio_match_ms": 15400,
                    "audio_match_snippet": "本日の進捗報告を行います。"
                }
            ],
            "score_kind": "cosine",
            "mode": "semantic"
        }
        """;
        var parsed = Protocol.ParseSearch(jsonWithSnippet);
        check(parsed.Items.Count == 1, "audio search parses 1 item");
        var item = parsed.Items[0];
        check(item.Id == 42, "item ID matches");
        check(item.AudioMatchMs == 15400, "audio_match_ms parsed correctly");
        check(item.AudioMatchSnippet == "本日の進捗報告を行います。", "audio_match_snippet parsed correctly");
        check(item.AIEvidence.Contains("音声発話一致（0:15 · 「本日の進捗報告を行います。」）"), "AIEvidence contains speech timestamp and snippet");
        check(item.AIEvidence.Contains("類似度 0.892"), "AIEvidence contains cosine similarity");

        // 2. Audio match without snippet
        var jsonWithoutSnippet = """
        {
            "total": 1,
            "items": [
                {
                    "id": 43,
                    "title": "voice_memo.wav",
                    "kind": "audio",
                    "tags": [],
                    "shelf": "",
                    "favorite": false,
                    "reviewed": false,
                    "semantic_score": 0.750,
                    "score_kind": "cosine",
                    "audio_match_ms": 65000
                }
            ],
            "score_kind": "cosine"
        }
        """;
        var parsedNoSnippet = Protocol.ParseSearch(jsonWithoutSnippet);
        var itemNoSnippet = parsedNoSnippet.Items[0];
        check(itemNoSnippet.AudioMatchMs == 65000, "audio_match_ms without snippet");
        check(itemNoSnippet.AudioMatchSnippet is null, "null audio_match_snippet when omitted");
        check(itemNoSnippet.AIEvidence.Contains("音声発話一致（1:05）"), "AIEvidence formats mm:ss without snippet");

        // 2b. Audio match with hours (>= 3600 seconds)
        var jsonWithHours = """
        {
            "total": 1,
            "items": [
                {
                    "id": 43,
                    "title": "long_symposium.mp3",
                    "kind": "audio",
                    "tags": [],
                    "shelf": "",
                    "favorite": false,
                    "reviewed": false,
                    "semantic_score": 0.880,
                    "score_kind": "cosine",
                    "audio_match_ms": 3920000,
                    "audio_match_snippet": "第2部のパネルディスカッションです"
                }
            ],
            "score_kind": "cosine"
        }
        """;
        var parsedHours = Protocol.ParseSearch(jsonWithHours);
        var itemHours = parsedHours.Items[0];
        check(itemHours.AudioMatchMs == 3920000, "audio_match_ms with hours");
        check(itemHours.AIEvidence.Contains("音声発話一致（1:05:20 · 「第2部のパネルディスカッションです」）"), "AIEvidence formats h:mm:ss when duration >= 1 hour");

        // 3. Audio match with literal hits
        var jsonWithLiteral = """
        {
            "total": 1,
            "items": [
                {
                    "id": 44,
                    "title": "interview.m4a",
                    "kind": "audio",
                    "tags": ["インタビュー"],
                    "shelf": "",
                    "favorite": false,
                    "reviewed": true,
                    "semantic_score": 0.8123,
                    "score_kind": "reciprocal-rank",
                    "literal_hits": 2,
                    "literal_words": 3,
                    "audio_match_ms": 125000,
                    "audio_match_snippet": "当時の状況について伺えますか"
                }
            ],
            "score_kind": "reciprocal-rank"
        }
        """;
        var parsedLiteral = Protocol.ParseSearch(jsonWithLiteral);
        var itemLiteral = parsedLiteral.Items[0];
        check(itemLiteral.AIEvidence.Contains("音声発話一致（2:05 · 「当時の状況について伺えますか」） · 文字一致2/3語"), "AIEvidence includes literal word count");
        check(itemLiteral.AIEvidence.Contains("一致率 0.8123"), "AIEvidence includes reciprocal-rank score");

        // 4. Long snippet truncation
        var longSnippet = new string('あ', 150);
        var jsonLong = $$"""
        {
            "total": 1,
            "items": [
                {
                    "id": 45,
                    "title": "long.ogg",
                    "kind": "audio",
                    "tags": [],
                    "shelf": "",
                    "favorite": false,
                    "reviewed": false,
                    "audio_match_ms": 0,
                    "audio_match_snippet": "{{longSnippet}}"
                }
            ]
        }
        """;
        var parsedLong = Protocol.ParseSearch(jsonLong);
        check(parsedLong.Items[0].AudioMatchSnippet is not null, "long snippet is parsed");
        check(parsedLong.Items[0].AudioMatchSnippet!.Length == 121, "snippet truncated to 120 chars + ellipsis");
        check(parsedLong.Items[0].AudioMatchSnippet!.EndsWith("…"), "snippet ends with ellipsis");

        // 5. Boundary value and corruption checks
        foreach (var invalidJson in new[]
        {
            // Negative timestamp
            """{"total":1,"items":[{"id":1,"title":"a.wav","kind":"audio","tags":[],"shelf":"","favorite":false,"reviewed":false,"audio_match_ms":-1}]}""",
            // Exceeds 86,400,000 ms (24 hours)
            """{"total":1,"items":[{"id":1,"title":"a.wav","kind":"audio","tags":[],"shelf":"","favorite":false,"reviewed":false,"audio_match_ms":86400001}]}""",
            // String timestamp
            """{"total":1,"items":[{"id":1,"title":"a.wav","kind":"audio","tags":[],"shelf":"","favorite":false,"reviewed":false,"audio_match_ms":"1000"}]}""",
            // Boolean timestamp
            """{"total":1,"items":[{"id":1,"title":"a.wav","kind":"audio","tags":[],"shelf":"","favorite":false,"reviewed":false,"audio_match_ms":true}]}"""
        })
        {
            var res = Protocol.ParseSearch(invalidJson);
            check(res.Items[0].AudioMatchMs is null, "invalid audio_match_ms safely rejected to null");
        }

        // Empty string snippet safely treated as null
        var jsonEmptySnippet = """{"total":1,"items":[{"id":1,"title":"a.wav","kind":"audio","tags":[],"shelf":"","favorite":false,"reviewed":false,"audio_match_snippet":""}]}""";
        check(Protocol.ParseSearch(jsonEmptySnippet).Items[0].AudioMatchSnippet is null, "empty string snippet rejected to null");
        // Number snippet safely rejected to null
        var jsonNumberSnippet = """{"total":1,"items":[{"id":1,"title":"a.wav","kind":"audio","tags":[],"shelf":"","favorite":false,"reviewed":false,"audio_match_snippet":12345}]}""";
        check(Protocol.ParseSearch(jsonNumberSnippet).Items[0].AudioMatchSnippet is null, "non-string snippet rejected to null");

        // 6. Acoustic descriptor match snippet
        var jsonAcoustic = """
        {
            "total": 1,
            "items": [
                {
                    "id": 50,
                    "title": "rain_ambient.wav",
                    "kind": "audio",
                    "tags": ["効果音"],
                    "shelf": "",
                    "favorite": false,
                    "reviewed": true,
                    "semantic_score": 0.92,
                    "score_kind": "cosine",
                    "audio_match_ms": 30000,
                    "audio_match_snippet": "音響特徴: 雨音"
                }
            ],
            "score_kind": "cosine"
        }
        """;
        var parsedAcoustic = Protocol.ParseSearch(jsonAcoustic);
        var itemAcoustic = parsedAcoustic.Items[0];
        check(itemAcoustic.AudioMatchSnippet == "音響特徴: 雨音", "acoustic descriptor snippet parsed");
        check(itemAcoustic.AIEvidence.Contains("音響特徴一致（0:30 · 「音響特徴: 雨音」）"), "AIEvidence formats acoustic feature match");

        // Speech snippet starting with 音響 (e.g. 音響工学の概要) must format as speech match, not acoustic descriptor
        var jsonSpeechAcousticWord = """
        {
            "total": 1,
            "items": [
                {
                    "id": 51,
                    "title": "lecture.mp3",
                    "kind": "audio",
                    "tags": ["講義"],
                    "shelf": "",
                    "favorite": false,
                    "reviewed": true,
                    "semantic_score": 0.88,
                    "score_kind": "cosine",
                    "audio_match_ms": 15000,
                    "audio_match_snippet": "音響工学の概要を説明します。"
                }
            ],
            "score_kind": "cosine"
        }
        """;
        var parsedSpeechWord = Protocol.ParseSearch(jsonSpeechAcousticWord);
        var itemSpeechWord = parsedSpeechWord.Items[0];
        check(itemSpeechWord.AIEvidence.Contains("音声発話一致（0:15 · 「音響工学の概要を説明します。」）"), "speech snippet starting with 音響 formats as speech match");

        // 7. AudioPlayerPolicy checks
        var presentMp3 = new MediaRow { Id = 1, Kind = "audio", Availability = "present", Location = "music/track.mp3" };
        var presentWav = new MediaRow { Id = 2, Kind = "audio", Availability = "present", Location = "music/sfx.WAV" };
        var presentFlac = new MediaRow { Id = 3, Kind = "audio", Availability = "present", Location = "music/album.flac" };
        var missingMp3 = new MediaRow { Id = 4, Kind = "audio", Availability = "missing", Location = "music/track.mp3" };
        var videoRow = new MediaRow { Id = 5, Kind = "video", Availability = "present", Location = "video/clip.mp4" };
        var unsupportedExt = new MediaRow { Id = 6, Kind = "audio", Availability = "present", Location = "music/track.exe" };
        check(AudioPlayerPolicy.CanOpen(presentMp3), "AudioPlayerPolicy accepts present mp3");
        check(AudioPlayerPolicy.CanOpen(presentWav), "AudioPlayerPolicy accepts present uppercase WAV");
        check(AudioPlayerPolicy.CanOpen(presentFlac), "AudioPlayerPolicy accepts present flac");
        check(!AudioPlayerPolicy.CanOpen(missingMp3), "AudioPlayerPolicy rejects missing audio");
        check(!AudioPlayerPolicy.CanOpen(videoRow), "AudioPlayerPolicy rejects non-audio kind");
        check(!AudioPlayerPolicy.CanOpen(unsupportedExt), "AudioPlayerPolicy rejects unsupported extension");
    }
}
