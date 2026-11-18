"""Generate synthetic ACF data-sharing agreements (MOU / ISA / amendment) as PDFs, following the ACF TECH MOU template.
Typed agreements are text PDFs (reportlab). Handwritten agreements are printed forms filled in by hand and scanned:
image-only PDFs (Pillow) with handwriting fonts, ink jitter, page skew and scanner noise.
Usage: python generate_agreements.py <out_dir> <fonts_dir>"""
import os, sys, random, json
from datetime import date
from agreements_spec import AGREEMENTS, ACF_SYSTEM, PEOPLE, TABLES, pii

OUT, FONTS = sys.argv[1], sys.argv[2]
os.makedirs(OUT, exist_ok=True)
MARK = "SYNTHETIC DEMONSTRATION DOCUMENT - not an official ACF or HHS agreement"
KIND_TITLE = {"MOU": "Memorandum of Understanding", "ISA": "Interconnection Security Agreement", "AMENDMENT": "Amendment to Agreement"}
PARTNER_NAME = {"NIH": "National Institutes of Health (NIH)", "CDC": "Centers for Disease Control and Prevention (CDC)",
                "FDA": "U.S. Food and Drug Administration (FDA)", "CMS": "Centers for Medicare & Medicaid Services (CMS)",
                "OS": "HHS Office of the Secretary (OS)"}
INDIRECT = {"county_fips", "address_zip", "zip_code", "latitude", "longitude", "street_address", "case_id", "recipient_id", "child_record_id",
            "afcars_record_id", "enrollment_id", "report_id"}

ISSO = {"nih_nichd": "Carla Jimenez, NICHD", "nih_niehs": "Daniel Osei, NIEHS", "cdc_ncipc": "Megan Fairbanks, NCIPC",
        "cdc_ncird": "Arjun Patel, NCIRD", "cdc_nchs": "Holly Brennan, NCHS", "fda_hfp": "Victor Chen, HFP",
        "cms_cmcs": "Natalie Brooks, CMCS", "os_aspe": "Samuel Ortiz, ASPE"}
def fmt(d): return date.fromisoformat(d).strftime("%B %d, %Y").replace(" 0", " ")
def sensitivity(t, c):
    if c in pii(t): return "PII - direct identifier"
    if c in INDIRECT: return "Indirect identifier"
    return "Non-identifying"

def content(a):
    """Ordered blocks shared by both renderers."""
    k, partner = a["kind"], PARTNER_NAME[a["partner"]]
    acf_sig, part_sig = PEOPLE["ACF"][0], PEOPLE[a["partner"]][0 if a["partner"] not in ("NIH", "CDC") else
                                                         {"nichd": 0, "niehs": 1, "ncipc": 0, "ncird": 1, "nchs": 2}[a["recipient"].split("_")[1]]]
    b = [("title", KIND_TITLE[k]), ("subtitle", "ACF TECH"),
         ("subtitle", f"{k if k != 'AMENDMENT' else 'Amendment No. 1'} Between {ACF_SYSTEM['name']} and {a['system_b']}"),
         ("fields", [("Agreement number", a["doc_id"]), ("Version", "1.0"), ("Date", fmt(a["effective"]))])]
    if k == "AMENDMENT":
        b += [("h", "1. Agreement Being Amended"),
              ("p", f"This amendment modifies Memorandum of Understanding {a['amends']} between the Administration for Children and Families (ACF) "
                    f"and the {a['office']}, {partner}. All other terms of the original agreement remain in effect."),
              ("h", "2. Change"), ("p", a["purpose"] + ". Appendix C, Shared Data Elements, is amended to add the data elements below."),
              ("fields", [("Delta Share name", a["share"]), ("Recipient", a["recipient"]), ("Amendment effective date", fmt(a["effective"])),
                          ("Agreement expiration (unchanged)", fmt(a["expires"]))]),
              ("table", (["Source table", "Column", "Sensitivity"], [[t, c, sensitivity(t, c)] for t, cs in a["tables"].items() for c in cs]))]
    else:
        b += [("h", "1. Supersession"), ("p", "None. This is the first agreement between the parties for this interconnection."),
              ("h", "2. Purpose and Scope"),
              ("p", f"The purpose of this {KIND_TITLE[k]} ({k}) is to establish a management agreement between the Administration for Children and "
                    f"Families (ACF), Office of the Chief Information Officer, and the {a['office']}, {partner}, hereafter referred to as \"both parties\", "
                    f"regarding the development, management, operation, and security of a connection between their respective systems, "
                    f"{ACF_SYSTEM['name']} and {a['system_b']}, hereafter referred to as \"the systems.\" Purpose of the data exchange: {a['purpose']}."),
              ("p", "This agreement is based on NIST Special Publication 800-47, Security Guide for Interconnecting Information Technology Systems. "
                    + ("An ISA is used because the interconnection is between separate, secure networks." if k == "ISA" else
                       "An MOU is used because the interconnection is within the same secure network.")),
              ("h", "3. Authority"),
              ("p", "Federal Information Security Modernization Act of 2014; OMB Circular A-130; 18 U.S.C. 641; 18 U.S.C. 1905; Privacy Act of 1974, "
                    "5 U.S.C. 552a; Health Insurance Portability and Accountability Act of 1996."),
              ("h", "4. Requirements"),
              ("fields", [("System A name", ACF_SYSTEM["name"]), ("System A function", ACF_SYSTEM["function"]), ("System A location", ACF_SYSTEM["location"]),
                          ("System B name", a["system_b"]), ("System B function", a["purpose"]),
                          ("System B location", f"{a['partner']} environment, Databricks Delta Sharing recipient '{a['recipient']}'"),
                          ("Description of data", "Records from the ACF tables and columns listed in Appendix C only, exchanged through Delta Sharing")]),
              ("h", "5. Data Exchange Method"),
              ("fields", [("Delta Share name", a["share"]), ("Recipient", a["recipient"]), ("Effective date", fmt(a["effective"])),
                          ("Expiration date", fmt(a["expires"]))]),
              ("p", "ACF will share only the tables and columns listed in Appendix C. Any change to the shared data elements requires a signed amendment "
                    "before the change is made. The recipient will not re-share, link to direct identifiers, or attempt to re-identify individuals."),
              ("h", "6. Security Responsibilities"),
              ("p", "Both parties agree to work together to ensure the joint security of the connected systems and the data they store, process, and "
                    "transmit, and to maintain the higher level of security commensurate with the risk of loss, misuse, or disclosure of the information."),
              ("h", "7. Communications"),
              ("p", "Both parties will designate technical leads and notify each other immediately of security incidents, disasters, and material "
                    "changes to system configuration, and at least 30 calendar days before any new interconnection."),
              ("h", "8. Timeline, Extensions, and Cancellations"),
              ("p", f"This agreement is effective {fmt(a['effective'])} and expires {fmt(a['expires'])}, unless extended by a newly signed agreement. "
                    "Either party may terminate it in writing with 30 calendar days notice, or immediately in the event of a security incident."),
              ("h", "Appendix B. Responsible Parties"),
              ("fields", [("ACF ISSO", "Lauren Mbeki, ACF OCIO"), ("ACF Technical POC", PEOPLE["ACF"][1][0]),
                          (f"{a['partner']} ISSO", ISSO[a["recipient"]]), (f"{a['partner']} Technical POC", part_sig[0])]),
              ("h", "Appendix C. Shared Data Elements"),
              ("p", f"Delta Share: {a['share']}    Recipient: {a['recipient']}"),
              ("table", (["Source table", "Column", "Sensitivity"], [[t, c, sensitivity(t, c)] for t, cs in a["tables"].items() for c in cs]))]
    b += [("h", "Agreement Signatures"), ("p", f"I agree with the terms of this {KIND_TITLE[k]}."),
          ("sig", [("APPROVED AND ACCEPTED FOR the Administration for Children and Families", acf_sig, a["effective"]),
                   (f"APPROVED AND ACCEPTED FOR {partner}", part_sig, a["effective"])])]
    return b

# ---------------------------------------------------------------- typed (text PDF)
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib import colors
from reportlab.lib.units import inch
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, KeepTogether

def typed(a, path):
    S = getSampleStyleSheet()
    body = ParagraphStyle("b", parent=S["Normal"], fontName="Times-Roman", fontSize=10.5, leading=14, spaceAfter=6)
    h = ParagraphStyle("h", parent=S["Heading2"], fontName="Times-Bold", fontSize=12.5, spaceBefore=10, spaceAfter=4)
    story = []
    for kind, v in content(a):
        if kind == "title": story += [Spacer(1, 30), Paragraph(v, ParagraphStyle("t", parent=S["Title"], fontName="Times-Bold", fontSize=24))]
        elif kind == "subtitle": story.append(Paragraph(v, ParagraphStyle("s", parent=S["Normal"], fontName="Times-Roman", fontSize=13, alignment=1, spaceAfter=6)))
        elif kind == "h": story.append(Paragraph(v, h))
        elif kind == "p": story.append(Paragraph(v, body))
        elif kind == "fields":
            t = Table([[Paragraph(f"<b>{l}:</b>", body), Paragraph(str(x), body)] for l, x in v], colWidths=[1.9 * inch, 4.9 * inch])
            t.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"), ("BOTTOMPADDING", (0, 0), (-1, -1), 1)])); story.append(t)
        elif kind == "table":
            t = Table([v[0]] + v[1], colWidths=[2.3 * inch, 2.4 * inch, 2.1 * inch], repeatRows=1)
            t.setStyle(TableStyle([("FONTNAME", (0, 0), (-1, 0), "Times-Bold"), ("FONTNAME", (0, 1), (-1, -1), "Times-Roman"), ("FONTSIZE", (0, 0), (-1, -1), 9.5),
                                   ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#DDE4EE")), ("GRID", (0, 0), (-1, -1), 0.4, colors.black)]))
            story.append(t)
        elif kind == "sig":
            for label, (name, title), d in v:
                story.append(KeepTogether([Spacer(1, 10), Paragraph(f"<b>{label}</b>", body),
                                           Paragraph(f"By: <font name='Times-Italic' size='14'>/s/ {name}</font>", body),
                                           Paragraph(f"Name: {name}    Title: {title}    Date: {fmt(d)}", body)]))
    def foot(c, d):
        c.saveState(); c.setFont("Times-Italic", 7.5); c.setFillColor(colors.HexColor("#AA0000")); c.drawString(0.75 * inch, 0.5 * inch, MARK)
        c.setFillColor(colors.grey); c.drawRightString(7.75 * inch, 0.5 * inch, f"{a['doc_id']}  |  Page {d.page}"); c.restoreState()
    SimpleDocTemplate(path, pagesize=letter, leftMargin=0.85 * inch, rightMargin=0.85 * inch, topMargin=0.8 * inch, bottomMargin=0.8 * inch,
                      title=f"{KIND_TITLE[a['kind']]} {a['doc_id']}").build(story, onFirstPage=foot, onLaterPages=foot)

# ---------------------------------------------------------------- handwritten (scanned image PDF)
from PIL import Image, ImageDraw, ImageFont, ImageFilter
import numpy as np
W, H, M = 1700, 2200, 130
def F(name, size): return ImageFont.truetype(os.path.join(FONTS, name), size)

class Page:
    def __init__(self, rng, hand_font, doc_id):
        self.rng, self.hand, self.doc_id = rng, hand_font, doc_id
        self.pages = []; self.new()
    def new(self):
        self.img = Image.new("RGB", (W, H), (252, 251, 246)); self.d = ImageDraw.Draw(self.img); self.y = M
        self.pages.append(self.img)
    def need(self, h):
        if self.y + h > H - M - 40: self.new()
    def printed(self, text, size=30, bold=False, center=False, width=W - 2 * M):
        f = F("CrimsonText-Bold.ttf" if bold else "CrimsonText-Regular.ttf", size)
        words, line, lines = text.split(), "", []
        for w_ in words:
            t = (line + " " + w_).strip()
            if self.d.textlength(t, font=f) > width: lines.append(line); line = w_
            else: line = t
        lines.append(line)
        for ln in lines:
            self.need(size + 12)
            x = (W - self.d.textlength(ln, font=f)) / 2 if center else M
            self.d.text((x, self.y), ln, font=f, fill=(25, 25, 25)); self.y += size + 10
        self.y += 6
    def ink(self, text, x, y, size=46, font=None, color=None):
        """Handwritten text: rendered on its own layer, slightly rotated, pasted with per-word baseline wobble."""
        font = font or self.hand
        if font == "ReenieBeanie.ttf": size = int(size * 1.22)
        f = F(font, size); col = color or self.rng.choice([(20, 40, 120), (25, 30, 90), (15, 15, 25)])
        cx = x
        for word in text.split(" "):
            w_ = int(self.d.textlength(word + " ", font=f)) + 10
            layer = Image.new("RGBA", (w_ + 20, size * 2), (0, 0, 0, 0))
            ImageDraw.Draw(layer).text((5, size // 3), word, font=f, fill=col + (235,))
            layer = layer.rotate(self.rng.uniform(-2.5, 2.5), resample=Image.BICUBIC, expand=False)
            self.img.paste(layer, (int(cx), int(y + self.rng.uniform(-4, 4) - size // 3)), layer)
            cx += w_ * self.rng.uniform(0.92, 1.02)
            if cx > W - M - 60: cx = x; y += size + 8
        return y
    def field(self, label, value):
        f = F("CrimsonText-Bold.ttf", 28); lw = self.d.textlength(label + ":", font=f) + 20
        self.need(70)
        self.d.text((M, self.y + 18), label + ":", font=f, fill=(25, 25, 25))
        self.d.line((M + lw, self.y + 58, W - M, self.y + 58), fill=(90, 90, 90), width=2)
        end_y = self.ink(value, M + lw + 8, self.y, size=self.rng.randint(40, 46))
        self.y = max(self.y + 72, end_y + 64)
    def table(self, header, rows):
        widths = [460, 520, W - 2 * M - 980]; rh = 64
        self.need(rh * 2)
        def hdr():
            x = M
            for i, h_ in enumerate(header):
                self.d.rectangle((x, self.y, x + widths[i], self.y + rh), outline=(30, 30, 30), width=2, fill=(232, 232, 228))
                self.d.text((x + 10, self.y + 16), h_, font=F("CrimsonText-Bold.ttf", 28), fill=(20, 20, 20)); x += widths[i]
            self.y += rh
        hdr()
        for r in rows:
            if self.y + rh > H - M - 40: self.new(); hdr()
            x = M
            for i, cell in enumerate(r):
                self.d.rectangle((x, self.y, x + widths[i], self.y + rh), outline=(30, 30, 30), width=2)
                self.ink(cell, x + 8, self.y + 2, size=self.rng.randint(34, 40)); x += widths[i]
            self.y += rh
        self.y += 20
    def signature(self, label, name, title, d):
        self.need(260)
        self.printed(label, size=27, bold=True)
        self.d.text((M, self.y + 50), "By:", font=F("CrimsonText-Regular.ttf", 30), fill=(25, 25, 25))
        self.d.line((M + 60, self.y + 90, M + 900, self.y + 90), fill=(60, 60, 60), width=2)
        self.ink(name.split(",")[0], M + 90, self.y - 6, size=74, font=self.rng.choice(["HomemadeApple.ttf", "NothingYouCouldDo.ttf"]), color=(15, 25, 110))
        self.y += 110
        self.field("Title", title); self.field("Date", date.fromisoformat(d).strftime("%m/%d/%Y"))
    def finish(self, path):
        out = []
        for n, im in enumerate(self.pages, 1):
            dr = ImageDraw.Draw(im)
            dr.text((M, H - 95), MARK, font=F("CrimsonText-Italic.ttf", 22), fill=(150, 20, 20))
            dr.text((W - M - 330, H - 95), f"{self.doc_id}  |  Page {n}", font=F("CrimsonText-Regular.ttf", 22), fill=(110, 110, 110))
            g = im.rotate(self.rng.uniform(-1.1, 1.1), resample=Image.BICUBIC, fillcolor=(240, 240, 236))   # page skew on the scanner
            arr = np.asarray(g).astype(np.int16)
            arr += np.random.default_rng(self.rng.randint(0, 10**6)).normal(0, 7, arr.shape[:2])[..., None].astype(np.int16)   # sensor noise
            arr = np.clip(arr, 0, 255).astype(np.uint8)
            g = Image.fromarray(arr).filter(ImageFilter.GaussianBlur(0.6)).convert("L")   # grayscale scan
            out.append(g)
        out[0].save(path, "PDF", resolution=200, save_all=True, append_images=out[1:])

def handwritten(a, path, rng):
    p = Page(rng, rng.choice(["Caveat.ttf", "ReenieBeanie.ttf"]), a["doc_id"])
    for kind, v in content(a):
        if kind == "title": p.y += 40; p.printed(v, size=56, bold=True, center=True)
        elif kind == "subtitle": p.printed(v, size=32, center=True)
        elif kind == "h":
            p.need(300 if v == "Agreement Signatures" else 120); p.y += 10; p.printed(v, size=36, bold=True)
        elif kind == "p": p.printed(v, size=28)
        elif kind == "fields":
            for l, x in v: p.field(l, str(x))
        elif kind == "table": p.table(*v)
        elif kind == "sig":
            for label, (name, title), d in v: p.signature(label, name, title, d)
    p.finish(path)

manifest = []
for i, a in enumerate(AGREEMENTS):
    fname = f"{a['doc_id']}.pdf"
    path = os.path.join(OUT, fname)
    (typed(a, path) if a["style"] == "typed" else handwritten(a, path, random.Random(1000 + i)))
    manifest.append({"file_name": fname, "doc_id": a["doc_id"], "kind": a["kind"], "style": a["style"], "partner": a["partner"]})
    print(f"{a['style']:11s} {a['kind']:9s} {fname}  {os.path.getsize(path)//1024} KB")
json.dump(manifest, open(os.path.join(OUT, "_manifest.json"), "w"), indent=1)
