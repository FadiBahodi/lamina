"""Render the Lamina design paper. Requires the package's pdf extra."""
from __future__ import annotations
import html
import re
from pathlib import Path
from reportlab import __file__ as reportlab_file
from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.utils import simpleSplit
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, PageBreak, Table, TableStyle, KeepTogether, Flowable

ROOT = Path(__file__).resolve().parents[1]
INK = colors.HexColor('#14242f'); BLUE = colors.HexColor('#176c88'); LINE = colors.HexColor('#d2dce1'); LIGHT=colors.HexColor('#f1f5f7')
fonts = Path(reportlab_file).parent / 'fonts'
for name, file in [('Paper','Vera.ttf'),('PaperBold','VeraBd.ttf'),('PaperItalic','VeraIt.ttf'),('PaperMono','VeraMono.ttf')]:
    path=fonts/file
    if path.exists(): pdfmetrics.registerFont(TTFont(name,str(path)))
if 'PaperMono' not in pdfmetrics.getRegisteredFontNames(): pdfmetrics.registerFont(TTFont('PaperMono',str(fonts/'Vera.ttf')))
pdfmetrics.registerFontFamily('Paper',normal='Paper',bold='PaperBold',italic='PaperItalic',boldItalic='PaperBold')
styles=getSampleStyleSheet()
styles.add(ParagraphStyle(name='BodyPaper',fontName='Paper',fontSize=9.4,leading=14.1,spaceAfter=9,textColor=INK))
styles.add(ParagraphStyle(name='TitlePaper',fontName='PaperBold',fontSize=33,leading=38,spaceAfter=22,textColor=INK))
styles.add(ParagraphStyle(name='H2Paper',fontName='PaperBold',fontSize=18,leading=23,spaceBefore=18,spaceAfter=12,textColor=INK,keepWithNext=True))
styles.add(ParagraphStyle(name='H3Paper',fontName='PaperBold',fontSize=11,leading=15,spaceBefore=12,spaceAfter=7,textColor=BLUE,keepWithNext=True))
styles.add(ParagraphStyle(name='SmallPaper',fontName='Paper',fontSize=8,leading=11,spaceAfter=7,textColor=colors.HexColor('#536875')))
styles.add(ParagraphStyle(name='CellPaper',parent=styles['BodyPaper'],fontSize=7.7,leading=10.6,spaceAfter=0))
styles.add(ParagraphStyle(name='CodePaper',fontName='PaperMono',fontSize=7.7,leading=11,spaceAfter=10,backColor=LIGHT,borderPadding=10,textColor=INK))
styles.add(ParagraphStyle(name='BulletPaper',parent=styles['BodyPaper'],leftIndent=12,firstLineIndent=-10,spaceAfter=6))

def inline(s):
    s=s.replace('—','; ').replace('–','-').replace('\u2011','-')
    s=s.replace('→',' -> ').replace('⊆',' subset of ').replace('Σ','sum ').replace('≥','>=')
    s=html.escape(s)
    s=re.sub(r'\[([^]]+)\]\(([^)]+)\)',lambda m:f'<a href="{m[2]}" color="#176c88">{m[1]}</a>',s)
    s=re.sub(r'`([^`]+)`',r'<font name="PaperMono">\1</font>',s)
    s=re.sub(r'\*\*([^*]+)\*\*',r'<b>\1</b>',s)
    s=re.sub(r'(?<!\*)\*([^*]+)\*(?!\*)',r'<i>\1</i>',s)
    return s

class Architecture(Flowable):
    def __init__(self): Flowable.__init__(self);self.width=480;self.height=178
    def draw(self):
        c=self.canv
        nodes=[('Task + sources','Output, constraints, allowed use'),('Method decision','Representation, context, alternatives'),('Revision','Find defect, reopen affected decisions'),('Execution','Read / reconcile / write / review')]
        w=230;h=56
        for i,(title,sub) in enumerate(nodes):
            x=(i%2)*250;y=106-(i//2)*85
            c.setFillColor(LIGHT);c.setStrokeColor(LINE);c.roundRect(x,y,w,h,4,fill=1,stroke=1)
            c.setFillColor(BLUE);c.setFont('PaperBold',10);c.drawString(x+12,y+35,title)
            c.setFillColor(INK);c.setFont('Paper',7.5);c.drawString(x+12,y+17,sub)
        c.setStrokeColor(BLUE);c.setLineWidth(1)
        for x1,y1,x2,y2 in [(231,134,249,134),(365,105,365,79),(249,49,231,49)]:
            c.line(x1,y1,x2,y2)
            if y1==y2:
                d=1 if x2>x1 else -1;c.line(x2,y2,x2-4*d,y2+3);c.line(x2,y2,x2-4*d,y2-3)
            else:c.line(x2,y2,x2-3,y2+4);c.line(x2,y2,x2+3,y2+4)
        c.setFillColor(colors.HexColor('#536875'));c.setFont('Paper',7.4);c.drawString(0,3,'Proposed integrated architecture. The current execution paths remain separate.')

def page(c,doc):
    c.saveState();w,h=doc.pagesize
    c.setFillColor(BLUE);c.rect(46,h-35,17,3,fill=1,stroke=0)
    c.setFont('PaperBold',8);c.setFillColor(INK);c.drawString(70,h-35,'LAMINA  /  SYSTEM DESIGN')
    c.setFont('Paper',7.5);c.setFillColor(colors.HexColor('#617580'));c.drawRightString(w-46,h-35,'21 SEPTEMBER 2026 · DESIGN PROPOSAL + REFERENCE IMPLEMENTATION')
    c.setStrokeColor(LINE);c.line(46,40,w-46,40)
    c.setFont('Paper',8);c.drawString(46,26,'Fadi Bahodi  ·  github.com/FadiBahodi/lamina');c.drawRightString(w-46,26,str(doc.page))
    c.restoreState()

def render(source:Path,output:Path):
    lines=source.read_text().splitlines();story=[];i=0;title=False
    while i<len(lines):
        line=lines[i].strip()
        if not line: i+=1;continue
        if line.startswith('# '):
            story.extend([Spacer(1,25),Paragraph('ENGINEERING DESIGN PAPER',styles['SmallPaper']),Paragraph(inline(line[2:]),styles['TitlePaper']),Paragraph('Fadi Bahodi · September 2026',styles['SmallPaper'])]);title=True;i+=1;continue
        if line.startswith('## '):
            heading=line[3:]
            # Major sections start at natural boundaries; long tables may flow.
            if heading == 'References':
                rest=[Paragraph('References',styles['H2Paper'])]
                for ref in lines[i+1:]:
                    if ref.strip(): rest.append(Paragraph(inline(ref.strip()),styles['SmallPaper']))
                story.append(KeepTogether(rest));break
            if story and any(isinstance(x,Paragraph) and x.style.name=='H2Paper' for x in story): story.append(Spacer(1,6))
            story.append(Paragraph(inline(heading),styles['H2Paper']))
            if re.search(r'(architecture|representation|graph that)',heading,re.I) and not any(isinstance(x,Architecture) for x in story):story.extend([Architecture(),Spacer(1,10)])
            i+=1;continue
        if line.startswith('### '): story.append(Paragraph(inline(line[4:]),styles['H3Paper']));i+=1;continue
        if line.startswith('```'):
            block=[];i+=1
            while i<len(lines) and not lines[i].startswith('```'):block.append(lines[i]);i+=1
            story.append(Paragraph('<br/>'.join(html.escape(x).replace(' ','&#160;') for x in block),styles['CodePaper']));i+=1;continue
        if line.startswith('|'):
            rows=[]
            while i<len(lines) and lines[i].strip().startswith('|'):
                row=[x.strip() for x in lines[i].strip().strip('|').split('|')]
                if not all(re.fullmatch(r'[:\-\s]+',x or '-') for x in row):rows.append(row)
                i+=1
            count=max(map(len,rows)); widths={2:[140,340],3:[112,184,184],4:[92,122,134,132]}.get(count,[480/count]*count)
            data=[[Paragraph(inline(cell),styles['CellPaper']) for cell in row] for row in rows]
            table=Table(data,colWidths=widths,repeatRows=1,hAlign='LEFT')
            table.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,0),colors.HexColor('#e6eff3')),('VALIGN',(0,0),(-1,-1),'TOP'),('LINEBELOW',(0,0),(-1,0),.8,BLUE),('LINEBELOW',(0,1),(-1,-1),.35,LINE),('LEFTPADDING',(0,0),(-1,-1),8),('RIGHTPADDING',(0,0),(-1,-1),8),('TOPPADDING',(0,0),(-1,-1),8),('BOTTOMPADDING',(0,0),(-1,-1),8)]));story.extend([table,Spacer(1,12)]);continue
        if line=='---':i+=1;continue
        bullet=re.match(r'^(- |\d+\. )(.*)',line)
        if bullet:
            story.append(Paragraph(inline(('• ' if bullet[1]=='- ' else bullet[1])+bullet[2]),styles['BulletPaper']));i+=1;continue
        block=[line];i+=1
        while i<len(lines) and lines[i].strip() and not re.match(r'^(#|\||```|- |\d+\. )',lines[i].strip()):block.append(lines[i].strip());i+=1
        story.append(Paragraph(inline(' '.join(block)),styles['BodyPaper']))
    output.parent.mkdir(parents=True,exist_ok=True)
    SimpleDocTemplate(str(output),pagesize=(595.28,841.89),rightMargin=57,leftMargin=57,topMargin=61,bottomMargin=57,title='Lamina: an inspectable runtime for document production',author='Fadi Bahodi',subject='System design, implementation boundaries, and evaluation').build(story,onFirstPage=page,onLaterPages=page)

if __name__=='__main__':
    import argparse
    parser=argparse.ArgumentParser();parser.add_argument('--source',type=Path,default=ROOT/'docs/technical-paper.md');parser.add_argument('--output',type=Path,default=ROOT/'output/pdf/lamina-technical-paper.pdf');args=parser.parse_args();render(args.source,args.output);print(args.output)
