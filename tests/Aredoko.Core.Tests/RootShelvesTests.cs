using Aredoko.Core;
internal static class RootShelvesTests
{
    public static void Run(Action<bool,string> check)
    {
        var root=new RegisteredRootRow(1,"fixture",true,true,"A",Array.Empty<string>(),ShelfIds:new long[]{1,2});
        var draft=new FolderSettingsDraft(new[]{root});
        check(!draft.IsDirty&&draft.ShelfIdsToSave!.SequenceEqual(new long[]{1,2}),"root draft starts clean with all initial memberships");
        draft.SelectShelfIds(new long[]{2,1});check(!draft.IsDirty,"root membership order does not mark draft dirty");
        draft.FillUnset=true;check(draft.IsShelfChanged,"same initial shelves can explicitly fill unset items");draft.FillUnset=false;
        draft.ExclusionsText="cache";draft.SelectShelfIds(new long[]{2});
        check(draft.IsDirty&&draft.IsExclusionsChanged&&draft.ResolveShelfToSave() is null,"root ID selection retains separate exclusions draft and avoids scalar save");
        draft.FillUnset=true;draft.MarkExclusionsSaved("cache");
        check(!draft.IsExclusionsChanged&&draft.IsShelfChanged&&draft.IsDirty&&draft.FillUnset&&draft.ShelfIdsToSave!.SequenceEqual(new long[]{2}),"saving exclusions preserves pending multiple shelf selection and fill option");
        draft.ExclusionsText="cache, temp";draft.MarkExclusionsSaved("cache");
        check(draft.IsExclusionsChanged,"marking submitted exclusions saved leaves later edits dirty");
        draft.ClearShelfIdSelection();draft.ShelfMode=BatchShelfMode.NewShelf;draft.NewShelfName="new shelf";draft.MarkExclusionsSaved(draft.ExclusionsText);
        check(draft.IsShelfChanged&&draft.NewShelfName=="new shelf"&&draft.FillUnset&&!draft.IsExclusionsChanged,"saving exclusions preserves a pending new shelf and fill option");
        var batch=new FolderSettingsDraft(new[]{root,root with{Id=2,ShelfIds=new long[]{1,3}}});
        check(batch.Summary.IsMixed&&!batch.IsShelfChanged,"same primary name with different secondary shelves is a mixed batch");
        batch.SelectShelfIds(Array.Empty<long>());check(batch.IsShelfChanged&&batch.ShelfIdsToSave!.Count==0,"explicit empty selection clears memberships, distinct from keep");
        draft=new FolderSettingsDraft(new[]{root});draft.ClearShelfIdSelection();draft.ShelfMode=BatchShelfMode.ExistingShelf;draft.SelectedExistingShelf="A";
        check(draft.IsShelfChanged,"choosing one current primary shelf deliberately replaces a previous multiple selection");
    }
}
