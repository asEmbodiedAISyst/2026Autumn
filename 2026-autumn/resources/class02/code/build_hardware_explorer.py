"""Build the offline Class 02 record explorer from every supplied CSV row.

Run: python code/build_hardware_explorer.py
No network or hardware access. All scripts/data are embedded except local MiSans.
"""
from pathlib import Path
import csv
import json

ROOT = Path(__file__).resolve().parents[1]
FIELDS = ["t_state_s", "goal_position_raw", "position_trajectory_raw", "present_position_raw",
          "present_velocity_raw", "present_current_raw", "present_pwm_raw", "input_voltage_raw", "temperature_C"]

TEMPLATE = r'''<!doctype html>
<html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>XC330 recorded telemetry explorer</title>
<style>
@font-face{font-family:MiSans;src:local('MiSans Regular'),local('MiSans-Regular'),url('../../source/fonts/MiSans-Regular.ttf') format('truetype');font-weight:400;font-display:swap}
@font-face{font-family:MiSans;src:local('MiSans Semibold'),local('MiSans-Semibold'),url('../../source/fonts/MiSans-Semibold.ttf') format('truetype');font-weight:600;font-display:swap}
*{box-sizing:border-box}body{margin:0;background:#fff;color:#20252b;font-family:MiSans,sans-serif;line-height:1.5}
main{max-width:1100px;margin:auto;padding:24px}h1{font-size:26px;margin:0 0 6px;font-weight:600}p{margin:6px 0 16px}.context{color:#535e69;font-size:14px}
.controls{display:flex;align-items:end;gap:18px;flex-wrap:wrap;border-top:1px solid #d5dce2;border-bottom:1px solid #d5dce2;padding:16px 0;margin:16px 0}
label{font-size:14px;display:grid;gap:6px}select,input,button{font:inherit}select,button{border:1px solid #7c8792;border-radius:4px;background:white;color:#20252b;padding:7px 10px}.sample{flex:1;min-width:230px}input[type=range]{width:100%;accent-color:#0072b2}:focus-visible{outline:3px solid #d55e00;outline-offset:3px}
canvas{display:block;width:100%;height:260px}h2{font-size:18px;margin:18px 0 8px;font-weight:600}.legend{display:flex;gap:20px;flex-wrap:wrap;font-size:13px}.legend span:before{content:'';display:inline-block;width:25px;border-top:3px solid;margin-right:6px;vertical-align:middle}.goal{color:#333}.ref{color:#b64c00}.measured{color:#0072b2}.goal:before{border-top-style:dashed!important}.ref:before{border-top-style:dotted!important}
table{border-collapse:collapse;width:100%;font-size:14px}th,td{text-align:left;padding:8px;border-bottom:1px solid #dce2e7}th{font-weight:600}output{font-variant-numeric:tabular-nums}.note{border-left:3px solid #0072b2;padding-left:12px;font-size:14px}footer{margin-top:18px;color:#535e69;font-size:12px}
@media(max-width:600px){main{padding:14px}h1{font-size:22px}canvas{height:230px}.controls{gap:12px}th,td{padding:6px}}
</style>
<main><h1>XC330 recorded telemetry explorer</h1>
<p class="context">One physical motor-only episode · ID 5 · firmware 53 · Mode 5 · H2 · 2,601 readings. This viewer does not connect to hardware.</p>
<div class="controls">
<label class="sample" for="row">Sample index <output id="sampleLabel">400</output><input id="row" type="range" min="0" max="2600" value="400" step="1"></label>
<label for="units">Display units<select id="units"><option value="engineering">Engineering units</option><option value="raw">Raw register values</option></select></label>
<label for="window">Time window<select id="window"><option value="full">Entire episode</option><option value="reversal">First reversal, 1.1 to 2.1 s</option></select></label>
<label for="channel">Second plot<select id="channel"><option value="velocity">Present Velocity</option><option value="current">Present Current</option><option value="pwm">Present PWM</option><option value="voltage">Input Voltage</option><option value="temperature">Temperature</option></select></label>
<button type="button" id="worked">Worked sample 400</button></div>
<p id="sampleInfo" aria-live="polite"></p>
<h2>Goal, internal reference and measured position</h2>
<div class="legend"><span class="goal">Goal readback</span><span class="ref">Internal reference</span><span class="measured">Measured position</span></div>
<canvas id="position" role="img" aria-label="Three recorded position signals with the selected sample marked"></canvas>
<h2 id="channelHeading">Present Velocity</h2><canvas id="secondary" role="img" aria-label="Selected recorded telemetry channel"></canvas>
<h2>Decode the selected sample</h2><table><thead><tr><th>Field</th><th>Raw value</th><th>Engineering interpretation</th></tr></thead><tbody id="sampleTable"></tbody></table>
<p class="note">Position uses count 2,048 as the declared zero. Values are already signed. Present Current is reported input-supply current; it is not calibrated output torque. Host receive-end time is not an independent physical sampling timestamp. Curves connect original samples; no smoothing or simulated motion is added.</p>
<footer>Source: M0__H2__P01_slow_triangle__R01, 1 September 2026. Figure/data generation is documented in media/FIGURE-CODE.md. Classroom static figures provide the same required evidence.</footer></main>
<script id="record" type="application/json">__RECORD__</script>
<script>
'use strict';
const rows=JSON.parse(document.getElementById('record').textContent),el=id=>document.getElementById(id);
const specs={velocity:[4,.229,'Velocity (r/min)','Present Velocity'],current:[5,1,'Reported input current (mA)','Present Current'],pwm:[6,.113,'Reported PWM (%)','Present PWM'],voltage:[7,.1,'Reported input voltage (V)','Input Voltage'],temperature:[8,1,'Internal temperature (deg C)','Temperature']};
function linePlot(canvas,series,axisLabel,index,xRange){
 const rect=canvas.getBoundingClientRect(),dpr=window.devicePixelRatio||1;
 canvas.width=Math.round(rect.width*dpr);canvas.height=Math.round(rect.height*dpr);
 const c=canvas.getContext('2d');if(!c)return;c.scale(dpr,dpr);const W=rect.width,H=rect.height;
 const left=W<600?65:82,right=20,top=18,bottom=50,x0=xRange[0],x1=xRange[1];
 const selected=rows.map((r,i)=>[r[0],i]).filter(r=>r[0]>=x0&&r[0]<=x1);
 let ymin=Infinity,ymax=-Infinity;for(const s of series)for(const pair of selected){const v=s.values[pair[1]];ymin=Math.min(ymin,v);ymax=Math.max(ymax,v)}
 const pad=Math.max((ymax-ymin)*.12,ymax===ymin?Math.max(1,Math.abs(ymax)*.02):.01);ymin-=pad;ymax+=pad;
 const x=t=>left+(t-x0)/(x1-x0)*(W-left-right),y=v=>top+(ymax-v)/(ymax-ymin)*(H-top-bottom);
 c.clearRect(0,0,W,H);c.font='12px MiSans';c.fillStyle='#535e69';c.textAlign='right';
 for(let i=0;i<=4;i++){let value=ymin+(ymax-ymin)*i/4,py=y(value);c.strokeStyle='#e1e5e9';c.setLineDash([]);c.beginPath();c.moveTo(left,py);c.lineTo(W-right,py);c.stroke();c.fillText(value.toFixed(Math.abs(ymax-ymin)<2?2:1),left-8,py+4)}
 c.textAlign='center';for(let i=0;i<=5;i++){let t=x0+(x1-x0)*i/5;c.fillText(t.toFixed(x1-x0<3?2:1),x(t),H-bottom+20)}
 c.fillText('Host receive-end time (s)',(left+W-right)/2,H-7);c.save();c.translate(15,(top+H-bottom)/2);c.rotate(-Math.PI/2);c.fillText(axisLabel,0,0);c.restore();
 for(const s of series){c.strokeStyle=s.color;c.lineWidth=1.7;c.setLineDash(s.dash||[]);c.beginPath();let first=true;for(const pair of selected){let px=x(pair[0]),py=y(s.values[pair[1]]);if(first){c.moveTo(px,py);first=false}else c.lineTo(px,py)}c.stroke()}
 const sample=rows[index];if(sample[0]>=x0&&sample[0]<=x1){c.setLineDash([3,3]);c.strokeStyle='#66717d';c.lineWidth=1;c.beginPath();c.moveTo(x(sample[0]),top);c.lineTo(x(sample[0]),H-bottom);c.stroke();for(const s of series){c.setLineDash([]);c.fillStyle=s.color;c.beginPath();c.arc(x(sample[0]),y(s.values[index]),3,0,Math.PI*2);c.fill()}}
}
function update(){
 const index=Number(el('row').value),r=rows[index],raw=el('units').value==='raw';el('sampleLabel').value=String(index);
 el('sampleInfo').textContent='Sample '+index+' of 2600 · host receive-end time '+r[0].toFixed(6)+' s · '+(raw?'raw register display':'engineering-unit display');
 const xr=el('window').value==='reversal'?[1.1,2.1]:[0,13.01];const p=k=>rows.map(r=>raw?r[k]:(r[k]-2048)*360/4096);
 linePlot(el('position'),[{values:p(1),color:'#333333',dash:[6,4]},{values:p(2),color:'#d55e00',dash:[2,3]},{values:p(3),color:'#0072b2'}],raw?'Position (counts)':'Position relative to 2048 (deg)',index,xr);
 const spec=specs[el('channel').value];el('channelHeading').textContent=spec[3];linePlot(el('secondary'),[{values:rows.map(r=>r[spec[0]]*(raw?1:spec[1])),color:'#0072b2'}],raw?spec[3]+' (raw)':spec[2],index,xr);
 const names=['Goal Position','Position Trajectory','Present Position','Present Velocity','Present Current','Present PWM','Input Voltage','Temperature'];
 const interpretations=[(r[1]-2048)*360/4096,(r[2]-2048)*360/4096,(r[3]-2048)*360/4096,r[4]*.229,r[5],r[6]*.113,r[7]*.1,r[8]];
 const labels=['deg relative to 2048','deg relative to 2048','deg relative to 2048','r/min','mA reported input current','percent','V','deg C'];
 el('sampleTable').replaceChildren();names.forEach((name,i)=>{const tr=document.createElement('tr');[name,String(r[i+1]),interpretations[i].toFixed(i===7?0:3)+' '+labels[i]].forEach(text=>{const td=document.createElement('td');td.textContent=text;tr.append(td)});el('sampleTable').append(tr)});
}
['row','units','window','channel'].forEach(id=>el(id).addEventListener('input',update));
el('worked').addEventListener('click',()=>{el('row').value='400';el('window').value='reversal';update()});
window.addEventListener('resize',update);document.fonts.ready.then(()=>{update();document.documentElement.dataset.ready='true'});
</script></html>'''


if __name__ == "__main__":
    with (ROOT / "data/xc330-hardware-demo/telemetry_events.csv").open(newline="") as stream:
        rows = list(csv.DictReader(stream))
    data = [[float(row[key]) if key == "t_state_s" else int(row[key]) for key in FIELDS] for row in rows]
    if len(data) != 2601:
        raise ValueError("Unexpected record size")
    html = TEMPLATE.replace("__RECORD__", json.dumps(data, separators=(",", ":")))
    path = ROOT / "media/interactive/hardware-telemetry.html"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(html)
    print(f"Built {path.name}: all {len(data)} rows, no external dependencies")
