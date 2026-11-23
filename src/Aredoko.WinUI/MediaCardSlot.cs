using Aredoko.Core;
using Microsoft.UI.Text;
using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Automation;
using Microsoft.UI.Xaml.Controls;
using Microsoft.UI.Xaml.Input;
using Microsoft.UI.Xaml.Media;

namespace Aredoko_WinUI;

internal sealed class MediaCardResources
{
    public Style? Title { get; }
    public Style? Metadata { get; }
    public Style? Caption { get; }
    public Style? PlaceholderIcon { get; }
    public Style? ThumbPlate { get; }
    public Style? KindOverlayPill { get; }
    public Style? TileQuickActionPill { get; }
    public Style? EvidenceAIPill { get; }
    public Style? EvidencePagePill { get; }
    public Style? EvidenceWordPill { get; }
    public Style? CardBadgeBorder { get; }
    public Style? MediaItemCard { get; }
    public Style? MediaItemSelectedCard { get; }
    public Style? UnselectedSegment { get; }
    public Style? CardFavoriteActive { get; }
    public SolidColorBrush WhiteBrush { get; } = new(Microsoft.UI.Colors.White);

    public MediaCardResources(ResourceDictionary pageResources)
    {
        Style? Get(string key) => (pageResources.TryGetValue(key, out var local) ? local
            : Application.Current.Resources.TryGetValue(key, out var app) ? app : null) as Style;

        Title = Get("MediaTitleStyle");
        Metadata = Get("MediaMetadataStyle");
        Caption = Get("CaptionTextBlockStyle");
        PlaceholderIcon = Get("MediaPlaceholderIconStyle");
        ThumbPlate = Get("ThumbPlateStyle");
        KindOverlayPill = Get("MediaKindOverlayPillStyle");
        TileQuickActionPill = Get("TileQuickActionPillStyle");
        EvidenceAIPill = Get("EvidenceAIPillStyle");
        EvidencePagePill = Get("EvidencePagePillStyle");
        EvidenceWordPill = Get("EvidenceWordPillStyle");
        CardBadgeBorder = Get("CardBadgeBorderStyle");
        MediaItemCard = Get("MediaItemCardStyle");
        MediaItemSelectedCard = Get("MediaItemSelectedCardStyle");
        UnselectedSegment = Get("UnselectedSegmentButtonStyle");
        CardFavoriteActive = Get("CardFavoriteActiveButtonStyle");
    }

    public Style? EvidenceStyle(string key) => key switch
    {
        "EvidencePagePillStyle" => EvidencePagePill,
        "EvidenceWordPillStyle" => EvidenceWordPill,
        _ => EvidenceAIPill,
    };
}

internal sealed class MediaCardSlot
{
    private const int MaxPooledBadges = 8;
    private const int MaxPooledEvidence = 5;

    private sealed class BadgeChipSlot
    {
        public Border Container { get; }
        public TextBlock Label { get; }

        public BadgeChipSlot(MediaCardResources res)
        {
            Label = new TextBlock
            {
                MaxLines = 1,
                TextWrapping = TextWrapping.NoWrap,
                TextTrimming = TextTrimming.CharacterEllipsis,
                Style = res.Metadata,
            };
            Container = new Border
            {
                Style = res.CardBadgeBorder,
                Visibility = Visibility.Collapsed,
                Child = Label,
            };
        }
    }

    private sealed class EvidencePillSlot
    {
        public Border Pill { get; }
        private readonly TextBlock wrappedLabel;
        private readonly StackPanel? structuredStack;
        private readonly TextBlock? primaryLabel;
        private readonly TextBlock? scoreLabel;
        private readonly TextBlock? secondaryLabel;
        private string? appliedStyleKey;
        private string? lastSummary;
        private UIElement? tooltipHost;

        public EvidencePillSlot(bool isTiles, MediaCardResources res)
        {
            wrappedLabel = new TextBlock
            {
                TextWrapping = TextWrapping.Wrap,
                MaxLines = 2,
                TextTrimming = TextTrimming.CharacterEllipsis,
                Style = res.Caption,
                Visibility = Visibility.Collapsed,
            };

            UIElement inner;
            if (isTiles)
            {
                primaryLabel = new TextBlock
                {
                    TextWrapping = TextWrapping.NoWrap,
                    MaxLines = 1,
                    TextTrimming = TextTrimming.CharacterEllipsis,
                    Style = res.Caption,
                };
                scoreLabel = new TextBlock
                {
                    FontWeight = FontWeights.SemiBold,
                    TextWrapping = TextWrapping.NoWrap,
                    MaxLines = 1,
                    Style = res.Caption,
                };
                secondaryLabel = new TextBlock
                {
                    TextWrapping = TextWrapping.NoWrap,
                    MaxLines = 1,
                    TextTrimming = TextTrimming.CharacterEllipsis,
                    Style = res.Metadata,
                };
                var secondRow = new Grid { ColumnSpacing = 6 };
                secondRow.ColumnDefinitions.Add(new ColumnDefinition { Width = GridLength.Auto });
                secondRow.ColumnDefinitions.Add(new ColumnDefinition { Width = new GridLength(1, GridUnitType.Star) });
                Grid.SetColumn(scoreLabel, 0);
                Grid.SetColumn(secondaryLabel, 1);
                secondRow.Children.Add(scoreLabel);
                secondRow.Children.Add(secondaryLabel);

                structuredStack = new StackPanel { Spacing = 1, Visibility = Visibility.Collapsed };
                structuredStack.Children.Add(primaryLabel);
                structuredStack.Children.Add(secondRow);

                var host = new Grid();
                host.Children.Add(wrappedLabel);
                host.Children.Add(structuredStack);
                inner = host;
            }
            else
            {
                inner = wrappedLabel;
            }

            Pill = new Border
            {
                Style = res.EvidenceAIPill,
                HorizontalAlignment = isTiles ? HorizontalAlignment.Stretch : HorizontalAlignment.Left,
                Visibility = Visibility.Collapsed,
                Child = inner,
            };
            appliedStyleKey = "EvidenceAIPillStyle";
        }

        public void Bind(bool isTiles, MediaCardResources res, string icon, string summary, string automationId, string styleKey)
        {
            if (appliedStyleKey != styleKey)
            {
                Pill.Style = res.EvidenceStyle(styleKey);
                appliedStyleKey = styleKey;
            }
            var normalized = summary.Replace("\r\n", "\n");
            var display = normalized.StartsWith(icon, StringComparison.Ordinal) ? normalized : $"{icon} {normalized}";
            lastSummary = summary;

            if (isTiles && structuredStack is not null && primaryLabel is not null && scoreLabel is not null && secondaryLabel is not null)
            {
                var (primary, score, secondary) = Protocol.FormatTileEvidence(icon, summary);
                if (score is not null || secondary is not null)
                {
                    wrappedLabel.Visibility = Visibility.Collapsed;
                    AutomationProperties.SetAutomationId(wrappedLabel, "");
                    structuredStack.Visibility = Visibility.Visible;
                    primaryLabel.Text = primary;
                    if (score is not null && secondary is not null)
                    {
                        scoreLabel.Text = score;
                        scoreLabel.Visibility = Visibility.Visible;
                        Grid.SetColumn(secondaryLabel, 1);
                        secondaryLabel.HorizontalAlignment = HorizontalAlignment.Right;
                        secondaryLabel.Text = secondary;
                        secondaryLabel.Visibility = Visibility.Visible;
                    }
                    else if (score is not null)
                    {
                        scoreLabel.Text = score;
                        scoreLabel.Visibility = Visibility.Visible;
                        secondaryLabel.Visibility = Visibility.Collapsed;
                    }
                    else
                    {
                        scoreLabel.Visibility = Visibility.Collapsed;
                        Grid.SetColumn(secondaryLabel, 0);
                        secondaryLabel.HorizontalAlignment = HorizontalAlignment.Left;
                        secondaryLabel.Text = secondary!;
                        secondaryLabel.Visibility = Visibility.Visible;
                    }
                    AutomationProperties.SetAutomationId(structuredStack, automationId);
                    AutomationProperties.SetName(structuredStack, display);
                    tooltipHost = structuredStack;
                }
                else
                {
                    structuredStack.Visibility = Visibility.Collapsed;
                    AutomationProperties.SetAutomationId(structuredStack, "");
                    wrappedLabel.Visibility = Visibility.Visible;
                    wrappedLabel.Text = primary;
                    AutomationProperties.SetAutomationId(wrappedLabel, automationId);
                    tooltipHost = wrappedLabel;
                }
            }
            else
            {
                wrappedLabel.Visibility = Visibility.Visible;
                wrappedLabel.Text = display;
                AutomationProperties.SetAutomationId(wrappedLabel, automationId);
                tooltipHost = wrappedLabel;
            }
            Pill.Visibility = Visibility.Visible;
        }

        public void BindToolTip()
        {
            if (lastSummary is null || Pill.Visibility != Visibility.Visible) return;
            ToolTipService.SetToolTip(Pill, lastSummary);
            if (tooltipHost is not null) ToolTipService.SetToolTip(tooltipHost, lastSummary);
        }

        public void ClearToolTip()
        {
            ToolTipService.SetToolTip(Pill, null);
            ToolTipService.SetToolTip(wrappedLabel, null);
            if (structuredStack is not null) ToolTipService.SetToolTip(structuredStack, null);
        }

        public void Hide(bool clearToolTips)
        {
            lastSummary = null;
            tooltipHost = null;
            Pill.Visibility = Visibility.Collapsed;
            wrappedLabel.Visibility = Visibility.Collapsed;
            AutomationProperties.SetAutomationId(wrappedLabel, "");
            if (structuredStack is not null)
            {
                structuredStack.Visibility = Visibility.Collapsed;
                AutomationProperties.SetAutomationId(structuredStack, "");
                AutomationProperties.SetName(structuredStack, "");
            }
            if (clearToolTips) ClearToolTip();
        }
    }

    public bool IsTiles { get; }
    public Grid Root { get; }
    public Image PreviewImage { get; }
    public Border ThumbPlate { get; }
    public Viewbox Placeholder { get; }
    public StackPanel TextPanel { get; }
    public TextBlock TitleText { get; }
    public StackPanel BadgeRow { get; }
    public TextBlock MetaBlock { get; }
    public TextBlock PreviewStatus { get; }
    public Button FavBtn { get; }
    public Button DetailsBtn { get; }
    public Button? OpenBtn { get; }

    public MediaRow? CurrentRow { get; private set; }
    public int CurrentOrdinal { get; private set; } = -1;
    public int RequestedEdge { get; set; }
    public long ThumbVersion { get; set; }
    public CancellationTokenSource? VisibleCts { get; set; }
    public long AppliedLayoutEpoch { get; set; } = -1;
    public bool TooltipsBound { get; private set; }
    public Action? RefreshThumbnail { get; set; }

    private readonly MediaCardResources res;
    private readonly SymbolIcon placeholderIcon;
    private readonly Border? kindOverlay;
    private readonly TextBlock? kindOverlayText;
    private readonly StackPanel quickActions;
    private readonly StackPanel? listMetaPanel;
    private readonly TextBlock? folderTb;
    private readonly TextBlock? fileDetailsTb;
    private readonly List<BadgeChipSlot> badgeChips = new(MaxPooledBadges);
    private readonly EvidencePillSlot[] evidencePills = new EvidencePillSlot[MaxPooledEvidence];
    private readonly int initialEvidenceCount = 2;
    private int createdEvidenceCount;

    private ListViewItem? attachedContainer;
    private Symbol? appliedSymbol = Symbol.Pictures;
    private bool? appliedFavoriteStyle;
    private bool pointerOver, cardFocused;
    private string? pendingTitleTooltip, pendingMetaTooltip, pendingFolderTooltip, pendingFileDetailsTooltip, pendingOpenTooltip;
    private bool pendingFavoriteTooltip;

    private readonly Func<MediaRow, string> formatShortMetadata;
    private readonly Func<MediaRow, string> formatFullMetadata;
    private readonly Func<MediaRow, string> formatFolderLabel;
    private readonly Func<long, string> shelfName;
    private readonly Func<int> kindIndex;
    private readonly Func<MediaRow, bool> canOpenMedia;
    private readonly Func<MediaRow, string> openTooltip;

    public MediaCardSlot(
        bool isTiles,
        MediaCardResources resources,
        PointerEventHandler pointerPressedHandler,
        Func<int, Task> onOpenPreview,
        Func<MediaRow, Task> onToggleFavorite,
        Func<MediaRow, Task> onOpenDetails,
        Func<MediaRow, Task> onOpenQuick,
        Func<MediaRow, string> formatShortMetadata,
        Func<MediaRow, string> formatFullMetadata,
        Func<MediaRow, string> formatFolderLabel,
        Func<long, string> shelfName,
        Func<int> kindIndex,
        Func<MediaRow, bool> canOpenMedia,
        Func<MediaRow, string> openTooltip)
    {
        IsTiles = isTiles;
        res = resources;
        this.formatShortMetadata = formatShortMetadata;
        this.formatFullMetadata = formatFullMetadata;
        this.formatFolderLabel = formatFolderLabel;
        this.shelfName = shelfName;
        this.kindIndex = kindIndex;
        this.canOpenMedia = canOpenMedia;
        this.openTooltip = openTooltip;

        Root = new Grid
        {
            Padding = isTiles ? new Thickness(7) : new Thickness(12, 8, 12, 8),
            ColumnSpacing = 12,
            RowSpacing = isTiles ? 6 : 8,
        };
        Root.AddHandler(UIElement.PointerPressedEvent, pointerPressedHandler, true);
        Root.SizeChanged += (_, _) => ConstrainCaption();
        Root.DoubleTapped += async (_, a) =>
        {
            a.Handled = true;
            if (CurrentRow is { } row) await onOpenPreview(row.Id);
        };

        PreviewImage = new Image { IsDoubleTapEnabled = true, Stretch = Stretch.Uniform, HorizontalAlignment = HorizontalAlignment.Center };
        PreviewImage.DoubleTapped += async (_, a) =>
        {
            a.Handled = true;
            if (CurrentRow is { } row) await onOpenPreview(row.Id);
        };

        ThumbPlate = new Border { Tag = "ThumbPlate", Style = res.ThumbPlate, HorizontalAlignment = HorizontalAlignment.Center };
        Canvas.SetZIndex(ThumbPlate, -1);

        placeholderIcon = new SymbolIcon(Symbol.Pictures) { Style = res.PlaceholderIcon };
        Placeholder = new Viewbox
        {
            Width = 32,
            Height = 32,
            HorizontalAlignment = HorizontalAlignment.Center,
            VerticalAlignment = VerticalAlignment.Center,
            IsHitTestVisible = false,
            Child = placeholderIcon,
        };

        TitleText = new TextBlock
        {
            TextWrapping = TextWrapping.NoWrap,
            MaxLines = 1,
            TextTrimming = TextTrimming.CharacterEllipsis,
            Style = res.Title,
        };
        BadgeRow = new StackPanel
        {
            Tag = "ItemBadges",
            Orientation = Orientation.Horizontal,
            Spacing = 4,
            Visibility = Visibility.Collapsed,
        };
        for (var i = 0; i < 4; i++)
        {
            var chip = new BadgeChipSlot(res);
            badgeChips.Add(chip);
            BadgeRow.Children.Add(chip.Container);
        }

        MetaBlock = new TextBlock
        {
            Tag = "ItemMeta",
            TextWrapping = TextWrapping.Wrap,
            MaxLines = isTiles ? 1 : 3,
            TextTrimming = TextTrimming.CharacterEllipsis,
            Style = res.Metadata,
            Visibility = Visibility.Collapsed,
        };
        PreviewStatus = new TextBlock
        {
            Text = "",
            Visibility = Visibility.Collapsed,
            Style = res.Metadata,
        };

        TextPanel = new StackPanel
        {
            Spacing = 4,
            VerticalAlignment = isTiles ? VerticalAlignment.Top : VerticalAlignment.Center,
            MaxWidth = 1,
        };
        TextPanel.Children.Add(TitleText);
        TextPanel.Children.Add(BadgeRow);
        TextPanel.Children.Add(MetaBlock);

        for (var i = 0; i < initialEvidenceCount; i++)
        {
            var slot = new EvidencePillSlot(isTiles, res);
            evidencePills[i] = slot;
            TextPanel.Children.Add(slot.Pill);
        }
        createdEvidenceCount = initialEvidenceCount;
        TextPanel.Children.Add(PreviewStatus);

        if (isTiles)
        {
            Root.RowDefinitions.Add(new RowDefinition { Height = GridLength.Auto });
            Root.RowDefinitions.Add(new RowDefinition { Height = GridLength.Auto });
            Grid.SetRow(TextPanel, 1);
        }
        else
        {
            Root.ColumnDefinitions.Add(new ColumnDefinition { Width = GridLength.Auto });
            Root.ColumnDefinitions.Add(new ColumnDefinition { Width = new GridLength(1, GridUnitType.Star) });
            Root.ColumnDefinitions.Add(new ColumnDefinition { Width = GridLength.Auto });
            Root.ColumnDefinitions.Add(new ColumnDefinition { Width = GridLength.Auto });
            Grid.SetColumn(TextPanel, 1);
        }

        Root.Children.Add(PreviewImage);
        Root.Children.Add(ThumbPlate);
        Root.Children.Add(Placeholder);
        Root.Children.Add(TextPanel);

        if (isTiles)
        {
            kindOverlayText = new TextBlock
            {
                MaxLines = 1,
                TextWrapping = TextWrapping.NoWrap,
                Style = res.Metadata,
                Foreground = res.WhiteBrush,
            };
            kindOverlay = new Border
            {
                Style = res.KindOverlayPill,
                RequestedTheme = ElementTheme.Dark,
                Child = kindOverlayText,
                Visibility = Visibility.Collapsed,
            };
            Grid.SetRow(kindOverlay, 0);
            Canvas.SetZIndex(kindOverlay, 2);
            Root.Children.Add(kindOverlay);

            quickActions = new StackPanel
            {
                Tag = "ItemQuickActions",
                Style = res.TileQuickActionPill,
                RequestedTheme = ElementTheme.Dark,
                Visibility = Visibility.Collapsed,
            };
            Grid.SetRow(quickActions, 0);
            Canvas.SetZIndex(quickActions, 2);
            quickActions.DoubleTapped += (_, a) => a.Handled = true;

            FavBtn = new Button { Padding = new Thickness(6, 2, 6, 2), MinWidth = 28, MinHeight = 28, Style = res.UnselectedSegment, Content = "☆" };
            DetailsBtn = new Button { Content = "✎", Padding = new Thickness(6, 2, 6, 2), MinWidth = 28, MinHeight = 28, Style = res.UnselectedSegment, Visibility = Visibility.Collapsed };
            ToolTipService.SetToolTip(DetailsBtn, "詳細・タグを編集");
            FavBtn.Click += async (_, _) => { if (CurrentRow is { } row) await onToggleFavorite(row); };
            DetailsBtn.Click += async (_, _) => { if (CurrentRow is { } row) await onOpenDetails(row); };
            quickActions.Children.Add(FavBtn);
            quickActions.Children.Add(DetailsBtn);
            Root.Children.Add(quickActions);

            Root.PointerEntered += (_, _) => { pointerOver = true; UpdateQuickActions(); EnsureTooltips(); };
            Root.PointerExited += (_, _) => { pointerOver = false; UpdateQuickActions(); };
        }
        else
        {
            folderTb = new TextBlock
            {
                MaxLines = 1,
                TextWrapping = TextWrapping.NoWrap,
                TextTrimming = TextTrimming.CharacterEllipsis,
                HorizontalAlignment = HorizontalAlignment.Right,
                Style = res.Metadata,
                Visibility = Visibility.Collapsed,
            };
            fileDetailsTb = new TextBlock
            {
                MaxLines = 1,
                TextWrapping = TextWrapping.NoWrap,
                TextTrimming = TextTrimming.CharacterEllipsis,
                HorizontalAlignment = HorizontalAlignment.Right,
                Style = res.Metadata,
                Visibility = Visibility.Collapsed,
            };
            listMetaPanel = new StackPanel
            {
                Tag = "ItemListMeta",
                Spacing = 2,
                VerticalAlignment = VerticalAlignment.Center,
                HorizontalAlignment = HorizontalAlignment.Right,
                MaxWidth = 260,
                Margin = new Thickness(8, 0, 8, 0),
                Visibility = Visibility.Collapsed,
            };
            listMetaPanel.Children.Add(folderTb);
            listMetaPanel.Children.Add(fileDetailsTb);
            Grid.SetColumn(listMetaPanel, 2);
            Root.Children.Add(listMetaPanel);

            quickActions = new StackPanel
            {
                Tag = "ItemQuickActions",
                Orientation = Orientation.Horizontal,
                Spacing = 4,
                VerticalAlignment = VerticalAlignment.Center,
            };
            quickActions.DoubleTapped += (_, a) => a.Handled = true;
            FavBtn = new Button { Padding = new Thickness(8, 4, 8, 4), MinWidth = 34, Style = res.UnselectedSegment, Content = "☆" };
            DetailsBtn = new Button { Content = "✎", Padding = new Thickness(8, 4, 8, 4), MinWidth = 34, Style = res.UnselectedSegment };
            OpenBtn = new Button { Content = "▶", Padding = new Thickness(8, 4, 8, 4), MinWidth = 34, Style = res.UnselectedSegment, Visibility = Visibility.Collapsed };
            ToolTipService.SetToolTip(DetailsBtn, "詳細・タグを編集");
            FavBtn.Click += async (_, _) => { if (CurrentRow is { } row) await onToggleFavorite(row); };
            DetailsBtn.Click += async (_, _) => { if (CurrentRow is { } row) await onOpenDetails(row); };
            OpenBtn.Click += async (_, _) => { if (CurrentRow is { } row) await onOpenQuick(row); };
            quickActions.Children.Add(FavBtn);
            quickActions.Children.Add(DetailsBtn);
            quickActions.Children.Add(OpenBtn);
            Grid.SetColumn(quickActions, 3);
            Root.Children.Add(quickActions);

            Root.PointerEntered += (_, _) => EnsureTooltips();
        }
        appliedFavoriteStyle = false;
    }

    public void AttachContainer(ListViewItem item)
    {
        if (ReferenceEquals(attachedContainer, item)) return;
        DetachContainer();
        attachedContainer = item;
        if (IsTiles)
        {
            item.GotFocus += Container_GotFocus;
            item.LostFocus += Container_LostFocus;
        }
    }

    public void DetachContainer()
    {
        if (attachedContainer is null) return;
        if (IsTiles)
        {
            attachedContainer.GotFocus -= Container_GotFocus;
            attachedContainer.LostFocus -= Container_LostFocus;
        }
        attachedContainer = null;
    }

    private void Container_GotFocus(object sender, RoutedEventArgs e)
    {
        cardFocused = true;
        UpdateQuickActions();
    }

    private void Container_LostFocus(object sender, RoutedEventArgs e)
    {
        cardFocused = false;
        UpdateQuickActions();
    }

    public void ConstrainCaption()
    {
        if (IsTiles)
        {
            if (PreviewImage.Width > 0) TextPanel.MaxWidth = Math.Max(1, PreviewImage.Width);
            return;
        }
        if (listMetaPanel is not null)
        {
            var cw = Root.ActualWidth;
            var narrow = cw > 0 && cw < 560;
            listMetaPanel.Visibility = narrow || (folderTb?.Visibility != Visibility.Visible && fileDetailsTb?.Visibility != Visibility.Visible)
                ? Visibility.Collapsed
                : Visibility.Visible;
            if (cw > 0) listMetaPanel.MaxWidth = Math.Clamp(cw * 0.28, 160, 280);
        }
        var available = Root.ColumnDefinitions.Count > 1
            ? Root.ColumnDefinitions[1].ActualWidth
            : Root.ActualWidth - Root.Padding.Left - Root.Padding.Right;
        if (double.IsFinite(available) && available > 0)
            TextPanel.MaxWidth = Math.Max(1, available);
    }

    public void ApplySizing(double cardWidth, double imgWidth, double imgHeight, double captionMinHeight, long layoutEpoch)
    {
        if (attachedContainer is not null) attachedContainer.Width = cardWidth;
        PreviewImage.Width = imgWidth;
        PreviewImage.Height = imgHeight;
        ThumbPlate.Width = imgWidth;
        ThumbPlate.Height = imgHeight;
        TextPanel.MinHeight = IsTiles ? captionMinHeight : 0;
        if (IsTiles) TextPanel.MaxWidth = Math.Max(1, imgWidth);
        else ConstrainCaption();
        AppliedLayoutEpoch = layoutEpoch;
    }

    public void CancelThumbnailRequest()
    {
        ++ThumbVersion;
        RequestedEdge = 0;
        VisibleCts?.Cancel();
        VisibleCts?.Dispose();
        VisibleCts = null;
    }

    public void UnloadImage()
    {
        CancelThumbnailRequest();
        PreviewImage.Source = null;
        Placeholder.Visibility = Visibility.Visible;
    }

    public void ResetForRecycle()
    {
        var wasTooltipsBound = TooltipsBound;
        CancelThumbnailRequest();
        PreviewImage.Source = null;
        PreviewImage.Tag = null;
        Placeholder.Visibility = Visibility.Visible;
        CurrentRow = null;
        CurrentOrdinal = -1;
        TooltipsBound = false;
        pointerOver = false;
        cardFocused = false;
        pendingTitleTooltip = pendingMetaTooltip = pendingFolderTooltip = pendingFileDetailsTooltip = pendingOpenTooltip = null;
        if (IsTiles) quickActions.Visibility = Visibility.Collapsed;
        if (wasTooltipsBound) ClearRowTooltips();
    }

    public void BindSkeleton(int ordinal)
    {
        var wasTooltipsBound = TooltipsBound;
        CancelThumbnailRequest();
        PreviewImage.Source = null;
        PreviewImage.Tag = null;
        Placeholder.Visibility = Visibility.Visible;
        if (appliedSymbol != Symbol.Pictures)
        {
            placeholderIcon.Symbol = Symbol.Pictures;
            appliedSymbol = Symbol.Pictures;
        }
        CurrentRow = null;
        CurrentOrdinal = ordinal;
        TooltipsBound = false;
        pointerOver = false;
        cardFocused = false;
        pendingTitleTooltip = pendingMetaTooltip = pendingFolderTooltip = pendingFileDetailsTooltip = pendingOpenTooltip = null;

        TitleText.Text = "";
        BadgeRow.Visibility = Visibility.Collapsed;
        for (var i = 0; i < badgeChips.Count; i++) badgeChips[i].Container.Visibility = Visibility.Collapsed;
        MetaBlock.Visibility = Visibility.Collapsed;
        for (var i = 0; i < createdEvidenceCount; i++) evidencePills[i].Hide(wasTooltipsBound);
        PreviewStatus.Text = "";
        PreviewStatus.Visibility = Visibility.Collapsed;
        if (kindOverlay is not null) kindOverlay.Visibility = Visibility.Collapsed;
        if (listMetaPanel is not null) listMetaPanel.Visibility = Visibility.Collapsed;
        if (IsTiles) quickActions.Visibility = Visibility.Collapsed;
        else
        {
            FavBtn.Visibility = Visibility.Collapsed;
            DetailsBtn.Visibility = Visibility.Collapsed;
            if (OpenBtn is not null) OpenBtn.Visibility = Visibility.Collapsed;
        }
        if (wasTooltipsBound) ClearRowTooltips();
    }

    public void BindRow(MediaRow row, int ordinal, string kindBadgeText, string detailKindLabel, string fileDetailsText)
    {
        var wasTooltipsBound = TooltipsBound;
        TooltipsBound = false;
        CurrentRow = row;
        CurrentOrdinal = ordinal;
        PreviewImage.Tag = row.Id;
        AutomationProperties.SetAutomationId(PreviewImage, $"Preview{row.Id}");
        AutomationProperties.SetName(PreviewImage, row.Title + "のサムネイル");

        var symbol = row.Kind switch
        {
            "audio" => Symbol.Audio,
            "video" => Symbol.Video,
            "book" or "archive" => Symbol.Library,
            "image" => Symbol.Pictures,
            _ => Symbol.Document,
        };
        if (appliedSymbol != symbol)
        {
            placeholderIcon.Symbol = symbol;
            appliedSymbol = symbol;
        }
        AutomationProperties.SetAutomationId(Placeholder, $"PreviewPlaceholder{row.Id}");
        AutomationProperties.SetName(Placeholder, kindBadgeText);

        TitleText.Text = (row.Favorite ? "★ " : "") + row.Title;
        AutomationProperties.SetAutomationId(TitleText, $"ItemTitle{row.Id}");
        AutomationProperties.SetName(TitleText, row.Title);

        BindBadges(row, kindBadgeText);
        AutomationProperties.SetAutomationId(BadgeRow, $"ItemBadges{row.Id}");

        var metadata = formatShortMetadata(row);
        MetaBlock.Text = metadata;
        MetaBlock.Visibility = string.IsNullOrWhiteSpace(metadata) ? Visibility.Collapsed : Visibility.Visible;
        AutomationProperties.SetAutomationId(MetaBlock, $"ItemMeta{row.Id}");

        BindEvidence(row, wasTooltipsBound);

        PreviewStatus.Text = "";
        PreviewStatus.Visibility = Visibility.Collapsed;
        AutomationProperties.SetAutomationId(PreviewStatus, $"PreviewStatus{row.Id}");

        var canOpen = canOpenMedia(row);
        pendingTitleTooltip = row.Title;
        pendingMetaTooltip = null;
        pendingOpenTooltip = canOpen ? openTooltip(row) : null;
        pendingFavoriteTooltip = row.Favorite;

        if (IsTiles)
        {
            if (kindOverlay is not null && kindOverlayText is not null)
            {
                if (row.Kind != "image")
                {
                    kindOverlayText.Text = detailKindLabel;
                    AutomationProperties.SetAutomationId(kindOverlayText, $"ItemKindBadge{row.Id}");
                    kindOverlay.Visibility = Visibility.Visible;
                }
                else
                {
                    kindOverlay.Visibility = Visibility.Collapsed;
                    AutomationProperties.SetAutomationId(kindOverlayText, "");
                }
            }
            UpdateFavoriteButton(row);
            AutomationProperties.SetAutomationId(FavBtn, $"ItemFavToggle{row.Id}");
            AutomationProperties.SetAutomationId(DetailsBtn, $"ItemDetailsQuick{row.Id}");
            AutomationProperties.SetName(DetailsBtn, $"{row.Title}の詳細を開く");
            FavBtn.Visibility = Visibility.Visible;
            UpdateQuickActions();
        }
        else
        {
            if (folderTb is not null && fileDetailsTb is not null && listMetaPanel is not null)
            {
                var folderLabel = formatFolderLabel(row);
                var hasFolder = !string.IsNullOrEmpty(folderLabel);
                var hasDetails = !string.IsNullOrEmpty(fileDetailsText);
                folderTb.Text = folderLabel;
                folderTb.Visibility = hasFolder ? Visibility.Visible : Visibility.Collapsed;
                AutomationProperties.SetAutomationId(folderTb, hasFolder ? $"ItemFolderMeta{row.Id}" : "");
                fileDetailsTb.Text = fileDetailsText;
                fileDetailsTb.Visibility = hasDetails ? Visibility.Visible : Visibility.Collapsed;
                AutomationProperties.SetAutomationId(fileDetailsTb, hasDetails ? $"ItemFileMeta{row.Id}" : "");
                pendingFolderTooltip = hasFolder ? row.LocationLabel : null;
                pendingFileDetailsTooltip = hasDetails ? fileDetailsText : null;
                ConstrainCaption();
            }
            UpdateFavoriteButton(row);
            AutomationProperties.SetAutomationId(FavBtn, $"ItemFavToggle{row.Id}");
            AutomationProperties.SetAutomationId(DetailsBtn, $"ItemDetailsQuick{row.Id}");
            AutomationProperties.SetName(DetailsBtn, $"{row.Title}の詳細を開く");
            FavBtn.Visibility = Visibility.Visible;
            DetailsBtn.Visibility = Visibility.Visible;
            if (OpenBtn is not null)
            {
                if (canOpen)
                {
                    AutomationProperties.SetAutomationId(OpenBtn, $"ItemOpenQuick{row.Id}");
                    AutomationProperties.SetName(OpenBtn, $"{row.Title}を開く");
                    OpenBtn.Visibility = Visibility.Visible;
                }
                else
                {
                    OpenBtn.Visibility = Visibility.Collapsed;
                }
            }
        }

        if (wasTooltipsBound) ClearRowTooltips();
    }

    public void ApplyFavoriteVisuals(MediaRow row, string kindBadgeText)
    {
        if (CurrentRow?.Id != row.Id) return;
        TitleText.Text = (row.Favorite ? "★ " : "") + row.Title;
        BindBadges(row, kindBadgeText);
        var metaText = formatShortMetadata(row);
        MetaBlock.Text = metaText;
        MetaBlock.Visibility = string.IsNullOrWhiteSpace(metaText) ? Visibility.Collapsed : Visibility.Visible;
        UpdateFavoriteButton(row);
        UpdateQuickActions();
        pendingFavoriteTooltip = row.Favorite;
        if (TooltipsBound)
        {
            var full = formatFullMetadata(row);
            ToolTipService.SetToolTip(BadgeRow, full);
            ToolTipService.SetToolTip(MetaBlock, full);
            ToolTipService.SetToolTip(FavBtn, row.Favorite ? "お気に入りを解除" : "お気に入りに追加");
        }
    }

    public void RefreshOpenTooltip()
    {
        if (CurrentRow is not { } row) return;
        pendingOpenTooltip = canOpenMedia(row) ? openTooltip(row) : null;
        if (TooltipsBound)
        {
            ToolTipService.SetToolTip(PreviewImage, pendingOpenTooltip);
            if (OpenBtn is not null) ToolTipService.SetToolTip(OpenBtn, pendingOpenTooltip);
        }
    }

    public void UpdateQuickActions()
    {
        if (!IsTiles || CurrentRow is not { } row) return;
        var activeOverlay = pointerOver || cardFocused;
        DetailsBtn.Visibility = activeOverlay ? Visibility.Visible : Visibility.Collapsed;
        quickActions.Visibility = (activeOverlay || row.Favorite) ? Visibility.Visible : Visibility.Collapsed;
    }

    private void UpdateFavoriteButton(MediaRow row)
    {
        FavBtn.Content = row.Favorite ? "★" : "☆";
        if (appliedFavoriteStyle != row.Favorite)
        {
            FavBtn.Style = row.Favorite ? res.CardFavoriteActive : res.UnselectedSegment;
            appliedFavoriteStyle = row.Favorite;
        }
        AutomationProperties.SetName(FavBtn, $"{row.Title}：{(row.Favorite ? "お気に入りを解除" : "お気に入りに追加")}");
    }

    private void BindBadges(MediaRow row, string kindText)
    {
        var maxBadgeTextWidth = IsTiles ? 96.0 : 140.0;
        var shelves = row.ShelfIds.Length > 0
            ? row.ShelfIds.Select(shelfName).Where(name => !string.IsNullOrWhiteSpace(name)).ToArray()
            : string.IsNullOrWhiteSpace(row.Shelf) ? [] : new[] { row.Shelf };

        var count = 0;
        void AddBadge(string text, string? automationId)
        {
            if (count >= MaxPooledBadges) return;
            while (badgeChips.Count <= count)
            {
                var chip = new BadgeChipSlot(res);
                badgeChips.Add(chip);
                BadgeRow.Children.Add(chip.Container);
            }
            var target = badgeChips[count++];
            target.Label.Text = text;
            target.Label.MaxWidth = maxBadgeTextWidth;
            AutomationProperties.SetAutomationId(target.Label, automationId ?? "");
            target.Container.Visibility = Visibility.Visible;
        }

        if (!IsTiles || (row.Kind == "image" && kindIndex() is not (0 or 1)))
            AddBadge(kindText, $"ItemKindBadge{row.Id}");
        if (shelves.Length > 0)
            AddBadge("📚 " + ShelfProtocol.SummarizeNames(shelves, maxVisible: 1), $"ItemShelfBadge{row.Id}");
        if (row.Tags.Length > 0)
        {
            if (IsTiles)
            {
                var suffix = row.Tags.Length > 1 ? $" +{row.Tags.Length - 1}" : "";
                AddBadge("#" + row.Tags[0] + suffix, $"ItemTagBadge{row.Id}");
            }
            else
            {
                var visibleCount = Math.Min(row.Tags.Length, 5);
                for (var i = 0; i < visibleCount; i++)
                    AddBadge("#" + row.Tags[i], i == 0 ? $"ItemTagBadge{row.Id}" : $"ItemTagBadge{row.Id}_{i}");
                if (row.Tags.Length > 5)
                    AddBadge($"+{row.Tags.Length - 5}", null);
            }
        }

        for (var i = count; i < badgeChips.Count; i++)
        {
            badgeChips[i].Container.Visibility = Visibility.Collapsed;
            AutomationProperties.SetAutomationId(badgeChips[i].Label, "");
        }

        if (count > 0)
        {
            var joined = badgeChips[0].Label.Text;
            for (var i = 1; i < count; i++) joined += " · " + badgeChips[i].Label.Text;
            AutomationProperties.SetName(BadgeRow, joined);
            BadgeRow.Visibility = Visibility.Visible;
        }
        else
        {
            AutomationProperties.SetName(BadgeRow, "");
            BadgeRow.Visibility = Visibility.Collapsed;
        }
    }

    private EvidencePillSlot GetOrCreateEvidence(int index)
    {
        if (evidencePills[index] is { } existing) return existing;
        var created = new EvidencePillSlot(IsTiles, res);
        evidencePills[index] = created;
        var insertAt = TextPanel.Children.IndexOf(PreviewStatus);
        TextPanel.Children.Insert(insertAt >= 0 ? insertAt : TextPanel.Children.Count, created.Pill);
        createdEvidenceCount = Math.Max(createdEvidenceCount, index + 1);
        return created;
    }

    private void BindEvidence(MediaRow row, bool clearToolTips)
    {
        var count = 0;
        void Add(string icon, string summary, string automationId, string styleKey)
        {
            if (count >= MaxPooledEvidence) return;
            GetOrCreateEvidence(count++).Bind(IsTiles, res, icon, summary, automationId, styleKey);
        }

        if (row.AIEvidence.Length > 0)
            Add(row.Kind == "video" ? "🎬" : row.Kind == "audio" ? "🎵" : "✨", row.AIEvidence, $"AIEvidence{row.Id}", "EvidenceAIPillStyle");
        if (row.Proposal is ProposalMatch proposal)
            Add("🎬", proposal.Summary, $"ProposalEvidence{row.Id}", "EvidenceAIPillStyle");
        if (row.AIPage is AIPageMatch aiPage)
            Add("📄", aiPage.Summary, $"AIPageEvidence{row.Id}", "EvidenceAIPillStyle");
        if (row.PageText is PageTextMatch pageText)
            Add("📄", pageText.Summary, $"PageTextEvidence{row.Id}", "EvidencePagePillStyle");
        if (row.Evidence is { AllDirect: false })
            Add("💬", Protocol.DescribeEvidence(row.Evidence), $"SearchEvidence{row.Id}", "EvidenceWordPillStyle");

        for (var i = count; i < createdEvidenceCount; i++)
            evidencePills[i]?.Hide(clearToolTips);
    }

    private void EnsureTooltips()
    {
        if (TooltipsBound || CurrentRow is not { } row) return;
        TooltipsBound = true;
        ToolTipService.SetToolTip(PreviewImage, pendingOpenTooltip);
        ToolTipService.SetToolTip(TitleText, pendingTitleTooltip);
        pendingMetaTooltip ??= formatFullMetadata(row);
        ToolTipService.SetToolTip(BadgeRow, pendingMetaTooltip);
        ToolTipService.SetToolTip(MetaBlock, pendingMetaTooltip);
        ToolTipService.SetToolTip(FavBtn, pendingFavoriteTooltip ? "お気に入りを解除" : "お気に入りに追加");
        if (folderTb is not null) ToolTipService.SetToolTip(folderTb, pendingFolderTooltip);
        if (fileDetailsTb is not null) ToolTipService.SetToolTip(fileDetailsTb, pendingFileDetailsTooltip);
        if (OpenBtn is not null) ToolTipService.SetToolTip(OpenBtn, pendingOpenTooltip);
        for (var i = 0; i < createdEvidenceCount; i++)
            evidencePills[i]?.BindToolTip();
    }

    private void ClearRowTooltips()
    {
        ToolTipService.SetToolTip(PreviewImage, null);
        ToolTipService.SetToolTip(TitleText, null);
        ToolTipService.SetToolTip(BadgeRow, null);
        ToolTipService.SetToolTip(MetaBlock, null);
        ToolTipService.SetToolTip(FavBtn, null);
        if (folderTb is not null) ToolTipService.SetToolTip(folderTb, null);
        if (fileDetailsTb is not null) ToolTipService.SetToolTip(fileDetailsTb, null);
        if (OpenBtn is not null) ToolTipService.SetToolTip(OpenBtn, null);
        for (var i = 0; i < createdEvidenceCount; i++)
            evidencePills[i]?.ClearToolTip();
    }
}
