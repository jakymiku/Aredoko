using Aredoko.Core;
using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Controls;
using Microsoft.UI.Xaml.Automation;
using System.Text.Json.Nodes;

namespace Aredoko_WinUI;

// A dialog-local draft. Only an explicit successful save updates active search.
public sealed class AIScopeEditor : IDisposable
{
    private readonly LibraryApi api;
    private readonly Action<JsonObject?> applied;
    private readonly StackPanel fields=new() {Spacing=12};
    private readonly StackPanel rootList=new() {Spacing=4};
    private RootPicker picker=new([]);
    private bool renderingRoots;
    private readonly TextBox rootQuery=new() {Header=AppText.L("フォルダを探す", "Find Folder"),PlaceholderText=AppText.L("フォルダ名・パスで絞り込み", "Filter by folder name or path"),MaxLength=512};
    private readonly TextBlock rootSummary=new() {TextWrapping=TextWrapping.Wrap};
    private readonly TextBlock rootPage=new();
    private readonly Button rootPrevious=new() {Content=AppText.L("前へ", "Previous")};
    private readonly Button rootNext=new() {Content=AppText.L("次へ", "Next")};
    private readonly TextBox rootPath=new() {Header=AppText.L("フルパス", "Full Path"),IsReadOnly=true,AcceptsReturn=true,TextWrapping=TextWrapping.Wrap,MaxHeight=120,Visibility=Visibility.Collapsed};
    private readonly List<Button> pathButtons=[];
    private readonly CheckBox all=new() {Content=AppText.L("登録フォルダをすべて対象にする", "Include all registered folders")};
    private readonly ComboBox kind=new() {Header=AppText.L("対象の種類", "Target Kind"),HorizontalAlignment=HorizontalAlignment.Stretch};
    private readonly ComboBox bookPages=new() {Header=AppText.L("CBZ・ZIP・本の内部ページ", "CBZ / ZIP / Book Inner Pages"),HorizontalAlignment=HorizontalAlignment.Stretch};
    private readonly ComboBox shelfMode=new() {Header=AppText.L("棚の条件", "Shelf Filter"),HorizontalAlignment=HorizontalAlignment.Stretch};
    private readonly TextBox shelf=new() {Header=AppText.L("棚（完全一致）", "Shelf (Exact Match)"),MaxLength=80};
    private readonly Button refresh=new() {Content=AppText.L("件数を確認", "Check Counts")};
    private readonly Button save=new() {Content=AppText.L("保存", "Save")};
    private readonly Button revert=new() {Content=AppText.L("元に戻す", "Revert")};
    private readonly TextBlock feedback=new() {TextWrapping=TextWrapping.Wrap};
    private readonly TextBlock[] counts=Enumerable.Range(0,4).Select(_=>new TextBlock {TextWrapping=TextWrapping.Wrap}).ToArray();
    private readonly Dictionary<int,CheckBox> roots=new();
    private readonly string[] kinds=["","book","image","video","audio","archive","material","compressed"];
    private JsonObject? saved;
    private bool initializationStarted,initializing=true,closed,counting,saving,confirmed,jobBusy;
    private int version,target;
    public event Action? StateChanged;
    public event Action? ScopeEdited;
    public Expander Content {get;}
    public bool Saving=>saving;
    public bool Ready=>!initializing&&!saving&&!counting&&confirmed&&!Dirty&&saved is not null&&target>0;
    private static JsonObject NormalizeForCompare(JsonObject value)
    {
        var copy=(JsonObject)value.DeepClone();
        if(!copy.ContainsKey("book_pages")||copy["book_pages"] is null)copy["book_pages"]="cover_only";
        return copy;
    }
    private bool Dirty=>saved is null || !JsonNode.DeepEquals(NormalizeForCompare(saved),Draft());
    private bool OnlyBookPagesChanged()
    {
        if(saved is null)return false;
        var baseNormalized=NormalizeForCompare(saved);
        var draft=(JsonObject)Draft().DeepClone();
        if(JsonNode.DeepEquals(baseNormalized,draft))return false;
        draft["book_pages"]=baseNormalized["book_pages"]?.DeepClone();
        return JsonNode.DeepEquals(baseNormalized,draft);
    }

    public AIScopeEditor(LibraryApi api,Action<JsonObject?> applied)
    {
        this.api=api;this.applied=applied;
        AutomationProperties.SetAutomationId(all,"AIScopeAllRoots");
        foreach(var (control,id) in new (DependencyObject,string)[]{(rootQuery,"AIScopeRootQuery"),(rootSummary,"AIScopeRootSummary"),(rootPage,"AIScopeRootPage"),(rootPrevious,"AIScopeRootPrevious"),(rootNext,"AIScopeRootNext"),(rootPath,"AIScopeRootPath")})AutomationProperties.SetAutomationId(control,id);
        AutomationProperties.SetName(rootQuery,AppText.L("対象フォルダを名前・パスで絞り込み", "Filter target folders by name or path"));
        AutomationProperties.SetName(rootPath,AppText.L("対象フォルダのフルパス", "Full path of target folder"));
        rootQuery.TextChanged+=(_,_)=>{if(!initializing&&!closed&&!renderingRoots){picker.Filter(rootQuery.Text);RenderRoots();}};
        rootPrevious.Click+=(_,_)=>{picker.Move(-1);RenderRoots();};
        rootNext.Click+=(_,_)=>{picker.Move(1);RenderRoots();};
        AutomationProperties.SetAutomationId(kind,"AIScopeKind");AutomationProperties.SetName(kind,AppText.L("AI対象の種類", "AI target kind"));
        AutomationProperties.SetAutomationId(bookPages,"AIScopeBookPages");AutomationProperties.SetName(bookPages,AppText.L("CBZ・ZIP・本の内部ページのAI対象", "AI scope for book inner pages"));
        AutomationProperties.SetAutomationId(shelfMode,"AIScopeShelfMode");AutomationProperties.SetName(shelfMode,AppText.L("AI対象の棚条件", "AI target shelf filter"));
        AutomationProperties.SetAutomationId(shelf,"AIScopeShelf");
        AutomationProperties.SetAutomationId(refresh,"AIScopeRefresh");
        AutomationProperties.SetAutomationId(save,"AIScopeSave");
        AutomationProperties.SetAutomationId(revert,"AIScopeRevert");
        AutomationProperties.SetAutomationId(feedback,"AIScopeFeedback");
        var labels=AppText.IsEnglish
            ?new[]{"All kinds","Books","Images","Videos","Audio","ZIP","Materials","Archives (ZIP / CBZ)"}
            :new[]{"すべての種類","本","画像","動画","音楽","ZIP","素材","圧縮ファイル（ZIP・CBZ）"};
        for(int i=0;i<kinds.Length;i++) {
            var item=new ComboBoxItem {Content=labels[i],Tag=kinds[i]};
            AutomationProperties.SetAutomationId(item,"AIScopeKind_"+(kinds[i].Length==0?"all":kinds[i]));kind.Items.Add(item);
        }
        foreach(var (value,label) in new[]{("cover_only",AppText.L("表紙のみ（標準・高速）", "Cover only (Standard / Fast)")),("all_pages",AppText.L("内部のすべての画像も含める（CBZ・ZIP・本）", "Include all inner pages (CBZ / ZIP / Books)"))}) {
            var item=new ComboBoxItem {Content=label,Tag=value};
            AutomationProperties.SetAutomationId(item,$"AIScopeBookPages_{value}");bookPages.Items.Add(item);
        }
        foreach(var (value,label) in new[]{(0,AppText.L("棚を指定しない", "Any shelf")),(1,AppText.L("指定した棚", "Specific shelf")),(2,AppText.L("未整理のみ", "Unshelved only"))}) {
            var item=new ComboBoxItem {Content=label,Tag=value};
            AutomationProperties.SetAutomationId(item,$"AIScopeShelfMode_{value}");shelfMode.Items.Add(item);
        }
        kind.SelectedIndex=0;bookPages.SelectedIndex=0;shelfMode.SelectedIndex=0;
        all.Checked+=(_,_)=>Changed();all.Unchecked+=(_,_)=>Changed();
        kind.SelectionChanged+=(_,_)=>Changed();bookPages.SelectionChanged+=(_,_)=>BookPagesChanged();shelfMode.SelectionChanged+=(_,_)=>Changed();shelf.TextChanged+=(_,_)=>Changed();
        // Bound the expanding settings extent even with hundreds of roots.
        var rootViewport=new ScrollViewer {Content=FormScrollContent.Wrap(rootList),MaxHeight=160,
            HorizontalScrollBarVisibility=ScrollBarVisibility.Disabled,
            VerticalScrollBarVisibility=ScrollBarVisibility.Auto};
        AutomationProperties.SetAutomationId(rootViewport,"AIScopeRootsScroll");
        AutomationProperties.SetName(rootViewport,AppText.L("AI対象フォルダ一覧", "AI target folder list"));
        var rootPager=new StackPanel {Orientation=Orientation.Horizontal,Spacing=8};
        rootPager.Children.Add(rootPrevious);rootPager.Children.Add(rootPage);rootPager.Children.Add(rootNext);
        foreach(var element in new UIElement[]{all,rootQuery,rootSummary,rootViewport,rootPager,rootPath,kind,bookPages,shelfMode,shelf})fields.Children.Add(element);
        var panel=new StackPanel {Spacing=12};
        var scopeNote=new TextBlock {Text=AppText.L("AI検索の対象範囲（文字検索には影響しません）", "AI search target scope (does not affect text search)"),TextWrapping=TextWrapping.Wrap};
        ToolTipService.SetToolTip(scopeNote,AppText.L("AI検索とこれから作るAI検索データに適用します。作成済みデータやモデルは変更しません。", "Applies to AI search and new AI indexes. Does not modify existing indexes or models."));
        panel.Children.Add(scopeNote);
        panel.Children.Add(fields);panel.Children.Add(refresh);
        var countPanel=new StackPanel {Spacing=4};
        for(int i=0;i<counts.Length;i++){AutomationProperties.SetAutomationId(counts[i],$"AIScopeCount{i}");countPanel.Children.Add(counts[i]);}
        panel.Children.Add(countPanel);panel.Children.Add(save);panel.Children.Add(revert);panel.Children.Add(feedback);
        Content=new Expander {Header=AppText.L("AI検索の対象範囲", "AI Search Scope"),Content=panel,HorizontalAlignment=HorizontalAlignment.Stretch,HorizontalContentAlignment=HorizontalAlignment.Stretch};
        AutomationProperties.SetAutomationId(Content,"AIScopeOptions");
        Content.Loaded+=async(_,_)=>{if(initializing&&!closed&&!initializationStarted){initializationStarted=true;await InitializeAsync();}};
        refresh.Click+=async(_,_)=>await RefreshCountsAsync();
        save.Click+=async(_,_)=>await SaveAsync();
        revert.Click+=async(_,_)=>{Restore(saved??Empty());await RefreshCountsAsync();};
        Sync();
    }
    private static JsonObject Empty()=>new() {{"root_ids",new JsonArray()},{"kind",""},{"shelf",null},{"book_pages","cover_only"}};
    private JsonObject Draft()
    {
        var ids=new JsonArray();foreach(var id in picker.Selected)ids.Add((JsonNode?)JsonValue.Create(id));
        return new JsonObject {{"root_ids",all.IsChecked==true?null:ids},{"kind",kind.SelectedItem is ComboBoxItem selected?selected.Tag as string??"":""},
            {"shelf",shelfMode.SelectedIndex==0?null:shelfMode.SelectedIndex==2?"":shelf.Text},
            {"book_pages",bookPages.SelectedItem is ComboBoxItem bp?bp.Tag as string??"cover_only":"cover_only"}};
    }
    private void Restore(JsonObject value)
    {
        initializing=true;
        all.IsChecked=value["root_ids"] is null;
        var chosen=value["root_ids"] is JsonArray ids?ids.Select(n=>n!.GetValue<int>()).ToHashSet():[];
        picker.Restore(chosen);rootQuery.Text="";rootPath.Visibility=Visibility.Collapsed;RenderRoots();
        kind.SelectedIndex=Array.IndexOf(kinds,value["kind"]?.GetValue<string>()??"");
        bookPages.SelectedIndex=value["book_pages"]?.GetValue<string>()=="all_pages"?1:0;
        var name=value["shelf"]?.GetValue<string>();shelfMode.SelectedIndex=name is null?0:name.Length==0?2:1;shelf.Text=name??"";
        initializing=false;Changed();
    }
    private async Task InitializeAsync()
    {
        var value=Empty();
        try {
            var registered=(await api.GetAsync("api/library/roots"))["items"]!.AsArray();
            if(closed)return;
            try {
                var data=await api.GetAsync("api/library/ai/scope");
                if(closed)return;
                value=(JsonObject)data["scope"]!.DeepClone();
                saved=data["valid"]?.GetValue<bool>()==true?(JsonObject)value.DeepClone():null;
                feedback.Text=AppText.TranslateBackend(data["error"]?.GetValue<string>());
            } catch(Exception ex){feedback.Text=AppText.L("対象を取得できません。選び直して保存してください: ", "Unable to load scope. Reselect and save: ")+ex.Message;saved=null;}
            if(closed)return;
            applied(saved is null?null:(JsonObject)saved.DeepClone());
            picker=new RootPicker(registered.Where(n=>n is not null).Select(n=>new RootChoice(n!["id"]!.GetValue<int>(),n["path"]!.GetValue<string>())));
            Restore(value);await RefreshCountsAsync();
        } catch(Exception ex){initializing=false;feedback.Text=AppText.L("登録フォルダを取得できません: ", "Unable to load registered folders: ")+ex.Message;applied(null);}
        finally {if(!closed)Sync();}
    }
    private void RenderRoots()
    {
        renderingRoots=true;
        rootList.Children.Clear();roots.Clear();pathButtons.Clear();
        foreach(var choice in picker.Visible) {
            var box=new CheckBox {HorizontalAlignment=HorizontalAlignment.Stretch,HorizontalContentAlignment=HorizontalAlignment.Stretch,IsChecked=picker.IsSelected(choice.Id),
                Content=new TextBlock {Text=choice.Path,TextWrapping=TextWrapping.Wrap,MaxLines=2,TextTrimming=TextTrimming.CharacterEllipsis}};
            AutomationProperties.SetAutomationId(box,$"AIScopeRoot_{choice.Id}");AutomationProperties.SetName(box,choice.Path);
            ToolTipService.SetToolTip(box,choice.Path);
            void ToggleRoot(){
                if(initializing||renderingRoots||closed)return;
                if(!picker.Select(choice.Id,box.IsChecked==true)){renderingRoots=true;box.IsChecked=false;renderingRoots=false;Sync();return;}
                Changed();
            }
            box.Checked+=(_,_)=>ToggleRoot();box.Unchecked+=(_,_)=>ToggleRoot();
            var detail=new Button {Content=AppText.L("パス", "Path"),VerticalAlignment=VerticalAlignment.Center};
            AutomationProperties.SetAutomationId(detail,$"AIScopeRootPath_{choice.Id}");AutomationProperties.SetName(detail,AppText.L(choice.Path+" のフルパスを表示", $"Show full path of {choice.Path}"));
            detail.Click+=(_,_)=>{rootPath.Text=choice.Path;rootPath.Visibility=Visibility.Visible;rootPath.Focus(FocusState.Programmatic);};
            var row=new Grid {ColumnSpacing=8};row.ColumnDefinitions.Add(new ColumnDefinition {Width=new GridLength(1,GridUnitType.Star)});row.ColumnDefinitions.Add(new ColumnDefinition {Width=GridLength.Auto});
            row.Children.Add(box);Grid.SetColumn(detail,1);row.Children.Add(detail);rootList.Children.Add(row);roots[choice.Id]=box;pathButtons.Add(detail);
        }
        if(picker.MatchCount==0)rootList.Children.Add(new TextBlock {Text=AppText.L("一致するフォルダがありません。選択済みの対象は保持しています。", "No matching folders found. Your current selection is preserved."),TextWrapping=TextWrapping.Wrap});
        renderingRoots=false;Sync();
    }
    private void Changed()
    {
        if(initializing||closed)return;
        version++;confirmed=false;target=0;
        foreach(var block in counts)block.Text="";
        counts[0].Text=AppText.L("条件を変更しました。件数を確認してください。", "Filters changed. Click Check Counts.");
        feedback.Text=Dirty?AppText.L("対象範囲の変更を保存するには「件数を確認」を押してください。", "Click Check Counts before saving scope changes."):"";
        ScopeEdited?.Invoke();
        Sync();
    }
    private void BookPagesChanged()
    {
        if(initializing||closed)return;
        if(!Dirty)feedback.Text="";
        else if(confirmed||OnlyBookPagesChanged())feedback.Text=AppText.L("未保存の変更があります。「保存」を押して反映してください。", "Unsaved changes. Click Save to apply.");
        else feedback.Text=AppText.L("対象範囲の変更を保存するには「件数を確認」を押してください。", "Click Check Counts before saving scope changes.");
        ScopeEdited?.Invoke();
        Sync();
    }
    private void Sync()
    {
        if(closed)return;
        all.IsEnabled=kind.IsEnabled=bookPages.IsEnabled=shelfMode.IsEnabled=!initializing&&!saving;
        foreach(var pair in roots)pair.Value.IsEnabled=!initializing&&!saving&&all.IsChecked!=true&&(picker.SelectionCount<RootPicker.SelectionLimit||picker.IsSelected(pair.Key));
        rootQuery.IsEnabled=!initializing&&!saving;
        rootPrevious.IsEnabled=!initializing&&!saving&&picker.Page>0;
        rootNext.IsEnabled=!initializing&&!saving&&picker.Page+1<picker.PageCount;
        rootPage.Text=$"{picker.Page+1} / {picker.PageCount}";
        rootSummary.Text=AppText.L($"表示 {picker.MatchCount:N0} · 選択 {picker.SelectionCount:N0}/{RootPicker.SelectionLimit}", $"Shown {picker.MatchCount:N0} · Selected {picker.SelectionCount:N0}/{RootPicker.SelectionLimit}");
        foreach(var button in pathButtons)button.IsEnabled=!initializing&&!saving;
        shelf.IsEnabled=!initializing&&!saving&&shelfMode.SelectedIndex==1;
        refresh.IsEnabled=!initializing&&!counting&&!saving;
        save.IsEnabled=!initializing&&!saving&&!counting&&Dirty&&!jobBusy&&(confirmed||OnlyBookPagesChanged());
        revert.IsEnabled=!initializing&&!saving&&!counting;
        StateChanged?.Invoke();
    }
    public void SetJobBusy(bool busy){if(jobBusy!=busy){jobBusy=busy;Sync();}}
    public async Task RefreshCountsAsync()
    {
        if(initializing||closed||counting||saving)return;
        var requested=Draft();int ticket=++version;counting=true;confirmed=false;Sync();
        try {
            var data=await api.PostAsync("api/library/ai/coverage",AIScopeRequests.Scoped(requested));
            if(closed||ticket!=version)return;
            target=data["target_total"]!.GetValue<int>();confirmed=true;
            int? coverageLimit=data["coverage_limit"] is JsonValue covVal&&covVal.TryGetValue<int>(out var covInt)?covInt:null;
            counts[0].Text=AppText.L($"条件に合う候補: {data["candidate_total"]!.GetValue<long>():N0} 件", $"Matching candidates: {data["candidate_total"]!.GetValue<long>():N0}");
            counts[1].Text=coverageLimit is >0
                ? AppText.L($"今回の対象枠: {target:N0} 件（上限 {coverageLimit.Value:N0} 件）", $"Target batch size: {target:N0} (limit {coverageLimit.Value:N0})")
                : AppText.L($"今回の対象枠: {target:N0} 件（全件対象）", $"Target batch size: {target:N0} (all matching)");
            counts[2].Text=AppText.L($"現在の文字索引: {data["fresh_total"]!.GetValue<int>():N0} 件", $"Current index ready: {data["fresh_total"]!.GetValue<int>():N0}");
            counts[3].Text=AppText.L($"残り: {data["remaining_total"]!.GetValue<int>():N0} 件 · 確認時点の件数です", $"Remaining: {data["remaining_total"]!.GetValue<int>():N0} · As of check time");
            if(Dirty&&!saving)feedback.Text=AppText.L("未保存の変更があります。「保存」を押して反映してください。", "Unsaved changes. Click Save to apply.");
        } catch(Exception ex){if(!closed&&ticket==version){counts[0].Text=AppText.L("件数を確認できません: ", "Unable to check counts: ")+ex.Message;confirmed=false;}}
        finally {counting=false;Sync();}
    }
    private async Task SaveAsync()
    {
        if(!save.IsEnabled||closed)return;
        var requested=Draft();saving=true;Sync();
        try {
            var data=await api.PostAsync("api/library/ai/scope",AIScopeRequests.Scoped(requested));
            if(closed)return;
            if(data["valid"]?.GetValue<bool>()!=true)throw new InvalidOperationException(AppText.L("対象を選び直してください。", "Reselect the target scope."));
            saved=(JsonObject)data["scope"]!.DeepClone();applied((JsonObject)saved.DeepClone());
            feedback.Text=AppText.L("✓ 保存しました", "✓ Saved");
        } catch(Exception ex){
            if(!closed) {
                // A lost response does not prove the server rejected the save.
                // Read back before adopting a scope; never retry a write silently.
                try {
                    var actual=await api.GetAsync("api/library/ai/scope");
                    if(closed)return;
                    var verified=actual["valid"]?.GetValue<bool>()==true?actual["scope"] as JsonObject:null;
                    if(verified is not null&&JsonNode.DeepEquals(NormalizeForCompare(verified),NormalizeForCompare(requested))) {
                        saved=(JsonObject)verified.DeepClone();applied((JsonObject)saved.DeepClone());
                        feedback.Text=AppText.L("✓ 保存しました（再確認済み）", "✓ Saved (verified)");
                    } else if(verified is not null&&saved is not null&&JsonNode.DeepEquals(NormalizeForCompare(verified),NormalizeForCompare(saved))) {
                        feedback.Text=AppText.L("保存できません。保存済みの対象を維持しました。件数を確認して再保存してください: ", "Could not save. Kept previously saved scope. Check counts and retry: ")+ex.Message;
                    } else {
                        saved=null;applied(null);confirmed=false;feedback.Text=AppText.L("保存結果を確認できません。対象の件数を確認して再保存してください。", "Unable to verify save result. Check counts and retry.");
                    }
                } catch(Exception) {if(!closed){saved=null;applied(null);confirmed=false;feedback.Text=AppText.L("保存結果を確認できません。対象の件数を確認して再保存してください。", "Unable to verify save result. Check counts and retry.");}}
            }
        }
        finally {saving=false;Sync();}
    }
    public void Dispose(){closed=true;version++;}
}
