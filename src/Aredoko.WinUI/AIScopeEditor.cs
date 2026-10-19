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
    private readonly TextBox rootQuery=new() {Header="フォルダを探す",PlaceholderText="フォルダ名・パスで絞り込み",MaxLength=512};
    private readonly TextBlock rootSummary=new() {TextWrapping=TextWrapping.Wrap};
    private readonly TextBlock rootPage=new();
    private readonly Button rootPrevious=new() {Content="前へ"};
    private readonly Button rootNext=new() {Content="次へ"};
    private readonly TextBox rootPath=new() {Header="フォルダのフルパス（選択・コピーできます）",IsReadOnly=true,AcceptsReturn=true,TextWrapping=TextWrapping.Wrap,MaxHeight=120,Visibility=Visibility.Collapsed};
    private readonly List<Button> pathButtons=[];
    private readonly CheckBox all=new() {Content="登録フォルダをすべて対象にする"};
    private readonly ComboBox kind=new() {Header="対象の種類",HorizontalAlignment=HorizontalAlignment.Stretch};
    private readonly ComboBox shelfMode=new() {Header="棚の条件",HorizontalAlignment=HorizontalAlignment.Stretch};
    private readonly TextBox shelf=new() {Header="棚（完全一致）",MaxLength=80};
    private readonly Button refresh=new() {Content="件数を確認"};
    private readonly Button save=new() {Content="保存してAI検索に適用"};
    private readonly Button revert=new() {Content="保存済みに戻す"};
    private readonly TextBlock feedback=new() {TextWrapping=TextWrapping.Wrap};
    private readonly TextBlock[] counts=Enumerable.Range(0,4).Select(_=>new TextBlock {TextWrapping=TextWrapping.Wrap}).ToArray();
    private readonly Dictionary<int,CheckBox> roots=new();
    private readonly string[] kinds=["","book","image","video","audio","archive","material"];
    private JsonObject? saved;
    private bool initializationStarted,initializing=true,closed,counting,saving,confirmed,jobBusy;
    private int version,target;
    public event Action? StateChanged;
    public event Action? ScopeEdited;
    public Expander Content {get;}
    public bool Saving=>saving;
    public bool Ready=>!initializing&&!saving&&!counting&&confirmed&&!Dirty&&saved is not null&&target>0;
    private bool Dirty=>saved is null || !JsonNode.DeepEquals(saved,Draft());

    public AIScopeEditor(LibraryApi api,Action<JsonObject?> applied)
    {
        this.api=api;this.applied=applied;
        AutomationProperties.SetAutomationId(all,"AIScopeAllRoots");
        foreach(var (control,id) in new (DependencyObject,string)[]{(rootQuery,"AIScopeRootQuery"),(rootSummary,"AIScopeRootSummary"),(rootPage,"AIScopeRootPage"),(rootPrevious,"AIScopeRootPrevious"),(rootNext,"AIScopeRootNext"),(rootPath,"AIScopeRootPath")})AutomationProperties.SetAutomationId(control,id);
        AutomationProperties.SetName(rootQuery,"対象フォルダを名前・パスで絞り込み");
        AutomationProperties.SetName(rootPath,"対象フォルダのフルパス");
        rootQuery.TextChanged+=(_,_)=>{if(!initializing&&!closed&&!renderingRoots){picker.Filter(rootQuery.Text);RenderRoots();}};
        rootPrevious.Click+=(_,_)=>{picker.Move(-1);RenderRoots();};
        rootNext.Click+=(_,_)=>{picker.Move(1);RenderRoots();};
        AutomationProperties.SetAutomationId(kind,"AIScopeKind");AutomationProperties.SetName(kind,"AI対象の種類");
        AutomationProperties.SetAutomationId(shelfMode,"AIScopeShelfMode");AutomationProperties.SetName(shelfMode,"AI対象の棚条件");
        AutomationProperties.SetAutomationId(shelf,"AIScopeShelf");
        AutomationProperties.SetAutomationId(refresh,"AIScopeRefresh");
        AutomationProperties.SetAutomationId(save,"AIScopeSave");
        AutomationProperties.SetAutomationId(revert,"AIScopeRevert");
        AutomationProperties.SetAutomationId(feedback,"AIScopeFeedback");
        var labels=new[]{"すべての種類","本","画像","動画","音楽","ZIP","素材"};
        for(int i=0;i<kinds.Length;i++) {
            var item=new ComboBoxItem {Content=labels[i],Tag=kinds[i]};
            AutomationProperties.SetAutomationId(item,"AIScopeKind_"+(kinds[i].Length==0?"all":kinds[i]));kind.Items.Add(item);
        }
        foreach(var (value,label) in new[]{(0,"棚を指定しない"),(1,"指定した棚"),(2,"未整理のみ")}) {
            var item=new ComboBoxItem {Content=label,Tag=value};
            AutomationProperties.SetAutomationId(item,$"AIScopeShelfMode_{value}");shelfMode.Items.Add(item);
        }
        kind.SelectedIndex=0;shelfMode.SelectedIndex=0;
        all.Checked+=(_,_)=>Changed();all.Unchecked+=(_,_)=>Changed();
        kind.SelectionChanged+=(_,_)=>Changed();shelfMode.SelectionChanged+=(_,_)=>Changed();shelf.TextChanged+=(_,_)=>Changed();
        // Bound the expanding settings extent even with hundreds of roots.
        var rootViewport=new ScrollViewer {Content=FormScrollContent.Wrap(rootList),MaxHeight=160,
            HorizontalScrollBarVisibility=ScrollBarVisibility.Disabled,
            VerticalScrollBarVisibility=ScrollBarVisibility.Auto};
        AutomationProperties.SetAutomationId(rootViewport,"AIScopeRootsScroll");
        AutomationProperties.SetName(rootViewport,"AI対象フォルダ一覧");
        var rootPager=new StackPanel {Orientation=Orientation.Horizontal,Spacing=8};
        rootPager.Children.Add(rootPrevious);rootPager.Children.Add(rootPage);rootPager.Children.Add(rootNext);
        foreach(var element in new UIElement[]{all,rootQuery,rootSummary,rootViewport,rootPager,rootPath,kind,shelfMode,shelf})fields.Children.Add(element);
        var panel=new StackPanel {Spacing=12};
        panel.Children.Add(new TextBlock {Text="保存するまで現在のAI対象は変わりません。閉じると未保存の条件は破棄します。文字検索には適用しません。",TextWrapping=TextWrapping.Wrap});
        panel.Children.Add(fields);panel.Children.Add(refresh);
        var countPanel=new StackPanel {Spacing=4};
        for(int i=0;i<counts.Length;i++){AutomationProperties.SetAutomationId(counts[i],$"AIScopeCount{i}");countPanel.Children.Add(counts[i]);}
        panel.Children.Add(countPanel);panel.Children.Add(save);panel.Children.Add(revert);panel.Children.Add(feedback);
        Content=new Expander {Header="AI検索と索引の対象",Content=panel,HorizontalAlignment=HorizontalAlignment.Stretch,HorizontalContentAlignment=HorizontalAlignment.Stretch};
        AutomationProperties.SetAutomationId(Content,"AIScopeOptions");
        Content.Loaded+=async(_,_)=>{if(initializing&&!closed&&!initializationStarted){initializationStarted=true;await InitializeAsync();}};
        refresh.Click+=async(_,_)=>await RefreshCountsAsync();
        save.Click+=async(_,_)=>await SaveAsync();
        revert.Click+=async(_,_)=>{Restore(saved??Empty());await RefreshCountsAsync();};
        Sync();
    }
    private static JsonObject Empty()=>new() {{"root_ids",new JsonArray()},{"kind",""},{"shelf",null}};
    private JsonObject Draft()
    {
        var ids=new JsonArray();foreach(var id in picker.Selected)ids.Add((JsonNode?)JsonValue.Create(id));
        return new JsonObject {{"root_ids",all.IsChecked==true?null:ids},{"kind",kind.SelectedItem is ComboBoxItem selected?selected.Tag as string??"":""},
            {"shelf",shelfMode.SelectedIndex==0?null:shelfMode.SelectedIndex==2?"":shelf.Text}};
    }
    private void Restore(JsonObject value)
    {
        initializing=true;
        all.IsChecked=value["root_ids"] is null;
        var chosen=value["root_ids"] is JsonArray ids?ids.Select(n=>n!.GetValue<int>()).ToHashSet():[];
        picker.Restore(chosen);rootQuery.Text="";rootPath.Visibility=Visibility.Collapsed;RenderRoots();
        kind.SelectedIndex=Array.IndexOf(kinds,value["kind"]?.GetValue<string>()??"");
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
                feedback.Text=data["error"]?.GetValue<string>()??"";
            } catch(Exception ex){feedback.Text="対象を取得できません。選び直して保存してください: "+ex.Message;saved=null;}
            if(closed)return;
            applied(saved is null?null:(JsonObject)saved.DeepClone());
            picker=new RootPicker(registered.Where(n=>n is not null).Select(n=>new RootChoice(n!["id"]!.GetValue<int>(),n["path"]!.GetValue<string>())));
            Restore(value);await RefreshCountsAsync();
        } catch(Exception ex){initializing=false;feedback.Text="登録フォルダを取得できません: "+ex.Message;applied(null);}
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
            var detail=new Button {Content="パス",VerticalAlignment=VerticalAlignment.Center};
            AutomationProperties.SetAutomationId(detail,$"AIScopeRootPath_{choice.Id}");AutomationProperties.SetName(detail,choice.Path+" のフルパスを表示");
            detail.Click+=(_,_)=>{rootPath.Text=choice.Path;rootPath.Visibility=Visibility.Visible;rootPath.Focus(FocusState.Programmatic);};
            var row=new Grid {ColumnSpacing=8};row.ColumnDefinitions.Add(new ColumnDefinition {Width=new GridLength(1,GridUnitType.Star)});row.ColumnDefinitions.Add(new ColumnDefinition {Width=GridLength.Auto});
            row.Children.Add(box);Grid.SetColumn(detail,1);row.Children.Add(detail);rootList.Children.Add(row);roots[choice.Id]=box;pathButtons.Add(detail);
        }
        if(picker.MatchCount==0)rootList.Children.Add(new TextBlock {Text="一致するフォルダがありません。選択済みの対象は保持しています。",TextWrapping=TextWrapping.Wrap});
        renderingRoots=false;Sync();
    }
    private void Changed()
    {
        if(initializing||closed)return;
        version++;confirmed=false;target=0;
        foreach(var block in counts)block.Text="";
        counts[0].Text="条件を変更しました。件数を確認してください。";
        ScopeEdited?.Invoke();
        Sync();
    }
    private void Sync()
    {
        if(closed)return;
        all.IsEnabled=kind.IsEnabled=shelfMode.IsEnabled=!initializing&&!saving;
        foreach(var pair in roots)pair.Value.IsEnabled=!initializing&&!saving&&all.IsChecked!=true&&(picker.SelectionCount<RootPicker.SelectionLimit||picker.IsSelected(pair.Key));
        rootQuery.IsEnabled=!initializing&&!saving;
        rootPrevious.IsEnabled=!initializing&&!saving&&picker.Page>0;
        rootNext.IsEnabled=!initializing&&!saving&&picker.Page+1<picker.PageCount;
        rootPage.Text=$"{picker.Page+1} / {picker.PageCount}";
        rootSummary.Text=$"一致: {picker.MatchCount:N0} フォルダ · 個別選択: {picker.SelectionCount:N0} / {RootPicker.SelectionLimit}（絞り込みやページ切替でも保持）";
        foreach(var button in pathButtons)button.IsEnabled=!initializing&&!saving;
        shelf.IsEnabled=!initializing&&!saving&&shelfMode.SelectedIndex==1;
        refresh.IsEnabled=!initializing&&!counting&&!saving;
        save.IsEnabled=!initializing&&!saving&&!counting&&confirmed&&Dirty&&!jobBusy;
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
            counts[0].Text=$"条件に合う候補: {data["candidate_total"]!.GetValue<long>():N0} 件";
            counts[1].Text=$"今回の対象枠: {target:N0} 件（最大10,000件）";
            counts[2].Text=$"現在の文字索引: {data["fresh_total"]!.GetValue<int>():N0} 件";
            counts[3].Text=$"残り: {data["remaining_total"]!.GetValue<int>():N0} 件 · 確認時点の件数です";
        } catch(Exception ex){if(!closed&&ticket==version){counts[0].Text="件数を確認できません: "+ex.Message;confirmed=false;}}
        finally {counting=false;Sync();}
    }
    private async Task SaveAsync()
    {
        if(!save.IsEnabled||closed)return;
        var requested=Draft();saving=true;Sync();
        try {
            var data=await api.PostAsync("api/library/ai/scope",AIScopeRequests.Scoped(requested));
            if(closed)return;
            if(data["valid"]?.GetValue<bool>()!=true)throw new InvalidOperationException("対象を選び直してください。");
            saved=(JsonObject)data["scope"]!.DeepClone();applied((JsonObject)saved.DeepClone());
            feedback.Text="保存しました。AI検索と次の索引作成に適用します。現在の索引・モデルは変更しません。";
        } catch(Exception ex){
            if(!closed) {
                // A lost response does not prove the server rejected the save.
                // Read back before adopting a scope; never retry a write silently.
                try {
                    var actual=await api.GetAsync("api/library/ai/scope");
                    if(closed)return;
                    var verified=actual["valid"]?.GetValue<bool>()==true?actual["scope"] as JsonObject:null;
                    if(verified is not null&&JsonNode.DeepEquals(verified,requested)) {
                        saved=(JsonObject)verified.DeepClone();applied((JsonObject)saved.DeepClone());
                        feedback.Text="保存しました（保存結果を再確認）。AI検索と次の索引作成に適用します。";
                    } else if(verified is not null&&saved is not null&&JsonNode.DeepEquals(verified,saved)) {
                        feedback.Text="保存できません。保存済みの対象を維持しました。件数を確認して再保存してください: "+ex.Message;
                    } else {
                        saved=null;applied(null);confirmed=false;feedback.Text="保存結果を確認できません。対象の件数を確認して再保存してください。";
                    }
                } catch(Exception) {if(!closed){saved=null;applied(null);confirmed=false;feedback.Text="保存結果を確認できません。対象の件数を確認して再保存してください。";}}
            }
        }
        finally {saving=false;Sync();}
    }
    public void Dispose(){closed=true;version++;}
}
