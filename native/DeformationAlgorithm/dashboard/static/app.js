'use strict';
const $=id=>document.getElementById(id), clone=x=>JSON.parse(JSON.stringify(x));
let catalog,recipe,pop='golgi_cell',cellIndex=0,previewMode='mean',previewData,baseData,seq=0,timer,valid=false;
let networkData=null,networkDirty=true,networkBusy=false,networkRequestSeq=0,connectionName='glomerulus_to_granule';
const CELL_ORDER=['golgi_cell','granule_cell','stellate_cell','basket_cell','purkinje_cell'];
const cache=new Map(), zero=()=>({mean:0,sigma:0});
const fmt=(n,d=1)=>(Object.is(Number(n),-0)?0:Number(n)).toLocaleString('en-US',{maximumFractionDigits:d,minimumFractionDigits:d});
const uiColour=name=>getComputedStyle(document.documentElement).getPropertyValue(name).trim();
const uiAccent=()=>uiColour('--accent');
const colors={granular_layer:'#0c8995',purkinje_layer:'#bc8c55',b_molecular_layer:'#8777b5',t_molecular_layer:'#bbb0d4'};
async function api(path,body){const r=await fetch(path,body?{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)}:{});const x=await r.json();if(!r.ok)throw new Error(x.error||r.statusText);return x;}
function setValid(ok,text){valid=ok;if($('cockpit-status'))$('cockpit-status').textContent=ok?'Updated':text==='Invalid configuration'?'Last valid preview':'Updating…';$('status').textContent=text;$('status').classList.toggle('invalid',!ok);$('download').disabled=!ok;$('export-package').disabled=!ok;$('generate-network').disabled=true;$('prepare-command').disabled=!ok;$('save-profile').disabled=!ok;}
function error(text){$('error').textContent=text;$('error').classList.toggle('hidden',!text);}
function notice(text){$('notice').textContent=text;$('notice').classList.toggle('hidden',!text);}
function rule(p=pop){recipe.populations??={};return recipe.populations[p]??={};}
function cells(p=pop){return rule(p).cells??={};}
function layerOf(p=pop){return catalog.populations.find(x=>x.id===p).layer;}
function effective(key,p=pop){let out=zero();for(const c of [recipe.defaults||{},recipe.layers?.[layerOf(p)]?.cells||{},rule(p).cells||{}]){if(key==='df_percent'){if(c.df_percent)out=c.df_percent;}else{if(['neurite_length_df_percent','neurite_radius_df_percent','soma_size_df_percent'].includes(key)&&c.df_percent)out=c.df_percent;if(c[key])out=c[key];}}return clone(out);}
function noteField(host,paths,title){
 const box=document.createElement('label');box.className='parameter-note';box.append(document.createTextNode('Note / reference'));
 const input=document.createElement('textarea');input.rows=2;input.maxLength=4000;input.placeholder='Optional rationale or reference';input.setAttribute('aria-label',title+' note');
 const list=Array.isArray(paths)?paths:[paths];const vals=list.map(p=>recipe.annotations?.parameter_notes?.[p]||'');input.value=vals.every(v=>v===vals[0])?vals[0]:'';if(new Set(vals).size>1)input.placeholder='Different notes exist in details; entering a note here applies it to all controlled parameters.';
 input.oninput=()=>{recipe.annotations??={};recipe.annotations.parameter_notes??={};for(const path of list)recipe.annotations.parameter_notes[path]=input.value;schedule();};box.append(input);host.append(box);
}
function rawText(items,change){return items.map(i=>`${i.label}: ${precise(i.value)} → ${precise(i.current?i.current():i.value*(1+change/100))} ${i.unit}`).join(' · ');}
function precise(v){if(v===0)return '0';return Math.abs(v)<.001?Number(v).toExponential(3):Number(v).toLocaleString('en-US',{maximumSignificantDigits:5});}
function densityItems(p){const sp=p.spatial;if(sp.planar_density!==undefined)return [{label:p.name,value:sp.planar_density,unit:'cells/µm²'}];if(sp.density!==undefined)return [{label:p.name,value:sp.density,unit:'cells/µm³'}];return [{label:p.name+' / glomerulus ratio',value:sp.count_ratio,unit:'MF/glomerulus',current:()=>{const g=liveGeometry().geometry.populations;return g.glomerulus.density_factor>0?sp.count_ratio*g[p.id].density_factor/g.glomerulus.density_factor:0;}}];}
function cellRaw(key){const b=cache.get(pop);if(!b)return [];const sp=catalog.populations.find(p=>p.id===pop).spatial;
 return key==='neurite_length_df_percent'?[{label:'Total neurite length',value:b.metrics.length_um,unit:'µm'}]:key==='neurite_radius_df_percent'?[{label:'Median SWC radius',value:b.raw_sizes.neurite_radius_um,unit:'µm'}]:[{label:'SWC soma radius',value:b.raw_sizes.soma_radius_um,unit:'µm'},{label:'Placement radius',value:sp.radius,unit:'µm'}];}
function paramControl(host,title,key,spec,onChange,{angular=false,disabled=false,toggle=null,toggleChecked=null,single=true,scalar=false,path,description='',raw=()=>[]}={}){
 const f=document.createElement('div');f.className='field'+(disabled?' disabled':'');const h=document.createElement('div');h.className='field-title';
 const label=document.createElement(toggle?'label':'span');if(toggle){const check=document.createElement('input');check.type='checkbox';check.checked=toggleChecked??!disabled;check.setAttribute('aria-label',`Override ${title}`);check.onchange=()=>toggle(check.checked);label.append(check);}label.append(document.createTextNode(title));h.append(label);const unit=document.createElement('small');unit.textContent=angular?'degrees':'Change %';h.append(unit);f.append(h);
 const desc=document.createElement('p');desc.className='parameter-description';desc.textContent=description;f.append(desc);
 const row=document.createElement('div');row.className='row';const caption=document.createElement('label');caption.textContent=angular?'Angle':'Change';const range=document.createElement('input');range.type='range';range.min=angular?-180:-100;range.max=angular?180:100;range.step=.5;range.value=spec.mean;range.disabled=disabled;
 const number=document.createElement('input');number.type='number';number.min=range.min;number.max=range.max;number.step=.5;number.value=spec.mean;number.disabled=disabled;
 const aid=`${key}-mean-${host.id||host.dataset.id||title}`.replace(/[^\w-]/g,'-');number.id=aid;caption.htmlFor=aid;number.setAttribute('aria-label',title+' change');range.setAttribute('aria-label',title+' change slider');
 const values=document.createElement('div');values.className='raw-values';f._refreshRaw=()=>{values.textContent=angular?(key==='bifurcation_tilt_deg'?`Requested angle change: ${precise(spec.mean)}°`:`Reference 0° → Current ${precise(spec.mean)}°`):rawText(raw(),spec.mean);};
 function change(value){if(!Number.isFinite(value))return;if(path?.includes('.cells.'))materializeCellDetails();else if(path?.startsWith('layers.')||path?.endsWith('.density_df_percent'))clearOverall('network-morphological');if(toggle)f.querySelector('input[type=checkbox]').checked=true;spec={...spec,mean:value,sigma:0};if(!angular)spec.bounds=[-100,100];number.value=value;range.value=value;onChange(scalar?spec.mean:clone(spec));f._refreshRaw();schedule();}
 range.oninput=()=>change(+range.value);number.oninput=()=>{if(number.value!=='')change(+number.value);};row.append(caption,range,number);f.append(row,values);f._refreshRaw();
 if(path)noteField(f,path,title);host.append(f);return f;
}
function refreshRaw(){document.querySelectorAll('.field').forEach(f=>f._refreshRaw?.());refreshOverallRaw();}
function refreshOverallRaw(){for(const [scope,c] of Object.entries(metaControls)){if(!c.raw)continue;if(scope==='cell-morphological'){c.raw.textContent='';c.raw.hidden=true;}else c.raw.textContent=`Cortical depth: ${precise(catalog.network.z)} → ${precise(liveGeometry().network.z)} µm · Density factor: ${metaValues(scope).every(v=>v===metaValues(scope)[0])?'1 → '+precise(1+metaValues(scope)[0]/100):'mixed; see details'}`;}}

function group(host,text){const h=document.createElement('div');h.className='group-title';h.textContent=text;host.append(h);}
function buildCells(){const host=$('cell-controls');host.replaceChildren();$('cell-title').textContent=catalog.populations.find(x=>x.id===pop).name;
 const fields=[['neurite_length_df_percent','Neurite length','Scales dendrites and axon about their soma attachment; no new branches.'],['neurite_radius_df_percent','Neurite radius','Scales the radius of every neurite segment; topology stays fixed.'],['soma_size_df_percent','Soma size','Scales soma dimensions and the radius reserved for BSB placement.']];
 for(const [key,label,description] of fields)paramControl(host,label,key,effective(key),x=>cells()[key]=x,{path:`populations.${pop}.cells.${key}.mean`,description,raw:()=>cellRaw(key)});
 buildBifurcation();buildRotations();
 $('pop-tabs').querySelectorAll('button').forEach(b=>b.classList.toggle('active',b.dataset.pop===pop));
}
function buildBifurcation(){const host=$('bifurcation-controls');host.replaceChildren();group(host,'DENDRITIC BIFURCATIONS');
 const key='bifurcation_tilt_deg',path=`populations.${pop}.cells.${key}.mean`;
 paramControl(host,'Bifurcation tilt',key,effective(key),x=>{cells()[key]=x;if(x.mean!==0){recipe.annotations??={};recipe.annotations.parameter_notes??={};recipe.annotations.parameter_notes[path]??='Mavroudis et al. (2017), Fig. 1D: altered Purkinje local/remote bifurcation tilt in human schizophrenia. This angle change is exploratory, not a measured disease effect or fitted reproduction. https://rjme.ro/RJME/resources/files/580217419424.pdf';}},{angular:true,path,description:'Change each local parent-facing daughter angle in degrees. Negative decreases tilt; positive increases it. Dendritic subtrees rotate about their junctions; soma and axon stay fixed.'});
 const info=document.createElement('p');info.className='rotation-explanation';info.textContent='Binary dendritic forks only; resulting angles are limited to 1–179°. Length, radius, topology and DCI stay unchanged. Local and remote tilt are measured below. This is separate from whole-cell orientation.';host.append(info);
 const link=document.createElement('a');link.href='https://rjme.ro/RJME/resources/files/580217419424.pdf';link.target='_blank';link.rel='noopener';link.textContent='Mavroudis et al. 2017 · Fig. 1D · exploratory mapping';host.append(link);
}
function buildRotations(){const host=$('rotation-controls');host.replaceChildren();group(host,'WHOLE-CELL ORIENTATION');
 const hint=document.createElement('p');hint.className='rotation-explanation';hint.textContent='Rotates the actual morphology about its soma in network axes. X/Y tilt the cell; Z rotates it around cortical depth. Applied in order X → Y → Z. The soma position, branch lengths and DCI stay unchanged. The same angles apply to all cells of this population.';host.append(hint);
 for(const axis of ['x','y','z']){const key=`rotation_${axis}_deg`;paramControl(host,axis==='z'?'Rotation Z':`Tilt ${axis.toUpperCase()}`,key,effective(key),x=>cells()[key]=x,{angular:true,path:`populations.${pop}.cells.${key}.mean`,description:axis==='z'?'Rotate around the depth axis Z (degrees).':'Tilt around the fixed '+axis.toUpperCase()+' axis (degrees).'});}
 const tools=document.createElement('div');tools.className='angle-tools';for(const [label,action] of [['Flip X 180°',()=>{cells().rotation_x_deg={mean:180,sigma:0};}],['Reset angles',()=>{for(const a of ['x','y','z'])cells()[`rotation_${a}_deg`]=zero();}]]){const b=document.createElement('button');b.textContent=label;b.onclick=()=>{materializeCellDetails();action();buildRotations();schedule();};tools.append(b);}host.append(tools);
}

function buildNetwork(){const host=$('layer-controls');host.replaceChildren();recipe.layers??={};
 for(const layer of catalog.layers){const r=recipe.layers[layer.id]??={};const box=document.createElement('div');box.className='layer-control';box.dataset.id=layer.id;
 const title=document.createElement('h3');title.textContent=layer.name;const summary=document.createElement('span');summary.className='layer-summary';summary.id='summary-'+layer.id;title.append(summary);box.append(title);
 paramControl(box,'Thickness','thickness',{mean:netValue(r.thickness_df_percent),sigma:0},v=>r.thickness_df_percent=v,{single:true,scalar:true,path:`layers.${layer.id}.thickness_df_percent`,description:'Vertical extent of this layer; changing it moves the layers above.',raw:()=>[{label:'Thickness',value:layer.thickness_um,unit:'µm'}]});
 paramControl(box,'Layer density','density',{mean:netValue(r.density_df_percent),sigma:0},v=>{r.density_df_percent=v;buildDensities();},{single:true,scalar:true,path:`layers.${layer.id}.density_df_percent`,description:'Scales native population densities in this layer, unless individually overridden. PC density is per area.',raw:()=>catalog.populations.filter(p=>p.layer===layer.id).flatMap(densityItems)});host.append(box);}
 buildDensities();
}
function buildDensities(){const host=$('density-controls');host.replaceChildren();for(const p of catalog.populations){const r=rule(p.id),enabled=Object.hasOwn(r,'density_df_percent');
 const inherited=netValue(recipe.layers?.[p.layer]?.density_df_percent);
 const box=paramControl(host,p.name,p.id+'-density',{mean:netValue(enabled?r.density_df_percent:inherited),sigma:0},v=>r.density_df_percent=v,{single:true,scalar:true,path:`populations.${p.id}.density_df_percent`,description:p.spatial.count_ratio!==undefined?'Scales the MF target count relative to its healthy value; the glomerulus-relative native ratio is adjusted.':'Population density override; replaces the layer density factor.',raw:()=>densityItems(p),disabled:false,toggleChecked:enabled,toggle:on=>{clearOverall('network-morphological');if(on)r.density_df_percent=clone(inherited);else delete r.density_df_percent;buildDensities();schedule();}});
 const txt=document.createElement('small');txt.id='density-'+p.id;txt.textContent=enabled?'Population override':'Inherited from layer';box.append(txt);}
}
function nonzeroSpec(x){if(typeof x==='number')return x!==0;return x&&typeof x==='object'&&(Object.hasOwn(x,'mean')?(x.mean!==0||x.sigma!==0):Object.entries(x).some(([k,v])=>k!=='bounds'&&nonzeroSpec(v)));}
function schedule(){queueLiveNetwork();renderNotes();refreshMeta(false);if(recipe.name==='Identity control'&&(nonzeroSpec(recipe.defaults)||nonzeroSpec(recipe.layers)||nonzeroSpec(recipe.populations)||Object.values(recipe.electrical?.cells||{}).some(r=>Object.values(r).some(Boolean))||Object.values(recipe.electrical?.connections||{}).some(m=>Object.values(m).some(c=>Object.values(c).some(r=>Object.values(r).some(Boolean))))))recipe.name='Custom cortical design';$('profile-name').value=recipe.name;invalidateCommand();networkDirty=true;setValid(false,'Pending validation…');error('');seq++;clearTimeout(timer);timer=setTimeout(update,240);}
async function update(){const ticket=++seq,requested=pop;setValid(false,'Validating…');try{
 const [b,p]=await Promise.all([cache.has(requested)?cache.get(requested):api('/api/morphology?population='+requested),api('/api/preview',{recipe,population:requested,cell_index:cellIndex,preview_mode:previewMode})]);cache.set(requested,b);if(ticket!==seq)return;
 baseData=b;previewData=p;error('');setValid(true,'Valid configuration');$('yaml-editor').value=p.yaml;render();
 }catch(e){if(ticket!==seq)return;setValid(false,'Invalid configuration');error(e.message+' — Plots show the last valid configuration.');$('yaml-editor').value=JSON.stringify(recipe,null,2);}}
function render(){refreshRaw();renderMorph();drawDendrogram();drawHist();drawLayers();if(networkData)updateNetworkStatus();
 $('profile-name').value=recipe.name;$('cell-presence').textContent=previewData.present?(previewData.types.every(t=>t==='soma')?'Soma only':'Cell present'):'Cell removed · reference shown';
 for(const key of ['neurite_length_df_percent','neurite_radius_df_percent','soma_size_df_percent'])if(!Object.hasOwn(cells(),key)){const spec=effective(key);for(const which of ['mean','sigma']){const el=$(`${key}-${which}-cell-controls`);if(el){el.value=spec[which];el.previousElementSibling.value=spec[which];}}}
 const v=previewData.parameters;const small=(label,value)=>`<span>${label}<b>${value}</b></span>`;
 $('sample-values').innerHTML=small('Length change',fmt(v.neurite_length_df_percent)+'%')+small('Radius change',fmt(v.neurite_radius_df_percent)+'%')+small('Soma change',fmt(v.soma_size_df_percent)+'%')+small('X / Y / Z', ['x','y','z'].map(a=>fmt(v[`rotation_${a}_deg`],0)+'°').join(' / '));
 renderCellOverview();renderTiltSummary();
 for(const l of catalog.layers){const g=previewData.geometry.layers[l.id];$('summary-'+l.id).textContent=`${fmt(l.thickness_um,0)} → ${fmt(g.thickness_um)} µm`;}
 for(const p of catalog.populations){const f=previewData.geometry.populations[p.id].density_factor;$('density-'+p.id).textContent=`${Object.hasOwn(rule(p.id),'density_df_percent')?'Override':'From layer'} · ${fmt(100*f)}% of original density`;}
 const dc=previewData.dci,ref=baseData.dci;$('dci-current').textContent=`${precise(dc.dci)} µm`;$('dci-value').textContent=`${precise(ref.dci)} → ${precise(dc.dci)} µm`;$('dci-change').textContent=changeLabel(ref.dci,dc.dci);$('dci-components').textContent=`${dc.tips} tips · order sum ${dc.tip_order_sum} · ${dc.primary_dendrites} primary dendrites · ${precise(dc.length_um)} µm dendrites`;
 $('morph-title').textContent=catalog.populations.find(x=>x.id===pop).name+' morphology';
 $('source-info').textContent=`${baseData.source} · ${baseData.nodes.length.toLocaleString('en-US')} SWC nodes`;
}
function changeLabel(reference,current){
 if(reference===0)return current===0?'No change':'Change from zero reference';
 const change=100*(current/reference-1);return `${change>0?'+':''}${fmt(Math.abs(change)<1e-8?0:change)}% from healthy`;
}
function renderTiltSummary(){const b=baseData.bifurcation_tilt,p=previewData.bifurcation_tilt,a=previewData.tilt_audit;if(!b||!p)return;
 const metric=key=>`${b[key].mean_deg===null?'n/a':fmt(b[key].mean_deg,2)+'°'} → ${p[key].mean_deg===null?'n/a':fmt(p[key].mean_deg,2)+'°'}`;
 $('tilt-summary').innerHTML=`<strong>Dendritic bifurcation tilt</strong><div class="tilt-metrics"><span>Local mean<b>${metric('local')}</b></span><span>Remote mean<b>${metric('remote')}</b></span></div><p>${p.local.n} measured binary forks · requested change ${fmt(a.requested_change_deg)}° · ${a.clipped_daughter_angles} daughter angles clipped</p><details><summary>Definition, scope & reference</summary><p></p><p></p><p></p><a target="_blank" rel="noopener"></a></details>`;
 $('comparison-info').textContent=`Local tilt: ${metric('local')} · Remote tilt: ${metric('remote')} · ${p.local.n} binary forks · Δ ${fmt(a.requested_change_deg)}° · Same scale and camera`;
 const details=$('tilt-summary').querySelector('details'),texts=details.querySelectorAll('p');texts[0].textContent=p.method.definition;texts[1].textContent=p.method.scope;texts[2].textContent=`${p.duplicate_junctions_resolved} forks measured across duplicate junction samples; ${p.undefined_local} undefined local angles, ${p.skipped_nonbinary} nonbinary forks and ${p.skipped_mixed_subtrees} mixed subtrees excluded. Remote tilt is not a second target.`;const link=details.querySelector('a');link.href=p.method.reference;link.textContent=p.method.reference_label;
}
function renderCellOverview(){
 const b=baseData,p=previewData,v=p.parameters,sp=catalog.populations.find(x=>x.id===pop).spatial;
 $('cockpit-title').textContent=`${catalog.populations.find(x=>x.id===pop).name} · healthy → current`;
 const medianRadius=type=>{const radii=p.nodes.filter((_,i)=>type==='neurite'?p.types[i]!=='soma':p.types[i]==='soma').map(n=>n[3]).sort((a,b)=>a-b);const m=Math.floor(radii.length/2);return radii.length?(radii.length%2?radii[m]:(radii[m-1]+radii[m])/2):0;};
 const metrics=[['Neurite length',b.metrics.length_um,p.metrics.length_um,'µm'],['Dendritic length',b.dendrite_metrics.length_um,p.dendrite_metrics.length_um,'µm'],['Median neurite radius',b.raw_sizes.neurite_radius_um,medianRadius('neurite'),'µm'],['SWC soma radius',b.raw_sizes.soma_radius_um,medianRadius('soma'),'µm'],['Placement radius',sp.radius,p.present?sp.radius*(1+v.soma_size_df_percent/100):0,'µm'],['Dendritic branch points',b.dendrite_metrics.branch_points,p.dendrite_metrics.branch_points,''],['Dendritic tips',b.dendrite_metrics.tips,p.dendrite_metrics.tips,''],['DCI',b.dci.dci,p.dci.dci,'µm']];
 $('metrics').innerHTML=metrics.map(([name,ref,current,unit])=>`<div class="metric" data-metric="${name}"><small>${name}</small><div class="metric-comparison"><span>${precise(ref)}</span><span aria-hidden="true">→</span><strong>${precise(current)}</strong><small>${unit}</small></div><span class="metric-delta">${changeLabel(ref,current)}</span></div>`).join('');
}
function canvasSetup(id){const canvas=$(id),rect=canvas.getBoundingClientRect();if(!rect.width||!rect.height)return null;const dpr=devicePixelRatio||1;canvas.width=Math.round(rect.width*dpr);canvas.height=Math.round(rect.height*dpr);const ctx=canvas.getContext('2d');ctx.scale(dpr,dpr);ctx.clearRect(0,0,rect.width,rect.height);ctx.font='11px system-ui';return {ctx,w:rect.width,h:rect.height};}
function drawDendrogram(){if(!previewData)return;const c=canvasSetup('dendrogram');if(!c)return;const {ctx,w,h}=c,left=52,right=18,top=18,bottom=48;
 const original=baseData.dendrogram,current=previewData.dendrogram,max=Math.max(original.max_distance_um,current.max_distance_um)*1.04||1;
 const sx=n=>left+n/max*(w-left-right),sy=n=>top+n/Math.max(1,original.leaves-1)*(h-top-bottom);
 for(let i=0;i<=4;i++){const x=sx(max*i/4);ctx.strokeStyle=uiColour('--grid');ctx.beginPath();ctx.moveTo(x,top);ctx.lineTo(x,h-bottom);ctx.stroke();ctx.fillStyle=uiColour('--muted');ctx.textAlign='center';ctx.fillText(fmt(max*i/4,0),x,h-bottom+19);}
 for(const [data,color,lw] of [[original,uiColour('--reference'),1],[current,uiAccent(),1.1]]){ctx.strokeStyle=color;ctx.lineWidth=lw;ctx.beginPath();for(const [x,y,x2,y2] of data.lines){ctx.moveTo(sx(x),sy(y));ctx.lineTo(sx(x2),sy(y2));}ctx.stroke();}
 ctx.fillStyle=uiColour('--muted');ctx.textAlign='center';ctx.fillText('Path distance from soma (µm)',w/2,h-9);ctx.save();ctx.translate(15,h/2);ctx.rotate(-Math.PI/2);ctx.fillText('Terminal ordering',0,0);ctx.restore();
}
function drawHist(){if(!previewData)return;const c=canvasSetup('histogram');if(!c)return;const {ctx,w,h}=c,{hist,edges,length_df:s}=previewData.sample,left=30,right=12,top=10,bottom=28,bw=(w-left-right)/hist.length,max=Math.max(...hist,1);
 ctx.fillStyle=uiAccent();hist.forEach((n,i)=>ctx.fillRect(left+i*bw+1,h-bottom-(h-bottom-top)*n/max,bw-2,(h-bottom-top)*n/max));
 ctx.fillStyle=uiColour('--muted');ctx.textAlign='center';for(let i=0;i<=4;i++)ctx.fillText(fmt(edges[0]+(edges.at(-1)-edges[0])*i/4,0)+'%',left+(w-left-right)*i/4,h-8);
 const x=left+(previewData.parameters.neurite_length_df_percent-edges[0])/(edges.at(-1)-edges[0])*(w-left-right);ctx.strokeStyle='#bd7c43';ctx.lineWidth=2;ctx.beginPath();ctx.moveTo(x,top);ctx.lineTo(x,h-bottom);ctx.stroke();
 $('hist-info').innerHTML=`<b>Length DF · sample</b><br>Sample mean: <b>${fmt(s.mean)}%</b><br>Sample σ: <b>${fmt(s.sigma)} pp</b><br>Range: ${fmt(s.min)}–${fmt(s.max)}%<br><span style="color:#a36c3d">${previewMode==='mean'?'Line: population mean':'Line: cell '+cellIndex}</span>`;
}
function drawLayers(){if(!catalog)return;const c=canvasSetup('layers-view');if(!c)return;const {ctx,w,h}=c;const lg=liveGeometry(),height=Math.max(lg.network.z,catalog.layers.reduce((s,x)=>s+x.thickness_um,0),1),scale=(h-85)/height,base=h-43,bw=Math.min(105,w*.18),xs=[w*.27-bw/2,w*.67-bw/2];
 for(let chart=0;chart<2;chart++){let y=base;for(const l of catalog.layers){const thick=chart?lg.geometry.layers[l.id].thickness_um:l.thickness_um;const hh=thick*scale;ctx.fillStyle=colors[l.id];ctx.globalAlpha=chart?.95:.35;ctx.fillRect(xs[chart],y-hh,bw,Math.max(0,hh-1));ctx.globalAlpha=1;if(hh>15){ctx.fillStyle=chart?'#fff':uiColour('--ink');ctx.textAlign='center';ctx.font='11px system-ui';ctx.fillText(`${fmt(thick,1)} µm`,xs[chart]+bw/2,y-hh/2+4);}y-=hh;}
 ctx.textAlign='center';ctx.fillStyle=uiColour('--muted');ctx.fillText(chart?'Current':'Healthy',xs[chart]+bw/2,h-18);ctx.fillText(`${fmt(chart?lg.network.z:catalog.network.z)} µm`,xs[chart]+bw/2,y-11);}
 ctx.strokeStyle=uiColour('--muted');ctx.beginPath();ctx.moveTo(30,base-height*scale);ctx.lineTo(30,base);ctx.stroke();for(let n=0;n<=height;n+=50){let y=base-n*scale;ctx.beginPath();ctx.moveTo(27,y);ctx.lineTo(34,y);ctx.stroke();ctx.fillStyle=uiColour('--muted');ctx.textAlign='right';ctx.fillText(n,24,y+4);}
 $('depth').textContent=`${fmt(lg.network.z)} µm`;
}
// Geometry is rendered in network coordinates. Camera navigation is independent of DF rotations.
let renderer,scene,camera,rootGroup,refGroup,curGroup,center=new THREE.Vector3(),radius=100,viewHeight=220,yaw=-Math.PI/2,pitch=.18,lastPop=null,lastParts=null,pendingMorphFit=false;
function initMorph(){const host=$('morph-view');renderer=new THREE.WebGLRenderer({antialias:true,alpha:true});renderer.setPixelRatio(Math.min(devicePixelRatio,2));renderer.setClearColor(0xffffff,0);host.append(renderer.domElement);scene=new THREE.Scene();scene.add(new THREE.AmbientLight(0xffffff,.8));const light=new THREE.DirectionalLight(0xffffff,.6);light.position.set(-1,-1,3);scene.add(light);camera=new THREE.OrthographicCamera(-1,1,1,-1,.01,100000);camera.up.set(0,0,1);rootGroup=new THREE.Group();scene.add(rootGroup);
 let drag=null;renderer.domElement.addEventListener('pointerdown',e=>{drag=[e.clientX,e.clientY];renderer.domElement.setPointerCapture(e.pointerId);});renderer.domElement.addEventListener('pointerup',()=>drag=null);renderer.domElement.addEventListener('pointercancel',()=>drag=null);renderer.domElement.addEventListener('pointermove',e=>{if(!drag)return;yaw-=(e.clientX-drag[0])*.008;pitch=Math.max(-1.55,Math.min(1.55,pitch+(e.clientY-drag[1])*.008));drag=[e.clientX,e.clientY];drawMorph();});renderer.domElement.addEventListener('wheel',e=>{e.preventDefault();viewHeight=Math.max(radius*.04,Math.min(radius*20,viewHeight*Math.exp(e.deltaY*.001)));drawMorph();},{passive:false});
}
function disposeGroup(g){if(!g)return;g.traverse(o=>{o.geometry?.dispose();if(Array.isArray(o.material))o.material.forEach(m=>m.dispose());else o.material?.dispose();});rootGroup.remove(g);}
function selectedNodes(){const mode=$('parts').value;return baseData.types.map(t=>mode==='all'||t===mode||t==='soma');}
function makeGroup(nodes,isRef){const split=$('morph-comparison').value==='split';const g=new THREE.Group(),data=isRef?baseData:previewData,types=data.types,parents=data.parents,mode=$('parts').value,selected=types.map(t=>mode==='all'||t===mode||t==='soma'),segments=[],radii=[];const points=[];
 for(let i=0;i<nodes.length;i++){const p=parents[i];if(p<0||!selected[i]||types[i]==='soma')continue;const a=nodes[p],b=nodes[i];if(Math.hypot(a[0]-b[0],a[1]-b[1],a[2]-b[2])<1e-8)continue;segments.push([a,b]);radii.push((a[3]+b[3])/2);points.push(...a.slice(0,3),...b.slice(0,3));}
 const geometry=new THREE.BufferGeometry();geometry.setAttribute('position',new THREE.Float32BufferAttribute(points,3));g.add(new THREE.LineSegments(geometry,new THREE.LineBasicMaterial({color:isRef&&!split?uiColour('--reference'):uiAccent(),transparent:true,opacity:isRef&&!split?.36:.88,depthWrite:!isRef||split})));
 if((!isRef||split)&&segments.length){const cyl=new THREE.CylinderGeometry(1,1,1,6);const material=new THREE.MeshLambertMaterial({color:isRef&&!split?uiColour('--reference'):uiAccent()});const mesh=new THREE.InstancedMesh(cyl,material,segments.length);const unit=new THREE.Vector3(0,1,0),obj=new THREE.Object3D(),a=new THREE.Vector3(),b=new THREE.Vector3(),dir=new THREE.Vector3();segments.forEach(([p,q],i)=>{a.fromArray(p);b.fromArray(q);dir.subVectors(b,a);obj.position.copy(a).add(b).multiplyScalar(.5);obj.quaternion.setFromUnitVectors(unit,dir.clone().normalize());obj.scale.set(radii[i],dir.length(),radii[i]);obj.updateMatrix();mesh.setMatrixAt(i,obj.matrix);});mesh.instanceMatrix.needsUpdate=true;g.add(mesh);}
 for(let i=0;i<nodes.length;i++)if(types[i]==='soma'){const n=nodes[i],mesh=new THREE.Mesh(new THREE.SphereGeometry(n[3],12,8),new THREE.MeshLambertMaterial({color:isRef?0xc0c9d1:0xcc8547,wireframe:isRef&&!split,transparent:isRef&&!split,opacity:isRef&&!split?.3:1}));mesh.position.set(...n.slice(0,3));g.add(mesh);}
 return g;
}
function renderMorph(){if(!renderer||!previewData)return;disposeGroup(refGroup);disposeGroup(curGroup);refGroup=makeGroup(baseData.nodes,true);curGroup=makeGroup(previewData.nodes,false);rootGroup.add(refGroup,curGroup);refGroup.visible=$('reference').checked;
 if(lastPop!==pop||lastParts!==$('parts').value){fitMorph();lastPop=pop;lastParts=$('parts').value;}drawMorph();}
function fitMorph(){if(!baseData||!previewData)return;const host=$('morph-view');if(!host.clientWidth||!host.clientHeight){pendingMorphFit=true;return;}pendingMorphFit=false;const box=new THREE.Box3(),mode=$('parts').value;for(const data of [baseData,previewData])data.nodes.forEach((p,i)=>{if(mode==='all'||data.types[i]===mode||data.types[i]==='soma')box.expandByPoint(new THREE.Vector3(...p.slice(0,3)));});box.getCenter(center);radius=Math.max(10,box.getSize(new THREE.Vector3()).length()/2);const split=$('morph-comparison').value==='split',aspect=host.clientWidth/(split?2:1)/host.clientHeight;viewHeight=radius*2.2/Math.min(1,aspect);drawMorph();}
function drawMorph(){if(!renderer)return;const host=$('morph-view'),w=host.clientWidth,h=host.clientHeight;if(!w||!h)return;if(pendingMorphFit){fitMorph();return;}const split=$('morph-comparison').value==='split';$('comparison-labels').hidden=!split;$('reference').disabled=split;renderer.setSize(w,h,false);const panelWidth=split?Math.floor(w/2):w,aspect=panelWidth/h;camera.left=-viewHeight*aspect/2;camera.right=viewHeight*aspect/2;camera.top=viewHeight/2;camera.bottom=-viewHeight/2;camera.far=radius*40+10000;camera.updateProjectionMatrix();const d=radius*6+100;camera.position.set(center.x+d*Math.cos(pitch)*Math.cos(yaw),center.y+d*Math.cos(pitch)*Math.sin(yaw),center.z+d*Math.sin(pitch));camera.lookAt(center);
 renderer.setScissorTest(false);renderer.setViewport(0,0,w,h);renderer.clear();
 if(refGroup&&curGroup&&split){renderer.setScissorTest(true);refGroup.visible=true;curGroup.visible=false;renderer.setViewport(0,0,panelWidth,h);renderer.setScissor(0,0,panelWidth,h);renderer.render(scene,camera);refGroup.visible=false;curGroup.visible=true;renderer.setViewport(panelWidth,0,panelWidth,h);renderer.setScissor(panelWidth,0,panelWidth,h);renderer.render(scene,camera);renderer.setScissorTest(false);}else{if(refGroup)refGroup.visible=$('reference').checked;if(curGroup)curGroup.visible=true;renderer.render(scene,camera);}
 const target=viewHeight/5,power=10**Math.floor(Math.log10(target)),n=[1,2,5,10].map(v=>v*power).reduce((a,b)=>Math.abs(a-target)<Math.abs(b-target)?a:b);$('scale-bar').style.width=`${n/viewHeight*h}px`;$('scale-bar').textContent=`${fmt(n,0)} µm`;
}
async function importYaml(text){setValid(false,'Validating…');const ticket=++seq;try{const x=await api('/api/import',{yaml:text,population:pop,cell_index:cellIndex,preview_mode:previewMode});if(ticket!==seq)return;recipe=x.recipe;overallState.clear();syncNotes();previewData=x;if(x.uniform_adjustment)notice('Cell variability is disabled in this editor. Imported effects are uniform; the original YAML is unchanged.');buildCells();buildNetwork();$('seed').value=recipe.seed;buildElectricalCells();buildConnections();refreshMeta();networkDirty=true;queueLiveNetwork();await update();}catch(e){error(e.message);setValid(false,'Invalid YAML');}}
function resetSelectedCell(){clearOverall('cell-morphological');
 // Explicit population-level zeros override imported defaults and layer cell rules.
 rule().cells={df_percent:zero(),soma_size_df_percent:zero(),rotation_x_deg:zero(),rotation_y_deg:zero(),rotation_z_deg:zero(),bifurcation_tilt_deg:zero()};
 recipe.individuals=(recipe.individuals||[]).filter(item=>item.population!==pop);
 cellIndex=0;$('cell-index').value=0;lastPop=null;buildCells();schedule();
 notice(`${catalog.populations.find(p=>p.id===pop).name}: cell size, bifurcation tilt and orientation reset. Network settings unchanged.`);
}
function reset(r){overallState.clear();recipe=clone(r);syncNotes();cellIndex=0;lastPop=null;$('cell-index').value=0;$('seed').value=recipe.seed;buildCells();buildNetwork();buildElectricalCells();buildConnections();refreshMeta();schedule();notice('');}
document.addEventListener('df-appearance-change',()=>{if(previewData){renderMorph();drawDendrogram();drawHist();}if(catalog)drawLayers();});
function renderSoftwareVersions(){const s=catalog.software||{},host=$('software-versions');host.replaceChildren();
 const text=document.createElement('span');text.textContent='BSB '+(s.bsb||'unknown')+' (reconstruction target) · cerebellar-models '+(s.cerebellar_models||'source version unavailable');host.append(text);
 if(s.cerebellar_models_commit){const commit=document.createElement('span');commit.textContent=' · source '+s.cerebellar_models_commit+(s.cerebellar_models_modified?' (modified)':'');host.append(commit);}
 const details=document.createElement('details'),summary=document.createElement('summary');summary.textContent='Bundled model & file locations';details.append(summary);
 for(const value of ['Model checkout: '+s.model_repository,'Python: '+s.python_executable,'Model distribution: '+s.cerebellar_models_installed,'Native Windows editor: no Ubuntu, WSL, BSB or Python installation is required. Exported reconstruction packages run separately in the pinned BSB 8 / MPI environment.', 'Your saved profiles and exports: '+catalog.data_directory]){const p=document.createElement('p');p.textContent=value;details.append(p);}host.append(details);
 if(!s.native_editor&&s.cerebellar_models&&s.cerebellar_models!==s.cerebellar_models_installed){const p=document.createElement('p');p.className='version-warning';p.textContent='Source and installed package versions differ. Review the environment before reconstruction.';host.append(p);}
 const sampling=catalog.spatial_sampling||{},rows=sampling.voxel_pathways||[],values=[...new Set(rows.map(r=>r.pre+' / '+r.post))];
 $('voxel-sampling-summary').textContent=rows.length?`The selected model has ${rows.length} VoxelIntersection pathways; pre / post settings: ${values.join(', ')}. `:'No VoxelIntersection pathway detected in this configuration. ';
 $('chunk-sampling-summary').textContent=sampling.chunk_size_um?`Current network chunks: ${sampling.chunk_size_um.join(' × ')} µm. `:'';
}
async function init(){try{catalog=await api('/api/catalog');recipe=clone(catalog.recipe);renderSoftwareVersions();
 for(const p of CELL_ORDER.map(id=>catalog.populations.find(x=>x.id===id)).filter(x=>x?.spatial.morphologies)){const b=document.createElement('button');b.textContent=p.name;b.dataset.pop=p.id;b.onclick=()=>{pop=p.id;cellIndex=0;$('cell-index').value=0;buildCells();buildElectricalCells();refreshMeta();schedule();};$('pop-tabs').append(b);}
 buildCells();buildNetwork();try{initMorph();}catch(e){error('WebGL rendering unavailable: '+e.message);}
 document.querySelectorAll('nav>button').forEach(b=>b.onclick=()=>{document.querySelectorAll('nav>button').forEach(x=>x.classList.toggle('active',x===b));document.querySelectorAll('.tab').forEach(x=>x.classList.toggle('active',x.id===b.dataset.tab));location.hash=b.dataset.tab;requestAnimationFrame(()=>{drawMorph();drawDendrogram();drawHist();drawLayers();drawNetwork();if(b.dataset.tab==='network'&&!networkReference)loadNetworkReference();});});
 $('preview-mode').onchange=()=>{previewMode=$('preview-mode').value;$('cell-index').disabled=previewMode==='mean';$('next-cell').disabled=previewMode==='mean';$('preview-mode-label').textContent=previewMode==='mean'?'CELL AT MEAN PARAMETERS':'REPRODUCIBLE INDIVIDUAL PREVIEW';schedule();};
 $('seed').onchange=()=>{recipe.seed=+$('seed').value;schedule();};$('cell-index').onchange=()=>{cellIndex=+$('cell-index').value;schedule();};$('next-cell').onclick=()=>{cellIndex++;$('cell-index').value=cellIndex;schedule();};
 $('reference').onchange=drawMorph;$('parts').onchange=renderMorph;$('morph-comparison').onchange=()=>{renderMorph();fitMorph();};$('fit').onclick=fitMorph;$('expand-morph').onclick=()=>{const panel=document.querySelector('.morph-panel'),expanded=panel.classList.toggle('expanded');$('expand-morph').textContent=expanded?'Close expanded view':'Expand view';fitMorph();};
 $('front').onclick=()=>{yaw=-Math.PI/2;pitch=0;drawMorph();};$('top').onclick=()=>{yaw=-Math.PI/2;pitch=1.55;drawMorph();};$('side').onclick=()=>{yaw=0;pitch=0;drawMorph();};
 $('identity').onclick=()=>reset({...clone(catalog.recipe),seed:recipe.seed});$('reset-cell').onclick=resetSelectedCell;
 $('profile-name').oninput=()=>{recipe.name=$('profile-name').value;schedule();};$('export-package').onclick=()=>exportPackage(true);
 $('generate-network').hidden=true;$('close-desktop').onclick=async()=>{await api('/api/quit',{});document.body.replaceChildren();const p=document.createElement('p');p.textContent='Cerebellum Designer is closed. Your saved profiles and exports are retained. You may close this tab.';p.style.cssText='padding:40px;font:20px system-ui';document.body.append(p);};initProfiles();initMeta();initRunActions();$('fit-network').onclick=fitNetwork;initElectrical();
 $('save-profile').onclick=()=>saveProfile(false);
 $('download').onclick=()=>{if(!valid)return;const a=document.createElement('a'),u=URL.createObjectURL(new Blob([previewData.yaml],{type:'application/yaml'}));a.href=u;a.download='deformation_profile.yaml';a.click();setTimeout(()=>URL.revokeObjectURL(u),1000);};
 $('apply-yaml').onclick=() => importYaml($('yaml-editor').value);$('import-file').onchange=async e=>{const f=e.target.files[0];if(f)await importYaml(await f.text());};
 new ResizeObserver(()=>{drawMorph();drawDendrogram();drawHist();drawLayers();drawNetwork();}).observe(document.querySelector('main'));
 document.querySelectorAll('[data-open]').forEach(b=>b.onclick=()=>document.querySelector(`[data-tab="${b.dataset.open}"]`).click());
 await update();if(['cells','network','yaml'].includes(location.hash.slice(1)))document.querySelector(`[data-tab="${location.hash.slice(1)}"]`).click();
 }catch(e){error(e.message);setValid(false,'Loading error');}}
init();

function electricalContext(){
 const e=recipe.electrical||{},models=catalog.electrical.models;
 const model=models.find(m=>m.id===(e.model||catalog.electrical.model)&&m.available);
 if(!model)throw new Error('The selected electrical model is not available.');
 const condition=model.conditions.find(c=>c.id===(e.state||catalog.electrical.state)&&c.available);
 if(!condition)throw new Error('The selected condition is unavailable for this model.');
 const preset=condition.synapse_presets.find(p=>p.id===(e.synapse_mode||condition.synapse_presets[0]?.id));
 if(!preset)throw new Error('The selected synapse preset is unavailable for this model and condition.');
 return {model,condition,preset};
}
function electrical(){const c=electricalContext();recipe.electrical??={model:c.model.id,state:c.condition.id,synapse_mode:c.preset.id,cells:{},connections:{}};return recipe.electrical;}
function syncElectricalContext(){
 const c=electricalContext();
 const fill=(id,items,value)=>{const select=$(id);select.replaceChildren();for(const item of items){const option=document.createElement('option');option.value=item.id;option.textContent=item.label;option.disabled=item.available===false;select.append(option);}select.value=value;select.disabled=!items.some(i=>i.available!==false);};
 for(const side of ['cell','network']){
  fill(side+'-model',catalog.electrical.models,c.model.id);
  fill(side+'-condition',c.model.conditions,c.condition.id);
 }
 fill('electrical-synapse-mode',c.condition.synapse_presets,c.preset.id);
 $('electrical-preset-files').textContent=c.condition.synapse_presets.map(p=>'electrical_'+p.id+'.yaml').join(' · ');
}
function changeElectricalContext(kind,value){
 const old=electricalContext();let e=electrical();
 if(kind==='model'){
  const model=catalog.electrical.models.find(m=>m.id===value&&m.available);if(!model)return;
  if(model.id!==old.model.id){const condition=model.conditions.find(c=>c.available);recipe.electrical={model:model.id,state:condition.id,synapse_mode:condition.synapse_presets[0].id,cells:{},connections:{}};}
 }else if(kind==='state'){
  const condition=old.model.conditions.find(c=>c.id===value&&c.available);if(!condition)return;
  if(condition.id!==old.condition.id)recipe.electrical={model:old.model.id,state:condition.id,synapse_mode:condition.synapse_presets[0].id,cells:{},connections:{}};
 }else{if(!old.condition.synapse_presets.some(p=>p.id===value))return;e.synapse_mode=value;}
 syncElectricalContext();buildElectricalCells();buildConnections();schedule();
}

function electricalRow(host,item,get,set,path){
 const div=document.createElement('div');div.className='electrical-row';
 const title=document.createElement('label');title.textContent=item.key;const unit=document.createElement('small');unit.textContent=item.unit;title.append(unit);div.append(title);
 const desc=document.createElement('p');desc.className='parameter-description';desc.textContent=item.description;div.append(desc);const vals=document.createElement('div');vals.className='electrical-values';
 const row=document.createElement('div');row.className='electrical-slider';
 const range=document.createElement('input');range.type='range';range.min=-100;range.max=100;range.step=.5;range.value=get();range.setAttribute('aria-label',item.key+' DF slider');
 const number=document.createElement('input');number.type='number';number.min=-100;number.max=100;number.step=.5;number.value=get();number.setAttribute('aria-label',item.key+' DF percent');
 const suffix=document.createElement('span');suffix.textContent='% change';row.append(range,number,suffix);div.append(row,vals);
 const bar=document.createElement('div');bar.className='electrical-bar';const fill=document.createElement('span');bar.append(fill);div.append(bar);
 function refresh(){const df=get(),value=item.baseline*(1+df/100);vals.textContent=`Reference ${precise(item.baseline)} → Current ${precise(value)} ${item.unit}`;fill.style.width=Math.max(0,(100+df)/2)+'%';div.classList.toggle('changed',df!==0);}
 function change(v){if(!Number.isFinite(v))return;set(v);range.value=v;number.value=v;refresh();schedule();}
 range.oninput=()=>change(+range.value);number.oninput=()=>{if(number.value!=='')change(+number.value);};
 if(item.baseline===0){const note=document.createElement('small');note.className='electrical-note';note.textContent='Reference is zero: percentage scaling keeps it at zero.';div.append(note);}
 if(item.strictly_positive){const note=document.createElement('small');note.className='electrical-note';note.textContent='Must remain positive; −100% change will block export.';div.append(note);}
 noteField(div,path,item.key);refresh();host.append(div);
}
function buildElectricalCells(){if(!catalog)return;syncElectricalContext();const host=$('cell-electrical-controls');host.replaceChildren();const groups=new Map();for(const item of catalog.electrical.cells[pop]){let g=groups.get(item.group);if(!g){g=document.createElement('article');g.className='panel electrical-section';const title=document.createElement('h3');title.textContent=item.group;g.append(title);host.append(g);groups.set(item.group,g);}electricalRow(g,item,()=>recipe.electrical?.cells?.[pop]?.[item.key]||0,v=>{const e=electrical();e.cells??={};e.cells[pop]??={};e.cells[pop][item.key]=v;},`electrical.cells.${pop}.${item.key}`);}}
function buildConnections(){if(!catalog)return;syncElectricalContext();const mode=electricalContext().preset.id;const conns=catalog.electrical.connections[mode],list=$('connection-list');if(!conns[connectionName])connectionName=Object.keys(conns)[0];list.replaceChildren();
 for(const name of Object.keys(conns)){const b=document.createElement('button');b.textContent=name.replaceAll('_',' ');b.classList.toggle('active',name===connectionName);b.onclick=()=>{connectionName=name;buildConnections();refreshMeta();};list.append(b);}
 $('connection-title').textContent=connectionName.replaceAll('_',' ');const host=$('connection-controls');host.replaceChildren();
 for(const syn of conns[connectionName]){const box=document.createElement('article');box.className='panel electrical-section';const title=document.createElement('h3');title.textContent=syn.receptor;const sub=document.createElement('p');sub.className='caption';sub.textContent=syn.model+(syn.receptor_type?' · receptor '+syn.receptor_type:'');box.append(title,sub);host.append(box);
 for(const item of syn.parameters)electricalRow(box,item,()=>recipe.electrical?.connections?.[mode]?.[connectionName]?.[syn.index]?.[item.key]||0,v=>{const e=electrical();e.connections??={};e.connections[mode]??={};e.connections[mode][connectionName]??={};e.connections[mode][connectionName][syn.index]??={};e.connections[mode][connectionName][syn.index][item.key]=v;},`electrical.connections.${mode}.${connectionName}.${syn.index}.${item.key}`);}
}
function initElectrical(){
 for(const target of ['cell','network'])document.querySelectorAll(`[data-${target}-mode]`).forEach(b=>b.onclick=()=>{const mode=b.dataset[target+'Mode'];document.querySelectorAll(`[data-${target}-mode]`).forEach(x=>x.classList.toggle('active',x===b));$(target+'-morphological').classList.toggle('hidden',mode!=='morphological');$(target+'-electrical').classList.toggle('hidden',mode!=='electrical');if(target==='cell'){for(const id of ['meta-cell-morphological','cell-cockpit'])$(id).classList.toggle('hidden',mode!=='morphological');}requestAnimationFrame(()=>{drawMorph();drawDendrogram();drawHist();drawLayers();drawNetwork();});});
 for(const side of ['cell','network']){$(side+'-model').onchange=e=>changeElectricalContext('model',e.target.value);$(side+'-condition').onchange=e=>changeElectricalContext('state',e.target.value);}
 $('electrical-synapse-mode').onchange=e=>changeElectricalContext('preset',e.target.value);
 $('reset-cell-electrical').onclick=()=>{if(recipe.electrical?.cells)delete recipe.electrical.cells[pop];buildElectricalCells();schedule();};
 $('reset-connection').onclick=()=>{const mode=electricalContext().preset.id;if(recipe.electrical?.connections?.[mode])delete recipe.electrical.connections[mode][connectionName];buildConnections();schedule();};
 buildElectricalCells();buildConnections();
}

let netRenderer,netScene,netCamera,netGroup,netYaw=-.95,netPitch=.4,netHeight=430,netCenter=new THREE.Vector3(150,100,147.5),netHidden=new Set(['mossy_fibers','glomerulus']);
const popColors={granule_cell:'#2c9ab2',golgi_cell:'#e18038',purkinje_cell:'#b14f9b',basket_cell:'#50864a',stellate_cell:'#7356b4',mossy_fibers:'#b3a28c',glomerulus:'#96a4af'};
function initNetwork(){if(netRenderer)return;const host=$('network-scatter');netRenderer=new THREE.WebGLRenderer({antialias:true,alpha:true});netRenderer.setPixelRatio(Math.min(devicePixelRatio,2));host.append(netRenderer.domElement);netScene=new THREE.Scene();netCamera=new THREE.OrthographicCamera(-1,1,1,-1,.01,10000);netCamera.up.set(0,0,1);
 let drag=null;host.addEventListener('pointerdown',e=>{drag=[e.clientX,e.clientY];host.setPointerCapture(e.pointerId);});host.addEventListener('pointerup',()=>drag=null);host.addEventListener('pointercancel',()=>drag=null);host.addEventListener('pointermove',e=>{if(!drag)return;netYaw-=(e.clientX-drag[0])*.008;netPitch=Math.max(-1.5,Math.min(1.5,netPitch+(e.clientY-drag[1])*.008));drag=[e.clientX,e.clientY];drawNetwork();});host.addEventListener('wheel',e=>{e.preventDefault();netHeight=Math.max(30,Math.min(3000,netHeight*Math.exp(e.deltaY*.001)));drawNetwork();},{passive:false});
}
function makeNetwork(){const first=!netGroup;initNetwork();if(netGroup){netGroup.traverse(o=>{o.geometry?.dispose();o.material?.dispose();});netScene.remove(netGroup);}netGroup=new THREE.Group();netScene.add(netGroup);let z=0;const n=networkData.network;
 for(const layer of catalog.layers){const dz=networkData.geometry.layers[layer.id].thickness_um;if(dz>0){const geo=new THREE.EdgesGeometry(new THREE.BoxGeometry(n.x,n.y,dz)),obj=new THREE.LineSegments(geo,new THREE.LineBasicMaterial({color:colors[layer.id],transparent:true,opacity:.6}));obj.position.set(n.x/2,n.y/2,z+dz/2);netGroup.add(obj);}z+=dz;}
 const legend=$('population-legend');legend.replaceChildren();
 for(const [p,data] of Object.entries(networkData.populations)){const geo=new THREE.BufferGeometry();geo.setAttribute('position',new THREE.Float32BufferAttribute(data.positions.flat(),3));geo.setAttribute('radius',new THREE.Float32BufferAttribute(data.radii_um,1));
 const material=new THREE.ShaderMaterial({uniforms:{color:{value:new THREE.Color(popColors[p])},pixelScale:{value:1},alpha:{value:p==='granule_cell'?.55:.95}},vertexShader:'attribute float radius; uniform float pixelScale; void main(){gl_Position=projectionMatrix*modelViewMatrix*vec4(position,1.0);gl_PointSize=max(2.0,2.0*radius*pixelScale);}',fragmentShader:'uniform vec3 color; uniform float alpha; void main(){if(distance(gl_PointCoord,vec2(.5))>.5)discard;gl_FragColor=vec4(color,alpha);}',transparent:true,depthWrite:false});
 const obj=new THREE.Points(geo,material);obj.name=p;obj.visible=!netHidden.has(p);netGroup.add(obj);
 const lab=document.createElement('label');lab.className='population-key';const check=document.createElement('input');check.type='checkbox';check.checked=obj.visible;check.onchange=()=>{obj.visible=check.checked;if(check.checked)netHidden.delete(p);else netHidden.add(p);updateNetworkStatus();drawNetwork();};const dot=document.createElement('i');dot.className='dot';dot.style.background=popColors[p];lab.append(check,dot,document.createTextNode(`${catalog.populations.find(x=>x.id===p).name}: ${networkData.live?'≈ ':''}${data.count.toLocaleString('en-US')}${data.has_soma?'':' (relay)'}`));legend.append(lab);
 }
 if(first)fitNetwork();else drawNetwork();
}
function fitNetwork(){if(networkData){const n=networkData.network;netCenter.set(n.x/2,n.y/2,n.z/2);netHeight=Math.max(n.x,n.y,n.z,20)*1.65;}drawNetwork();}
function drawNetwork(){if(!netRenderer)return;const host=$('network-scatter'),w=host.clientWidth,h=host.clientHeight;if(!w||!h)return;netRenderer.setSize(w,h,false);const aspect=w/h;netCamera.left=-netHeight*aspect/2;netCamera.right=netHeight*aspect/2;netCamera.top=netHeight/2;netCamera.bottom=-netHeight/2;netCamera.updateProjectionMatrix();netCamera.position.set(netCenter.x+1800*Math.cos(netPitch)*Math.cos(netYaw),netCenter.y+1800*Math.cos(netPitch)*Math.sin(netYaw),netCenter.z+1800*Math.sin(netPitch));netCamera.lookAt(netCenter);netGroup?.children.forEach(o=>{if(o.material?.uniforms?.pixelScale)o.material.uniforms.pixelScale.value=h/netHeight*netRenderer.getPixelRatio();});netRenderer.render(netScene,netCamera);}
function updateNetworkStatus(){if(!networkData||networkBusy)return;const total=Object.values(networkData.populations).filter(d=>d.has_soma).reduce((n,d)=>n+d.count,0);$('network-status').textContent=`${networkData.live?'Live estimate · ≈':'Verified BSB · '}${total.toLocaleString('en-US')} somata · ${fmt(networkData.network.z)} µm depth`;}
async function generateNetwork(){if(networkBusy||!valid)return;networkBusy=true;const ticket=++networkRequestSeq,snapshot=JSON.stringify(recipe);$('generate-network').disabled=true;$('network-status').textContent='Verifying exact BSB placement with MPI ×8…';
 try{let r=await api('/api/network',{recipe:clone(recipe)});while(r.status==='RUNNING'){await new Promise(resolve=>setTimeout(resolve,1600));if(ticket!==networkRequestSeq)return;r=await api('/api/network-status?key='+r.key);}
 if(r.status!=='COMPLETED')throw new Error(r.error||r.status);if(snapshot!==JSON.stringify(recipe)){queueLiveNetwork();notice('Exact placement finished for previous settings; live view keeps your latest edits.');return;}networkData=r.data;networkDirty=false;makeNetwork();$('network-status').textContent=networkDirty?'Preview ready for previous settings. Generate again to update.':`${r.total_somas.toLocaleString('en-US')} actual somata · all cortical cells shown · ${fmt(networkData.network.x,0)} × ${fmt(networkData.network.y,0)} × ${fmt(networkData.network.z,1)} µm`;
 $('network-provenance').textContent=`Native BSB coordinates · marker sizes follow soma radius (minimum 2 px) · relay points hidden by default. Placement only; no connections or simulation. HDF5: ${networkData.source_hdf5}`;
 }catch(e){$('network-status').textContent='Placement preview failed: '+e.message;error(e.message);}finally{networkBusy=false;$('generate-network').disabled=!valid;}}
let preparedCommand=null;
function invalidateCommand(){if(!preparedCommand)return;preparedCommand=null;$('bash-command').value='Settings changed. Prepare the updated package to obtain its exact command.';$('copy-command').disabled=true;$('command-status').textContent='Regenerate the package after any change.';}
function initRunActions(){$('show-limitations').onclick=()=>$('limitations-dialog').showModal();$('close-limitations').onclick=()=>$('limitations-dialog').close();$('show-run').onclick=()=>document.querySelector('.final-run').scrollIntoView({behavior:'smooth'});$('prepare-command').onclick=()=>exportPackage(false);$('copy-command').onclick=async()=>{if(preparedCommand){await navigator.clipboard.writeText(preparedCommand);$('copy-command').textContent='Copied';}};}
async function exportPackage(download=true){if(!valid)return;const button=$('export-package');button.disabled=true;$('prepare-command').disabled=true;button.textContent='Preparing package…';try{const snapshot=JSON.stringify(recipe),result=await api('/api/export',{recipe:clone(recipe)});if(snapshot!==JSON.stringify(recipe)){notice('Previous settings exported; prepare a new package for the current settings.');return;}const host=$('export-results');host.replaceChildren();for(const [label,url] of [['Download ZIP',result.download],['HTML report',result.html],['PDF report',result.pdf]]){const a=document.createElement('a');a.textContent=label;a.href=url;a.className='button';if(label==='Download ZIP')a.download='deformation_package.zip';else a.target='_blank';host.append(a);}preparedCommand=result.command;$('bash-command').value=result.command;$('copy-command').disabled=false;$('copy-command').textContent='Copy command';$('command-status').textContent='Saved. No reconstruction or simulation started. To reconstruct later with MPI ×8, activate the matching environment on your BSB machine and copy this command into Bash.';notice('Package saved on this computer: '+result.folder);if(download){const a=document.createElement('a');a.href=result.download;a.download='deformation_package.zip';a.click();}}catch(e){error(e.message);}finally{button.disabled=!valid;$('prepare-command').disabled=!valid;button.textContent='Save & download ZIP';}}
async function refreshSavedProfiles(){const data=await api('/api/profiles');let group=$('saved-profile-options');if(!group){group=document.createElement('optgroup');group.id='saved-profile-options';group.label='Saved profiles on this computer';$('disease-preset').append(group);}group.replaceChildren();for(const p of data.profiles){const o=document.createElement('option');o.value='saved:'+p.id;o.textContent=p.name+' · '+p.saved_utc;group.append(o);}if(data.unreadable.length)notice(`${data.unreadable.length} saved profile(s) could not be read; original files retained.`);}
async function saveProfile(download){if(!valid)return;try{const x=await api('/api/save-profile',{recipe:clone(recipe)});await refreshSavedProfiles();$('disease-preset').value='saved:'+x.id;notice('Profile saved on this computer and added to the preload list: '+recipe.name);if(download)$('download').click();}catch(e){error(e.message);}}

let networkReference=null,liveFrame=null,loadingReference=false,undoProfile=null;
function liveGeometry(){return estimatedGeometry(catalog,recipe);}
function queueLiveNetwork(){if(!catalog)return;if(liveFrame!==null)cancelAnimationFrame(liveFrame);liveFrame=requestAnimationFrame(()=>{liveFrame=null;drawLayers();if(networkReference){networkData=projectSomata(networkReference,catalog,recipe);networkDirty=true;makeNetwork();updateNetworkStatus();$('network-provenance').textContent='';}});}
async function loadNetworkReference(){if(loadingReference||networkReference)return;loadingReference=true;try{networkReference=await api('/api/network-reference');queueLiveNetwork();}catch(e){$('network-status').textContent=e.message;}finally{loadingReference=false;}}
function renderNotes(){if(!catalog)return;const a=recipe.annotations||{},host=$('evidence-entries');host.replaceChildren();$('preset-summary').textContent=a.summary||'';let changed=0;
 const at=path=>parameterValue(recipe,path),notes=a.parameter_notes||{},covered=new Set();
 const noteBlock=(parent,path,note)=>{const block=document.createElement('div');block.className='note-context';const title=document.createElement('strong');title.textContent=path;const v=at(path),current=document.createElement('p');current.className='evidence-target';current.textContent='Current setting: '+(v===undefined?'inherited / reset':v)+(path.includes('_deg')?'°':'%');const text=document.createElement('p');text.textContent=note;block.append(title,current,text);parent.append(block);};
 for(const e of a.entries||[]){const matches=e.targets.every(t=>at(t.path)===t.value);if(!matches)changed++;
 const details=document.createElement('details'),summary=document.createElement('summary');summary.textContent=e.title+' · '+(matches?e.evidence:'Modified after preload');details.append(summary);
 const text=document.createElement('p');text.textContent=e.rationale;details.append(text);
 const sourceURLs=e.sources.map(id=>a.sources?.find(s=>s.id===id)?.url).filter(Boolean),originalNote=e.rationale+'\nSources: '+sourceURLs.join('; ');
 for(const t of e.targets){const row=document.createElement('p');row.className='evidence-target';row.textContent=t.path+': preset '+fmt(t.value,3)+'; current '+(at(t.path)===undefined?'inherited / reset':fmt(at(t.path),3));details.append(row);covered.add(t.path);
  const note=notes[t.path]?.trim();if(note&&note!==originalNote.trim()&&note!==e.rationale.trim())noteBlock(details,t.path,note);
 }
 for(const id of e.sources){const ref=a.sources?.find(s=>s.id===id);if(ref){const link=document.createElement('a');link.href=ref.url;link.textContent=ref.title;link.target='_blank';link.rel='noopener';details.append(link);}}host.append(details);}
 // Keep custom parameter notes in the same section; preset rationales appear once.
 for(const [path,note] of Object.entries(notes)){if(covered.has(path)||!note.trim())continue;const d=document.createElement('details'),s=document.createElement('summary');s.textContent=path+' · note';d.append(s);noteBlock(d,path,note);host.append(d);}
 const refs=$('reference-list');refs.replaceChildren();if(a.sources?.length){const d=document.createElement('details'),s=document.createElement('summary');s.textContent='Source library · '+a.sources.length+' records';d.append(s);for(const ref of a.sources){const p=document.createElement('p'),link=document.createElement('a');link.href=ref.url;link.target='_blank';link.rel='noopener';link.textContent=ref.title;p.append(link,document.createTextNode(' — '+ref.kind+'. '+ref.note));d.append(p);}refs.append(d);}
 $('evidence-status').textContent=(a.entries?.length?changed+' modified evidence groups':'');$('preset-status').textContent=a.preset_id?(a.title+(changed?' · edited':' · loaded')):'Custom profile';
}
function syncNotes(){if($('profile-notes'))$('profile-notes').value=recipe.annotations?.notes||'';renderNotes();}
function initProfiles(){for(const p of catalog.presets){const o=document.createElement('option');o.value=p.id;o.textContent=p.label;o.disabled=!p.available;$('disease-preset').append(o);}
 $('load-disease-preset').onclick=async()=>{try{const id=$('disease-preset').value;const next=id.startsWith('saved:')?(await api('/api/profile?id='+encodeURIComponent(id.slice(6)))).recipe:id==='healthy'?{...clone(catalog.recipe),seed:recipe.seed}:{...clone(catalog.presets.find(p=>p.id===id).recipe),seed:recipe.seed};undoProfile=clone(recipe);let flattened=false;const uniform=o=>{if(!o||typeof o!=='object')return;if(Object.hasOwn(o,'mean')&&o.sigma){o.sigma=0;flattened=true;}Object.values(o).forEach(uniform);};uniform(next);reset(next);$('undo-profile').disabled=false;notice(flattened?'Profile loaded with uniform effects; variability in the saved source was retained on disk.':'Profile loaded. Review Notes & references before export.');}catch(e){error(e.message);}};
 refreshSavedProfiles().catch(e=>error(e.message));
 $('undo-profile').onclick=()=>{if(undoProfile){const previous=undoProfile;undoProfile=null;reset(previous);$('undo-profile').disabled=true;}};
 $('profile-notes').oninput=()=>{recipe.annotations??={};recipe.annotations.notes=$('profile-notes').value;schedule();};syncNotes();
}
const metaControls={},overallState=new Map();
const sizeFeatures=['neurite_length_df_percent','neurite_radius_df_percent','soma_size_df_percent'];
function overallKey(scope){return scope==='cell-morphological'?scope+':'+pop:scope;}
function clearOverall(scope){overallState.delete(overallKey(scope));}
function materializeCellDetails(){
 const current=Object.fromEntries(sizeFeatures.map(k=>[k,effective(k)]));
 // A neutral shared factor prevents a previous -100% common factor overriding edited details.
 cells().df_percent=zero();Object.assign(cells(),current);clearOverall('cell-morphological');
}
function metaValues(scope){
 if(scope==='cell-morphological')return sizeFeatures.map(k=>effective(k).mean);
 return [...catalog.layers.flatMap(l=>['thickness_df_percent','density_df_percent'].map(k=>netValue(recipe.layers?.[l.id]?.[k]))),...catalog.populations.map(p=>netValue(recipe.populations?.[p.id]?.density_df_percent??recipe.layers?.[p.layer]?.density_df_percent))];
}
function applyMeta(scope,value){
 overallState.set(overallKey(scope),value);
 if(scope==='cell-morphological'){
  cells().df_percent=zero();for(const k of sizeFeatures)cells()[k]={mean:value,sigma:0,bounds:[-100,100]};
  recipe.individuals=(recipe.individuals||[]).filter(i=>i.population!==pop);buildCells();
 }
 if(scope==='network-morphological'){
  recipe.layers??={};for(const l of catalog.layers){recipe.layers[l.id]??={};recipe.layers[l.id].thickness_df_percent=value;recipe.layers[l.id].density_df_percent=value;}
  for(const p of catalog.populations)delete rule(p.id).density_df_percent;buildNetwork();
 }
 schedule();refreshMeta(false);refreshRaw();
}
function refreshMeta(auto=true){for(const [scope,c] of Object.entries(metaControls)){
 const key=overallKey(scope),applied=overallState.has(key),value=overallState.get(key)??0;
 c.slider.value=c.number.value=value;c.value.textContent=applied?fmt(value)+'% applied to all':'0% · individual settings active';
 if(auto){c.noteHost.replaceChildren();noteField(c.noteHost,scope==='cell-morphological'?sizeFeatures.map(k=>`populations.${pop}.cells.${k}.mean`):catalog.layers.flatMap(l=>['thickness_df_percent','density_df_percent'].map(k=>`layers.${l.id}.${k}`)),scope+' overall');}
 }refreshOverallRaw();}
function initMeta(){for(const scope of ['cell-morphological','network-morphological']){
 const host=$('meta-'+scope);host.className='meta-panel';
 const title=document.createElement('label');title.textContent='Overall change';
 const slider=document.createElement('input');slider.type='range';slider.min=-100;slider.max=100;slider.step=.5;slider.value=0;slider.setAttribute('aria-label',scope+' overall slider');
 const number=document.createElement('input');number.type='number';number.min=-100;number.max=100;number.step=.5;number.value=0;number.setAttribute('aria-label',scope+' overall percent');
 const value=document.createElement('strong'),note=document.createElement('small');
 note.textContent=(scope==='cell-morphological'?'Sets length, radius and soma to the same change from their reference. Orientation and bifurcation tilt stay separate. ':'Sets all layer thicknesses and densities to the same change from their reference. ')+ 'All details remain editable. Editing one resets this command to 0; the other detail values stay unchanged.';
 host.append(title,slider,number,value,note);const raw=document.createElement('div');raw.className='overall-raw raw-values';host.append(raw);
 if(scope==='cell-morphological')host.append($('reset-cell'));
 const noteHost=document.createElement('div');noteHost.className='overall-notes';host.append(noteHost);
 slider.oninput=()=>applyMeta(scope,+slider.value);number.oninput=()=>{if(number.value!==''&&Number.isFinite(+number.value))applyMeta(scope,+number.value);};
 metaControls[scope]={slider,number,value,noteHost,raw};
 }refreshMeta();}

function parameterValue(obj,path){if(!obj||typeof obj!=='object')return undefined;if(Object.hasOwn(obj,path))return obj[path];const [head,...tail]=path.split('.');return tail.length?parameterValue(obj[head],tail.join('.')):obj[head];}
