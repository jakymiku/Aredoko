// Pure editor snapshot used by the WinUI comparison UI to distinguish genuine
// user edits from delayed TextChanged/Checked events raised during item selection.
namespace AredokoWinUiBench;

internal readonly record struct EditorState(
    string Tags,
    string Shelf,
    bool Favorite,
    bool Reviewed)
{
    public static bool IsDirty(EditorState saved, EditorState current) => saved != current;
}
