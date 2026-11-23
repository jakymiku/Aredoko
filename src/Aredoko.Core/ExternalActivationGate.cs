namespace Aredoko.Core;

// Pointer double-click fallback and DoubleTapped can describe the same gesture.
// Keep one shell launch per item/gesture without delaying or blocking the UI.
public sealed class ExternalActivationGate
{
    private int item;
    private long tick=long.MinValue;
    public bool TryActivate(int itemId,long now,int doubleClickMilliseconds)
    {
        if(itemId<1||now<0||doubleClickMilliseconds<1)throw new ArgumentOutOfRangeException();
        if(item==itemId&&now>=tick&&now-tick<=doubleClickMilliseconds)return false;
        item=itemId;tick=now;return true;
    }
}
