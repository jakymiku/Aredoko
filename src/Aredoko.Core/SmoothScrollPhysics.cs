namespace Aredoko.Core;

public struct SmoothScrollState
{
    public double Current;
    public double Target;
    public double Velocity;
    public bool Active;
}

/// <summary>
/// Frame-rate-independent critically-damped spring kinematics for smooth wheel scrolling.
/// </summary>
public static class SmoothScrollPhysics
{
    public const double DefaultOmega = 21.0;
    public const double DefaultPixelsPerLine = 42.0;
    public const double SettleDistance = 0.25;
    public const double SettleVelocity = 6.0;

    public static double PixelsPerNotch(uint wheelScrollLines, double viewportHeight)
    {
        var maxStep = Math.Max(120.0, viewportHeight * 0.85);
        if (wheelScrollLines == uint.MaxValue) return maxStep;
        var lines = wheelScrollLines == 0 ? 3u : wheelScrollLines;
        return Math.Clamp(lines * DefaultPixelsPerLine, DefaultPixelsPerLine, maxStep);
    }

    public static SmoothScrollState AddWheelDelta(
        SmoothScrollState state,
        double currentOffset,
        double scrollableHeight,
        int wheelDelta,
        double pixelsPerNotch)
    {
        if (wheelDelta == 0 || scrollableHeight <= 0) return state;

        var deltaY = -(wheelDelta / 120.0) * pixelsPerNotch;
        if (!state.Active)
        {
            var clamped = Math.Clamp(currentOffset, 0, scrollableHeight);
            state.Current = clamped;
            state.Target = clamped;
            state.Velocity = 0;
        }
        else if ((deltaY > 0 && (state.Target < state.Current || state.Velocity < -1.0))
            || (deltaY < 0 && (state.Target > state.Current || state.Velocity > 1.0)))
        {
            // Redirect immediately on direction reversal instead of coasting in the old direction.
            state.Target = Math.Clamp(state.Current, 0, scrollableHeight);
            state.Velocity *= 0.2;
        }

        state.Target = Math.Clamp(state.Target + deltaY, 0, scrollableHeight);
        if (Math.Abs(state.Target - state.Current) >= SettleDistance || Math.Abs(state.Velocity) >= SettleVelocity)
            state.Active = true;
        return state;
    }

    public static SmoothScrollState Step(
        SmoothScrollState state,
        double dtSeconds,
        double scrollableHeight,
        double omega = DefaultOmega)
    {
        if (!state.Active) return state;
        var maxY = Math.Max(0, scrollableHeight);
        if (maxY <= 0)
            return new SmoothScrollState { Current = 0, Target = 0, Velocity = 0, Active = false };

        var dt = Math.Clamp(dtSeconds, 0.0005, 0.05);
        var target = Math.Clamp(state.Target, 0, maxY);
        var current = Math.Clamp(state.Current, 0, maxY);

        var diff = current - target;
        var exp = Math.Exp(-omega * dt);
        var term = state.Velocity + omega * diff;
        var nextY = target + (diff + term * dt) * exp;
        var nextV = (state.Velocity - omega * term * dt) * exp;

        if (nextY <= 0 && target <= 0)
        {
            nextY = 0;
            if (nextV < 0) nextV = 0;
        }
        else if (nextY >= maxY && target >= maxY)
        {
            nextY = maxY;
            if (nextV > 0) nextV = 0;
        }
        else
        {
            nextY = Math.Clamp(nextY, 0, maxY);
        }

        if (Math.Abs(nextY - target) < SettleDistance && Math.Abs(nextV) < SettleVelocity)
            return new SmoothScrollState { Current = target, Target = target, Velocity = 0, Active = false };

        return new SmoothScrollState
        {
            Current = nextY,
            Target = target,
            Velocity = nextV,
            Active = true,
        };
    }

    public static bool IsExternalScrollTakeover(
        double actualOffset,
        double previousActualOffset,
        double appliedOffset,
        double tolerance = 32.0)
    {
        var low = Math.Min(previousActualOffset, appliedOffset) - tolerance;
        var high = Math.Max(previousActualOffset, appliedOffset) + tolerance;
        return actualOffset < low || actualOffset > high;
    }
}
