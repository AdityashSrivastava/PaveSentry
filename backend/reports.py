import io
import csv
from datetime import datetime
from pathlib import Path
import openpyxl
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.utils import get_column_letter

from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib import colors
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, KeepTogether, PageBreak
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.pdfgen import canvas

def format_currency_inr(val):
    if val is None or val == "":
        return "₹0"
    try:
        val = float(val)
        abs_val = abs(val)
        if abs_val >= 10000000:
            return f"₹{val / 10000000:.2f} Cr"
        elif abs_val >= 100000:
            return f"₹{val / 100000:.2f} L"
        else:
            return f"₹{int(val):,}"
    except (ValueError, TypeError):
        return str(val)

# ==============================================================================
# 1. CSV EXPORT (RFC 4180 Standard with UTF-8-BOM)
# ==============================================================================
def generate_schedule_csv(scheduled_segments, summary_info=None) -> bytes:
    """
    Generates an RFC 4180 compliant CSV export containing the optimized 12-month
    work schedule with corridor IDs, PWD divisions, estimated costs, and net savings.
    Uses UTF-8 with BOM so Excel on Windows opens Indian currency symbols properly.
    """
    output = io.StringIO()
    writer = csv.writer(output)
    
    # Metadata Header
    gen_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    writer.writerow(["# PaveSentry: Delhi NCT Pavement Intelligence System"])
    writer.writerow(["# Government of NCT of Delhi — Public Works Department (PWD) & MCD"])
    writer.writerow([f"# Optimized 12-Month Work Schedule Export (Generated: {gen_time})"])
    if summary_info:
        writer.writerow([
            f"# Annual Budget: INR {summary_info.get('annual_budget_inr', 0):,}",
            f"Allocated Spend: INR {summary_info.get('total_spent_inr', 0):,}",
            f"Net Projected Savings: INR {summary_info.get('total_net_savings_inr', 0):,}",
            f"Corridors Scheduled: {summary_info.get('scheduled_count', len(scheduled_segments))}",
            f"Total KM: {summary_info.get('total_km_repaired', 0)} km"
        ])
    writer.writerow([]) # Blank row
    
    # Column Headers
    headers = [
        "Corridor ID",
        "Corridor Name & Chainage",
        "PWD Division",
        "Administrative Zone",
        "Road Classification",
        "Length (km)",
        "Carriageway Lanes",
        "Surface Material",
        "Pavement Condition Index (PCI)",
        "Roughness Index (IRI m/km)",
        "Failure Risk Level",
        "Structural Priority Score",
        "Scheduled Month",
        "Execution Month No",
        "Mandatory Timeline (Days)",
        "IRC Treatment Specification",
        "Estimated Preventive Tender Cost (INR)",
        "Reactive Cost Avoided (INR)",
        "Net Taxpayer Savings (INR)",
        "CSIR-CRRI Audit Compliance Code",
        "Est Time to Failure (Months)"
    ]
    writer.writerow(headers)
    
    for s in scheduled_segments:
        seg_name = s.get("name") or s.get("road_name") or "Corridor"
        sched_time = s.get("scheduled_month") or (f"{s.get('year_label', 'Year 1')} · {s.get('scheduled_quarter', 'Q1')}" if s.get("year_label") else "Month 1")
        pci_val = s.get("pci") if s.get("pci") is not None else s.get("pre_repair_pci", 70)
        risk_lvl = s.get("predicted_risk_level") or ("High" if pci_val < 55 else ("Medium" if pci_val < 70 else "Low"))
        react_avoided = s.get("reactive_avoided_inr") or s.get("avoided_reactive_inr") or 0
        crri_code = s.get("crri_compliance_code") or s.get("tender_code") or ""
        
        writer.writerow([
            s.get("segment_id", ""),
            seg_name,
            s.get("pwd_division", ""),
            s.get("city_zone", ""),
            s.get("road_type", "Arterial"),
            s.get("length_km", 0),
            s.get("lanes", 0),
            s.get("surface_type", "Bituminous Concrete"),
            pci_val,
            s.get("iri", 2.5),
            risk_lvl,
            s.get("priority_score", 0),
            sched_time,
            s.get("month_number", ""),
            s.get("tender_timeline_days", 45),
            s.get("recommended_action", "Preventive Maintenance"),
            s.get("allocated_cost_inr", 0),
            react_avoided,
            s.get("net_savings_inr", 0),
            crri_code,
            s.get("est_time_to_failure_months", "")
        ])
        
    csv_text = output.getvalue()
    # Prepend UTF-8 BOM so Excel opens with proper encoding
    return ("\ufeff" + csv_text).encode("utf-8")


# ==============================================================================
# 2. EXCEL EXPORT (.xlsx — Formatted Multi-Sheet Executive Workbook)
# ==============================================================================
def generate_schedule_excel(scheduled_segments, summary_info=None) -> bytes:
    """
    Generates a formatted, multi-tab Microsoft Excel (.xlsx) workbook using openpyxl:
    - Sheet 1: 'Tender_Work_Schedule' (Formatted table with PWD headers, currency, and formulas)
    - Sheet 2: 'Executive_Audit_Summary' (Division-level summaries and CSIR-CRRI audit rules)
    """
    wb = openpyxl.Workbook()
    
    # --------------------------------------------------------------------------
    # Styles Setup
    # --------------------------------------------------------------------------
    title_font = Font(name="Segoe UI", size=15, bold=True, color="1E3A8A")
    subtitle_font = Font(name="Segoe UI", size=10, italic=True, color="475569")
    meta_font = Font(name="Segoe UI", size=9, bold=True, color="1E293B")
    
    header_fill = PatternFill(start_color="1E3A8A", end_color="1E3A8A", fill_type="solid")
    header_font = Font(name="Segoe UI", size=10, bold=True, color="FFFFFF")
    
    zebra_fill = PatternFill(start_color="F8FAFC", end_color="F8FAFC", fill_type="solid")
    white_fill = PatternFill(start_color="FFFFFF", end_color="FFFFFF", fill_type="solid")
    
    high_risk_fill = PatternFill(start_color="FEE2E2", end_color="FEE2E2", fill_type="solid")
    high_risk_font = Font(name="Segoe UI", size=9, bold=True, color="991B1B")
    
    med_risk_fill = PatternFill(start_color="FEF3C7", end_color="FEF3C7", fill_type="solid")
    med_risk_font = Font(name="Segoe UI", size=9, bold=True, color="92400E")
    
    low_risk_fill = PatternFill(start_color="D1FAE5", end_color="D1FAE5", fill_type="solid")
    low_risk_font = Font(name="Segoe UI", size=9, bold=True, color="065F46")
    
    border_thin = Side(style="thin", color="E2E8F0")
    cell_border = Border(left=border_thin, right=border_thin, top=border_thin, bottom=border_thin)
    
    total_fill = PatternFill(start_color="E2E8F0", end_color="E2E8F0", fill_type="solid")
    total_font = Font(name="Segoe UI", size=10, bold=True, color="0F172A")
    
    # --------------------------------------------------------------------------
    # Sheet 1: Work Order Schedule
    # --------------------------------------------------------------------------
    ws1 = wb.active
    ws1.title = "12-Month Tender Schedule"
    ws1.views.sheetView[0].showGridLines = True
    
    # Title Block
    ws1["A1"] = "GOVERNMENT OF NATIONAL CAPITAL TERRITORY OF DELHI — PUBLIC WORKS DEPARTMENT (PWD) & MCD"
    ws1["A1"].font = title_font
    
    ws1["A2"] = "EXECUTIVE WORK ORDER SCHEDULE & 12-MONTH CAPITAL MAINTENANCE PLAN (FY 2026-27)"
    ws1["A2"].font = Font(name="Segoe UI", size=12, bold=True, color="0F766E")
    
    gen_str = datetime.now().strftime("%d-%b-%Y %H:%M")
    ws1["A3"] = f"Statutory Compliance: IRC:82-2015, IRC:SP:81-2008, IRC:37-2018 | CSIR-CRRI Audited | Generated: {gen_str}"
    ws1["A3"].font = subtitle_font
    
    # KPI Callout Row
    if summary_info:
        kpi_data = [
            ("Sanctioned Budget", summary_info.get("annual_budget_inr", 100000000)),
            ("Tender Outlay", summary_info.get("total_spent_inr", 0)),
            ("Net Taxpayer Savings", summary_info.get("total_net_savings_inr", 0)),
            ("Corridors Scheduled", summary_info.get("scheduled_count", len(scheduled_segments))),
            ("Total Length (km)", summary_info.get("total_km_repaired", 0)),
            ("Projected ROI", f"{summary_info.get('roi_percentage', 0)}%")
        ]
        
        for idx, (label, val) in enumerate(kpi_data):
            col_letter = get_column_letter(idx * 3 + 1)
            col_end = get_column_letter(idx * 3 + 2)
            cell_ref = f"{col_letter}5"
            val_ref = f"{col_letter}6"
            
            ws1[cell_ref] = label
            ws1[cell_ref].font = Font(name="Segoe UI", size=8, color="64748B", bold=True)
            
            if isinstance(val, (int, float)):
                ws1[val_ref] = val
                ws1[val_ref].number_format = '₹#,##,##0'
            else:
                ws1[val_ref] = val
            ws1[val_ref].font = Font(name="Segoe UI", size=11, bold=True, color="0F172A")
            
    # Table Headers at Row 8
    start_row = 8
    columns = [
        ("Corridor ID", 14),
        ("Corridor / Road Name", 36),
        ("PWD Division", 28),
        ("Administrative Zone", 18),
        ("Type", 12),
        ("Length (km)", 12),
        ("Lanes", 8),
        ("Surface Material", 20),
        ("PCI", 8),
        ("IRI (m/km)", 10),
        ("Risk Level", 12),
        ("Priority", 10),
        ("Schedule Month", 15),
        ("Timeline (Days)", 14),
        ("Recommended IRC Treatment", 32),
        ("Estimated Tender Cost (INR)", 24),
        ("Reactive Avoided (INR)", 22),
        ("Net Public Savings (INR)", 22),
        ("CSIR-CRRI Audit Code", 22)
    ]
    
    for c_idx, (col_name, col_width) in enumerate(columns, start=1):
        cell = ws1.cell(row=start_row, column=c_idx, value=col_name)
        cell.fill = header_fill
        cell.font = header_font
        cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
        cell.border = cell_border
        ws1.column_dimensions[get_column_letter(c_idx)].width = col_width
        
    ws1.row_dimensions[start_row].height = 28
    
    # Populate Rows
    current_r = start_row + 1
    for s_idx, s in enumerate(scheduled_segments):
        row_fill = zebra_fill if s_idx % 2 == 1 else white_fill
        
        vals = [
            s.get("segment_id", ""),
            s.get("name", ""),
            s.get("pwd_division", ""),
            s.get("city_zone", ""),
            s.get("road_type", ""),
            s.get("length_km", 0),
            s.get("lanes", 0),
            s.get("surface_type", ""),
            s.get("pci", 0),
            s.get("iri", 0),
            s.get("predicted_risk_level", ""),
            s.get("priority_score", 0),
            s.get("scheduled_month", ""),
            s.get("tender_timeline_days", 45),
            s.get("recommended_action", ""),
            s.get("allocated_cost_inr", 0),
            s.get("reactive_avoided_inr", 0),
            s.get("net_savings_inr", 0),
            s.get("crri_compliance_code", "")
        ]
        
        for c_idx, val in enumerate(vals, start=1):
            cell = ws1.cell(row=current_r, column=c_idx, value=val)
            cell.fill = row_fill
            cell.border = cell_border
            cell.font = Font(name="Segoe UI", size=9)
            
            # Alignments & Number formats
            if c_idx in [6, 9, 10, 12]:
                cell.alignment = Alignment(horizontal="right")
                cell.number_format = '0.0'
            elif c_idx in [7, 14]:
                cell.alignment = Alignment(horizontal="center")
                cell.number_format = '#,##0'
            elif c_idx in [16, 17, 18]:
                cell.alignment = Alignment(horizontal="right")
                cell.number_format = '₹#,##,##0'
                if c_idx == 18:
                    cell.font = Font(name="Segoe UI", size=9, bold=True, color="047857")
            elif c_idx in [1, 9, 11, 13]:
                cell.alignment = Alignment(horizontal="center")
            else:
                cell.alignment = Alignment(horizontal="left")
                
            # Highlight Risk Badge
            if c_idx == 11:
                if val == "High":
                    cell.fill = high_risk_fill
                    cell.font = high_risk_font
                elif val == "Medium":
                    cell.fill = med_risk_fill
                    cell.font = med_risk_font
                else:
                    cell.fill = low_risk_fill
                    cell.font = low_risk_font
                    
        ws1.row_dimensions[current_r].height = 20
        current_r += 1
        
    # Total / Summary Row
    total_row = current_r
    ws1.cell(row=total_row, column=1, value="TOTAL / NET SCHEDULE OUTLAY").font = total_font
    for c in range(1, len(columns) + 1):
        cell = ws1.cell(row=total_row, column=c)
        cell.fill = total_fill
        cell.border = cell_border
        
    # Formulas for totals
    last_data_row = total_row - 1
    if last_data_row >= start_row + 1:
        # Sum Length
        len_cell = ws1.cell(row=total_row, column=6, value=f"=SUM(F{start_row+1}:F{last_data_row})")
        len_cell.font = total_font
        len_cell.number_format = '0.00 "km"'
        
        # Sum Tender Cost
        cost_cell = ws1.cell(row=total_row, column=16, value=f"=SUM(P{start_row+1}:P{last_data_row})")
        cost_cell.font = total_font
        cost_cell.number_format = '₹#,##,##0'
        
        # Sum Reactive Cost
        react_cell = ws1.cell(row=total_row, column=17, value=f"=SUM(Q{start_row+1}:Q{last_data_row})")
        react_cell.font = total_font
        react_cell.number_format = '₹#,##,##0'
        
        # Sum Net Savings
        sav_cell = ws1.cell(row=total_row, column=18, value=f"=SUM(R{start_row+1}:R{last_data_row})")
        sav_cell.font = Font(name="Segoe UI", size=10, bold=True, color="047857")
        sav_cell.number_format = '₹#,##,##0'
        
    ws1.row_dimensions[total_row].height = 24
    
    # --------------------------------------------------------------------------
    # Sheet 2: Executive Division & Audit Summary
    # --------------------------------------------------------------------------
    ws2 = wb.create_sheet(title="Division Audit Summary")
    ws2.views.sheetView[0].showGridLines = True
    
    ws2["A1"] = "CSIR-CRRI STATUTORY AUDIT & ADMINISTRATIVE DIVISION BREAKDOWN"
    ws2["A1"].font = title_font
    ws2["A2"] = "Division-wise Allocation, Quality Verification Standards, and DLP Warranty Terms"
    ws2["A2"].font = subtitle_font
    
    # Aggregate by Division
    div_stats = {}
    for s in scheduled_segments:
        div = s.get("pwd_division", "Delhi NCT Division")
        if div not in div_stats:
            div_stats[div] = {
                "count": 0,
                "length_km": 0.0,
                "cost": 0.0,
                "savings": 0.0
            }
        div_stats[div]["count"] += 1
        div_stats[div]["length_km"] += float(s.get("length_km", 0))
        div_stats[div]["cost"] += float(s.get("allocated_cost_inr", 0))
        div_stats[div]["savings"] += float(s.get("net_savings_inr", 0))
        
    headers_ws2 = [
        ("PWD Administrative Division", 36),
        ("Corridors Scheduled", 20),
        ("Total Length (km)", 18),
        ("Allocated Tender Cost (INR)", 26),
        ("Net Taxpayer Savings (INR)", 26)
    ]
    
    start_r2 = 5
    for c_idx, (h_name, w) in enumerate(headers_ws2, start=1):
        cell = ws2.cell(row=start_r2, column=c_idx, value=h_name)
        cell.fill = header_fill
        cell.font = header_font
        cell.alignment = Alignment(horizontal="center", vertical="center")
        cell.border = cell_border
        ws2.column_dimensions[get_column_letter(c_idx)].width = w
        
    r2 = start_r2 + 1
    for div_name, st in sorted(div_stats.items()):
        ws2.cell(row=r2, column=1, value=div_name).alignment = Alignment(horizontal="left")
        ws2.cell(row=r2, column=2, value=st["count"]).alignment = Alignment(horizontal="center")
        
        len_c = ws2.cell(row=r2, column=3, value=round(st["length_km"], 2))
        len_c.alignment = Alignment(horizontal="right")
        len_c.number_format = '0.00'
        
        cost_c = ws2.cell(row=r2, column=4, value=round(st["cost"], 2))
        cost_c.alignment = Alignment(horizontal="right")
        cost_c.number_format = '₹#,##,##0'
        
        sav_c = ws2.cell(row=r2, column=5, value=round(st["savings"], 2))
        sav_c.alignment = Alignment(horizontal="right")
        sav_c.number_format = '₹#,##,##0'
        sav_c.font = Font(name="Segoe UI", size=9, bold=True, color="047857")
        
        for c in range(1, 6):
            ws2.cell(row=r2, column=c).border = cell_border
        r2 += 1
        
    # Statutory Compliance Notes Box
    notes_r = r2 + 3
    ws2.cell(row=notes_r, column=1, value="MANDATORY CSIR-CRRI AUDIT & TENDER SPECIFICATIONS:").font = Font(name="Segoe UI", size=10, bold=True, color="1E3A8A")
    notes = [
        "1. Roughness Benchmark (IRC:SP:81 & IRC:82): Post-execution International Roughness Index (IRI) must not exceed 2.2 m/km.",
        "2. Defect Liability Period (DLP): 36 months mandatory guarantee for Bituminous Concrete overlays; 24 months for Micro-surfacing.",
        "3. Milestone Completion: Contractor to mobilize paving crews within 15 days of work order issue. Penalty of 1.0% per week for unjustified delay.",
        "4. Pre-Monsoon Clause: All resurfacing and storm drain culvert clearance must conclude prior to June 25th monsoon arrival."
    ]
    for idx, note in enumerate(notes, start=1):
        c = ws2.cell(row=notes_r + idx, column=1, value=note)
        c.font = Font(name="Segoe UI", size=9, color="334155")
        
    buffer = io.BytesIO()
    wb.save(buffer)
    return buffer.getvalue()


# ==============================================================================
# 3. EXECUTIVE WORK ORDER PDF (Official PWD/MCD & CSIR-CRRI Formatted)
# ==============================================================================
class NumberedCanvas(canvas.Canvas):
    """Adds official Delhi Government footer with Page X of Y and timestamp."""
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._saved_page_states = []

    def showPage(self):
        self._saved_page_states.append(dict(self.__dict__))
        self._startPage()

    def save(self):
        num_pages = len(self._saved_page_states)
        for state in self._saved_page_states:
            self.__dict__.update(state)
            self.draw_footer(num_pages)
            super().showPage()
        super().save()

    def draw_footer(self, page_count):
        self.saveState()
        self.setFont("Helvetica", 8)
        self.setFillColor(colors.HexColor("#64748B"))
        
        # Border line
        self.setStrokeColor(colors.HexColor("#CBD5E1"))
        self.setLineWidth(0.6)
        self.line(30, 28, 812, 28)
        
        # Footer text
        footer_text = f"Government of NCT of Delhi · PWD Road Infrastructure Division · CSIR-CRRI Audit Compliance Ref: CRRI/AUD/2026/PS-04"
        self.drawString(30, 16, footer_text)
        page_str = f"Page {self._pageNumber} of {page_count}"
        self.drawRightString(812, 16, page_str)
        self.restoreState()


def generate_executive_tender_pdf(scheduled_segments, summary_info=None, division_name=None) -> bytes:
    """
    Generates an official Executive Work Order PDF formatted to CPWD / Delhi PWD & MCD norms,
    ready for contractor e-tendering and CSIR-CRRI audit verification.
    Rendered on A4 Landscape.
    """
    buffer = io.BytesIO()
    # A4 Landscape: 841.89 x 595.27 points
    doc = SimpleDocTemplate(
        buffer,
        pagesize=landscape(A4),
        leftMargin=30,
        rightMargin=30,
        topMargin=26,
        bottomMargin=36
    )
    
    styles = getSampleStyleSheet()
    
    # Custom Paragraph Styles
    title_style = ParagraphStyle(
        "GovTitle",
        parent=styles["Normal"],
        fontName="Helvetica-Bold",
        fontSize=12,
        leading=14,
        textColor=colors.HexColor("#1E3A8A"),
        alignment=1 # Center
    )
    
    sub_title_style = ParagraphStyle(
        "GovSubTitle",
        parent=styles["Normal"],
        fontName="Helvetica-Bold",
        fontSize=10,
        leading=12,
        textColor=colors.HexColor("#0F766E"),
        alignment=1
    )
    
    doc_type_style = ParagraphStyle(
        "DocType",
        parent=styles["Normal"],
        fontName="Helvetica-Bold",
        fontSize=14,
        leading=16,
        textColor=colors.HexColor("#0F172A"),
        alignment=1,
        spaceBefore=3,
        spaceAfter=6
    )
    
    meta_style = ParagraphStyle(
        "MetaText",
        parent=styles["Normal"],
        fontName="Helvetica",
        fontSize=8.5,
        leading=11,
        textColor=colors.HexColor("#334155")
    )
    
    tbl_hdr_style = ParagraphStyle(
        "TblHdr",
        parent=styles["Normal"],
        fontName="Helvetica-Bold",
        fontSize=8,
        leading=9.5,
        textColor=colors.white,
        alignment=1
    )
    
    tbl_cell_style = ParagraphStyle(
        "TblCell",
        parent=styles["Normal"],
        fontName="Helvetica",
        fontSize=7.5,
        leading=9,
        textColor=colors.HexColor("#1E293B")
    )
    
    tbl_cell_bold = ParagraphStyle(
        "TblCellBold",
        parent=styles["Normal"],
        fontName="Helvetica-Bold",
        fontSize=7.5,
        leading=9,
        textColor=colors.HexColor("#1E293B")
    )
    
    tbl_cell_accent = ParagraphStyle(
        "TblCellAccent",
        parent=styles["Normal"],
        fontName="Helvetica-Bold",
        fontSize=7.5,
        leading=9,
        textColor=colors.HexColor("#047857"),
        alignment=2 # Right
    )
    
    clause_title_style = ParagraphStyle(
        "ClauseTitle",
        parent=styles["Normal"],
        fontName="Helvetica-Bold",
        fontSize=8.5,
        leading=10,
        textColor=colors.HexColor("#1E3A8A"),
        spaceBefore=4,
        spaceAfter=2
    )
    
    clause_body_style = ParagraphStyle(
        "ClauseBody",
        parent=styles["Normal"],
        fontName="Helvetica",
        fontSize=7.5,
        leading=9.5,
        textColor=colors.HexColor("#334155")
    )
    
    story = []
    
    # --------------------------------------------------------------------------
    # Official Letterhead Header
    # --------------------------------------------------------------------------
    story.append(Paragraph("GOVERNMENT OF NATIONAL CAPITAL TERRITORY OF DELHI", title_style))
    story.append(Paragraph("PUBLIC WORKS DEPARTMENT (PWD) — ROAD MAINTENANCE DIVISION", sub_title_style))
    story.append(Paragraph("IN TECHNICAL COLLABORATION WITH CSIR - CENTRAL ROAD RESEARCH INSTITUTE (CRRI)", ParagraphStyle("SubSub", parent=styles["Normal"], fontName="Helvetica", fontSize=8, leading=10, textColor=colors.HexColor("#64748B"), alignment=1)))
    story.append(Spacer(1, 4))
    
    story.append(Paragraph("OFFICIAL NOTICE INVITING TENDER (NIT) & EXECUTIVE WORK ORDER SCHEDULE", doc_type_style))
    story.append(Spacer(1, 2))
    
    # Meta Strip: Tender Ref, Issue Date, Compliance Standards
    nit_ref = f"NIT/PWD-DL/2026/R-042"
    today_str = datetime.now().strftime("%d-%b-%Y")
    zone_label = division_name if division_name and division_name != "all" else "Delhi NCT Arterial Network (All Divisions)"
    
    meta_table_data = [
        [
            Paragraph(f"<b>Tender Notice No:</b> {nit_ref}", meta_style),
            Paragraph(f"<b>Date of Notification:</b> {today_str}", meta_style),
            Paragraph(f"<b>Statutory Norms:</b> IRC:82-2015 · IRC:SP:81-2008 · IRC:37", meta_style),
            Paragraph(f"<b>Administrative Territory:</b> {zone_label}", meta_style)
        ]
    ]
    meta_tbl = Table(meta_table_data, colWidths=[200, 160, 220, 202])
    meta_tbl.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor("#F1F5F9")),
        ('TOPPADDING', (0, 0), (-1, -1), 4),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
        ('LEFTPADDING', (0, 0), (-1, -1), 6),
        ('RIGHTPADDING', (0, 0), (-1, -1), 6),
        ('BOX', (0, 0), (-1, -1), 0.5, colors.HexColor("#CBD5E1")),
    ]))
    story.append(meta_tbl)
    story.append(Spacer(1, 8))
    
    # --------------------------------------------------------------------------
    # Executive Financial & Technical Summary Callout Box
    # --------------------------------------------------------------------------
    summary = summary_info or {}
    annual_budget = summary.get("annual_budget_inr", 100000000)
    total_spent = summary.get("total_spent_inr", sum(s.get("allocated_cost_inr", 0) for s in scheduled_segments))
    total_savings = summary.get("total_net_savings_inr", sum(s.get("net_savings_inr", 0) for s in scheduled_segments))
    corridor_count = summary.get("scheduled_count", len(scheduled_segments))
    total_km = summary.get("total_km_repaired", sum(s.get("length_km", 0) for s in scheduled_segments))
    roi = summary.get("roi_percentage", round((total_savings / (total_spent + 1.0)) * 100.0, 1))
    
    fin_summary_data = [
        [
            Paragraph("<b>Sanctioned Budget</b>", meta_style),
            Paragraph("<b>Total Work Order Value</b>", meta_style),
            Paragraph("<b>Projected Public Savings</b>", meta_style),
            Paragraph("<b>Scheduled Corridors</b>", meta_style),
            Paragraph("<b>Repaired Network</b>", meta_style),
            Paragraph("<b>Lifecycle Capital ROI</b>", meta_style),
        ],
        [
            Paragraph(f"<b>{format_currency_inr(annual_budget)}</b>", ParagraphStyle("H1", parent=meta_style, fontName="Helvetica-Bold", fontSize=10, textColor=colors.HexColor("#1E3A8A"))),
            Paragraph(f"<b>{format_currency_inr(total_spent)}</b>", ParagraphStyle("H2", parent=meta_style, fontName="Helvetica-Bold", fontSize=10, textColor=colors.HexColor("#0F172A"))),
            Paragraph(f"<b>+{format_currency_inr(total_savings)}</b>", ParagraphStyle("H3", parent=meta_style, fontName="Helvetica-Bold", fontSize=10, textColor=colors.HexColor("#047857"))),
            Paragraph(f"<b>{corridor_count} Corridors</b>", ParagraphStyle("H4", parent=meta_style, fontName="Helvetica-Bold", fontSize=10, textColor=colors.HexColor("#1E293B"))),
            Paragraph(f"<b>{total_km:.1f} km</b>", ParagraphStyle("H5", parent=meta_style, fontName="Helvetica-Bold", fontSize=10, textColor=colors.HexColor("#1E293B"))),
            Paragraph(f"<b>{roi}%</b>", ParagraphStyle("H6", parent=meta_style, fontName="Helvetica-Bold", fontSize=10, textColor=colors.HexColor("#0F766E"))),
        ]
    ]
    fin_tbl = Table(fin_summary_data, colWidths=[130, 130, 132, 130, 130, 130])
    fin_tbl.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor("#E2E8F0")),
        ('BACKGROUND', (0, 1), (-1, 1), colors.HexColor("#FFFFFF")),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('TOPPADDING', (0, 0), (-1, -1), 3),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
        ('BOX', (0, 0), (-1, -1), 0.8, colors.HexColor("#94A3B8")),
        ('INNERGRID', (0, 0), (-1, -1), 0.4, colors.HexColor("#E2E8F0")),
    ]))
    story.append(fin_tbl)
    story.append(Spacer(1, 10))
    
    # --------------------------------------------------------------------------
    # Schedule of Work Items Table (Bill of Quantities / Corridor List)
    # --------------------------------------------------------------------------
    table_headers = [
        Paragraph("<b>Item / ID</b>", tbl_hdr_style),
        Paragraph("<b>Corridor Name & Chainage</b>", tbl_hdr_style),
        Paragraph("<b>PWD Division</b>", tbl_hdr_style),
        Paragraph("<b>Type / L (km)</b>", tbl_hdr_style),
        Paragraph("<b>PCI / IRI</b>", tbl_hdr_style),
        Paragraph("<b>Risk</b>", tbl_hdr_style),
        Paragraph("<b>Prescribed IRC Treatment</b>", tbl_hdr_style),
        Paragraph("<b>Tender Cost (₹)</b>", tbl_hdr_style),
        Paragraph("<b>Net Savings (₹)</b>", tbl_hdr_style),
        Paragraph("<b>Month</b>", tbl_hdr_style),
        Paragraph("<b>Days</b>", tbl_hdr_style),
        Paragraph("<b>CRRI Compliance</b>", tbl_hdr_style),
    ]
    
    sched_rows = [table_headers]
    for s_idx, s in enumerate(scheduled_segments):
        risk = s.get("predicted_risk_level", "Low")
        risk_color = "#991B1B" if risk == "High" else ("#B45309" if risk == "Medium" else "#047857")
        
        row_cells = [
            Paragraph(f"<b>{s.get('segment_id', '')}</b>", tbl_cell_bold),
            Paragraph(f"{s.get('name', '')}", tbl_cell_style),
            Paragraph(f"{s.get('pwd_division', '')}", tbl_cell_style),
            Paragraph(f"{s.get('road_type', '')} · {s.get('length_km', 0)} km", tbl_cell_style),
            Paragraph(f"<b>{s.get('pci', 0)}</b> | {s.get('iri', 0)}", tbl_cell_style),
            Paragraph(f"<font color='{risk_color}'><b>{risk}</b></font>", tbl_cell_style),
            Paragraph(f"{s.get('recommended_action', '')}", tbl_cell_style),
            Paragraph(f"{format_currency_inr(s.get('allocated_cost_inr', 0))}", tbl_cell_bold),
            Paragraph(f"+{format_currency_inr(s.get('net_savings_inr', 0))}", tbl_cell_accent),
            Paragraph(f"{s.get('scheduled_month', '')}", tbl_cell_bold),
            Paragraph(f"{s.get('tender_timeline_days', 45)}d", tbl_cell_style),
            Paragraph(f"<font size='6'>{s.get('crri_compliance_code', '')}</font>", tbl_cell_style),
        ]
        sched_rows.append(row_cells)
        
    # Column widths totaling ~782 points
    col_widths = [56, 116, 102, 68, 48, 42, 114, 58, 58, 46, 26, 48]
    sched_table = Table(sched_rows, colWidths=col_widths, repeatRows=1)
    
    t_style = [
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor("#1E3A8A")),
        ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('TOPPADDING', (0, 0), (-1, -1), 3),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
        ('LEFTPADDING', (0, 0), (-1, -1), 3),
        ('RIGHTPADDING', (0, 0), (-1, -1), 3),
        ('BOX', (0, 0), (-1, -1), 0.8, colors.HexColor("#94A3B8")),
        ('INNERGRID', (0, 0), (-1, -1), 0.3, colors.HexColor("#E2E8F0")),
    ]
    
    for r_i in range(1, len(sched_rows)):
        bg = colors.HexColor("#F8FAFC") if r_i % 2 == 0 else colors.HexColor("#FFFFFF")
        t_style.append(('BACKGROUND', (0, r_i), (-1, r_i), bg))
        
    sched_table.setStyle(TableStyle(t_style))
    story.append(sched_table)
    story.append(Spacer(1, 12))
    
    # --------------------------------------------------------------------------
    # Mandatory Technical & Audit Clauses
    # --------------------------------------------------------------------------
    clauses_block = [
        Paragraph("STATUTORY CPWD / CSIR-CRRI TENDER CONDITIONS & DEFECT LIABILITY TERMS:", clause_title_style),
        Paragraph("<b>1. Ride Quality Benchmark (IRC:82 & IRC:SP:81):</b> Contractor must achieve final International Roughness Index (IRI) &le; 2.2 m/km as independently validated by CSIR-CRRI Network Survey Vehicle (NSV) with class-1 laser profilometer before issuance of completion certificate.", clause_body_style),
        Paragraph("<b>2. Defect Liability Period (DLP):</b> Minimum 36 calendar months for Bituminous Concrete (BC) overlays and 24 calendar months for Micro-surfacing/slurry seals. Any pothole emergence or cracking &gt; 5% within DLP shall be rectified by the contractor at zero cost within 48 hours of notification.", clause_body_style),
        Paragraph("<b>3. Liquidated Damages for Delay:</b> If the contractor fails to achieve monthly milestones, liquidated damages shall be levied at 1.0% of the contract value per week of delay up to a maximum ceiling of 10.0% under CPWD GCC Clause 2.", clause_body_style),
        Paragraph("<b>4. Pre-Monsoon Clause:</b> All asphalt milling, tack coat, and surface sealing operations across listed corridors must conclude prior to June 25th to prevent monsoon moisture ingress.", clause_body_style)
    ]
    story.append(KeepTogether(clauses_block))
    story.append(Spacer(1, 14))
    
    # --------------------------------------------------------------------------
    # Official Signature & Seal Block
    # --------------------------------------------------------------------------
    sig_data = [
        [
            Paragraph("<b>Prepared & Verified by:</b><br/><br/><br/>___________________________<br/><b>Assistant Engineer (Roads)</b><br/>Delhi PWD Division", meta_style),
            Paragraph("<b>Pavement Audit Clearance:</b><br/><br/><br/>___________________________<br/><b>Principal Scientist & Auditor</b><br/>CSIR - Central Road Research Institute", meta_style),
            Paragraph("<b>Financial Concurrence:</b><br/><br/><br/>___________________________<br/><b>Chief Accounts Officer</b><br/>Delhi Urban Development / MCD", meta_style),
            Paragraph("<b>Tender Sanctioned & Approved:</b><br/><br/><br/>___________________________<br/><b>Executive Engineer (Civil)</b><br/>Public Works Department, NCT of Delhi", meta_style),
        ]
    ]
    sig_table = Table(sig_data, colWidths=[195, 195, 195, 197])
    sig_table.setStyle(TableStyle([
        ('BOX', (0, 0), (-1, -1), 0.5, colors.HexColor("#CBD5E1")),
        ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor("#F8FAFC")),
        ('TOPPADDING', (0, 0), (-1, -1), 6),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
        ('LEFTPADDING', (0, 0), (-1, -1), 8),
        ('RIGHTPADDING', (0, 0), (-1, -1), 8),
    ]))
    story.append(KeepTogether([sig_table]))
    
    # Build Document with NumberedCanvas
    doc.build(story, canvasmaker=NumberedCanvas)
    return buffer.getvalue()


# ==============================================================================
# 4. MULTI-YEAR 5-YEAR CAPITAL IMPROVEMENT PLAN (CIP) EXCEL WORKBOOK
# ==============================================================================
def generate_multi_year_excel_cip(plan_data: dict) -> bytes:
    """
    Generates a professional 3-sheet Excel workbook containing the comprehensive
    5-Year Capital Improvement Master Plan (CIP) for Delhi NCT road networks:
    - Sheet 1: Executive 5-Year Financial Summary & Year-by-Year Allocations
    - Sheet 2: 5-Year Master Work Schedule with Spatial Clusters & RSL Ratings
    - Sheet 3: Weibull Deterioration Trajectory (Managed vs Do-Nothing)
    """
    wb = openpyxl.Workbook()
    # Remove default sheet
    wb.remove(wb.active)

    fin = plan_data.get("financial_summary", {})
    yearly = plan_data.get("yearly_plans", [])
    master_sched = plan_data.get("master_schedule", [])
    traj = plan_data.get("trajectory", {})

    # Styles
    f_title = Font(name="Segoe UI", size=15, bold=True, color="FFFFFF")
    f_header = Font(name="Segoe UI", size=11, bold=True, color="FFFFFF")
    f_bold = Font(name="Segoe UI", size=10, bold=True)
    f_regular = Font(name="Segoe UI", size=10)
    f_accent = Font(name="Segoe UI", size=10, bold=True, color="059669")
    f_red = Font(name="Segoe UI", size=10, bold=True, color="DC2626")

    fill_navy = PatternFill(start_color="1E293B", end_color="1E293B", fill_type="solid")
    fill_slate = PatternFill(start_color="334155", end_color="334155", fill_type="solid")
    fill_sub = PatternFill(start_color="F1F5F9", end_color="F1F5F9", fill_type="solid")
    fill_green = PatternFill(start_color="DCFCE7", end_color="DCFCE7", fill_type="solid")

    border_thin = Border(
        left=Side(style='thin', color="CBD5E1"),
        right=Side(style='thin', color="CBD5E1"),
        top=Side(style='thin', color="CBD5E1"),
        bottom=Side(style='thin', color="CBD5E1")
    )

    # --------------------------------------------------------------------------
    # SHEET 1: Executive Financial Summary
    # --------------------------------------------------------------------------
    ws1 = wb.create_sheet(title="Executive CIP Summary")
    ws1.views.sheetView[0].showGridLines = True

    # Title Banner
    ws1.merge_cells("A1:G2")
    title_cell = ws1["A1"]
    title_cell.value = "DELHI NCT 5-YEAR CAPITAL IMPROVEMENT MASTER PLAN (CIP)"
    title_cell.font = f_title
    title_cell.fill = fill_navy
    title_cell.alignment = Alignment(horizontal="center", vertical="center")

    ws1.merge_cells("A3:G3")
    sub_cell = ws1["A3"]
    sub_cell.value = f"Multi-Year Proactive Pavement Preservation · IRC:37 & IRC:82 Calibrated · Zone: {fin.get('selected_zone', 'All Delhi')}"
    sub_cell.font = Font(name="Segoe UI", size=10, italic=True, color="475569")
    sub_cell.alignment = Alignment(horizontal="center", vertical="center")

    # High-level KPIs block
    kpis = [
        ("Total 5-Yr Capital Investment (Nominal):", fin.get("total_invested_nominal_formatted", "--")),
        ("Discounted Capital Investment (NPV @ 6%):", fin.get("total_invested_npv_formatted", "--")),
        ("Avoided Deferred Repair Liability:", fin.get("total_avoided_liability_formatted", "--")),
        ("Net Municipal Capital Savings (NPV):", fin.get("total_net_savings_npv_formatted", "--")),
        ("Proactive Return on Investment (ROI):", f"{fin.get('roi_percentage', 0)}%"),
        ("Spatial Route Clustering Efficiency Savings:", fin.get("total_mobilization_savings_formatted", "--")),
        ("Initial Average Network PCI:", f"{fin.get('initial_avg_pci', '--')} / 100"),
        ("Year 5 Managed PCI vs Do-Nothing:", f"{fin.get('final_managed_pci', '--')} vs {fin.get('final_do_nothing_pci', '--')} (+{fin.get('net_pci_lift', 0)} pts)")
    ]

    row_idx = 5
    for lbl, val in kpis:
        ws1.cell(row=row_idx, column=2, value=lbl).font = f_bold
        val_cell = ws1.cell(row=row_idx, column=4, value=val)
        val_cell.font = f_accent if "Savings" in lbl or "ROI" in lbl or "Managed" in lbl else f_bold
        row_idx += 1

    # Year-by-Year Allocation Table
    row_idx += 2
    ws1.cell(row=row_idx, column=1, value="YEAR-BY-YEAR MASTER ALLOCATION BREAKDOWN").font = Font(name="Segoe UI", size=11, bold=True, color="1E293B")
    row_idx += 1

    headers_y = ["Year", "Allocated Budget", "Corridors Treated", "Lane Length (km)", "Avoided Reactive Cost", "Net Savings", "Year-End PCI"]
    for col_idx, h_text in enumerate(headers_y, 1):
        c = ws1.cell(row=row_idx, column=col_idx, value=h_text)
        c.font = f_header
        c.fill = fill_slate
        c.alignment = Alignment(horizontal="center", vertical="center")
    row_idx += 1

    for y_plan in yearly:
        ws1.cell(row=row_idx, column=1, value=y_plan["year_label"]).font = f_bold
        ws1.cell(row=row_idx, column=2, value=y_plan["allocated_budget_formatted"]).font = f_regular
        ws1.cell(row=row_idx, column=3, value=y_plan["corridors_treated_count"]).font = f_regular
        ws1.cell(row=row_idx, column=4, value=f"{y_plan['total_km_treated']} km").font = f_regular
        ws1.cell(row=row_idx, column=5, value=f"₹{y_plan['avoided_reactive_inr'] / 1e7:.2f} Cr").font = f_regular
        ws1.cell(row=row_idx, column=6, value=y_plan["net_savings_formatted"]).font = f_accent
        ws1.cell(row=row_idx, column=7, value=f"{y_plan['year_end_avg_pci']} / 100").font = f_bold

        for c_idx in range(1, 8):
            ws1.cell(row=row_idx, column=c_idx).border = border_thin
        row_idx += 1

    # --------------------------------------------------------------------------
    # SHEET 2: 5-Year Master Work Schedule
    # --------------------------------------------------------------------------
    ws2 = wb.create_sheet(title="Master Work Schedule")
    ws2.views.sheetView[0].showGridLines = True

    headers_sched = [
        "Year", "Quarter", "Tender Code", "Corridor ID", "Road Name",
        "Division / Zone", "Length (km)", "Pre-Repair PCI", "Post-Repair PCI",
        "Allocated Cost", "Net Savings", "Spatial Cluster", "Mobilization Savings",
        "Remaining Service Life (RSL)", "Prescribed Treatment (IRC Norm)"
    ]

    for col_idx, h_text in enumerate(headers_sched, 1):
        c = ws2.cell(row=1, column=col_idx, value=h_text)
        c.font = f_header
        c.fill = fill_navy
        c.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)

    ws2.row_dimensions[1].height = 26

    row_s = 2
    for p in master_sched:
        ws2.cell(row=row_s, column=1, value=p.get("year_label", "")).font = f_bold
        ws2.cell(row=row_s, column=2, value=p.get("scheduled_quarter", "")).font = f_regular
        ws2.cell(row=row_s, column=3, value=p.get("tender_code", "")).font = f_regular
        ws2.cell(row=row_s, column=4, value=p.get("segment_id", "")).font = f_bold
        ws2.cell(row=row_s, column=5, value=p.get("road_name", "")).font = f_regular
        ws2.cell(row=row_s, column=6, value=p.get("city_zone", "")).font = f_regular
        ws2.cell(row=row_s, column=7, value=p.get("length_km", 0.0)).font = f_regular
        ws2.cell(row=row_s, column=8, value=p.get("pre_repair_pci", 0.0)).font = f_regular
        ws2.cell(row=row_s, column=9, value=p.get("post_repair_pci", 96.0)).font = f_bold
        ws2.cell(row=row_s, column=10, value=p.get("allocated_cost_formatted", "")).font = f_regular
        ws2.cell(row=row_s, column=11, value=f"₹{p.get('net_savings_inr', 0) / 1e5:.2f} L").font = f_accent
        ws2.cell(row=row_s, column=12, value=p.get("cluster_name", "")).font = f_regular
        ws2.cell(row=row_s, column=13, value=p.get("mobilization_savings_formatted", "")).font = f_accent
        ws2.cell(row=row_s, column=14, value=f"{p.get('rsl_years', '--')} yrs ({p.get('rsl_category', '')})").font = f_regular
        ws2.cell(row=row_s, column=15, value=p.get("recommended_action", "")).font = f_regular

        for c_idx in range(1, len(headers_sched) + 1):
            ws2.cell(row=row_s, column=c_idx).border = border_thin
        row_s += 1

    # --------------------------------------------------------------------------
    # SHEET 3: Deterioration & Inaction Decay
    # --------------------------------------------------------------------------
    ws3 = wb.create_sheet(title="Decay & Asset Trajectory")
    ws3.views.sheetView[0].showGridLines = True

    ws3.merge_cells("A1:E1")
    t3 = ws3["A1"]
    t3.value = "5-YEAR WEIBULL NETWORK DECAY: PROACTIVE MANAGEMENT VS DO-NOTHING"
    t3.font = f_title
    t3.fill = fill_navy
    t3.alignment = Alignment(horizontal="center", vertical="center")

    headers_d = ["Year", "Timeframe", "Proactive Managed PCI", "Do-Nothing Neglect PCI", "Quality Gap Lift"]
    for c_idx, h_text in enumerate(headers_d, 1):
        c = ws3.cell(row=3, column=c_idx, value=h_text)
        c.font = f_header
        c.fill = fill_slate
        c.alignment = Alignment(horizontal="center", vertical="center")

    years_list = traj.get("years", [])
    m_pci = traj.get("managed_pci", [])
    dn_pci = traj.get("do_nothing_pci", [])

    row_d = 4
    for i, y_str in enumerate(years_list):
        pci_val = m_pci[i] if i < len(m_pci) else "--"
        dn_val = dn_pci[i] if i < len(dn_pci) else "--"
        gap = round(pci_val - dn_val, 1) if isinstance(pci_val, (int, float)) and isinstance(dn_val, (int, float)) else "--"

        ws3.cell(row=row_d, column=1, value=f"T+{i}").font = f_bold
        ws3.cell(row=row_d, column=2, value=y_str).font = f_regular
        ws3.cell(row=row_d, column=3, value=pci_val).font = f_accent
        ws3.cell(row=row_d, column=4, value=dn_val).font = f_red
        ws3.cell(row=row_d, column=5, value=f"+{gap} pts" if gap != "--" else "--").font = f_bold

        for c_idx in range(1, 6):
            ws3.cell(row=row_d, column=c_idx).border = border_thin
        row_d += 1

    # Auto-adjust column widths across all sheets
    for sheet in [ws1, ws2, ws3]:
        for col in sheet.columns:
            max_len = 0
            col_letter = get_column_letter(col[0].column)
            for cell in col:
                val_str = str(cell.value or "")
                if len(val_str) > max_len and len(val_str) < 60:
                    max_len = len(val_str)
            sheet.column_dimensions[col_letter].width = max(12, max_len + 3)

    out_buf = io.BytesIO()
    wb.save(out_buf)
    return out_buf.getvalue()

