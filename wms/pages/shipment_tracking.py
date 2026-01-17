from __future__ import annotations

import io
import json
import re
from typing import Iterable

import pdfplumber
import streamlit as st
import streamlit.components.v1 as components

TRACKING_REGEX = re.compile(r"\b(9\d{21,22}|\d{20,22})\b")
TRACKING_SPACED_REGEX = re.compile(r"[\d\s-]{20,40}")


def _extract_tracking_numbers_from_text(text: str) -> list[str]:
    if not text:
        return []

    numbers = TRACKING_REGEX.findall(text)

    for chunk in TRACKING_SPACED_REGEX.findall(text):
        compact = re.sub(r"\D", "", chunk)
        if 20 <= len(compact) <= 22:
            numbers.append(compact)

    # Unique while preserving order
    seen = set()
    unique = []
    for num in numbers:
        if num not in seen:
            seen.add(num)
            unique.append(num)
    return unique


def _extract_tracking_numbers_from_pdfs(
    files: Iterable[st.runtime.uploaded_file_manager.UploadedFile],
) -> list[str]:
    numbers: list[str] = []
    for uploaded in files or []:
        try:
            data = uploaded.getvalue()
        except Exception:
            continue
        if not data:
            continue
        try:
            with pdfplumber.open(io.BytesIO(data)) as pdf:
                for page in pdf.pages:
                    page_text = page.extract_text() or ""
                    numbers.extend(_extract_tracking_numbers_from_text(page_text))
        except Exception:
            continue
    return numbers


def _format_tracking_csv(numbers: list[str]) -> str:
    cleaned: list[str] = []
    seen = set()
    for num in numbers:
        compact = re.sub(r"\D", "", str(num))
        if not compact:
            continue
        if compact not in seen:
            seen.add(compact)
            cleaned.append(compact)
    return ",".join(cleaned)


def _render_copy_button(text: str, button_label: str, key: str) -> None:
    if not text:
        st.button(
            button_label,
            use_container_width=True,
            disabled=True,
            key=f"{key}_disabled",
        )
        return

    if st.button(button_label, use_container_width=True, key=f"{key}_btn"):
        html = f"""
        <script>
            try {{
                navigator.clipboard.writeText({json.dumps(text)});
            }} catch (err) {{
                console.error(err);
            }}
        </script>
        """
        components.html(html, height=0)
        st.toast("Copied to clipboard")


def render() -> None:
    st.title("Shipment Tracking")
    st.caption("Extract tracking numbers from labels or manual input.")

    st.markdown(
        """
        <style>
        .stTextArea textarea {
            border-radius: 8px;
        }
        .stFileUploader {
            border-radius: 8px;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )

    if "shipment_uploader_key" not in st.session_state:
        st.session_state.shipment_uploader_key = 0

    label_numbers = st.session_state.get("label_tracking_numbers") or []

    header_left, header_right = st.columns([3, 1], gap="medium")
    with header_left:
        st.subheader("Track by Label (PDF)")
        st.caption(
            "Upload one or more label PDFs to extract tracking numbers. "
            "If the label is image-only, extraction may fail; ensure the PDF includes selectable text."
        )
    with header_right:
        if st.button("Reset", use_container_width=True):
            for state_key in (
                "label_tracking_numbers",
                "label_tracking_csv",
                "manual_tracking_input",
                "manual_tracking_csv",
            ):
                st.session_state.pop(state_key, None)
            st.session_state.label_tracking_csv = ""
            st.session_state.shipment_uploader_key += 1
            label_numbers = []

    st.divider()

    left_col, right_col = st.columns([1, 1], gap="large")

    with left_col:
        st.markdown("**Upload Labels**")
        uploaded_files = st.file_uploader(
            "Upload label PDFs",
            type=["pdf"],
            accept_multiple_files=True,
            key=f"label_upload_{st.session_state.shipment_uploader_key}",
        )

        if st.button("Extract Tracking Numbers", use_container_width=True):
            st.session_state.label_tracking_numbers = _extract_tracking_numbers_from_pdfs(
                uploaded_files
            )
            label_numbers = st.session_state.label_tracking_numbers
            st.session_state.label_tracking_csv = _format_tracking_csv(label_numbers)

        if label_numbers:
            st.success(f"Found {len(label_numbers)} tracking number(s).")
        else:
            st.info("No tracking numbers extracted yet.")

    with right_col:
        st.markdown("**Output**")
        st.text_area(
            "Comma-separated tracking numbers",
            height=180,
            key="label_tracking_csv",
        )

        _render_copy_button(
            st.session_state.get("label_tracking_csv", ""),
            "Copy joined tracking numbers",
            key="copy_label_tracking",
        )
