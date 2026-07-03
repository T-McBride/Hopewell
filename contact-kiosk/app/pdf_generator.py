"""
Builds the printable directory as a real foldable booklet, matching the
classic church/community-directory layout: a cover page, a section of
individual photos arranged in a grid, then a text-only alphabetical
listing (name/phone/email/address, phone-book style with letter
headers - no photos there, matching the reference layout).

Two stages:

1. _build_content_pdf() - lays out the cover, photo grid, and text
   listing at HALF-LETTER trim size (5.5in x 8.5in) - this is the size
   each booklet page will be once the final sheet is folded. Done with
   reportlab, since its Frame/PageTemplate flow handles the automatic
   two-column text flow for the listing section for us.

2. _impose_booklet() - takes those half-letter pages and merges them in
   pairs onto landscape Letter sheets (11in x 8.5in), in standard
   saddle-stitch imposition order, using pypdf. The result is a PDF where
   each page IS a physical sheet to print: print double-sided (flip on
   the SHORT edge, since the pages are landscape), then fold the whole
   stack in half and staple along the fold.

reportlab is used for layout (no system library dependencies - matters on
a Raspberry Pi); pypdf is used only for the page-merging/imposition step.
"""
import io
from io import BytesIO
from pathlib import Path

from PIL import Image as PILImage
from pypdf import PageObject, PdfReader, PdfWriter, Transformation
from reportlab.lib import colors
from reportlab.lib.units import inch
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.platypus import (
    BaseDocTemplate,
    Frame,
    Image,
    KeepTogether,
    NextPageTemplate,
    PageBreak,
    PageTemplate,
    Paragraph,
    Spacer,
    Table,
    TableStyle,
)

PHOTO_DIR = Path(__file__).parent / "data" / "photos"

# Half-letter: the trim size of each booklet page once a Letter sheet is
# folded in half down the middle.
HALF_LETTER_WIDTH = 5.5 * inch
HALF_LETTER_HEIGHT = 8.5 * inch

MARGIN = 0.35 * inch
GUTTER = 0.28 * inch
COLUMN_WIDTH = (HALF_LETTER_WIDTH - 2 * MARGIN - GUTTER) / 2
COLUMN_HEIGHT = HALF_LETTER_HEIGHT - 2 * MARGIN

# Photo grid: 2 columns x 4 rows per page, matching the reference layout's density
GRID_COLS = 2
GRID_ROWS = 4
PHOTOS_PER_PAGE = GRID_COLS * GRID_ROWS
PHOTO_GRID_SIZE = 1.3 * inch

styles = getSampleStyleSheet()
cover_title_style = ParagraphStyle(
    "CoverTitle", parent=styles["Title"], fontSize=20, leading=24, alignment=1
)
cover_subtitle_style = ParagraphStyle(
    "CoverSubtitle", parent=styles["Normal"], fontSize=10.5, alignment=1,
    textColor=colors.grey, spaceBefore=10,
)
cover_note_style = ParagraphStyle(
    "CoverNote", parent=styles["Normal"], fontSize=9, alignment=1,
    textColor=colors.black, spaceBefore=48, leading=11,
)
section_title_style = ParagraphStyle(
    "SectionTitle", parent=styles["Title"], fontSize=18, alignment=1, textColor=colors.HexColor("#2f6f4f")
)
photo_name_style = ParagraphStyle(
    "PhotoName", parent=styles["Normal"], fontSize=10.5, leading=10.5, alignment=1,
    fontName="Helvetica-Bold", spaceBefore=4,
)
letter_header_style = ParagraphStyle(
    "LetterHeader", parent=styles["Heading2"], fontSize=14, spaceBefore=6, spaceAfter=4,
    textColor=colors.HexColor("#2f6f4f"),
)
name_style = ParagraphStyle(
    "ContactName", parent=styles["Normal"], fontSize=10.5, leading=12, fontName="Helvetica-Bold"
)
detail_style = ParagraphStyle(
    "ContactDetail", parent=styles["Normal"], fontSize=9.8, leading=10, textColor=colors.black
)


# ---------------------------------------------------------------------------
# Photo handling
# ---------------------------------------------------------------------------

def _square_photo_reader(photo_path):
    """Center-crop a contact's photo to a square so the grid doesn't stretch
    non-square camera captures, then hand it back as a file-like object
    reportlab's Image flowable can embed directly."""
    if not photo_path:
        return None
    full_path = PHOTO_DIR / photo_path
    if not full_path.exists():
        return None
    img = PILImage.open(full_path).convert("RGB")
    w, h = img.size
    side = min(w, h)
    left = (w - side) // 2
    top = (h - side) // 2
    cropped = img.crop((left, top, left + side, top + side))
    buf = io.BytesIO()
    cropped.save(buf, format="JPEG", quality=85)
    buf.seek(0)
    return buf


# ---------------------------------------------------------------------------
# Section 1: cover / divider pages
# ---------------------------------------------------------------------------

def _cover_flowables(contacts, include_home_address, org_name):
    return [
        Spacer(1, 1.8 * inch),
        Paragraph(org_name, cover_title_style),
        Paragraph(
            f"{len(contacts)} contact(s)" + (" - includes home addresses" if include_home_address else ""),
            cover_subtitle_style,
        ),
        Paragraph(
            "Print double-sided (flip on the short edge), then fold this "
            "stack in half and staple along the fold to assemble.",
            cover_note_style,
        ),
    ]


def _divider_flowables(title):
    return [Spacer(1, 3.2 * inch), Paragraph(title, section_title_style)]


# ---------------------------------------------------------------------------
# Section 2: photo grid
# ---------------------------------------------------------------------------

def _photo_grid_cell(c):
    reader = _square_photo_reader(c.get("photo_path"))
    photo = Image(reader, width=PHOTO_GRID_SIZE, height=PHOTO_GRID_SIZE) if reader else Spacer(
        PHOTO_GRID_SIZE, PHOTO_GRID_SIZE
    )
    return [photo, Paragraph(c["full_name"], photo_name_style)]


def _photo_grid_flowables(contacts):
    flowables = []
    col_width = (HALF_LETTER_WIDTH - 2 * MARGIN) / GRID_COLS
    chunks = [contacts[i : i + PHOTOS_PER_PAGE] for i in range(0, len(contacts), PHOTOS_PER_PAGE)]

    for chunk_index, chunk in enumerate(chunks):
        rows = []
        for r in range(GRID_ROWS):
            row = []
            for col in range(GRID_COLS):
                idx = r * GRID_COLS + col
                row.append(_photo_grid_cell(chunk[idx]) if idx < len(chunk) else "")
            rows.append(row)

        table = Table(rows, colWidths=[col_width] * GRID_COLS)
        table.setStyle(
            TableStyle(
                [
                    ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                    ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                    ("TOPPADDING", (0, 0), (-1, -1), 10),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 10),
                ]
            )
        )
        flowables.append(table)
        if chunk_index < len(chunks) - 1:
            flowables.append(PageBreak())

    return flowables


# ---------------------------------------------------------------------------
# Section 3: text-only alphabetical listing (no photos - matches reference)
# ---------------------------------------------------------------------------

def _contact_text_entry(c, include_home_address):
    lines = [Paragraph(c["full_name"], name_style)]
    if c.get("phone_mobile"):
        lines.append(Paragraph(c["phone_mobile"], detail_style))
    if c.get("email"):
        lines.append(Paragraph(c["email"], detail_style))
    if include_home_address and c.get("home_address"):
        s = c["home_address"]
        #lines.append(Paragraph(c["home_address"], detail_style))
    if include_home_address and c.get("city"):
        s = s + c["city"]
        #lines.append(c["city"])
    if include_home_address and c.get("state"):
        #lines.append(c["state"])
        s = s + c["state"]
    if include_home_address and c.get("zip"):
        #lines.append(c["zip"])
        s = s + c["zip"]
    if include_home_address:
        lines.append(Paragraph(s, detail_style))
    
    lines.append(Spacer(1, 8))
    return KeepTogether(lines)


def _text_listing_flowables(sorted_contacts, include_home_address):
    flowables = []
    current_letter = None
    for c in sorted_contacts:
        first_letter = c["full_name"][0].upper() if c["full_name"] else "#"
        if first_letter != current_letter:
            current_letter = first_letter
            flowables.append(Paragraph(current_letter, letter_header_style))
        flowables.append(_contact_text_entry(c, include_home_address))
    return flowables


# ---------------------------------------------------------------------------
# Notes page
# ---------------------------------------------------------------------------

def _notes_flowables():
    rows = [[""] for _ in range(20)]
    table = Table(rows, colWidths=[HALF_LETTER_WIDTH - 2 * MARGIN], rowHeights=[0.32 * inch] * 20)
    table.setStyle(
        TableStyle(
            [
                ("LINEBELOW", (0, 0), (-1, -1), 0.5, colors.lightgrey),
            ]
        )
    )
    return [Paragraph("Notes", section_title_style), Spacer(1, 18), table]


# ---------------------------------------------------------------------------
# Assembly
# ---------------------------------------------------------------------------

def _draw_footer(canvas, doc):
    if doc.page == 1:
        return  # no footer on the front cover
    canvas.saveState()
    canvas.setFont("Helvetica", 7)
    canvas.setFillColor(colors.grey)
    canvas.drawCentredString(HALF_LETTER_WIDTH / 2, MARGIN * 0.45, str(doc.page))
    canvas.restoreState()


def _build_content_pdf(contacts, include_home_address: bool, org_name: str, extra_blank_pages: int = 0) -> bytes:
    """Half-letter content PDF (pre-imposition): cover, photo grid, text listing."""
    buffer = BytesIO()

    single_frame = Frame(
        MARGIN, MARGIN, HALF_LETTER_WIDTH - 2 * MARGIN, HALF_LETTER_HEIGHT - 2 * MARGIN, id="single"
    )
    left_frame = Frame(MARGIN, MARGIN, COLUMN_WIDTH, COLUMN_HEIGHT, id="left")
    right_frame = Frame(MARGIN + COLUMN_WIDTH + GUTTER, MARGIN, COLUMN_WIDTH, COLUMN_HEIGHT, id="right")

    doc = BaseDocTemplate(
        buffer,
        pagesize=(HALF_LETTER_WIDTH, HALF_LETTER_HEIGHT),
        leftMargin=MARGIN, rightMargin=MARGIN, topMargin=MARGIN, bottomMargin=MARGIN,
        title=org_name,
    )
    doc.addPageTemplates(
        [
            PageTemplate(id="single", frames=[single_frame], onPage=_draw_footer),
            PageTemplate(id="content", frames=[left_frame, right_frame], onPage=_draw_footer),
        ]
    )

    sorted_contacts = sorted(contacts, key=lambda c: c["full_name"].lower())

    story = []
    story += _cover_flowables(contacts, include_home_address, org_name)

    if contacts:
        story.append(PageBreak())
        story += _divider_flowables("Photo Directory")
        story.append(PageBreak())
        story += _photo_grid_flowables(sorted_contacts)

        story.append(NextPageTemplate("single"))
        story.append(PageBreak())
        story += _divider_flowables("Alphabetical Listing")
        story.append(NextPageTemplate("content"))
        story.append(PageBreak())
        story += _text_listing_flowables(sorted_contacts, include_home_address)

    story.append(NextPageTemplate("single"))
    story.append(PageBreak())
    story += _notes_flowables()

    for _ in range(extra_blank_pages):
        story.append(PageBreak())
        story.append(Spacer(1, 0.001))  # forces the blank page to actually flush -
        # reportlab silently drops a trailing PageBreak() with nothing after it

    doc.build(story)
    return buffer.getvalue()


def _impose_booklet(content_pdf_bytes: bytes) -> bytes:
    """
    Merge half-letter content pages, two at a time, onto landscape Letter
    sheets in standard saddle-stitch order so the result prints correctly
    and reads in order once folded.

    For N pages (N a multiple of 4) and S = N/4 sheets, sheet s (0-indexed):
      front: left = N-1-2s,  right = 2s        (0-indexed page numbers)
      back:  left = 1+2s,    right = N-2-2s
    """
    reader = PdfReader(BytesIO(content_pdf_bytes))
    pages = reader.pages
    n = len(pages)
    if n % 4 != 0:
        raise ValueError(f"Content PDF must be padded to a multiple of 4 pages, got {n}")
    sheets = n // 4

    writer = PdfWriter()

    def blank_sheet():
        return PageObject.create_blank_page(width=HALF_LETTER_WIDTH * 2, height=HALF_LETTER_HEIGHT)

    def place(dest_page, src_index, x_offset):
        dest_page.merge_transformed_page(pages[src_index], Transformation().translate(tx=x_offset, ty=0))

    for s in range(sheets):
        front_left = n - 1 - 2 * s
        front_right = 2 * s
        back_left = 1 + 2 * s
        back_right = n - 2 - 2 * s

        front = blank_sheet()
        place(front, front_left, 0)
        place(front, front_right, HALF_LETTER_WIDTH)
        writer.add_page(front)

        back = blank_sheet()
        place(back, back_left, 0)
        place(back, back_right, HALF_LETTER_WIDTH)
        writer.add_page(back)

    out = BytesIO()
    writer.write(out)
    return out.getvalue()


def build_directory_pdf(contacts: list[dict], include_home_address: bool, org_name: str = "Hopewell directory") -> bytes:
    """Public entry point: returns the final, print-ready booklet PDF bytes."""
    content_bytes = _build_content_pdf(contacts, include_home_address, org_name)
    page_count = len(PdfReader(BytesIO(content_bytes)).pages)

    remainder = page_count % 4
    if remainder != 0:
        pad = 4 - remainder
        content_bytes = _build_content_pdf(contacts, include_home_address, org_name, extra_blank_pages=pad)

    return _impose_booklet(content_bytes)
