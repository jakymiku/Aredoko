using Aredoko.Core;

internal static class SmoothScrollPhysicsTests
{
    public static void Run(Action<bool, string> check)
    {
        // 1. Single wheel notch downward and upward settles smoothly without overshoot.
        var state = SmoothScrollPhysics.AddWheelDelta(default, 0, 5000, -120, 126.0);
        check(state.Active && Math.Abs(state.Target - 126.0) < 1e-9, "single downward wheel notch sets exact target");
        var maxSeen = state.Current;
        var dt200 = 0.005;
        var elapsed = 0.0;
        var monotonic = true;
        var progressAt250Ms = 0.0;
        for (var i = 0; i < 200 && state.Active; i++)
        {
            var prev = state.Current;
            state = SmoothScrollPhysics.Step(state, dt200, 5000);
            elapsed += dt200;
            if (state.Current < prev - 1e-12) monotonic = false;
            if (elapsed <= 0.25 + 1e-9) progressAt250Ms = state.Current;
            if (state.Current > maxSeen) maxSeen = state.Current;
        }
        check(monotonic, "single downward notch is monotonic without oscillation");
        check(!state.Active && Math.Abs(state.Current - 126.0) < 1e-9, "single downward notch settles to exact target");
        check(maxSeen <= 126.0 + 1e-9 && progressAt250Ms >= 126.0 * 0.95 && elapsed <= 0.45, "single notch has zero overshoot, reaches 95% within 250ms, and settles within 450ms");

        var up = SmoothScrollPhysics.AddWheelDelta(default, 600, 5000, 120, 126.0);
        check(up.Active && Math.Abs(up.Target - 474.0) < 1e-9, "single upward wheel notch sets exact target");
        var minUp = up.Current;
        for (var i = 0; i < 200 && up.Active; i++)
        {
            up = SmoothScrollPhysics.Step(up, dt200, 5000);
            if (up.Current < minUp) minUp = up.Current;
        }
        check(!up.Active && Math.Abs(up.Current - 474.0) < 1e-9 && minUp >= 474.0 - 1e-9, "upward wheel notch settles monotonically without overshoot");

        // 2. Frame-rate invariance: 200Hz (20 x 5ms) matches 60Hz (6 x 16.667ms) at t = 100ms.
        var s200 = SmoothScrollPhysics.AddWheelDelta(default, 0, 5000, -120, 126.0);
        var s60 = s200;
        for (var i = 0; i < 20; i++) s200 = SmoothScrollPhysics.Step(s200, 0.005, 5000);
        for (var i = 0; i < 6; i++) s60 = SmoothScrollPhysics.Step(s60, 0.1 / 6.0, 5000);
        check(Math.Abs(s200.Current - s60.Current) < 1e-9 && Math.Abs(s200.Velocity - s60.Velocity) < 1e-9, "spring kinematics are frame-rate invariant between 60Hz and 200Hz");

        // 3. Continuous wheel ticks every 90ms maintain smooth velocity without sawtooth spikes.
        SmoothScrollState cont = default;
        var steadySteps = new List<double>();
        for (var f = 0; f < 18 * 12; f++)
        {
            if (f % 18 == 0)
                cont = SmoothScrollPhysics.AddWheelDelta(cont, cont.Current, 5000, -120, 126.0);
            var prevY = cont.Current;
            cont = SmoothScrollPhysics.Step(cont, 0.005, 5000);
            if (f >= 18 * 5 && f < 18 * 11)
                steadySteps.Add(cont.Current - prevY);
        }
        var minStep = steadySteps.Min();
        var maxStep = steadySteps.Max();
        var maxAdjDiff = Enumerable.Range(1, steadySteps.Count - 1).Max(i => Math.Abs(steadySteps[i] - steadySteps[i - 1]));
        check(minStep > 0 && maxStep / minStep < 1.5 && maxAdjDiff < 1.0, "continuous 90ms wheel ticks glide smoothly at 200Hz without sawtooth spikes");

        // 4. Direction reversal redirects immediately from current position without coasting past old target.
        var rev = SmoothScrollPhysics.AddWheelDelta(default, 1000, 5000, -240, 126.0); // target 1252
        for (var i = 0; i < 6; i++) rev = SmoothScrollPhysics.Step(rev, 0.005, 5000); // ~30ms in, still moving down
        var currentBeforeReversal = rev.Current;
        rev = SmoothScrollPhysics.AddWheelDelta(rev, currentBeforeReversal, 5000, 120, 126.0);
        check(rev.Target < currentBeforeReversal && Math.Abs(rev.Target - (currentBeforeReversal - 126.0)) < 1e-9, "reversal redirects target from current offset");
        var peakAfterReversal = rev.Current;
        for (var i = 0; i < 200 && rev.Active; i++)
        {
            rev = SmoothScrollPhysics.Step(rev, 0.005, 5000);
            if (rev.Current > peakAfterReversal) peakAfterReversal = rev.Current;
        }
        check(peakAfterReversal - currentBeforeReversal < 3.0 && !rev.Active && Math.Abs(rev.Current - rev.Target) < 1e-9, "reversal settles cleanly without overshooting toward old target");

        // 5. Edge clamping at 0 and scrollableHeight.
        var topClamp = SmoothScrollPhysics.AddWheelDelta(default, 40, 1000, 240, 126.0);
        for (var i = 0; i < 200 && topClamp.Active; i++) topClamp = SmoothScrollPhysics.Step(topClamp, 0.005, 1000);
        check(!topClamp.Active && topClamp.Current == 0 && topClamp.Velocity == 0, "top edge clamp settles cleanly at 0");

        var botClamp = SmoothScrollPhysics.AddWheelDelta(default, 960, 1000, -240, 126.0);
        for (var i = 0; i < 200 && botClamp.Active; i++) botClamp = SmoothScrollPhysics.Step(botClamp, 0.005, 1000);
        check(!botClamp.Active && Math.Abs(botClamp.Current - 1000) < 1e-9 && botClamp.Velocity == 0, "bottom edge clamp settles cleanly at scrollableHeight");

        // 6. PixelsPerNotch handles default, custom lines, WHEEL_PAGESCROLL, and viewport cap.
        check(Math.Abs(SmoothScrollPhysics.PixelsPerNotch(0, 900) - 126.0) < 1e-9, "wheel lines 0 falls back to 3 lines");
        check(Math.Abs(SmoothScrollPhysics.PixelsPerNotch(6, 900) - 252.0) < 1e-9, "wheel lines 6 scales linearly within viewport cap");
        check(Math.Abs(SmoothScrollPhysics.PixelsPerNotch(uint.MaxValue, 900) - 765.0) < 1e-9, "WHEEL_PAGESCROLL uses viewport-scaled page step");
        check(Math.Abs(SmoothScrollPhysics.PixelsPerNotch(50, 900) - 765.0) < 1e-9, "large line count is capped by 0.85 * viewport");

        // 7. IsExternalScrollTakeover tolerates ChangeView async lag while catching real jumps.
        check(!SmoothScrollPhysics.IsExternalScrollTakeover(100, 90, 140), "trailing offset within applied interval is not treated as takeover");
        check(!SmoothScrollPhysics.IsExternalScrollTakeover(75, 90, 140), "small jitter within tolerance is not treated as takeover");
        check(SmoothScrollPhysics.IsExternalScrollTakeover(300, 90, 140), "external jump far outside applied window triggers takeover");
        check(SmoothScrollPhysics.IsExternalScrollTakeover(20, 90, 140), "external upward jump outside tolerance triggers takeover");
    }
}
