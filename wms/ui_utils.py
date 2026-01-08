import io

import pandas as pd
import streamlit.components.v1 as components


def disable_scanner_hotkeys() -> None:
    """Prevent F7 and F12 hotkeys triggered by scanner devices."""
    components.html(
        """
        <script>
        (function() {
            function preventScannerKeys(e) {
                // Only block F1-F12 function keys on keydown event
                // Don't block keypress or keyup to allow normal typing
                if (e.type === 'keydown' && 
                    ((e.keyCode >= 112 && e.keyCode <= 123) || 
                     (e.key && e.key.startsWith('F') && e.key.length <= 3))) {
                    e.preventDefault();
                    e.stopPropagation();
                    e.stopImmediatePropagation();
                    return false;
                }
            }
            
            // Only add keydown listener to block function keys
            // Don't intercept keypress/keyup to allow normal typing
            window.parent.document.addEventListener('keydown', preventScannerKeys, true);
            window.addEventListener('keydown', preventScannerKeys, true);
            
            // Disable right-click context menu
            window.parent.document.addEventListener('contextmenu', function(e) {
                e.preventDefault();
                return false;
            }, true);
        })();
        </script>
        """,
        height=0,
    )


def auto_focus_js() -> None:
    components.html(
        "<script>function setFocus(){const input=window.parent.document.querySelector('input[aria-label=\\\"SCAN_ZONE\\\"]');if(input&&window.parent.document.activeElement!==input){input.focus();}}setInterval(setFocus,300);setTimeout(setFocus,100);</script>",
        height=0,
    )


def auto_focus_aria_label_js(aria_label: str) -> None:
    """Force-focus a Streamlit input by aria-label.

    Streamlit renders widgets inside an iframe. This helper focuses the matching
    input element in the *parent* document.
    """

    # Keep it small + defensive: focus only if element exists and isn't already active.
    js = (
        "<script>"
        "function setFocus(){"
        f"const input=window.parent.document.querySelector('input[aria-label=\\\"{aria_label}\\\"]');"
        "if(input&&window.parent.document.activeElement!==input){input.focus();}}"
        "setInterval(setFocus,300);setTimeout(setFocus,100);"
        "</script>"
    )
    components.html(js, height=0)


def to_excel(df: pd.DataFrame) -> bytes:
    """Serialize a DataFrame to XLSX bytes with headers."""
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        df.to_excel(writer, index=False, header=True, sheet_name="WMS_Export")
    return output.getvalue()
