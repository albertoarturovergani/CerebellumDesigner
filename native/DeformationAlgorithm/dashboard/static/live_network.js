'use strict';
// Pure visual estimate. It never writes reconstruction coordinates or synapses.
function netValue(v){return typeof v==='number'?v:(v?.mean||0);}
function estimatedGeometry(catalog,recipe){
 const geometry={layers:{},populations:{}};let z=0;
 for(const l of catalog.layers){const r=recipe.layers?.[l.id]||{},t=l.thickness_um*(1+Math.max(-100,Math.min(100,netValue(r.thickness_df_percent)))/100);geometry.layers[l.id]={thickness_um:Math.max(0,t),offset:z};z+=Math.max(0,t);}
 for(const p of catalog.populations){const r=recipe.populations?.[p.id]||{},df=Object.hasOwn(r,'density_df_percent')?r.density_df_percent:recipe.layers?.[p.layer]?.density_df_percent;geometry.populations[p.id]={density_factor:Math.max(0,1+Math.max(-100,Math.min(100,netValue(df)))/100)};}
 return {network:{...catalog.network,z},geometry};
}
function projectSomata(reference,catalog,recipe){
 const g=estimatedGeometry(catalog,recipe),populations={};let originalOffset=0;const offsets={};for(const l of catalog.layers){offsets[l.id]=originalOffset;originalOffset+=l.thickness_um;}
 const effectiveMean=(p,key)=>{let v=0;for(const c of [recipe.defaults||{},recipe.layers?.[p.layer]?.cells||{},recipe.populations?.[p.id]?.cells||{}]){if(c.df_percent)v=c.df_percent.mean;if(c[key])v=c[key].mean;}return v;};
 for(const p of catalog.populations){const src=reference.populations[p.id],baseLayer=catalog.layers.find(l=>l.id===p.layer),layer=g.geometry.layers[p.layer];if(!src)continue;
 const density=g.geometry.populations[p.id].density_factor,thickness=layer.thickness_um/baseLayer.thickness_um;
 const common=effectiveMean(p,'df_percent'),soma=effectiveMean(p,'soma_size_df_percent');
 let ratio=density*(p.spatial.planar_density?1:thickness);if(!layer.thickness_um||(src.has_soma&&(common<=-100||soma<=-100)))ratio=0;
 if(p.id==='mossy_fibers'&&g.geometry.populations.glomerulus.density_factor===0)ratio=0;
 const count=Math.round(src.count*ratio),positions=[],radii_um=[];
 for(let j=0;j<count&&src.count;j++){
  // Stable evenly spaced reference selection; extra points are synthetic and labelled estimates.
  const idx=Math.floor(j/ratio),k=idx%src.count,base=src.positions[k];let xyz=[base[0],base[1],layer.offset+(base[2]-offsets[p.layer])*thickness];
  if(j&&Math.floor((j-1)/ratio)===idx){const u=(Math.imul(j+recipe.seed,1664525)>>>0)/4294967296;xyz[0]=(xyz[0]+7*u)%g.network.x;xyz[1]=(xyz[1]+11*(1-u))%g.network.y;}
  positions.push(xyz);radii_um.push(src.has_soma?p.spatial.radius*(1+soma/100):src.radii_um[k]);
 }
 populations[p.id]={...src,count:positions.length,positions,radii_um};
 }
 return {...g,populations,live:true,source_hdf5:reference.source_hdf5};
}
if(typeof module!=='undefined')module.exports={estimatedGeometry,projectSomata};
