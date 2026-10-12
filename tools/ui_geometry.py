"""Bounds checks for the native AI settings test, not product layout."""


def resource_control_visible(title, summary, item):
    """Reject clipped UIA fragments between the title and fixed index row.

    WinUI reports the clipped rectangle: captured release feedback had height
    1 despite IsOffscreen=False. A full single text line needs 19px in this
    96-DPI test; native buttons/ComboBoxes need at least 32px. This guard is
    not a replacement for reviewing screenshots or testing other DPI values.
    """
    if not title or not summary or not item:
        return False
    minimum_height = 19 if item.get('type') == 'Text' else 32
    return (item['height'] >= minimum_height and item['width'] > 0
            and not item.get('isOffscreen')
            and item['y'] >= title['y'] + title['height'] + 8
            and item['y'] + item['height'] <= summary['y'] - 12)
