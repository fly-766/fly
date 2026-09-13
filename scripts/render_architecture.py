"""Draw the schematic architecture as SVG and PNG. No experimental data are used."""
import html, math, random
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "docs" / "figures"
W,H,S = 2000,1440,2
BG="#ffffff"; INK="#172c3a"; MUTED="#63737d"; LINE="#d9e1e5"; TEAL="#267e86"; GOLD="#b6813c"; BLUE="#547d9b"
img=Image.new("RGB",(W*S,H*S),BG);draw=ImageDraw.Draw(img)
svg=[f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}" role="img" aria-labelledby="title desc">', '<title id="title">Fly: connectome-driven control under verifiable capital constraints</title>', '<desc id="desc">Four-panel schematic showing completed-candle visual encoding, a retained spiking connectome with restricted plasticity, long-flat execution, and principal-versus-profit accounting. Connectivity is schematic, not anatomical data. No performance results are plotted.</desc>',f'<rect width="{W}" height="{H}" fill="{BG}"/>']

def font(size,bold=False,serif=False):
    names = (["georgiab.ttf" if bold else "georgia.ttf"] if serif else ["arialbd.ttf" if bold else "arial.ttf"])
    names += ["DejaVuSerif.ttf" if serif else "DejaVuSans.ttf"]
    for name in names:
        for path in [Path("C:/Windows/Fonts")/name,Path("/usr/share/fonts/truetype/dejavu")/name,Path(name)]:
            try:return ImageFont.truetype(str(path),round(size*S))
            except OSError:pass
    return ImageFont.load_default(size=round(size*S))

def text(x,y,s,size=26,color=INK,bold=False,serif=False,anchor="start"):
    family="Georgia,DejaVu Serif,serif" if serif else "Arial,DejaVu Sans,sans-serif"
    svg.append(f'<text x="{x}" y="{y}" fill="{color}" font-family="{family}" font-size="{size}" font-weight="{700 if bold else 400}" text-anchor="{anchor}">{html.escape(s)}</text>')
    draw.text((x*S,y*S),s,font=font(size,bold,serif),fill=color,anchor={"start":"ls","middle":"ms","end":"rs"}[anchor])

def line(x1,y1,x2,y2,color=LINE,width=2,dash=False):
    svg.append(f'<line x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}" stroke="{color}" stroke-width="{width}"'+(' stroke-dasharray="8 6"' if dash else '')+'/>')
    if dash:
        n=max(1,int(math.hypot(x2-x1,y2-y1)/8))
        for i in range(0,n,2):draw.line(((x1+(x2-x1)*i/n)*S,(y1+(y2-y1)*i/n)*S,(x1+(x2-x1)*min(i+1,n)/n)*S,(y1+(y2-y1)*min(i+1,n)/n)*S),fill=color,width=max(1,int(width*S)))
    else:draw.line((x1*S,y1*S,x2*S,y2*S),fill=color,width=max(1,int(width*S)))

def rect(x,y,w,h,fill=BG,stroke=LINE,width=2):
    svg.append(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" fill="{fill}" stroke="{stroke}" stroke-width="{width}"/>')
    draw.rectangle((x*S,y*S,(x+w)*S,(y+h)*S),fill=fill,outline=stroke,width=max(1,int(width*S)))

def circle(x,y,r,fill):
    svg.append(f'<circle cx="{x}" cy="{y}" r="{r}" fill="{fill}"/>');draw.ellipse(((x-r)*S,(y-r)*S,(x+r)*S,(y+r)*S),fill=fill)

def arrow(x1,y1,x2,y2,color=TEAL,width=2.5):
    line(x1,y1,x2,y2,color,width);a=math.atan2(y2-y1,x2-x1)
    for offset in [-0.48,0.48]:line(x2,y2,x2-13*math.cos(a+offset),y2-13*math.sin(a+offset),color,width)

def panel(x,y,w,h,label,title):
    rect(x,y,w,h);text(x+28,y+52,label,39,TEAL,True,True);text(x+76,y+48,title,30,INK,True)

# Editorial title and model scale.
text(70,132,"FLY",102,INK,True,True)
text(1930,72,"TECHNICAL METHODS",23,MUTED,True,anchor="end")
text(1930,106,"CONNECTOME × CAPITAL",20,MUTED,anchor="end")
text(70,190,"Neural dynamics. Constrained action. Verifiable state.",39,INK,False,True)
line(70,224,1930,224,INK,2)
for x,number,label in [(70,"166,700","RETAINED NEURONS"),(710,"25,582,938","DIRECTED CONNECTIONS"),(1380,"500 ms","SIMULATED DECISION WINDOW")]:
    text(x,279,number,39,INK,True);text(x,313,label,18,MUTED,True)

# A: the exact qualitative states of the declared encoder.
panel(70,352,900,417,"a","Market-to-neural transduction")
text(105,445,"Completed candles → normalized movement",25,MUTED)
text(105,491,"z(t) = log[p(t) / p(t−3)] / [√3 σ(t)]",32,INK,False,True)
text(105,527,"60-return volatility · 3-bar horizon · explicit deadband",21,MUTED)
for x,z,label in [(110,-.75,"NEGATIVE MOVE"),(397,0,"NEUTRAL"),(684,.75,"POSITIVE MOVE")]:
    values=(128,128) if z==0 else ((176,0) if z<0 else (0,176))
    for i,v in enumerate(values):rect(x+i*119,559,119,98,fill=f'#{v:02x}{v:02x}{v:02x}',stroke=BG,width=0.5)
    text(x+119,695,label,19,MUTED,True,anchor="middle")
    text(x+119,731,('z = 0' if z==0 else 'z = −0.75' if z<0 else 'z = +0.75'),23,INK,anchor="middle")

# B: topology is deliberately schematic, not a claim of anatomical coordinates.
panel(1030,352,900,417,"b","Retained graph & candidate plasticity")
rng=random.Random(23);nodes=[]
for cx,cy,rx,ry,count in [(1125,542,35,95,12),(1268,543,87,116,37),(1385,540,40,84,15)]:
    group=[]
    for _ in range(count):
        a=rng.random()*2*math.pi;r=math.sqrt(rng.random());group.append((cx+math.cos(a)*rx*r,cy+math.sin(a)*ry*r))
    nodes.append(group)
for _ in range(100):
    group=rng.randrange(2);a=rng.choice(nodes[group]);b=rng.choice(nodes[group+1]);line(*a,*b,color="#ccdce3",width=.9)
for _ in range(25):
    a,b=rng.sample(nodes[1],2);line(*a,*b,color="#d5e0e7",width=.8)
for g in nodes:
    for x,y in g:circle(x,y,4.4,BLUE)
text(1251,694,"SCHEMATIC CONNECTIVITY",18,MUTED,True,anchor="middle")
arrow(1435,520,1480,520,BLUE)
rect(1497,438,390,114,fill="#f4f8fa")
text(1520,477,"Spiking state",26,INK,True);text(1520,516,"0.1 ms event schedule",23,MUTED)
rect(1497,582,390,145,fill="#fcf8f1",stroke="#e9dac5")
text(1520,622,"Restricted plasticity",26,GOLD,True)
text(1520,664,"KC → MBON07 / 11",24,INK)
text(1520,700,"0.1 ≤ W / W(base) ≤ 2",23,MUTED)
arrow(1655,554,1655,579,GOLD)

# C: proposal semantics and the actual long-flat state space.
panel(70,811,900,438,"c","Contract-constrained execution")
text(105,904,"Neural proposal ≠ execution authorization",25,MUTED)
rect(115,955,223,96,fill="#f4f8fa");text(226,1015,"FLAT",34,INK,True,anchor="middle")
rect(705,955,223,96,fill="#edf6f5",stroke="#b7d8d5");text(816,1015,"LONG",34,TEAL,True,anchor="middle")
arrow(355,980,687,980);text(519,959,"BUY · bounded entry",21,TEAL,anchor="middle")
arrow(687,1040,355,1040);text(519,1077,"SELL · reduce only",21,TEAL,anchor="middle")
line(108,1111,931,1111)
text(110,1154,"Entry budget ≤ min(M, 100E / 101)",28,INK,False,True)
text(110,1195,"Sequence · freshness · exposure · pending settlement",22,MUTED)
text(110,1227,"HOLD or veto: no new position. No short entry.",21,MUTED)

# D: ledger quantities, not fabricated return or equity curves.
panel(1030,811,900,438,"d","Capital accounting & profit return")
text(1065,904,"Principal, execution equity and profit remain distinct",24,MUTED)
for x,label in [(1068,"Tax principal"),(1360,"Account equity"),(1652,"Eligible profit")]:
    rect(x,951,240,89,fill="#f4f8fa");text(x+120,1007,label,25,INK,True,anchor="middle")
arrow(1315,994,1351,994);arrow(1607,994,1643,994)
text(1065,1098,"P = max(0, min(N − D − O, E − B − O))",28,INK,False,True)
text(1065,1140,"Evaluated only when flat, settled and eligible.",23,MUTED)
line(1068,1169,1890,1169)
text(1065,1213,"Profit return → budgeted token repurchase",26,TEAL,True)

line(70,1305,1930,1305,INK,2)
text(70,1352,"REPRODUCIBILITY",22,INK,True)
text(414,1352,"source  →  input  →  neural state  →  proposal  →  settlement",26,TEAL)
text(70,1405,"Architecture schematic · Not an anatomical rendering or a performance result · Fly technical methods",20,MUTED)
svg.append('</svg>');OUT.mkdir(parents=True,exist_ok=True)
(OUT/'fly-architecture.svg').write_text('\n'.join(svg)+'\n',encoding='utf-8')
img.resize((W,H),Image.Resampling.LANCZOS).save(OUT/'fly-architecture.png',optimize=True)
print('Architecture SVG and PNG generated')
