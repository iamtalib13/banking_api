# Copyright (c) 2026, Talib Sheikh and contributors
# For license information, please see license.txt

from openpyxl.worksheet.table import Table, TableStyleInfo
from openpyxl.utils import get_column_letter
from openpyxl.styles import Font, PatternFill, Alignment
from openpyxl import Workbook
import frappe
import csv
import io
from frappe import _
from frappe.model.document import Document
import io
import frappe
from frappe import _
from frappe.utils import getdate, formatdate
from frappe.model.document import Document
from docx import Document as DocxDocument
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.shared import Pt, Inches
from docx.oxml.ns import qn
from docx.shared import Pt
from docx.enum.text import WD_ALIGN_PARAGRAPH
import random
import os
from docx.shared import Inches
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.shared import Pt, Inches
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
import json
from PIL import Image
from collections import defaultdict
from decimal import Decimal, InvalidOperation

from docx import Document as DocxDocument
from docx.enum.table import WD_CELL_VERTICAL_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Inches, Pt
import psycopg2
from psycopg2.extras import RealDictCursor


def db_connection():
    """Connect to external PostgreSQL (Finacle) using Finacle DB Credentials."""
    try:
        creds = frappe.get_single("Finacle DB Credentials")

        port = int(creds.db_port) if creds.db_port else 5432

        conn = psycopg2.connect(
            host=creds.db_host,
            port=port,
            user=creds.db_user,
            password=creds.get_password("db_password"),
            database=creds.db_name
        )
        return conn

    except Exception as e:
        frappe.log_error(
            frappe.get_traceback(),
            "PostgreSQL Connection Failed"
        )
        frappe.throw(
            _("Database Connection Error: {0}").format(str(e))
        )


def cint_safe(value, default=0):
    try:
        return int(value)
    except Exception:
        return default


def execute_finacle_query(query, params=None):
    """
    Execute a read-only query against Finacle PostgreSQL and return
    records as Frappe-style dictionaries.
    """
    conn = None
    cursor = None

    try:
        conn = db_connection()
        cursor = conn.cursor(cursor_factory=RealDictCursor)

        cursor.execute(query, params or ())
        rows = cursor.fetchall()

        return [dict(row) for row in rows]

    except Exception:
        frappe.log_error(
            frappe.get_traceback(),
            "Finacle PostgreSQL Query Failed"
        )
        frappe.throw(_("Unable to fetch data from Finacle database."))

    finally:
        if cursor:
            cursor.close()

        if conn:
            conn.close()


def set_docx_cell_background(cell, hex_color):
    """
    Apply Word table-cell background colour.
    Pass colour without '#', e.g. 'D9E1F2'.
    """
    tc_pr = cell._tc.get_or_add_tcPr()

    shading = OxmlElement("w:shd")
    shading.set(qn("w:fill"), hex_color.replace("#", ""))
    shading.set(qn("w:val"), "clear")
    tc_pr.append(shading)


def set_docx_cell_text(
    cell,
    value,
    *,
    bold=False,
    alignment=WD_ALIGN_PARAGRAPH.LEFT,
    font_size=8
):
    """Set one formatted paragraph in a DOCX table cell."""
    cell.text = ""
    cell.vertical_alignment = WD_CELL_VERTICAL_ALIGNMENT.CENTER

    paragraph = cell.paragraphs[0]
    paragraph.alignment = alignment

    paragraph_format = paragraph.paragraph_format
    paragraph_format.space_before = Pt(0)
    paragraph_format.space_after = Pt(0)

    run = paragraph.add_run(str(value if value is not None else ""))
    run.bold = bold
    run.font.name = "Arial"
    run.font.size = Pt(font_size)


def safe_float(value, default=0.0):
    """Convert Finacle numeric values safely for totals."""
    try:
        if value in (None, ""):
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def format_amount(value):
    """Format a numeric loan amount without currency symbol."""
    return "{:,.2f}".format(safe_float(value))


class ShareApplication(Document):
    def autoname(self):
        from frappe import _
        from frappe.model.naming import getseries

        sol_id = str(self.sol_id or "").strip()

        if not sol_id:
            frappe.throw(_("SOL ID is mandatory for naming."))

        if not sol_id.isdigit():
            frappe.throw(_("SOL ID must contain digits only."))

        if len(sol_id) != 4:
            frappe.throw(_("SOL ID must be exactly 4 digits."))

        prefix = f"{sol_id}01"

        for _ in range(5):
            sequence = getseries("Share Application-", 9)
            new_name = f"{prefix}{sequence}"

            if not frappe.db.exists("Share Application", new_name):
                self.name = new_name
                return

        frappe.throw(
            _("Unable to generate a unique Share Application ID. Please try again."))

    def validate(self):
        if self.docstatus == 1:
            if self.payment_status != "Success":
                frappe.throw(
                    _("Only documents with Status = 'Success' can be submitted."))

            if not self.transaction_id:
                frappe.throw(
                    _("Transaction ID is mandatory before submission."))

#########################################################################################


# list of directors
DIRECTORS = [
    "जयेशचंद्र रमण रामादे",
    "दत्तात्रय शायमराव सावंत",
    "आशीष वासुदेव बाहेकर",
    "जितेंद्र इंद्रराज रंगारी",
    "शुभम गोपाल भिमटे"
]


# APP_PATH = frappe.get_app_path("banking_api")
# IMAGES_PATH = os.path.join(APP_PATH, "public", "images")

# JAYESH_SIGN_PATH = os.path.join(IMAGES_PATH, "jayesh_sir_sign.png")
# WASNIK_SIGN_PATH = os.path.join(IMAGES_PATH, "wasnik_sir_sign.png")


def add_page_number(paragraph):
    """Insert an automatic PAGE field into the given paragraph."""
    run = paragraph.add_run()
    fld_char_begin = OxmlElement('w:fldChar')
    fld_char_begin.set(qn('w:fldCharType'), 'begin')
    run._r.append(fld_char_begin)

    instr_text = OxmlElement('w:instrText')
    instr_text.text = "PAGE"
    run._r.append(instr_text)

    fld_char_end = OxmlElement('w:fldChar')
    fld_char_end.set(qn('w:fldCharType'), 'end')
    run._r.append(fld_char_end)


def add_footer_page_number(doc):
    section = doc.sections[0]
    footer = section.footer

    # Use the first footer paragraph (or create one if needed)
    if not footer.paragraphs:
        footer_para = footer.add_paragraph()
    else:
        footer_para = footer.paragraphs[0]

    footer_para.clear()  # remove any existing text
    footer_para.alignment = WD_ALIGN_PARAGRAPH.CENTER

    # Optional label: "Page " + number
    footer_para.text = "Page "
    add_page_number(footer_para)

    # Small font
    for run in footer_para.runs:
        run.font.size = Pt(8)


def normalize_branch_name(branch_name: str) -> str:
    if not branch_name:
        return branch_name
    if branch_name.lower() == "main branch":
        return "Gondia"
    else:
        words = branch_name.split()
        filtered = [w for w in words if w.lower() != "branch"]
        return " ".join(filtered).strip()


# def get_proposer_approver(selected_date):
#     """
#     Get (or create) proposer & approver for a given date from Share Proceeding Log.
#     Returns: (proposer, approver)
#     """
#     date_obj = getdate(selected_date)
#     date_str = date_obj.strftime("%Y-%m-%d")

#     # Try to fetch existing record
#     existing_name = frappe.db.get_value(
#         "Share Proceeding Log",
#         {"date": date_obj},
#         "name"
#     )

#     if existing_name:
#         existing_doc = frappe.get_doc("Share Proceeding Log", existing_name)
#         if existing_doc.json:
#             schedule = existing_doc.json
#             return schedule["proposer"], schedule["approver"]

#     # No record found → create one with a new pair
#     DIRECTORS = [
#         "जयेशचंद्र रमण रामादे",
#         "दत्तात्रय शायमराव सावंत",
#         "आशीष वासुदेव बाहेकर",
#         "जितेंद्र इंद्रराज रंगारी",
#         "शुभम गोपाल भिमटे"
#     ]

#     # Deterministic per date
#     random.seed(date_str)
#     proposer, approver = random.sample(DIRECTORS, 2)
#     random.seed()  # reset

#     schedule = {
#         "proposer": proposer,
#         "approver": approver
#     }

#     doc = frappe.get_doc({
#         "doctype": "Share Proceeding Log",
#         "date": date_obj,
#         "json": schedule
#     })
#     doc.insert(ignore_permissions=True)
#     frappe.db.commit()

#     return proposer, approver

def get_proceeding_data(selected_date):
    """
    Get (or create) proposer, approver, and meeting number for a given date
    from Share Proceeding Log.
    Returns: (proposer, approver, meeting_no)
    """
    date_obj = getdate(selected_date)
    date_str = date_obj.strftime("%Y-%m-%d")

    # Try to fetch existing record by date
    existing_name = frappe.db.get_value(
        "Share Proceeding Log",
        {"date": date_obj},
        "name"
    )

    if existing_name:
        existing_doc = frappe.get_doc("Share Proceeding Log", existing_name)
        if existing_doc.json:
            # Parse JSON string to dict
            schedule = existing_doc.json
            if isinstance(schedule, str):
                schedule = json.loads(schedule)

            return (
                schedule["proposer"],
                schedule["approver"],
                schedule.get("meeting_no", 1)
            )

    # No record found → create one with new proposer, approver, and meeting_no
    DIRECTORS = [
        "जयेशचंद्र रमण रामादे",
        "दत्तात्रय शायमराव सावंत",
        "आशीष वासुदेव बाहेकर",
        "जितेंद्र इंद्रराज रंगारी",
        "शुभम गोपाल भिमटे"
    ]

    # Deterministic per date
    random.seed(date_str)
    proposer, approver = random.sample(DIRECTORS, 2)
    meeting_no = random.randint(1, 15)
    random.seed()  # reset

    schedule = {
        "proposer": proposer,
        "approver": approver,
        "meeting_no": meeting_no
    }

    doc = frappe.get_doc({
        "doctype": "Share Proceeding Log",
        "date": date_obj,
        "json": schedule  # Frappe will store this as JSON text
    })
    doc.insert(ignore_permissions=True)
    frappe.db.commit()

    return proposer, approver, meeting_no


def get_signature_file_path(file_url, label):
    """
    Convert the Frappe attachment URL to a server filesystem path.
    Validates that a signature is configured and its image file exists.
    """
    if not file_url:
        frappe.throw(
            f"{label} is not configured. "
            "Please upload it in Share Application Setting."
        )

    # Reject remote URL files because python-docx needs a local path.
    if file_url.startswith(("http://", "https://")):
        frappe.throw(
            f"{label} must be uploaded as a local image file, "
            "not an external URL."
        )

    # Frappe attachment paths normally begin with /files/ or /private/files/
    file_path = frappe.get_site_path(file_url.lstrip("/"))

    if not os.path.exists(file_path):
        frappe.throw(
            f"{label} file was not found on the server: {file_url}. "
            "Please upload the signature again in Share Application Setting."
        )

    allowed_extensions = {".png", ".jpg", ".jpeg", ".bmp", ".gif"}
    extension = os.path.splitext(file_path)[1].lower()

    if extension not in allowed_extensions:
        frappe.throw(
            f"{label} must be an image file. Allowed formats: "
            "PNG, JPG, JPEG, BMP, GIF."
        )
    validate_image_file(file_path, label)
    return file_path


def get_proceeding_signatures():
    """
    Reads both signatures from the Share Application Setting Single DocType.
    Returns local filesystem paths for python-docx.
    """
    settings = frappe.get_single("Share Application Settings")

    chairman_signature_path = get_signature_file_path(
        settings.chairman_signature,
        "Chairman Signature"
    )

    ceo_signature_path = get_signature_file_path(
        settings.ceo_signature,
        "CEO Signature"
    )

    return chairman_signature_path, ceo_signature_path


def add_centered_image(doc, image_path, width_inch=1.8):
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.LEFT
    run = p.add_run()
    run.add_picture(image_path, width=Inches(width_inch))
    return p


def validate_image_file(file_path, label):
    try:
        with Image.open(file_path) as image:
            image.verify()
    except Exception:
        frappe.throw(
            f"{label} is not a valid image file. "
            "Please upload a valid PNG or JPG signature image."
        )


@frappe.whitelist()
def download_proceeding_form(account_opening_date):
    import io
    import frappe
    from frappe import _
    from frappe.utils import getdate, formatdate
    from docx import Document as DocxDocument
    from docx.shared import Inches, Pt
    from docx.enum.text import WD_ALIGN_PARAGRAPH, WD_LINE_SPACING
    from docx.oxml.ns import qn

    if not account_opening_date:
        frappe.throw(_("Account Opening Date is required."))

    try:
        selected_date = getdate(account_opening_date)
    except Exception:
        frappe.throw(_("Invalid date selected."))

    records = frappe.get_all(
        "Share Application",
        filters={
            "account_opening_date": selected_date,
            "payment_status": "Success"
        },
        fields=["name", "customer_name", "branch"],
        order_by="name asc"
    )

    # if not records:
    #     frappe.throw(
    #         _("No Share Application records with successful payment found for the selected Account Opening Date."))

    if not records:
        frappe.msgprint(
            _("No Share Application records with successful payment found for the selected Account Opening Date."),
            title=_("No Records"),
            indicator="orange"
        )
        return

    def to_devanagari_digits(number):
        """
        Convert an integer to Devanagari (Marathi) digits.
        Example: 708 -> '७०८'
        """
        devanagari_digits = "०१२३४५६७८९"
        return "".join(devanagari_digits[int(d)] for d in str(number))

    total_members = len(records)
    total_members_dev = to_devanagari_digits(total_members)

    def to_devanagari_date(date_obj):
        """
        Convert a Python date object to Devanagari digits in dd/mm/yyyy format.
        Example: 2026-08-18 -> '१८/०८/२०२६'
        """
        day = to_devanagari_digits(date_obj.day)
        month = to_devanagari_digits(date_obj.month)
        year = to_devanagari_digits(date_obj.year)
        return f"{day}/{month}/{year}"

    selected_date_dev = to_devanagari_date(selected_date)

    def add_image_paragraph(image_path, width_inch=0.5):
        p = doc.add_paragraph()
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        run = p.add_run()
        run.add_picture(image_path, width=Inches(width_inch))
        return p

    doc = DocxDocument()

    section = doc.sections[0]
    section.top_margin = Inches(0.6)
    section.bottom_margin = Inches(0.6)
    section.left_margin = Inches(0.7)
    section.right_margin = Inches(0.7)

    DEFAULT_FONT = "Kokila"
    DEFAULT_SIZE = 14

    def set_run_font(run, bold=False, size=DEFAULT_SIZE, font_name=DEFAULT_FONT):
        run.bold = bold
        run.font.size = Pt(size)
        run.font.name = font_name
        r = run._element
        if r.rPr is None:
            r.get_or_add_rPr()
        r.rPr.rFonts.set(qn("w:ascii"), font_name)
        r.rPr.rFonts.set(qn("w:hAnsi"), font_name)
        r.rPr.rFonts.set(qn("w:cs"), font_name)
        r.rPr.rFonts.set(qn("w:eastAsia"), font_name)

    def apply_paragraph_spacing(paragraph, alignment=WD_ALIGN_PARAGRAPH.LEFT):
        paragraph.alignment = alignment
        pf = paragraph.paragraph_format
        pf.space_before = Pt(0)
        pf.space_after = Pt(0)
        pf.line_spacing_rule = WD_LINE_SPACING.EXACTLY
        pf.line_spacing = Pt(22)
        return paragraph

    def add_center(text, bold=False, size=DEFAULT_SIZE):
        p = doc.add_paragraph()
        apply_paragraph_spacing(p, WD_ALIGN_PARAGRAPH.CENTER)
        run = p.add_run(text)
        set_run_font(run, bold=bold, size=size)
        return p

    def add_left(text, bold=False, size=DEFAULT_SIZE):
        p = doc.add_paragraph()
        apply_paragraph_spacing(p, WD_ALIGN_PARAGRAPH.LEFT)
        run = p.add_run(text)
        set_run_font(run, bold=bold, size=size)
        return p

    def add_left_mixed(parts, size=DEFAULT_SIZE):
        p = doc.add_paragraph()
        apply_paragraph_spacing(p, WD_ALIGN_PARAGRAPH.LEFT)

        for part in parts:
            if isinstance(part, str):
                run = p.add_run(part)
                set_run_font(run, bold=False, size=size)
            else:
                text, is_bold = part
                run = p.add_run(text)
                set_run_font(run, bold=is_bold, size=size)

        return p

    def set_table_col_widths(table, widths):
        table.autofit = False
        try:
            table.allow_autofit = False
        except Exception:
            pass

        for col_idx, width in enumerate(widths):
            try:
                table.columns[col_idx].width = width
            except Exception:
                pass

        for row in table.rows:
            for col_idx, width in enumerate(widths):
                row.cells[col_idx].width = width

    def format_cell_paragraph(paragraph, alignment=WD_ALIGN_PARAGRAPH.CENTER):
        apply_paragraph_spacing(paragraph, alignment)
        return paragraph

    formatted_date = formatdate(selected_date, "dd / mm / yyyy")
    formatted_date_dev = to_devanagari_date(selected_date)
    proposer, approver, meeting_no = get_proceeding_data(selected_date)

    # Read dynamic signatures from Share Application Setting
    chairman_signature_path, ceo_signature_path = get_proceeding_signatures()

    meeting_no_dev = to_devanagari_digits(meeting_no)

    add_center("सहयोग मल्टीस्टेट क्रेडिट को-ऑपरेटिव्ह सोसायटी लि.",
               bold=True, size=24)
    add_center("")
    add_left("सभासद उपसमिती बैठकीची कार्यवाही", bold=True, size=14)

    # add_left("बैठक क्र.: __________", bold=True, size=14)
    add_left(f"दिनांक: {formatted_date_dev}", bold=True, size=14)
    add_left("वेळ: ____११:३०____", bold=True, size=14)
    add_left("स्थळ: मुख्यालय, गोंदिया", bold=True, size=14)
    add_left(
        f"विषय क्र. {meeting_no_dev}: नवीन सभासदत्व मंजूर करण्याबाबत", bold=True, size=14)

    add_left_mixed([
        "मुख्य कार्यकारी अधिकारी यांनी सभेस अवगत केले की, संस्थेचे सभासदत्व प्राप्त करण्यासाठी विविध अर्जदारांकडून विहित नमुन्यात अर्ज प्राप्त झाले आहेत. सदर अर्जांची कार्यालयीन स्तरावर छाननी व पडताळणी करण्यात आली असून, अर्जदारांनी ",
        ("मल्टी स्टेट को-ऑपरेटिव्ह सोसायटीज अधिनियम, 2002,", True),
        " त्याअंतर्गत नियम व संस्थेच्या उपविधींनुसार आवश्यक पात्रता, प्रवेश फी, भागभांडवल रक्कम व इतर आवश्यक कागदपत्रांची पूर्तता केलेली आहे."
    ], size=14)

    add_left_mixed([
        "सदर अर्जदारांची तपशीलवार यादी ",
        ("परिशिष्ट – अ", True),
        " मध्ये जोडण्यात आलेली असून ती सभासद उपसमिती समोर विचारार्थ सादर करण्यात आली."
    ], size=14)

    add_left("")
    add_left(f"ठराव क्र. {meeting_no_dev}", bold=True)

    p = doc.add_paragraph()
    apply_paragraph_spacing(p, WD_ALIGN_PARAGRAPH.LEFT)

    r1 = p.add_run(
        "सभासद उपसमिती विषयावर सविस्तर चर्चा केली. परिशिष्ट – अ मधील सर्व अर्जदारांनी संस्थेच्या उपविधींनुसार सभासदत्वासाठी आवश्यक अटी पूर्ण केल्याचे निदर्शनास आले.\n"
    )
    set_run_font(r1, bold=False, size=14)

    r2 = p.add_run(
        "त्याअनुषंगाने खालीलप्रमाणे ठराव एकमताने मंजूर करण्यात आला :\n"
    )
    set_run_font(r2, bold=False, size=14)

    # r3 = p.add_run(
    #     '"ठरविण्यात येते की, मल्टी स्टेट को-ऑपरेटिव्ह सोसायटीज अधिनियम, 2002, त्याअंतर्गत नियम व संस्थेच्या उपविधींमधील तरतुदींनुसार परिशिष्ट – अ मध्ये नमूद १ ते १०० अर्जदारांना संस्थेचे नियमित सभासद म्हणून प्रवेश देण्यास मंजुरी देण्यात येत आहे. तसेच संबंधित अर्जदारांकडून विहित प्रवेश फी, भागभांडवल रक्कम व इतर आवश्यक औपचारिकता पूर्ण करून त्यांची सभासद म्हणून नोंद सदस्य नोंदवहीत करण्यात यावी व नियमानुसार सभासदत्व/भाग प्रमाणपत्र निर्गमित करण्यात यावे. असे सर्व समंतीने ठरविण्यात आले. "'
    # )
    resolution_text = (
        f'"ठरविण्यात येते की, मल्टी स्टेट को-ऑपरेटिव्ह सोसायटीज अधिनियम, 2002, त्याअंतर्गत नियम व संस्थेच्या उपविधींमधील तरतुदींनुसार '
        f'परिशिष्ट – अ मध्ये नमूद १ ते {total_members_dev} अर्जदारांना संस्थेचे नियमित सभासद म्हणून प्रवेश देण्यास मंजुरी देण्यात येत आहे. '
        f'तसेच संबंधित अर्जदारांकडून विहित प्रवेश फी, भागभांडवल रक्कम व इतर आवश्यक औपचारिकता पूर्ण करून त्यांची सभासद म्हणून नोंद सदस्य नोंदवहीत करण्यात यावी '
        f'व नियमानुसार सभासदत्व/भाग प्रमाणपत्र निर्गमित करण्यात यावे. असे सर्व समंतीने ठरविण्यात आले. "'
    )

    r3 = p.add_run(resolution_text)
    set_run_font(r3, bold=False, size=14)

    add_left("")
    # proposer, ap0prover = random.sample(DIRECTORS, 2)
    # proposer, approver, meeting_no = get_proceeding_data(selected_date)
    add_left(f"प्रस्तावक : {proposer}", bold=True)
    add_left(f"अनुमोदक : {approver}", bold=True)
    # add_left("प्रस्तावक : _______________________", bold=True)
    # add_left("अनुमोदक : _______________________", bold=True)
    add_left("ठराव सर्वानुमते मंजूर.", bold=True)
    # add_left("")
    add_left("")

    # # Jayesh Sir signature
    # add_image_paragraph(JAYESH_SIGN_PATH, width_inch=0.8)
    # # Wasnik Sir signature
    # add_image_paragraph(WASNIK_SIGN_PATH, width_inch=0.8)

    # Single paragraph with both signatures side by side
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.LEFT

    # Jayesh Sir signature
    run1 = p.add_run()
    # run1.add_picture(JAYESH_SIGN_PATH, width=Inches(1.0))
    # Chairman / Jayesh signature
    run1.add_picture(chairman_signature_path, width=Inches(1.0))

    # Space between signatures
    p.add_run("                                                      ")

    # Wasnik Sir signature
    run2 = p.add_run()
    # run2.add_picture(WASNIK_SIGN_PATH, width=Inches(1.0))
    # CEO / Wasnik signature
    run2.add_picture(ceo_signature_path, width=Inches(1.0))

    add_left("अध्यक्ष                                                             मुख्य कार्यकारी अधिकारी", bold=True)
    add_left("सहयोग मल्टीस्टेट क्रेडिट को-ऑपरेटिव्ह सोसायटी लि.     सहयोग मल्टीस्टेट क्रेडिट को-ऑपरेटिव्ह सोसायटी लि.", bold=True)
    add_left(
        "मुख्यालय, गोंदिया                                           मुख्यालय, गोंदिया", bold=True)

    doc.add_page_break()

    add_center("परिशिष्ट – अ", bold=True, size=14)
    add_center(
        "नवीन सभासदत्वासाठी मंजुरी देण्यात आलेल्या अर्जदारांची यादी", bold=True, size=14)
    add_left("बैठक क्र.: __________", bold=True)
    add_left(f"दिनांक: {formatted_date_dev}", bold=True)
    add_left("")

    table = doc.add_table(rows=1, cols=6)
    table.style = "Table Grid"
    table.autofit = False

    col_widths = [
        Inches(0.45),  # अ.क्र.
        Inches(1.55),  # अर्ज क्र.
        Inches(2.45),  # अर्जदाराचे नाव
        Inches(1.05),  # गाव/शहर
        Inches(0.80),  # भागभांडवल रक्कम
        Inches(0.75),  # प्रवेश फी
    ]

    hdr = table.rows[0].cells
    headers = [
        "अ.क्र.",
        "अर्ज क्र.",
        "अर्जदाराचे नाव",
        "गाव/शहर",
        "भागभांडवल रक्कम",
        "प्रवेश फी"
    ]

    for i, text in enumerate(headers):
        paragraph = hdr[i].paragraphs[0]
        format_cell_paragraph(paragraph, WD_ALIGN_PARAGRAPH.CENTER)
        run = paragraph.add_run(text)
        set_run_font(run, bold=True, size=14)

    # Set column widths ONCE, not in the loop
    set_table_col_widths(table, col_widths)

    # Add all data rows WITHOUT re-setting widths each time
    # for idx, row in enumerate(records, start=1):
    #     cells = table.add_row().cells
    #     row_values = [
    #         str(idx),
    #         row.get("name") or "",
    #         row.get("customer_name") or "",
    #         branch_name,
    #         row.get("branch") or "",
    #         "10"
    #     ]

    #     for col_idx, value in enumerate(row_values):
    #         paragraph = cells[col_idx].paragraphs[0]

    #         if col_idx in (0, 4, 5):
    #             format_cell_paragraph(paragraph, WD_ALIGN_PARAGRAPH.CENTER)
    #         else:
    #             format_cell_paragraph(paragraph, WD_ALIGN_PARAGRAPH.LEFT)

    #         run = paragraph.add_run(value)
    #         set_run_font(run, bold=False, size=14)

    for idx, row in enumerate(records, start=1):
        cells = table.add_row().cells

        # Normalize this row's branch
        branch_raw = (row.get("branch") or "").strip()
        branch_value = normalize_branch_name(branch_raw)

        row_values = [
            str(idx),
            row.get("name") or "",
            row.get("customer_name") or "",
            branch_value,  # per-row branch
            "10",
            "10"
        ]

        for col_idx, value in enumerate(row_values):
            paragraph = cells[col_idx].paragraphs[0]

            if col_idx in (0, 4, 5):
                format_cell_paragraph(paragraph, WD_ALIGN_PARAGRAPH.CENTER)
            else:
                format_cell_paragraph(paragraph, WD_ALIGN_PARAGRAPH.LEFT)

            run = paragraph.add_run(value)
            set_run_font(run, bold=False, size=14)

    # Optional: set widths once at the end if needed
    # set_table_col_widths(table, col_widths)

    add_left("")
    # add_left(
    #     "प्रमाणित करण्यात येते की, परिशिष्ट – अ मध्ये नमूद १ ते १०० अर्जदारांची यादी संचालक मंडळाच्या बैठकी क्र. _____ दिनांक _____ मध्ये मंजूर करण्यात आलेल्या ठराव क्र. _____ चा अविभाज्य भाग आहे.",
    #     bold=True
    # )
    add_left(
        f"प्रमाणित करण्यात येते की, परिशिष्ट – अ मध्ये नमूद १ ते {total_members_dev} अर्जदारांची यादी संचालक मंडळाच्या बैठकी क्र. {meeting_no_dev} दिनांक __{selected_date_dev}__ मध्ये मंजूर करण्यात आलेल्या ठराव क्र. {meeting_no_dev} चा अविभाज्य भाग आहे.",
        bold=True
    )
    # add_left("")
    # add_left("मुख्य कार्यकारी अधिकारी", bold=True)
    # add_left("सहयोग मल्टीस्टेट क्रेडिट को-ऑपरेटिव्ह सोसायटी लि.", bold=True)
    # add_left("मुख्यालय, गोंदिया", bold=True)
    # add_left("")
    # add_left("अध्यक्ष", bold=True)
    # add_left("सहयोग मल्टीस्टेट क्रेडिट को-ऑपरेटिव्ह सोसायटी लि.", bold=True)
    # add_left("मुख्यालय, गोंदिया", bold=True)

    add_left("")

    # add_left("")

    # Wasnik Sir sign
    # add_centered_image(doc, WASNIK_SIGN_PATH, width_inch=1.0)
    add_centered_image(doc, ceo_signature_path, width_inch=1.0)

    add_left("मुख्य कार्यकारी अधिकारी", bold=True)
    add_left("सहयोग मल्टीस्टेट क्रेडिट को-ऑपरेटिव्ह सोसायटी लि.", bold=True)
    add_left("मुख्यालय, गोंदिया", bold=True)

    # add_left("")

    # Jayesh Sir sign
    # add_centered_image(doc, JAYESH_SIGN_PATH, width_inch=1.0)
    add_centered_image(doc, chairman_signature_path, width_inch=1.0)

    add_left("अध्यक्ष", bold=True)
    add_left("सहयोग मल्टीस्टेट क्रेडिट को-ऑपरेटिव्ह सोसायटी लि.", bold=True)
    add_left("मुख्यालय, गोंदिया", bold=True)

    file_buffer = io.BytesIO()

    add_footer_page_number(doc)
    doc.save(file_buffer)
    file_buffer.seek(0)

    frappe.response.filename = f"Proceeding_Form_{selected_date}.docx"
    frappe.response.filecontent = file_buffer.getvalue()
    frappe.response.type = "download"
    frappe.response.display_content_as = "attachment"


# ########################################################################################


@frappe.whitelist()
def download_share_application_report(report_type):
    report_type = (report_type or "").strip().lower()

    filters = {}
    filename = ""

    export_fields = [
        "name",
        # "docstatus",
        "sol_id",
        "cif",
        "account_number",
        "customer_name",
        "scheme_type",
        "scheme_code",
        "transaction_amount",
        "payment_status",
        "failed_reason",
        "transaction_id",
        "error_log",
        "fund_transfer_date",
        "amount",
        "cif_creation_date",
        "account_opening_date",
        "success_but_fund_not_debited",
        # "retry_attempted",
        # "last_retry_attempted",
        # "owner",
        # "creation",
        "address",
    ]

    db_fields = [
        "name",
        # "docstatus",
        "sol_id",
        "cif",
        "account_number",
        "customer_name",
        "scheme_type",
        "scheme_code",
        "transaction_amount",
        "payment_status",
        "transaction_id",
        "error_log",
        "fund_transfer_date",
        "amount",
        "cif_creation_date",
        "account_opening_date",
        "success_but_fund_not_debited",
        # "retry_attempted",
        # "last_retry_attempted",
        # "owner",
        # "creation",
        "address",
        "insufficient_balance",
        "account_closed",
        "account_frozen",
        "account_not_found",
    ]

    if report_type == "success":
        filters = {"payment_status": "Success"}
        filename = "share_application_success_report.csv"

    elif report_type == "failed":
        filters = {"payment_status": "Failed"}
        filename = "share_application_failed_report.csv"

    elif report_type == "pending":
        filters = {"payment_status": "Pending"}
        filename = "share_application_pending_report.csv"

    elif report_type == "consolidated":
        filters = {}
        filename = "share_application_consolidated_report.csv"

    else:
        frappe.throw(_("Invalid report type."))

    label_map = {
        "name": "Share Application ID",
        # "docstatus": "Doc Status",
        "sol_id": "SOL ID",
        "cif": "CIF",
        "account_number": "Account Number",
        "customer_name": "Customer Name",
        "scheme_type": "Scheme Type",
        "scheme_code": "Scheme Code",
        "transaction_amount": "Transaction Amount",
        "payment_status": "Payment Status",
        "failed_reason": "Failed Reason",
        "transaction_id": "Transaction ID",
        "error_log": "API Response",
        "fund_transfer_date": "Fund Transfer Date",
        "amount": "Amount",
        "cif_creation_date": "CIF Creation Date",
        "account_opening_date": "Account Opening Date",
        "success_but_fund_not_debited": "Success But Fund Not Debited",
        # "retry_attempted": "Retry Attempted",
        # "last_retry_attempted": "Last Retry Attempted",
        # "owner": "Owner",
        # "creation": "Created On",
        "address": "Address",
    }

    docstatus_map = {
        0: "Draft",
        1: "Submitted",
        2: "Cancelled",
    }

    def get_failed_reason(row):
        if row.get("payment_status") != "Failed":
            return ""

        if row.get("insufficient_balance"):
            return "Insufficient Balance"
        if row.get("account_closed"):
            return "Account Closed"
        if row.get("account_frozen"):
            return "Account Frozen"
        if row.get("account_not_found"):
            return "Account Not Found"

        return "Network Issue"

    def set_success_but_fund_not_debited(row):
        if row.get("payment_status") == "Success" and row.get("success_but_fund_not_debited"):
            return "Yes"
        return "No"

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow([label_map.get(field, field) for field in export_fields])

    chunk_size = 10000
    start = 0

    while True:
        records = frappe.get_all(
            "Share Application",
            filters=filters,
            fields=db_fields,
            limit_start=start,
            limit_page_length=chunk_size,
            order_by="name asc"
        )

        if not records:
            break

        for row in records:
            row_data = []

            # for field in export_fields:
            #     if field == "failed_reason":
            #         value = get_failed_reason(row)
            #     elif field == "docstatus":
            #         value = docstatus_map.get(row.get(field), row.get(field))
            #     else:
            #         value = row.get(field, "")

            #     row_data.append(value)

            for field in export_fields:
                if field == "failed_reason":
                    value = get_failed_reason(row)
                elif field == "docstatus":
                    value = docstatus_map.get(row.get(field), row.get(field))
                elif field == "success_but_fund_not_debited":
                    value = set_success_but_fund_not_debited(row)
                else:
                    value = row.get(field, "")

                row_data.append(value)

            writer.writerow(row_data)

        start += chunk_size

    frappe.response.filename = filename
    frappe.response.filecontent = output.getvalue()
    frappe.response.type = "download"
    frappe.response.display_content_as = "attachment"


@frappe.whitelist()
def get_share_application_status_counts():
    data = frappe.db.sql("""
        SELECT payment_status, COUNT(*) AS count
        FROM `tabShare Application`
        GROUP BY payment_status
    """, as_dict=True)

    counts = {
        "Success": 0,
        "Pending": 0,
        "Failed": 0
    }

    for row in data:
        status = row.get("payment_status")
        if status in counts:
            counts[status] = row.get("count", 0)

    return counts


@frappe.whitelist()
def download_loan_meeting_register(start_date=None, end_date=None):
    """
    Download Zone-wise Loan Meeting Register as a DOCX file.

    Data source: external Finacle PostgreSQL database.
    Output columns:
    Zone | Region | Branch | Customer Name | Scheme Name | Months |
    A/c No./CIF. | Req. Loan Amount
    """

    if not start_date:
        frappe.throw(_("Start Date is required."))

    if not end_date:
        frappe.throw(_("End Date is required."))

    try:
        start_date_obj = getdate(start_date)
        end_date_obj = getdate(end_date)
    except Exception:
        frappe.throw(_("Please select valid Start Date and End Date."))

    if start_date_obj > end_date_obj:
        frappe.throw(_("Start Date cannot be greater than End Date."))

    # PostgreSQL / Finacle query.
    # DISTINCT ON (acid) is valid here because execute_finacle_query()
    # runs this in Finacle PostgreSQL, not Frappe MariaDB.
    query = """
        SELECT
            g.cif_id,
            g.foracid AS ac_no,
            g.acct_name,
            g.acct_opn_date,
            g.acct_cls_date,
            g.sol_id,
            s.sol_desc,

            CASE
                WHEN g.schm_type = 'LAA'
                THEN l.dis_amt
                ELSE lh.sanct_lim
            END AS dis_amt,

            lr.flow_amt,
            e.interest_rate,
            g.clr_bal_amt,
            g.cum_cr_amt AS total_amt_received,
            g.schm_code,
            g2.schm_desc,
            g.schm_type,

            CASE
                WHEN g.schm_type = 'LAA'
                THEN l.rep_perd_mths
                ELSE NULL
            END AS rep_perd_mths,

            l2.lim_exp_date,

            CASE
                WHEN g.schm_type = 'LAA'
                THEN l.ei_perd_start_date
                ELSE NULL
            END AS ei_perd_start_date,

            CASE
                WHEN g.schm_type = 'LAA'
                THEN l.ei_perd_end_date
                ELSE NULL
            END AS ei_perd_end_date,

            g.acct_cls_flg,
            a.address_line1,
            a.address_line2,
            s.division_name,
            s.region_name,
            s.circle_office_name

        FROM tbaadm.gam g

        JOIN tbaadm.sol s
            ON g.sol_id = s.sol_id

        JOIN tbaadm.gsp g2
            ON g.schm_code = g2.schm_code

        LEFT JOIN crmuser.accounts a
            ON g.cif_id = a.orgkey

        LEFT JOIN tbaadm.lam l
            ON g.acid = l.acid

        LEFT JOIN tbaadm.eit e
            ON e.entity_id = g.acid

        LEFT JOIN tbaadm.lht l2
            ON l2.acid = g.acid

        LEFT JOIN (
            SELECT DISTINCT ON (acid)
                acid,
                sanct_lim
            FROM tbaadm.lht
            ORDER BY acid, applicable_date DESC
        ) lh
            ON lh.acid = g.acid

        LEFT JOIN (
            SELECT
                acid,
                MAX(flow_amt) AS flow_amt
            FROM tbaadm.lrs
            GROUP BY acid
        ) lr
            ON lr.acid = g.acid

        WHERE (
            g.schm_type = 'LAA'
            OR g.schm_code IN ('1301', '1302', '3028', '3047', '3050')
        )
        AND g.entity_cre_flg = 'Y'
        AND g.del_flg = 'N'
        AND g.acct_opn_date BETWEEN %(start_date)s AND %(end_date)s

        ORDER BY
            s.circle_office_name NULLS LAST,
            s.region_name NULLS LAST,
            s.sol_desc NULLS LAST,
            g.acct_name NULLS LAST,
            g.foracid NULLS LAST
    """

    params = {
        "start_date": start_date_obj,
        "end_date": end_date_obj
    }

    rows = execute_finacle_query(query, params)

    if not rows:
        frappe.msgprint(
            _("No loan records found for the selected date range."),
            title=_("No Records"),
            indicator="orange"
        )
        return

    # Normalize Zone names and group data zone-wise.
    zone_wise_rows = {}

    for row in rows:
        zone = (
            row.get("circle_office_name")
            or "Unassigned Zone"
        ).strip()

        zone_wise_rows.setdefault(zone, []).append(row)

    document = DocxDocument()

    section = document.sections[0]
    section.top_margin = Inches(0.45)
    section.bottom_margin = Inches(0.45)
    section.left_margin = Inches(0.35)
    section.right_margin = Inches(0.35)

    normal_style = document.styles["Normal"]
    normal_style.font.name = "Arial"
    normal_style.font.size = Pt(8)

    title = document.add_paragraph()
    title.alignment = WD_ALIGN_PARAGRAPH.CENTER

    title_run = title.add_run("LOAN MEETING REGISTER")
    title_run.bold = True
    title_run.font.name = "Arial"
    title_run.font.size = Pt(15)

    date_line = document.add_paragraph()
    date_line.alignment = WD_ALIGN_PARAGRAPH.CENTER

    date_run = date_line.add_run(
        "Account Opening Date: {0} To {1}".format(
            start_date_obj.strftime("%d-%m-%Y"),
            end_date_obj.strftime("%d-%m-%Y")
        )
    )
    date_run.bold = True
    date_run.font.name = "Arial"
    date_run.font.size = Pt(9)

    document.add_paragraph("")

    headers = [
        "Zone",
        "Region",
        "Branch",
        "Customer Name",
        "Scheme Name",
        "Months",
        "A/c No./CIF.",
        "Req. Loan Amount"
    ]

    table = document.add_table(rows=1, cols=len(headers))
    table.style = "Table Grid"
    table.autofit = False

    header_row = table.rows[0]

    for column_index, header in enumerate(headers):
        cell = header_row.cells[column_index]

        set_docx_cell_background(cell, "D9E1F2")

        set_docx_cell_text(
            cell,
            header,
            bold=True,
            alignment=WD_ALIGN_PARAGRAPH.CENTER,
            font_size=8
        )

    column_widths = [
        Inches(1.00),  # Zone
        Inches(1.00),  # Region
        Inches(1.10),  # Branch
        Inches(1.70),  # Customer Name
        Inches(1.20),  # Scheme Name
        Inches(0.65),  # Months
        Inches(1.25),  # A/c No./CIF.
        Inches(1.15),  # Req. Loan Amount
    ]

    for table_row in table.rows:
        for column_index, width in enumerate(column_widths):
            table_row.cells[column_index].width = width

    grand_total_records = 0
    grand_total_amount = 0.0

    for zone, zone_rows in sorted(
        zone_wise_rows.items(),
        key=lambda item: item[0].lower()
    ):
        zone_total_records = 0
        zone_total_amount = 0.0

        for row in zone_rows:
            record_row = table.add_row()

            for column_index, width in enumerate(column_widths):
                record_row.cells[column_index].width = width

            cif_id = row.get("cif_id") or ""
            ac_no = row.get("ac_no") or ""

            # Requirement: cif_id as A/c No./CIF.
            # If CIF is blank, account number is used as fallback.
            account_or_cif = cif_id or ac_no

            requested_amount = safe_float(row.get("dis_amt"))

            values = [
                zone,
                row.get("region_name") or "",
                row.get("sol_desc") or "",
                row.get("acct_name") or "",
                row.get("schm_desc") or "",
                "APR",
                account_or_cif,
                format_amount(requested_amount),
            ]

            for column_index, value in enumerate(values):
                alignment = WD_ALIGN_PARAGRAPH.LEFT

                if column_index in (5, 7):
                    alignment = WD_ALIGN_PARAGRAPH.CENTER

                set_docx_cell_text(
                    record_row.cells[column_index],
                    value,
                    bold=False,
                    alignment=alignment,
                    font_size=7
                )

            zone_total_records += 1
            zone_total_amount += requested_amount
            grand_total_records += 1
            grand_total_amount += requested_amount

        # Zone subtotal row: background #63A4F7.
        zone_total_row = table.add_row()

        for column_index, width in enumerate(column_widths):
            zone_total_row.cells[column_index].width = width

        for cell in zone_total_row.cells:
            set_docx_cell_background(cell, "63A4F7")

        # Merge columns Zone through A/c No./CIF.
        merged_cell = zone_total_row.cells[0].merge(zone_total_row.cells[6])

        set_docx_cell_text(
            merged_cell,
            "{0} Total — Records: {1}".format(
                zone,
                zone_total_records
            ),
            bold=True,
            alignment=WD_ALIGN_PARAGRAPH.RIGHT,
            font_size=8
        )

        set_docx_cell_text(
            zone_total_row.cells[7],
            format_amount(zone_total_amount),
            bold=True,
            alignment=WD_ALIGN_PARAGRAPH.CENTER,
            font_size=8
        )

    # Grand total row: background #D9E1F2.
    grand_total_row = table.add_row()

    for column_index, width in enumerate(column_widths):
        grand_total_row.cells[column_index].width = width

    for cell in grand_total_row.cells:
        set_docx_cell_background(cell, "D9E1F2")

    grand_merged_cell = grand_total_row.cells[0].merge(
        grand_total_row.cells[6]
    )

    set_docx_cell_text(
        grand_merged_cell,
        "Grand Total — Records: {0}".format(grand_total_records),
        bold=True,
        alignment=WD_ALIGN_PARAGRAPH.RIGHT,
        font_size=9
    )

    set_docx_cell_text(
        grand_total_row.cells[7],
        format_amount(grand_total_amount),
        bold=True,
        alignment=WD_ALIGN_PARAGRAPH.CENTER,
        font_size=9
    )

    document.add_paragraph("")

    summary = document.add_paragraph()
    summary.alignment = WD_ALIGN_PARAGRAPH.LEFT

    summary_run = summary.add_run(
        "Total Records: {0}    |    Total Requested Loan Amount: {1}".format(
            grand_total_records,
            format_amount(grand_total_amount)
        )
    )
    summary_run.bold = True
    summary_run.font.name = "Arial"
    summary_run.font.size = Pt(9)

    file_buffer = io.BytesIO()
    document.save(file_buffer)
    file_buffer.seek(0)

    frappe.response.filename = (
        "Loan_Meeting_Register_{0}_to_{1}.docx".format(
            start_date_obj.strftime("%Y-%m-%d"),
            end_date_obj.strftime("%Y-%m-%d")
        )
    )
    frappe.response.filecontent = file_buffer.getvalue()
    frappe.response.type = "download"
    frappe.response.display_content_as = "attachment"
