using Aredoko.Core;
using Microsoft.UI.Input;
using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Controls;
using Microsoft.UI.Xaml.Controls.Primitives;
using Microsoft.UI.Xaml.Input;
using Microsoft.UI.Xaml.Media;
using System.Diagnostics;
using System.Runtime.InteropServices;
using Windows.System;
using Windows.UI.Core;

namespace Aredoko_WinUI;

/// <summary>
/// Replaces WinUI ScrollViewer's discrete mouse-wheel jump with per-frame smooth scrolling.
/// Preserves native Precision Touchpad, touch, pen, Shift/Alt modifiers, and Ctrl+Wheel zoom.
/// </summary>
internal sealed class SmoothWheelScroller
{
    private const uint SPI_GETWHEELSCROLLLINES = 0x0068;

    [DllImport("user32.dll")]
    private static extern bool SystemParametersInfo(uint uiAction, uint uiParam, out uint pvParam, uint fWinIni);

    private readonly List<ScrollBar> hookedBars = new();
    private readonly PointerEventHandler scrollBarPressedHandler;

    private ScrollViewer? scroll;
    private UIElement? scrollContent;
    private UIElement? scrollRoot;
    private Func<bool>? canHandleWheel;
    private Action<double>? onVelocityChanged;
    private Action? onStopped;

    private SmoothScrollState state;
    private bool renderingSubscribed;
    private bool loadedHooked;
    private bool hasAppliedFirstFrame;
    private long lastTimestamp;
    private double lastObservedActualY;
    private double lastAppliedY;
    private uint wheelScrollLines = 3;

    public SmoothWheelScroller()
    {
        scrollBarPressedHandler = (_, _) => Stop();
    }

    public bool IsActive => state.Active;
    public double Velocity => state.Velocity;

    public void Attach(
        ScrollViewer target,
        Func<bool> canHandleWheel,
        Action<double>? onVelocityChanged = null,
        Action? onStopped = null)
    {
        if (ReferenceEquals(scroll, target))
        {
            this.canHandleWheel = canHandleWheel;
            this.onVelocityChanged = onVelocityChanged;
            this.onStopped = onStopped;
            if (scrollContent is null && scrollRoot is null)
                HookVisualChildren();
            return;
        }

        Detach();
        scroll = target;
        this.canHandleWheel = canHandleWheel;
        this.onVelocityChanged = onVelocityChanged;
        this.onStopped = onStopped;
        HookVisualChildren();
    }

    public void Detach()
    {
        Stop();
        UnhookVisualChildren();
        if (scroll is not null && loadedHooked)
        {
            scroll.Loaded -= OnScrollLoaded;
            loadedHooked = false;
        }
        scroll = null;
        canHandleWheel = null;
        onVelocityChanged = null;
        onStopped = null;
    }

    public void Stop()
    {
        if (renderingSubscribed)
        {
            CompositionTarget.Rendering -= OnRendering;
            renderingSubscribed = false;
        }
        var wasActive = state.Active;
        state = default;
        hasAppliedFirstFrame = false;
        if (wasActive) onStopped?.Invoke();
    }

    private void OnScrollLoaded(object sender, RoutedEventArgs e)
    {
        if (scroll is null) return;
        scroll.Loaded -= OnScrollLoaded;
        loadedHooked = false;
        HookVisualChildren();
    }

    private void HookVisualChildren()
    {
        if (scroll is null) return;
        UnhookVisualChildren();

        if (VisualTreeHelper.GetChildrenCount(scroll) == 0)
        {
            if (!loadedHooked)
            {
                scroll.Loaded += OnScrollLoaded;
                loadedHooked = true;
            }
            return;
        }

        scrollContent = scroll.Content as UIElement;
        if (scrollContent is not null)
            scrollContent.PointerWheelChanged += OnPointerWheelChanged;

        var root = VisualTreeHelper.GetChild(scroll, 0) as UIElement;
        if (root is not null && !ReferenceEquals(root, scrollContent))
        {
            scrollRoot = root;
            scrollRoot.PointerWheelChanged += OnPointerWheelChanged;
        }

        CollectScrollBars(scroll, hookedBars);
        foreach (var bar in hookedBars)
            bar.AddHandler(UIElement.PointerPressedEvent, scrollBarPressedHandler, true);
    }

    private void UnhookVisualChildren()
    {
        if (scrollContent is not null)
        {
            scrollContent.PointerWheelChanged -= OnPointerWheelChanged;
            scrollContent = null;
        }
        if (scrollRoot is not null)
        {
            scrollRoot.PointerWheelChanged -= OnPointerWheelChanged;
            scrollRoot = null;
        }
        foreach (var bar in hookedBars)
            bar.RemoveHandler(UIElement.PointerPressedEvent, scrollBarPressedHandler);
        hookedBars.Clear();
    }

    private static void CollectScrollBars(DependencyObject parent, List<ScrollBar> bars)
    {
        var count = VisualTreeHelper.GetChildrenCount(parent);
        for (var i = 0; i < count; i++)
        {
            var child = VisualTreeHelper.GetChild(parent, i);
            if (child is ScrollBar bar) bars.Add(bar);
            CollectScrollBars(child, bars);
        }
    }

    private static bool IsKeyDown(VirtualKey key)
        => (InputKeyboardSource.GetKeyStateForCurrentThread(key) & CoreVirtualKeyStates.Down) != 0;

    private void OnPointerWheelChanged(object sender, PointerRoutedEventArgs args)
    {
        if (args.Handled || scroll is null || canHandleWheel?.Invoke() != true) return;

        if (args.Pointer.PointerDeviceType != PointerDeviceType.Mouse)
        {
            Stop();
            return;
        }

        var properties = args.GetCurrentPoint(scroll).Properties;
        if (properties.IsHorizontalMouseWheel || properties.MouseWheelDelta == 0) return;

        if (IsKeyDown(VirtualKey.Control))
        {
            Stop();
            args.Handled = true;
            return;
        }
        if (IsKeyDown(VirtualKey.Shift) || IsKeyDown(VirtualKey.Menu))
        {
            Stop();
            return;
        }

        if (scroll.ScrollableHeight <= 0) return;

        if (!state.Active && SystemParametersInfo(SPI_GETWHEELSCROLLLINES, 0, out var lines, 0))
            wheelScrollLines = lines;

        var pixelsPerNotch = SmoothScrollPhysics.PixelsPerNotch(wheelScrollLines, scroll.ViewportHeight);
        state = SmoothScrollPhysics.AddWheelDelta(
            state,
            scroll.VerticalOffset,
            scroll.ScrollableHeight,
            properties.MouseWheelDelta,
            pixelsPerNotch);
        args.Handled = true;

        if (state.Active && !renderingSubscribed)
        {
            lastTimestamp = Stopwatch.GetTimestamp();
            lastObservedActualY = scroll.VerticalOffset;
            lastAppliedY = state.Current;
            hasAppliedFirstFrame = false;
            renderingSubscribed = true;
            CompositionTarget.Rendering += OnRendering;
        }
    }

    private void OnRendering(object? sender, object e)
    {
        if (scroll is null || !state.Active || canHandleWheel?.Invoke() != true)
        {
            Stop();
            return;
        }

        var actualY = scroll.VerticalOffset;
        if (hasAppliedFirstFrame && SmoothScrollPhysics.IsExternalScrollTakeover(actualY, lastObservedActualY, lastAppliedY))
        {
            Stop();
            return;
        }
        lastObservedActualY = actualY;

        var now = Stopwatch.GetTimestamp();
        var dt = (now - lastTimestamp) / (double)Stopwatch.Frequency;
        lastTimestamp = now;

        var next = SmoothScrollPhysics.Step(state, dt, scroll.ScrollableHeight);
        state = next;

        if (!next.Active || Math.Abs(next.Current - lastAppliedY) >= 0.05)
        {
            lastAppliedY = next.Current;
            hasAppliedFirstFrame = true;
            scroll.ChangeView(null, next.Current, null, disableAnimation: true);
        }

        onVelocityChanged?.Invoke(next.Velocity);
        if (!next.Active) Stop();
    }
}
