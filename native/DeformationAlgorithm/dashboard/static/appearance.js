'use strict';
// Personal display preferences are independent of scientific recipes and exports.
(() => {
 const key='deformationalgorithm.appearance.v2', legacyKey='deformationalgorithm.appearance.v1';
 const accents=[['Orange','#b34b0c'],['Red','#c6262e'],['Blue','#2459a6'],['Teal','#007b83'],['Violet','#7250a3'],['Rose','#ad385c'],['Gold','#b18b20'],['Graphite','#555555'],['White','#ffffff']];
 const backgrounds=[['White','#ffffff'],['Ivory','#fff8ee'],['Black','#000000'],['Charcoal','#171717'],['Midnight','#101827']];
 const root=document.documentElement, accentHost=document.getElementById('accent-swatches'), backgroundHost=document.getElementById('background-swatches');
 const accentPicker=document.getElementById('custom-accent'), backgroundPicker=document.getElementById('custom-background');
 const rgb=hex=>hex.slice(1).match(/../g).map(x=>parseInt(x,16));
 const hex=values=>'#'+values.map(v=>Math.round(v).toString(16).padStart(2,'0')).join('');
 const mix=(a,b,f)=>hex(rgb(a).map((v,i)=>v*(1-f)+rgb(b)[i]*f));
 const luminance=color=>rgb(color).map(v=>{v/=255;return v<=.04045?v/12.92:((v+.055)/1.055)**2.4;}).reduce((n,v,i)=>n+v*[.2126,.7152,.0722][i],0);
 const contrast=(a,b)=>{const x=luminance(a),y=luminance(b);return (Math.max(x,y)+.05)/(Math.min(x,y)+.05);};
 const valid=color=>typeof color==='string'&&/^#[0-9a-f]{6}$/i.test(color);
 let preference={accent:accents[0][1],background:backgrounds[0][1]};
 function apply(save=true){
  const chosen=preference.accent, bg=preference.background;
  const light=contrast('#ffffff',bg)>contrast('#000000',bg), foreground=light?'#ffffff':'#000000';
  let accent=chosen;
  // Accent text must remain readable on the selected background and tinted panels.
  for(let i=0;i<180;i++){
   const soft=mix(bg,accent,.065),tint=mix(bg,accent,.025);
   if(Math.min(contrast(accent,bg),contrast(accent,soft),contrast(accent,tint))>=4.5)break;
   accent=mix(accent,foreground,.06);
  }
  const onAccent=contrast('#ffffff',accent)>contrast('#000000',accent)?'#ffffff':'#000000';
  const soft=mix(bg,accent,.065),tint=mix(bg,accent,.025);
  const values={'--bg':bg,'--surface':bg,'--ink':mix(bg,foreground,.92),'--muted':mix(bg,foreground,.72),'--border':mix(bg,foreground,.2),'--grid':mix(bg,foreground,.13),'--reference':mix(bg,foreground,.52),
   '--accent':accent,'--on-accent':onAccent,'--accent-hover':mix(accent,foreground,.15),'--accent-soft':soft,'--accent-tint':tint,'--accent-border':mix(bg,accent,.4),'--focus':accent,
   '--success-bg':light?'#102e22':'#e8f4ef','--success-ink':light?'#9de4ba':'#2a6b52','--warning-bg':light?'#302819':'#fff9ed','--warning-ink':light?'#e9c98e':'#765d2f','--error-bg':light?'#361b1b':'#fff0ec','--error-ink':light?'#ffb2a4':'#a13e27'};
  Object.entries(values).forEach(([name,value])=>root.style.setProperty(name,value));root.style.colorScheme=light?'dark':'light';
  accentPicker.value=chosen;backgroundPicker.value=bg;
  accentHost.querySelectorAll('button').forEach(b=>b.setAttribute('aria-pressed',String(b.dataset.color===chosen)));
  backgroundHost.querySelectorAll('button').forEach(b=>b.setAttribute('aria-pressed',String(b.dataset.color===bg)));
  document.getElementById('active-accent').textContent=(accents.find(p=>p[1]===chosen)?.[0]||'Custom')+' · '+(backgrounds.find(p=>p[1]===bg)?.[0]||'custom background');
  document.getElementById('accent-hint').textContent=(chosen===accent?'':'Accent brightness is adjusted for readable contrast. ')+'Saved in this browser. Population colours stay unchanged.';
  if(save)try{localStorage.setItem(key,JSON.stringify(preference));}catch{}
  document.dispatchEvent(new CustomEvent('df-appearance-change'));
 }
 function swatches(host,items,field){for(const [name,color] of items){const b=document.createElement('button');b.type='button';b.className=field==='accent'?'accent-swatch':'background-swatch';b.dataset.color=color;b.style.setProperty('--swatch',color);b.setAttribute('aria-label',name+' '+field);b.title=name;b.onclick=()=>{preference[field]=color;apply();};host.append(b);}}
 swatches(accentHost,accents,'accent');swatches(backgroundHost,backgrounds,'background');
 accentPicker.oninput=()=>{preference.accent=accentPicker.value;apply();};backgroundPicker.oninput=()=>{preference.background=backgroundPicker.value;apply();};
 document.getElementById('reset-appearance').onclick=()=>{preference={accent:accents[0][1],background:backgrounds[0][1]};apply();};
 try{const saved=localStorage.getItem(key);if(saved){const p=JSON.parse(saved);if(valid(p.accent)&&valid(p.background))preference={accent:p.accent.toLowerCase(),background:p.background.toLowerCase()};}else{const old=localStorage.getItem(legacyKey);if(valid(old))preference.accent=old.toLowerCase();}}catch{}
 apply(false);
})();
