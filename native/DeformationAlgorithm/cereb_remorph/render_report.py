"""Render the portable report JSON with ReportLab (also works in the bundled runtime)."""
import json
from pathlib import Path
import sys
from xml.sax.saxutils import escape
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_LEFT
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, KeepTogether, PageBreak
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.lib.pagesizes import A4


def render(data, output):
    from .desktop_paths import RESOURCES
    font=RESOURCES/'fonts/DejaVuSans.ttf'
    bold=font.with_name('DejaVuSans-Bold.ttf')
    pdfmetrics.registerFont(TTFont('DF',str(font)));pdfmetrics.registerFont(TTFont('DF-Bold',str(bold)))
    pdfmetrics.registerFontFamily('DF',normal='DF',bold='DF-Bold',italic='DF',boldItalic='DF-Bold')
    teal=colors.HexColor('#087e8e');ink=colors.HexColor('#193a4b');muted=colors.HexColor('#5c7482')
    styles=getSampleStyleSheet()
    styles.add(ParagraphStyle('DFBody',fontName='DF',fontSize=9,leading=14,textColor=ink,spaceAfter=8))
    styles.add(ParagraphStyle('DFNote',parent=styles['DFBody'],keepWithNext=True))
    styles.add(ParagraphStyle('DFSmall',parent=styles['DFBody'],fontSize=7.4,leading=10.8,spaceAfter=0))
    styles.add(ParagraphStyle('DFHead',fontName='DF-Bold',fontSize=17,leading=23,textColor=teal,spaceBefore=17,spaceAfter=10,keepWithNext=True))
    styles.add(ParagraphStyle('DFTitle',fontName='DF-Bold',fontSize=27,leading=33,textColor=ink,spaceAfter=12))
    styles.add(ParagraphStyle('DFCode',fontName='DF',fontSize=8,leading=13,backColor=colors.HexColor('#eef5f7'),borderPadding=10,spaceBefore=8,spaceAfter=12,wordWrap='CJK'))
    def p(text,style='DFBody'):return Paragraph(escape(str(text)).replace('\n','<br/>'),styles[style])
    story=[p('DEFORMATIONALGORITHM v0.0.1  /  CONFIGURATION REPORT','DFSmall'),p('Maintained by Alberto Arturo Vergani','DFSmall'),Spacer(1,12),p(data['name'],'DFTitle'),p('BSB 8 - cerebellar cortex - in-vitro multireceptor preset'),p(data['created_utc']+'  |  Seed '+str(data['seed']),'DFSmall'),Spacer(1,13)]
    story.append(p('0% DF = reference. −100% = zero; +100% = twice the reference. Electrical changes do not imply a proportional change in firing rate.'))
    story.append(p(data['summary']))
    def table(headers,rows,widths):
        vals=[[p(x,'DFSmall') for x in headers]]+[[p(x,'DFSmall') for x in r] for r in rows]
        t=Table(vals,colWidths=widths,repeatRows=1,hAlign='LEFT')
        t.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,0),colors.HexColor('#dceff0')),('VALIGN',(0,0),(-1,-1),'TOP'),('LEFTPADDING',(0,0),(-1,-1),7),('RIGHTPADDING',(0,0),(-1,-1),7),('TOPPADDING',(0,0),(-1,-1),7),('BOTTOMPADDING',(0,0),(-1,-1),7),('ROWBACKGROUNDS',(0,1),(-1,-1),[colors.white,colors.HexColor('#f5f8fa')]),('LINEBELOW',(0,0),(-1,0),.7,teal)]))
        story.append(t)
    for section in data['sections']:
        story.append(p(section['title'],'DFHead'))
        story.append(p(section['note'],'DFNote'))
        if section['rows']:table(section['headers'],section['rows'],section['widths'])
        else:story.append(p('No modifications. The official reference values are retained.'))
    if data.get('parameter_notes'):
        story.append(PageBreak());story.append(p('Parameter notes / justification log','DFHead'))
        for item in data['parameter_notes']:
            value=item['value'] if item['value'] is not None else 'inherited / reset'
            story.append(KeepTogether([p(item['path'],'DFNote'),p('Current signed setting: '+str(value),'DFSmall'),p(item['note']),Spacer(1,8)]))
    a=data.get('annotations',{})
    if a:
        story.append(PageBreak());story.append(p('Notes & references','DFHead'))
        if a.get('summary'):story.append(p(a['summary']))
        for e in data.get('evidence',[]):
            story.append(p(e['title'],'DFHead'));story.append(p(e['evidence'] if e['matches'] else 'Modified after preload','DFNote'));story.append(p(e['rationale']))
            for t in e['current']:story.append(p(t['path']+': preset '+str(t['expected'])+'; current '+str(t['current']),'DFSmall'))
            story.append(p('Sources: '+', '.join(e['sources']),'DFSmall'))
        for index,ref in enumerate(a.get('sources',[])):
            story.append(KeepTogether(([p('Sources consulted','DFHead')] if index==0 else [])+[p(ref['id']+' / '+ref['title'],'DFNote'),
                Paragraph('<link href="'+escape(ref['url'])+'" color="#087e8e">'+escape(ref['url'])+'</link>',styles['DFSmall']),
                p(ref['kind']+'. '+ref['note'])]))
        if a.get('notes'):story.extend([p('Your notes','DFHead'),p(a['notes'])])
    story.append(PageBreak())
    story.extend([p('Reconstruction from a terminal','DFHead'),p('The package is prepared and validated. No full reconstruction or simulation has been launched.'),p('1. On your BSB 8 / MPI machine, activate the matching environment and enter the extracted package folder. The Windows editor does not perform reconstruction. Run the commands below in Bash. Existing output folders are never overwritten. The included SWCs are already transformed.'),p(data['command'],'DFCode'),p('2. The output folder is created only when the launcher runs:'),p(data['output_folder'],'DFCode'),p('3. A successful reconstruction writes success.json, network.hdf5, circuit.yaml, cell_assignments.json and connectivity_availability.json. Electrical settings are saved separately in electrical_parameters.yaml; choose a stimulation protocol before running a simulation.'),p('Files and provenance','DFHead')])
    table(['File','Purpose'],data['files'],[175,336])
    story.append(Spacer(1,14));story.append(p('Official model commit: '+data['model_commit'],'DFSmall'));story.append(p('Recipe SHA-256: '+data['recipe_sha256'],'DFSmall'))
    story.append(p('These settings are exploratory. Structural geometry constraints and electrical parameter domains are checked; this is not a validation of physiological behavior.','DFBody'))
    def footer(canvas,doc):
        canvas.saveState();canvas.setStrokeColor(colors.HexColor('#d3e0e5'));canvas.line(42,40,553,40);canvas.setFont('DF',7);canvas.setFillColor(muted);canvas.drawString(42,27,'DeformationAlgorithm | configuration, not simulation results');canvas.drawRightString(553,27,str(doc.page));canvas.restoreState()
    doc=SimpleDocTemplate(str(output),pagesize=A4,rightMargin=42,leftMargin=42,topMargin=40,bottomMargin=53,title=data['name']+' - Deformation report',author='Alberto Arturo Vergani')
    doc.build(story,onFirstPage=footer,onLaterPages=footer)

if __name__=='__main__':render(json.loads(Path(sys.argv[1]).read_text( encoding='utf-8')),sys.argv[2])
