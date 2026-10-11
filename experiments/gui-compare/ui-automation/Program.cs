using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Threading;
using System.Threading.Tasks;
using System.Diagnostics;
using System.Net.Http;
using System.Runtime.InteropServices;
using System.Text;
using System.Text.Json;
using System.Text.RegularExpressions;
using System.Windows.Automation;

// Windows-only UI Automation benchmark driver. This must interact with actual GUI
// controls; updating the HTTP API directly would produce invalid GUI measurements.
internal static class Program
{
    private static readonly HttpClient Http = new() { BaseAddress = new Uri("http://127.0.0.1:8768/") };
    private static AutomationElement Window = null!;
    private static string Variant = "";
    private static readonly List<string> Evidence = [];
    private static int Attempts;
    private static int Verified;
    private static string QueryLabel => Variant == "WinUI" ? "TxtQuery" : "作品名・タグで検索";
    private static string ListLabel => Variant == "WinUI" ? "ItemList" : "作品一覧";
    private static string TagLabel => Variant == "WinUI" ? "TxtTags" : "タグ（カンマ区切り）";
    private static string SaveLabel => Variant == "WinUI" ? "BtnSave" : "変更を保存";
    private static string TitleLabel => Variant == "WinUI" ? "TxtTitle" : "選択中の作品";

    [STAThread]
    private static int Main(string[] args)
    {
        string? outputPath = null;
        string phase = "";
        try
        {
            var a = new Dictionary<string, string>(StringComparer.OrdinalIgnoreCase);
            for (var i = 0; i < args.Length; i += 2)
            {
                if (i + 1 >= args.Length || !args[i].StartsWith("--", StringComparison.Ordinal))
                    throw new ArgumentException("Expected --name value arguments");
                a.Add(args[i][2..], args[i + 1]);
            }
            if (a.ContainsKey("self-test"))
            {
                if (!Regex.IsMatch("雨の街 — Sample 00001", @"Sample\s*0*1\b"))
                    throw new Exception("Title parser failed");
                int inputSize = Native.InputSizeProbe.Size;
                int expected = IntPtr.Size == 8 ? 40 : 28;
                if (inputSize != expected)
                    throw new Exception($"SendInput native struct layout mismatch: {inputSize}, expected {expected}");
                string[] defaultRows = ["作品: 雨の街 — Sample 00001", "作品: 夜の図書館 — Sample 00004"];
                string[] filteredRows = ["作品: 雨の街 — Sample 00001", "作品: 雨の街 — Sample 00002"];
                if (SearchRowsMatch(defaultRows, true) || !SearchRowsMatch(defaultRows, false) ||
                    !SearchRowsMatch(filteredRows, true) || SearchRowsMatch(filteredRows, false) ||
                    SearchRowsMatch([], true) || SearchRowsMatch([], false))
                    throw new Exception("Search UI verification predicates failed");
                Console.WriteLine("PASS: GUI driver title/input layout and search-state checks");
                return 0;
            }
            outputPath = a["result"];
            phase = a["phase"];
            Variant = a["variant"];
            if (Variant is not ("Tauri" or "WinUI") ||
                phase is not ("Check" or "Idle" or "Search" or "Scroll" or "Detail" or "Edit"))
                throw new ArgumentException("Unknown phase or variant");
            var pid = int.Parse(a["pid"]);
            var seconds = int.Parse(a["seconds"]);
            if (seconds is < 3 or > 300) throw new ArgumentOutOfRangeException(nameof(seconds));
            Window = WaitForWindow(pid);
            Log($"対象を確認：{Variant} / PID {pid} / {phase}");
            Activate();
            FindRequired(QueryLabel);
            FindRequired(ListLabel);
            // React renders the inspector (including Save) only after an item
            // is selected. Do not require Save before the first selection.
            VerifyListHasRows();
            if (phase == "Check")
            {
                SearchOnce();
                ScrollOnce();
                DetailOnce();
                EditOnce();
                ClearQuery();
                Log("GUI操作の自動チェックが完了しました");
            }
            else
            {
                if (phase == "Search") ClearQuery();
                if (phase == "Detail" || phase == "Edit") ResetList();
                var deadline = Stopwatch.StartNew();
                while (deadline.Elapsed < TimeSpan.FromSeconds(seconds))
                {
                    switch (phase)
                    {
                        case "Idle":
                            Thread.Sleep(500);
                            break;
                        case "Search": SearchOnce(); break;
                        case "Scroll": ScrollOnce(); break;
                        case "Detail": DetailOnce(); break;
                        case "Edit": EditOnce(); break;
                    }
                }
                if (phase != "Idle" && Verified == 0)
                    throw new InvalidOperationException("操作が1件も検証できませんでした");
            }
            WriteResult(outputPath, phase, true, null);
            return 0;
        }
        catch (Exception ex)
        {
            Log("エラー: " + ex.GetType().Name + ": " + ex.Message);
            try
            {
                if (Window is not null) DumpElements(Path.ChangeExtension(outputPath ?? "uia-error", ".tree.txt"));
            }
            catch (Exception debugEx) { Log("UIA tree collection failed: " + debugEx.Message); }
            if (!string.IsNullOrWhiteSpace(outputPath))
            {
                try { WriteResult(outputPath, phase, false, ex.ToString()); }
                catch (Exception ioEx) { Console.Error.WriteLine(ioEx); }
            }
            return 1;
        }
    }

    private static void WriteResult(string path, string phase, bool success, string? error)
    {
        Directory.CreateDirectory(Path.GetDirectoryName(Path.GetFullPath(path))!);
        var body = new {
            success, variant = Variant, phase,
            attempts = Attempts, verified = Verified,
            events = Evidence, error,
            finishedUtc = DateTimeOffset.UtcNow
        };
        File.WriteAllText(path, JsonSerializer.Serialize(body, new JsonSerializerOptions { WriteIndented = true }), Encoding.UTF8);
    }

    private static void Log(string message)
    {
        Evidence.Add(message);
        Console.WriteLine(message);
    }

    private static AutomationElement WaitForWindow(int pid)
    {
        for (var attempt = 0; attempt < 60; attempt++)
        {
            if (Process.GetProcessById(pid).HasExited)
                throw new InvalidOperationException($"GUI process {pid} exited");
            var windows = AutomationElement.RootElement.FindAll(
                TreeScope.Children, new PropertyCondition(AutomationElement.ProcessIdProperty, pid));
            foreach (AutomationElement w in windows)
            {
                if (w.Current.ControlType == ControlType.Window)
                    return w;
            }
            Thread.Sleep(250);
        }
        throw new InvalidOperationException("指定PIDのトップレベルウィンドウが見つかりません");
    }

    private static void Activate()
    {
        var hwnd = new IntPtr(Window.Current.NativeWindowHandle);
        if (hwnd == IntPtr.Zero) throw new InvalidOperationException("ウィンドウハンドルがありません");
        Native.ShowWindow(hwnd, 9); // restore if minimized
        Native.SetForegroundWindow(hwnd);
        Thread.Sleep(150);
    }

    private static AutomationElement? Find(string idOrName)
    {
        var property = Variant == "WinUI" ?
            AutomationElement.AutomationIdProperty : AutomationElement.NameProperty;
        var byKey = Window.FindFirst(TreeScope.Descendants, new PropertyCondition(property, idOrName));
        if (byKey is not null) return byKey;
        // Accessibility names differ across WebView2 / XAML builds: attempt both
        // exact name and exact automation identifier before failing.
        var other = property == AutomationElement.NameProperty ?
            AutomationElement.AutomationIdProperty : AutomationElement.NameProperty;
        return Window.FindFirst(TreeScope.Descendants, new PropertyCondition(other, idOrName));
    }

    private static AutomationElement FindRequired(string idOrName)
        => Find(idOrName) ?? throw new InvalidOperationException(
            $"操作対象「{idOrName}」がアクセシビリティツリーにありません。tree.txt を確認してください");

    // React's <label> and its nested <textarea> can share the same accessible
    // name. FindFirst(name) may resolve to the label, which cannot take focus.
    // Only return an actual, enabled and focusable text-entry UIA control.
    // WinUI TextBox also advertises ControlType.Edit.
    private static bool IsUsableEdit(AutomationElement item)
    {
        try
        {
            var c = item.Current;
            return c.ControlType == ControlType.Edit
                && c.IsKeyboardFocusable && c.IsEnabled && !c.IsOffscreen;
        }
        catch (ElementNotAvailableException) { return false; }
    }

    private static AutomationElement FindEditRequired(string idOrName)
    {
        var identifier = new OrCondition(
            new PropertyCondition(AutomationElement.AutomationIdProperty, idOrName),
            new PropertyCondition(AutomationElement.NameProperty, idOrName));
        for (var retry = 0; retry < 15; retry++)
        {
            var named = Window.FindAll(TreeScope.Descendants, identifier);
            foreach (AutomationElement candidate in named)
            {
                if (IsUsableEdit(candidate)) return candidate;
                // For React's nested <label><textarea>, walk the associated
                // descendants instead of treating the label as an input.
                foreach (var child in Descendants(candidate))
                    if (IsUsableEdit(child)) return child;
            }
            Thread.Sleep(100);
        }
        throw new InvalidOperationException(
            $"編集対象「{idOrName}」に対応するフォーカス可能なテキスト入力欄がありません。UIA tree.txtを確認してください");
    }

    private static string NameOf(AutomationElement e)
    {
        try { return e.Current.Name ?? ""; }
        catch (ElementNotAvailableException) { return ""; }
    }
    private static List<AutomationElement> Descendants(AutomationElement root)
    {
        var collection = root.FindAll(TreeScope.Descendants, Condition.TrueCondition);
        return collection.Cast<AutomationElement>().ToList();
    }
    private static string RowName(AutomationElement item)
    {
        var accessibleName = NameOf(item);
        if (accessibleName.Contains("Sample ", StringComparison.OrdinalIgnoreCase))
            return accessibleName;
        // Some WinUI 3 ListViewItem wrappers expose an empty Name while their
        // nested TextBlock contains the actual title. Inspect only that row.
        var descendants = Descendants(item);
        var texts = descendants
            .Where(x => x.Current.ControlType == ControlType.Text)
            .Select(NameOf)
            .Where(x => !string.IsNullOrWhiteSpace(x))
            .Take(5);
        return string.Join(" ", texts);
    }
    private static void VerifyListHasRows()
    {
        for (var i = 0; i < 35; i++)
        {
            if (FindRows().Count > 0) return;
            Thread.Sleep(200);
        }
        throw new InvalidOperationException("5万件の一覧行がUIA上で確認できませんでした");
    }

    private static List<AutomationElement> FindRows()
    {
        var list = FindRequired(ListLabel);
        var matching = new List<AutomationElement>();
        foreach (var item in Descendants(list))
        {
            try
            {
                var type = item.Current.ControlType;
                if (Variant == "Tauri" && type != ControlType.Button) continue;
                if (Variant == "WinUI" && type != ControlType.ListItem) continue;
                var title = RowName(item);
                if (title.Contains("Sample ", StringComparison.OrdinalIgnoreCase) &&
                    !item.Current.IsOffscreen && !item.Current.BoundingRectangle.IsEmpty)
                    matching.Add(item);
            }
            catch (ElementNotAvailableException) { }
        }
        return matching.OrderBy(x => x.Current.BoundingRectangle.Top).ToList();
    }

    private static void Click(AutomationElement e)
    {
        Activate();
        try
        {
            if (e.TryGetCurrentPattern(SelectionItemPattern.Pattern, out var pattern))
            {
                ((SelectionItemPattern)pattern).Select();
                return;
            }
            if (e.TryGetCurrentPattern(InvokePattern.Pattern, out pattern))
            {
                ((InvokePattern)pattern).Invoke();
                return;
            }
        }
        catch (InvalidOperationException) { /* pointer fallback */ }
        var b = e.Current.BoundingRectangle;
        if (b.IsEmpty || e.Current.IsOffscreen) throw new InvalidOperationException("クリック対象が表示されていません");
        var x = (int)(b.Left + b.Width / 2);
        var y = (int)(b.Top + b.Height / 2);
        Native.SetCursorPos(x, y);
        Thread.Sleep(80);
        Native.mouse_event(0x0002, 0, 0, 0, UIntPtr.Zero);
        Native.mouse_event(0x0004, 0, 0, 0, UIntPtr.Zero);
    }

    // WebView2 may hand focus back to the page between rapid search cycles.
    // Re-acquire the live element on every attempt; do not keep an obsolete UIA
    // reference across React renders. Require actual keyboard focus and verify
    // the exact displayed value, rather than treating SendInput as success.
    private static void Type(string label, string value)
    {
        string lastValue = "(取得できず)";
        string lastFocus = "(未確認)";
        for (var attempt = 1; attempt <= 3; attempt++)
        {
            var target = FindEditRequired(label);
            Activate();
            try { target.SetFocus(); }
            catch (InvalidOperationException) { /* click-to-focus fallback */ }

            if (attempt > 1 || !target.Current.HasKeyboardFocus)
                Click(target); // an actual mouse click also foregrounds WebView2
            for (var wait = 0; wait < 8 && !target.Current.HasKeyboardFocus; wait++)
                Thread.Sleep(60);

            if (!target.Current.HasKeyboardFocus)
            {
                lastFocus = "キーボードフォーカスがありません";
                Log($"入力先を再フォーカスします: {label} ({attempt}/3)");
                Thread.Sleep(180);
                continue;
            }

            lastFocus = "フォーカスあり";
            Native.Key(0x11, true);
            Native.Key(0x41, true);
            Native.Key(0x41, false);
            Native.Key(0x11, false);
            Thread.Sleep(60);
            Native.Press(0x08);
            Thread.Sleep(80);
            foreach (var ch in value)
            {
                Native.Unicode(ch);
                Thread.Sleep(35);
            }

            // React controlled inputs can re-render while async search results
            // arrive. Check the *current* UIA element, not a pre-render handle.
            for (var wait = 0; wait < 12; wait++)
            {
                Thread.Sleep(100);
                var current = FindEditRequired(label);
                if (!current.TryGetCurrentPattern(ValuePattern.Pattern, out var pattern))
                    throw new InvalidOperationException($"入力欄「{label}」はValuePatternを提供していません");
                lastValue = ((ValuePattern)pattern).Current.Value;
                if (string.Equals(value, lastValue, StringComparison.Ordinal))
                    return;
            }
            Log($"入力を再試行します: {label} ({attempt}/3)、期待値={value}、実際={lastValue}");
            Thread.Sleep(220);
        }
        throw new InvalidOperationException(
            $"入力の反映を3回試しましたが確認できません: {label}, expected {value}, actual {lastValue}, focus {lastFocus}");
    }

    private static bool SearchRowsMatch(IEnumerable<string> names, bool filtered)
    {
        // The first unfiltered page already includes "雨の街"; checking for
        // its mere presence is not proof a search actually filtered anything.
        var rows = names.ToArray();
        return filtered
            ? rows.Length > 0 && rows.All(x => x.Contains("雨の街", StringComparison.Ordinal))
            : rows.Any(x => x.Contains("夜の図書館", StringComparison.Ordinal));
    }

    private static void WaitForSearchState(bool filtered)
    {
        for (var wait = 0; wait < 40; wait++)
        {
            if (SearchRowsMatch(FindRows().Select(RowName), filtered))
                return;
            Thread.Sleep(125);
        }
        throw new InvalidOperationException(filtered
            ? "検索入力後も、一覧が「雨の街」の結果に切り替わりませんでした"
            : "検索を消したあと、5万件の通常一覧に戻ったことを確認できませんでした");
    }

    private static void ClearQuery()
    {
        Type(QueryLabel, "");
        WaitForSearchState(filtered: false);
    }

    private static void SearchOnce()
    {
        Attempts++;
        Type(QueryLabel, "雨の街");
        WaitForSearchState(filtered: true);
        ClearQuery();
        Verified++;
        Log("検索入力・絞り込み結果・5万件一覧への復帰を確認");
    }

    private static void ResetList()
    {
        var list = FindRequired(ListLabel);
        if (list.TryGetCurrentPattern(ScrollPattern.Pattern, out var p))
        {
            var scroll = (ScrollPattern)p;
            if (scroll.Current.VerticallyScrollable)
            {
                try { scroll.SetScrollPercent(ScrollPattern.NoScroll, 0); }
                catch (InvalidOperationException) { /* keyboard fallback */ }
            }
        }
        // React uses a <div role="group"> which is not keyboard-focusable.
        // Focusing a visible row lets HOME scroll without throwing for group.
        var target = list.Current.IsKeyboardFocusable ? list
            : FindRows().FirstOrDefault(x => x.Current.IsKeyboardFocusable);
        if (target is not null)
        {
            target.SetFocus();
            Native.Press(0x24); // HOME
        }
        Thread.Sleep(160);
    }

    private static void ScrollOnce()
    {
        Attempts++;
        ResetList();
        var list = FindRequired(ListLabel);
        var b = list.Current.BoundingRectangle;
        if (b.IsEmpty) throw new InvalidOperationException("一覧表示領域がありません");
        var before = FindRows().Select(RowName).FirstOrDefault();
        var scroll = FindScrollContainer(list);
        double old = scroll is null ? -1 : scroll.Current.VerticalScrollPercent;
        Native.SetCursorPos((int)(b.Left + b.Width / 2), (int)(b.Top + Math.Min(b.Height / 2, 260)));
        for (var i = 0; i < 9; i++)
        {
            Native.mouse_event(0x0800, 0, 0, unchecked((uint)(-120)), UIntPtr.Zero);
            Thread.Sleep(70);
        }
        Thread.Sleep(230);
        var after = FindRows().Select(RowName).FirstOrDefault();
        var moved = before != after;
        if (scroll is not null)
        {
            var pos = scroll.Current.VerticalScrollPercent;
            moved |= old >= 0 && pos >= 0 && Math.Abs(pos - old) > 0.1;
        }
        if (!moved) throw new InvalidOperationException("スクロール後の一覧位置の変化を確認できませんでした");
        for (var i = 0; i < 9; i++)
        {
            Native.mouse_event(0x0800, 0, 0, 120, UIntPtr.Zero);
            Thread.Sleep(55);
        }
        ResetList();
        Verified++;
        Log("一覧スクロールの変化を確認");
    }

    private static ScrollPattern? FindScrollContainer(AutomationElement list)
    {
        if (list.TryGetCurrentPattern(ScrollPattern.Pattern, out var s)) return (ScrollPattern)s;
        foreach (var node in Descendants(list))
            if (node.TryGetCurrentPattern(ScrollPattern.Pattern, out s))
            {
                var pattern = (ScrollPattern)s;
                if (pattern.Current.VerticallyScrollable) return pattern;
            }
        return null;
    }

    private static string SelectedTitle()
    {
        if (Variant == "WinUI") return NameOf(FindRequired(TitleLabel));
        // React inspector text appears on right side. Do not confuse it with list rows.
        var listRect = FindRequired(ListLabel).Current.BoundingRectangle;
        foreach (var element in Descendants(Window))
        {
            var name = NameOf(element);
            if (!name.Contains("Sample ", StringComparison.OrdinalIgnoreCase)) continue;
            var rect = element.Current.BoundingRectangle;
            if (!rect.IsEmpty && rect.Left >= listRect.Right + 4 && !element.Current.IsOffscreen)
                return name;
        }
        return "";
    }

    private static void DetailOnce()
    {
        Attempts++;
        ResetList();
        var rows = FindRows();
        if (rows.Count < 3) throw new InvalidOperationException("詳細テスト用の一覧行が3つ見つかりません");
        var first3 = rows.Take(3).ToList();
        foreach (var row in first3)
        {
            var intended = RowName(row);
            Click(row);
            var ok = false;
            for (var i = 0; i < 25; i++)
            {
                if (SelectedTitle().Contains(Regex.Match(intended, @"Sample\s*\d+").Value, StringComparison.OrdinalIgnoreCase))
                { ok = true; break; }
                Thread.Sleep(100);
            }
            if (!ok) throw new InvalidOperationException($"作品を選んでも詳細表示を確認できません: {intended}");
        }
        Verified++;
        Log("3作品の選択と右側詳細の一致を確認");
    }

    private static async Task<(string title, string[] tags)> GetOriginalAsync(int id)
    {
        using var response = await Http.GetAsync("api/items/" + id);
        response.EnsureSuccessStatusCode();
        using var doc = JsonDocument.Parse(await response.Content.ReadAsStringAsync());
        var root = doc.RootElement;
        return (root.GetProperty("title").GetString() ?? "", root.GetProperty("tags").EnumerateArray()
            .Select(x => x.GetString() ?? "").ToArray());
    }

    private static void EditOnce()
    {
        Attempts++;
        ClearQuery();
        ResetList();
        var rows = FindRows();
        if (rows.Count == 0) throw new InvalidOperationException("タグ編集対象が表示されません");
        // The synthetic database is sorted by ID and its first item is always ID=1.
        Click(rows[0]);
        var expectedTitle = GetOriginalAsync(1).GetAwaiter().GetResult().title;
        var ok = false;
        for (var i = 0; i < 25; i++)
        {
            if (SelectedTitle().Contains(expectedTitle, StringComparison.OrdinalIgnoreCase)) { ok = true; break; }
            Thread.Sleep(100);
        }
        if (!ok) throw new InvalidOperationException("編集対象の詳細が表示されません");
        var original = GetOriginalAsync(1).GetAwaiter().GetResult().tags;
        // On Tauri both the tag field and Save button exist only after
        // selection. Validate them here, once the detail pane is populated.
        var save = FindRequired(SaveLabel);
        var before = string.Join(", ", original);
        var marker = "aredoko_auto_test";
        var changed = original.Contains(marker) ?
            original.Where(x => x != marker).ToArray() :
            original.Concat([marker]).ToArray();
        var after = string.Join(", ", changed);
        Type(TagLabel, after);
        // Only click when a real change was detected (button must be enabled).
        if (!save.Current.IsEnabled) throw new InvalidOperationException("編集後に保存ボタンが有効になりません");
        Click(save);
        ok = false;
        for (var i = 0; i < 40; i++)
        {
            var stored = GetOriginalAsync(1).GetAwaiter().GetResult().tags;
            if (stored.SequenceEqual(changed)) { ok = true; break; }
            Thread.Sleep(100);
        }
        if (!ok) throw new InvalidOperationException("UIの保存がAPIのDBに反映されません");
        Verified++;
        Log($"GUIでID=1のタグを変更してDB反映を確認（元: {before}; 今: {after}）");
    }

    private static void DumpElements(string? path)
    {
        if (string.IsNullOrEmpty(path)) return;
        var items = new List<string>();
        foreach (var node in Descendants(Window).Take(450))
        {
            try
            {
                var c = node.Current;
                items.Add($"{c.ControlType.ProgrammaticName} | {c.AutomationId} | {c.Name} | visible={!c.IsOffscreen} | focusable={c.IsKeyboardFocusable} | enabled={c.IsEnabled}");
            }
            catch (ElementNotAvailableException) {}
        }
        File.WriteAllLines(path, items, Encoding.UTF8);
        Log("UIAツリー診断を保存: " + path);
    }
}

internal static class Native
{
    internal readonly struct InputSizeProbe
    {
        internal static int Size => Marshal.SizeOf<Input>();
    }
    [DllImport("user32.dll")] internal static extern bool SetForegroundWindow(IntPtr hWnd);
    [DllImport("user32.dll")] internal static extern bool ShowWindow(IntPtr hWnd, int nCmdShow);
    [DllImport("user32.dll")] internal static extern bool SetCursorPos(int x, int y);
    [DllImport("user32.dll")] internal static extern void mouse_event(uint flags, uint dx, uint dy, uint data, UIntPtr extraInfo);

    [StructLayout(LayoutKind.Sequential)]
    private struct KeyboardInput
    {
        internal ushort vk, scan;
        internal uint flags, time;
        internal IntPtr extra;
    }
    [StructLayout(LayoutKind.Sequential)]
    private struct MouseInput
    {
        internal int dx, dy;
        internal uint mouseData, flags, time;
        internal IntPtr extra;
    }
    [StructLayout(LayoutKind.Explicit)]
    private struct InputData
    {
        [FieldOffset(0)] internal KeyboardInput keyboard;
        // INPUT's native union is sized for MOUSEINPUT (32 bytes on x64).
        // Without this, Marshal.SizeOf<Input>() was 32 instead of 40,
        // so SendInput would reject every unicode keystroke.
        [FieldOffset(0)] internal MouseInput mouse;
    }
    [StructLayout(LayoutKind.Sequential)]
    private struct Input
    {
        internal uint type;
        internal InputData data;
    }
    [DllImport("user32.dll", SetLastError = true)] private static extern uint SendInput(uint count, [In] Input[] inputs, int size);
    private static void SendKey(ushort code, bool up, bool unicode)
    {
        var data = new Input {
            type = 1,
            data = new InputData { keyboard = new KeyboardInput {
                vk = unicode ? (ushort)0 : code, scan = unicode ? code : (ushort)0,
                flags = (up ? 0x0002u : 0u) | (unicode ? 0x0004u : 0u)
            }}
        };
        if (SendInput(1, [data], Marshal.SizeOf<Input>()) != 1)
            throw new System.ComponentModel.Win32Exception(Marshal.GetLastWin32Error(), "Windowsのキーボード入力が失敗しました");
    }
    internal static void Key(ushort code, bool down) => SendKey(code, !down, false);
    internal static void Press(ushort code) { Key(code, true); Key(code, false); }
    internal static void Unicode(char ch) { SendKey(ch, false, true); SendKey(ch, true, true); }
}
