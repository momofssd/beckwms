from __future__ import annotations

import io
import re
import textwrap
import zipfile
from typing import Iterable

import pdfplumber
import streamlit as st

# Barcode scanning imports
try:
    from pdf2image import convert_from_bytes
    from pyzbar import pyzbar
    BARCODE_AVAILABLE = True
except ImportError:
    BARCODE_AVAILABLE = False

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

    return numbers


def _extract_tracking_from_barcode(pdf_bytes: bytes) -> list[str]:
    """Extract tracking numbers by scanning barcodes in PDF."""
    if not BARCODE_AVAILABLE:
        return []
    
    numbers = []
    try:
        # Convert PDF pages to images
        images = convert_from_bytes(pdf_bytes, dpi=200)
        
        for img in images:
            # Decode all barcodes found in the image
            barcodes = pyzbar.decode(img)
            for barcode in barcodes:
                try:
                    data = barcode.data.decode('utf-8')
                    # Extract numbers from barcode data
                    extracted = _extract_tracking_numbers_from_text(data)
                    numbers.extend(extracted)
                except Exception:
                    continue
    except Exception:
        return []
    
    return numbers


def _extract_tracking_numbers_from_pdf_bytes(data: bytes) -> list[str]:
    """Extract tracking numbers from PDF text."""
    numbers: list[str] = []
    try:
        with pdfplumber.open(io.BytesIO(data)) as pdf:
            for page in pdf.pages:
                page_text = page.extract_text() or ""
                numbers.extend(_extract_tracking_numbers_from_text(page_text))
    except Exception:
        return []
    return numbers


def _extract_tracking_numbers_from_pdfs(
    files: Iterable[st.runtime.uploaded_file_manager.UploadedFile],
) -> list[str]:
    """Extract tracking numbers using both text and barcode methods."""
    all_numbers: list[str] = []
    
    for uploaded in files or []:
        try:
            data = uploaded.getvalue()
        except Exception:
            continue
        if not data:
            continue
        
        filename = (uploaded.name or "").lower()
        
        if filename.endswith(".zip"):
            all_numbers.extend(_extract_tracking_numbers_from_zip(data))
            continue

        # Try both methods for regular PDFs
        text_numbers = _extract_tracking_numbers_from_pdf_bytes(data)
        barcode_numbers = _extract_tracking_from_barcode(data)
        
        all_numbers.extend(text_numbers)
        all_numbers.extend(barcode_numbers)
    
    # Remove duplicates while preserving order
    seen = set()
    unique = []
    for num in all_numbers:
        compact = re.sub(r"\D", "", str(num))
        if compact and compact not in seen:
            seen.add(compact)
            unique.append(compact)
    
    return unique


def _extract_tracking_numbers_from_zip(data: bytes) -> list[str]:
    numbers: list[str] = []
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            for info in archive.infolist():
                if info.is_dir():
                    continue
                if not info.filename.lower().endswith(".pdf"):
                    continue
                try:
                    pdf_bytes = archive.read(info)
                except Exception:
                    continue
                if not pdf_bytes:
                    continue
                
                # Try both methods
                text_numbers = _extract_tracking_numbers_from_pdf_bytes(pdf_bytes)
                barcode_numbers = _extract_tracking_from_barcode(pdf_bytes)
                
                numbers.extend(text_numbers)
                numbers.extend(barcode_numbers)
    except Exception:
        return []
    return numbers


def _format_tracking_csv(numbers: list[str]) -> str:
    return ",".join(numbers)


def render() -> None:
    st.title("Shipment Tracking")
    st.caption("Extract tracking numbers from labels using text extraction and barcode scanning.")

    if not BARCODE_AVAILABLE:
        st.warning(
            "Barcode scanning unavailable. Install: pip install pyzbar pdf2image pillow"
        )

    if "shipment_uploader_key" not in st.session_state:
        st.session_state.shipment_uploader_key = 0

    label_numbers = st.session_state.get("label_tracking_numbers") or []

    header_left, header_right = st.columns([3, 1], gap="medium")
    with header_left:
        st.subheader("Track by Label (PDF)")
        st.caption(
            "Upload one or more label PDFs to extract tracking numbers. "
            "Uses text extraction and barcode scanning for image-only PDFs."
        )
    with header_right:
        if st.button("Reset", use_container_width=True):
            for state_key in (
                "label_tracking_numbers",
                "label_tracking_csv",
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
            "Upload label PDFs or ZIP folders",
            type=["pdf", "zip"],
            accept_multiple_files=True,
            key=f"label_upload_{st.session_state.shipment_uploader_key}",
        )

        if st.button("Extract Tracking Numbers", use_container_width=True):
            extracted_numbers = _extract_tracking_numbers_from_pdfs(uploaded_files)
            st.session_state.label_tracking_numbers = extracted_numbers
            label_numbers = extracted_numbers
            st.session_state.label_tracking_csv = _format_tracking_csv(label_numbers)

        if label_numbers:
            st.success(f"Found {len(label_numbers)} tracking number(s).")
        else:
            st.info("No tracking numbers extracted yet.")

    with right_col:
        st.markdown("**Output**")
        label_csv = st.session_state.get("label_tracking_csv", "")
        if label_csv:
            st.markdown("**Copy using the icon in the code block.**")
            wrapped_csv = "\n".join(textwrap.wrap(label_csv, width=90))
            st.code(wrapped_csv, language=None)
            st.caption("Click the copy icon on the right to copy the tracking numbers.")
        else:
            st.info("No tracking numbers extracted yet.")