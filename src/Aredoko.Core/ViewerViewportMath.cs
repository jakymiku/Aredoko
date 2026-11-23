namespace Aredoko.Core;

public static class ViewerViewportMath
{
    // Canvas coordinates, including centered letterboxing, stay under the same
    // viewport center. All units here are DIPs; DPI is handled by the image fit.
    public static double ZoomOffset(double offset,double viewport,double oldZoom,double newZoom)
    {
        if(!double.IsFinite(offset)||!double.IsFinite(viewport)||!double.IsFinite(oldZoom)||!double.IsFinite(newZoom)||viewport<=0||oldZoom<=0||newZoom<=0)
            throw new ArgumentOutOfRangeException(nameof(viewport));
        return Math.Clamp((offset+viewport/2)*newZoom/oldZoom-viewport/2,0,Math.Max(0,viewport*(newZoom-1)));
    }
}
