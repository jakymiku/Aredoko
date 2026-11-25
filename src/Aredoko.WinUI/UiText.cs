using System.Runtime.CompilerServices;
using Aredoko.Core;
using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Automation;
using Microsoft.UI.Xaml.Controls;
using Microsoft.UI.Xaml.Controls.Primitives;

namespace Aredoko_WinUI;

internal static class UiText
{
    private static readonly ConditionalWeakTable<DependencyObject, Dictionary<string, string>> Originals = new();

    public static void Apply(DependencyObject? root)
    {
        if (root is null) return;
        var visited = new HashSet<object>(ReferenceEqualityComparer.Instance);
        Walk(root, visited);
    }

    private static string ResolveSlot(DependencyObject obj, string slot, string current)
    {
        var map = Originals.GetOrCreateValue(obj);
        if (map.TryGetValue(slot, out var original))
        {
            if (AppText.TryTranslateExact(original, out var mapped) && (current == original || current == mapped))
                return AppText.IsEnglish ? mapped : original;
            map.Remove(slot);
        }
        if (AppText.TryTranslateExact(current, out var en))
        {
            map[slot] = current;
            return AppText.IsEnglish ? en : current;
        }
        return current;
    }

    private static void Translate(DependencyObject obj, string slot, string? current, Action<string> setter)
    {
        if (string.IsNullOrEmpty(current)) return;
        var next = ResolveSlot(obj, slot, current);
        if (!string.Equals(current, next, StringComparison.Ordinal)) setter(next);
    }

    private static void Walk(DependencyObject? node, HashSet<object> visited)
    {
        if (node is null || !visited.Add(node)) return;

        if (ToolTipService.GetToolTip(node) is string tip)
            Translate(node, "ToolTip", tip, v => ToolTipService.SetToolTip(node, v));
        Translate(node, "AutoName", AutomationProperties.GetName(node), v => AutomationProperties.SetName(node, v));
        Translate(node, "HelpText", AutomationProperties.GetHelpText(node), v => AutomationProperties.SetHelpText(node, v));

        switch (node)
        {
            case NavigationView nav:
                foreach (var item in nav.MenuItems.OfType<DependencyObject>()) Walk(item, visited);
                foreach (var item in nav.FooterMenuItems.OfType<DependencyObject>()) Walk(item, visited);
                if (nav.Content is DependencyObject navContent) Walk(navContent, visited);
                break;
            case SplitView split:
                if (split.Pane is DependencyObject pane) Walk(pane, visited);
                if (split.Content is DependencyObject splitContent) Walk(splitContent, visited);
                break;
            case Expander exp:
                if (exp.Header is string expHeader) Translate(exp, "Header", expHeader, v => exp.Header = v);
                else if (exp.Header is DependencyObject expHeaderObj) Walk(expHeaderObj, visited);
                if (exp.Content is DependencyObject expContent) Walk(expContent, visited);
                break;
            case TextBlock tb:
                Translate(tb, "Text", tb.Text, v => tb.Text = v);
                break;
            case TextBox box:
                if (box.Header is string bh) Translate(box, "Header", bh, v => box.Header = v);
                else if (box.Header is DependencyObject bho) Walk(bho, visited);
                Translate(box, "Placeholder", box.PlaceholderText, v => box.PlaceholderText = v);
                break;
            case NumberBox num:
                if (num.Header is string nh) Translate(num, "Header", nh, v => num.Header = v);
                else if (num.Header is DependencyObject nho) Walk(nho, visited);
                Translate(num, "Placeholder", num.PlaceholderText, v => num.PlaceholderText = v);
                break;
            case ComboBox combo:
                if (combo.Header is string ch) Translate(combo, "Header", ch, v => combo.Header = v);
                else if (combo.Header is DependencyObject cho) Walk(cho, visited);
                Translate(combo, "Placeholder", combo.PlaceholderText, v => combo.PlaceholderText = v);
                foreach (var item in combo.Items.OfType<DependencyObject>()) Walk(item, visited);
                break;
            case InfoBar bar:
                Translate(bar, "Title", bar.Title, v => bar.Title = v);
                Translate(bar, "Message", bar.Message, v => bar.Message = v);
                if (bar.ActionButton is DependencyObject actionBtn) Walk(actionBtn, visited);
                if (bar.Content is DependencyObject barContent) Walk(barContent, visited);
                break;
            case MenuFlyoutItem mfi:
                Translate(mfi, "Text", mfi.Text, v => mfi.Text = v);
                break;
            case MenuFlyoutSubItem sub:
                Translate(sub, "Text", sub.Text, v => sub.Text = v);
                foreach (var item in sub.Items) Walk(item, visited);
                break;
            case ContentControl cc:
                if (cc.Content is string cs) Translate(cc, "Content", cs, v => cc.Content = v);
                else if (cc.Content is DependencyObject co) Walk(co, visited);
                break;
            case Border border:
                Walk(border.Child, visited);
                break;
            case Panel panel:
                foreach (var child in panel.Children) Walk(child, visited);
                break;
            case UserControl uc:
                Walk(uc.Content, visited);
                break;
        }

        if (node is Button { Flyout: FlyoutBase btnFlyout }) WalkFlyout(btnFlyout, visited);
        if (node is FrameworkElement { ContextFlyout: FlyoutBase ctxFlyout }) WalkFlyout(ctxFlyout, visited);
    }

    private static void WalkFlyout(FlyoutBase? flyout, HashSet<object> visited)
    {
        if (flyout is null || !visited.Add(flyout)) return;
        if (flyout is MenuFlyout menu)
            foreach (var item in menu.Items) Walk(item, visited);
        else if (flyout is Flyout f && f.Content is DependencyObject content)
            Walk(content, visited);
    }
}
