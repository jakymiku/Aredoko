namespace Aredoko.Core;

// Absolute deadlines prevent copy/dispatch time accumulating in every frame.
// A long stall rebases playback; frames are never silently skipped.
public sealed class AnimationPlaybackClock
{
    private double? deadline;
    public void Reset()=>deadline=null;
    public double NextDelay(double nowMs,int durationMs)
    {
        if(!double.IsFinite(nowMs)||durationMs is <1 or >60000)throw new ArgumentOutOfRangeException(nameof(durationMs));
        if(deadline is null||nowMs-deadline.Value>250)deadline=nowMs;
        deadline+=durationMs;
        return Math.Max(1,deadline.Value-nowMs);
    }
}
