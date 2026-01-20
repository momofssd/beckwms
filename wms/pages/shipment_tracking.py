from __future__ import annotations

import io
import re
import textwrap
import zipfile
from typing import Iterable

import pdfplumber
import streamlit as st

from wms.ups_tracking_pattern import _is_valid_usps_tracking, _extract_tracking_numbers_from_text

# Barcode scanning imports
try:
    from pdf2image import convert_from_bytes
    from pyzbar import pyzbar
    BARCODE_AVAILABLE = True
except ImportError:
    BARCODE_AVAILABLE = False

TRACKING_REGEX = re.compile(r"\b(9\d{21,22}|\d{20,22})\b")
TRACKING_SPACED_REGEX = re.compile(r"[\d\s-]{20,40}")


def _extract_tracking_from_barcode(pdf_bytes: bytes) -> list[str]:
    """Extract tracking numbers by scanning barcodes in PDF."""
    if not BARCODE_AVAILABLE:
        return []
    
    numbers = []
    try:
        images = convert_from_bytes(pdf_bytes, dpi=200)
        for img in images:
            barcodes = pyzbar.decode(img)
            for barcode in barcodes:
                try:
                    data = barcode.data.decode('utf-8')
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

        text_numbers = _extract_tracking_numbers_from_pdf_bytes(data)
        barcode_numbers = _extract_tracking_from_barcode(data)
        all_numbers.extend(text_numbers)
        all_numbers.extend(barcode_numbers)
    
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
                if info.is_dir() or not info.filename.lower().endswith(".pdf"):
                    continue
                try:
                    pdf_bytes = archive.read(info)
                except Exception:
                    continue
                if not pdf_bytes:
                    continue
                numbers.extend(_extract_tracking_numbers_from_pdf_bytes(pdf_bytes))
                numbers.extend(_extract_tracking_from_barcode(pdf_bytes))
    except Exception:
        return []
    return numbers


def render() -> None:
    st.title("Shipment Tracking")
    st.caption("Extract tracking numbers from labels using text extraction and barcode scanning.")

    # --- Initialize Session States ---
    if "shipment_uploader_key" not in st.session_state:
        st.session_state.shipment_uploader_key = 0
    if "label_tracking_page" not in st.session_state:
        st.session_state.label_tracking_page = 0
    if "label_tracking_numbers" not in st.session_state:
        st.session_state.label_tracking_numbers = []

    if not BARCODE_AVAILABLE:
        st.warning("Barcode scanning unavailable. Install: pip install pyzbar pdf2image pillow")

    label_numbers = st.session_state.label_tracking_numbers

    header_left, header_right = st.columns([3, 1], gap="medium")
    with header_left:
        st.subheader("Track by Label (PDF)")
        st.caption("Upload label PDFs or ZIPs. Images-only PDFs are scanned via barcode.")
    
    with header_right:
        if st.button("Reset", use_container_width=True):
            st.session_state.label_tracking_numbers = []
            st.session_state.label_tracking_page = 0
            st.session_state.shipment_uploader_key += 1
            st.rerun()

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
            extracted = _extract_tracking_numbers_from_pdfs(uploaded_files)
            st.session_state.label_tracking_numbers = extracted
            st.session_state.label_tracking_page = 0
            st.rerun()

        if label_numbers:
            st.success(f"Found {len(label_numbers)} tracking number(s).")
        else:
            st.info("No tracking numbers extracted yet.")

    with right_col:
        st.markdown("**Output**")
        if label_numbers:
            # --- Pagination Logic (Batch of 25) ---
            items_per_page = 25
            total_pages = (len(label_numbers) + items_per_page - 1) // items_per_page
            current_page = st.session_state.label_tracking_page

            if current_page >= total_pages:
                current_page = 0
                st.session_state.label_tracking_page = 0

            start_idx = current_page * items_per_page
            end_idx = min(start_idx + items_per_page, len(label_numbers))
            current_batch = label_numbers[start_idx:end_idx]

            st.markdown(f"**Batch {current_page + 1} of {total_pages}**")
            
            # Formatting batch display
            wrapped_lines = []
            current_line = []
            current_length = 0
            for tracking in current_batch:
                item_len = len(tracking) + (2 if current_line else 0)
                if current_length + item_len > 90 and current_line:
                    wrapped_lines.append(", ".join(current_line) + ",")
                    current_line = [tracking]
                    current_length = len(tracking)
                else:
                    current_line.append(tracking)
                    current_length += item_len
            if current_line:
                wrapped_lines.append(", ".join(current_line))
            
            st.code("\n".join(wrapped_lines), language=None)
            st.caption("Click the copy icon to copy this batch.")

            # --- USPS Web Tracking Button (Batch-Specific) ---
            encoded_labels = "%2C".join(current_batch)
            usps_url = f"https://tools.usps.com/go/TrackConfirmAction?tRef=fullpage&tLc=19&text28777=&tLabels={encoded_labels}&tABt=false"
            
            st.link_button(
                f"🚚 USPS Web Tracking (Batch {current_page + 1})", 
                usps_url, 
                use_container_width=True,
                help=f"Track the {len(current_batch)} numbers visible in this batch."
            )

            # Pagination Controls
            if total_pages > 1:
                p1, p2, p3 = st.columns([1, 2, 1])
                if current_page > 0:
                    if p1.button("⬅️ Previous", key="lbl_prev_btn"):
                        st.session_state.label_tracking_page -= 1
                        st.rerun()
                p2.markdown(f"<p style='text-align: center;'>Batch {current_page + 1} / {total_pages}</p>", unsafe_allow_html=True)
                if current_page < total_pages - 1:
                    if p3.button("Next ➡️", key="lbl_next_btn"):
                        st.session_state.label_tracking_page += 1
                        st.rerun()
        else:
            st.info("No tracking numbers extracted yet.")