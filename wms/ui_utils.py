import io

import pandas as pd
import streamlit.components.v1 as components


def auto_focus_js() -> None:
    components.html(
        "<script>function setFocus(){const input=window.parent.document.querySelector('input[aria-label=\\\"SCAN_ZONE\\\"]');if(input&&window.parent.document.activeElement!==input){input.focus();}}setInterval(setFocus,300);setTimeout(setFocus,100);</script>",
        height=0,
    )


def to_excel(df: pd.DataFrame) -> bytes:
    """Serialize a DataFrame to XLSX bytes with headers."""
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        df.to_excel(writer, index=False, header=True, sheet_name="WMS_Export")
    return output.getvalue()

