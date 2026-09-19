"""Small dependency-free SVG icon set used by the Oluso Streamlit dashboard."""

from __future__ import annotations

import html

_PATHS: dict[str, str] = {
    "logo": '<circle cx="12" cy="12" r="8.8"/><circle cx="12" cy="12" r="5.8"/><path d="M12 1.8v2.1M12 20.1v2.1M1.8 12h2.1M20.1 12h2.1"/>',
    "home": '<path d="m3 11 9-7 9 7"/><path d="M5.5 10.5V20h13v-9.5"/><path d="M9.5 20v-6h5v6"/>',
    "activity": '<path d="M3 12h4l2.2-6 4.1 12 2.1-6H21"/>',
    "user": '<circle cx="12" cy="8" r="3.2"/><path d="M5 20c.8-4 3.2-6 7-6s6.2 2 7 6"/>',
    "mesh": '<circle cx="5" cy="12" r="2.2"/><circle cx="12" cy="5" r="2.2"/><circle cx="19" cy="12" r="2.2"/><path d="m6.6 10.4 3.8-3.8M13.6 6.6l3.8 3.8M7.2 12h9.6"/>',
    "terminal": '<rect x="3" y="4" width="18" height="13" rx="2"/><path d="M8 21h8M12 17v4M7 9l2 2-2 2M11 13h4"/>',
    "shield": '<path d="M12 2.5 20 6v5.5c0 5.1-3.2 8.4-8 10-4.8-1.6-8-4.9-8-10V6l8-3.5Z"/><path d="m8.5 12 2.2 2.2 4.8-5"/>',
    "bolt": '<path d="M13 2 5 13h6l-1 9 9-12h-6V2Z"/>',
    "file": '<path d="M6 2.5h8l4 4V21H6Z"/><path d="M14 2.5v4h4M9 11h6M9 15h6"/>',
    "search": '<circle cx="10.5" cy="10.5" r="6"/><path d="m15 15 5 5"/>',
    "bell": '<path d="M6.5 16h11l-1.5-2v-4a4 4 0 0 0-8 0v4l-1.5 2Z"/><path d="M10 19h4"/>',
    "plus": '<path d="M12 5v14M5 12h14"/>',
    "database": '<ellipse cx="12" cy="5.5" rx="7" ry="3"/><path d="M5 5.5v6c0 1.7 3.1 3 7 3s7-1.3 7-3v-6M5 11.5v6c0 1.7 3.1 3 7 3s7-1.3 7-3v-6"/>',
    "check": '<circle cx="12" cy="12" r="9"/><path d="m8 12 2.6 2.6L16.5 9"/>',
    "warning": '<path d="M12 3 2.8 20h18.4L12 3Z"/><path d="M12 9v4.5M12 17h.01"/>',
    "brain": '<path d="M9 4.5a3 3 0 0 0-4.5 2.6A3.2 3.2 0 0 0 4 13a3 3 0 0 0 2.5 4.8A3 3 0 0 0 12 19V6a2.5 2.5 0 0 0-3-1.5Z"/><path d="M15 4.5a3 3 0 0 1 4.5 2.6A3.2 3.2 0 0 1 20 13a3 3 0 0 1-2.5 4.8A3 3 0 0 1 12 19V6a2.5 2.5 0 0 1 3-1.5ZM7.5 9.5H12M16.5 9.5H12M8.5 14H12M15.5 14H12"/>',
    "wave": '<path d="M3 12h3l2-6 4 12 3-10 2 4h4"/>',
    "clock": '<circle cx="12" cy="12" r="9"/><path d="M12 7v5l3.5 2"/>',
    "coverage": '<path d="M6 2.5h8l4 4V21H6Z"/><path d="M14 2.5v4h4M9 11h6M9 15h4"/>',
    "calendar": '<rect x="3.5" y="5" width="17" height="15" rx="2"/><path d="M7 3v4M17 3v4M3.5 9h17M7 13h2M11 13h2M15 13h2M7 16h2M11 16h2"/>',
    "recipient": '<circle cx="9" cy="8" r="3"/><path d="M3.5 20c.7-4 2.5-6 5.5-6 2.1 0 3.7 1 4.7 2.8M16 9h5M18.5 6.5V11.5"/>',
    "sim": '<rect x="6" y="3" width="12" height="18" rx="2"/><path d="M9 7h6v4H9zM10 15h4"/>',
    "recovery": '<path d="M5 8V4m0 0h4M5 4l4 4"/><path d="M6.5 16.5A7 7 0 1 0 5 8"/>',
    "drain": '<ellipse cx="12" cy="6" rx="7" ry="3"/><path d="M5 6v5c0 1.7 3.1 3 7 3s7-1.3 7-3V6M12 14v7M9.5 18.5 12 21l2.5-2.5"/>',
    "grid": '<rect x="4" y="4" width="6" height="6"/><rect x="14" y="4" width="6" height="6"/><rect x="4" y="14" width="6" height="6"/><rect x="14" y="14" width="6" height="6"/>',
    "lock": '<rect x="5" y="10" width="14" height="10" rx="2"/><path d="M8 10V7a4 4 0 0 1 8 0v3M12 14v2"/>',
    "phone": '<path d="M7 3h3l1 5-2 1.5a14 14 0 0 0 5.5 5.5L16 13l5 1v3c0 2-1.6 4-4 4C9.8 21 3 14.2 3 7c0-2.4 2-4 4-4Z"/>',
    "bank": '<path d="m3 9 9-6 9 6M5 9h14M6 10v7M10 10v7M14 10v7M18 10v7M4 18h16M3 21h18"/>',
    "link": '<path d="M10 13a4 4 0 0 0 5.7 0l2.3-2.3A4 4 0 0 0 12.3 5L11 6.3"/><path d="M14 11a4 4 0 0 0-5.7 0L6 13.3A4 4 0 1 0 11.7 19L13 17.7"/>',
    "queue": '<path d="M5 6h14M5 12h14M5 18h9"/><circle cx="3" cy="6" r=".5"/><circle cx="3" cy="12" r=".5"/><circle cx="3" cy="18" r=".5"/>',
    "trend": '<path d="m4 17 5-5 4 3 7-8"/><path d="M16 7h4v4"/>',
    "equity": '<circle cx="8" cy="8" r="2.5"/><circle cx="16" cy="8" r="2.5"/><path d="M3 19c.5-4 2.2-6 5-6s4.5 2 5 6M11 19c.5-4 2.2-6 5-6s4.5 2 5 6"/>',
    "sliders": '<path d="M4 7h5M13 7h7M4 17h9M17 17h3"/><circle cx="11" cy="7" r="2"/><circle cx="15" cy="17" r="2"/>',
    "globe": '<circle cx="12" cy="12" r="9"/><path d="M3 12h18M12 3c3 3 4 6 4 9s-1 6-4 9c-3-3-4-6-4-9s1-6 4-9Z"/>',
    "play": '<path d="m8 5 11 7-11 7Z"/>',
    "chevron": '<path d="m8 10 4 4 4-4"/>',
    "eye": '<path d="M2.5 12s3.5-6 9.5-6 9.5 6 9.5 6-3.5 6-9.5 6S2.5 12 2.5 12Z"/><circle cx="12" cy="12" r="2.5"/>',
}


def icon(name: str, size: int = 18, css_class: str = "") -> str:
    """Return an inline SVG icon. Unknown names degrade to a small circle."""

    body = _PATHS.get(name, '<circle cx="12" cy="12" r="7"/>')
    klass = html.escape(css_class, quote=True)
    return (
        f'<svg class="ol-icon {klass}" width="{int(size)}" height="{int(size)}" '
        'viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" '
        'stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">'
        f"{body}</svg>"
    )
