// Keep source coordinates unchanged. Maps with explicit input types perform
// their own conversion; never relabel WGS84 numbers as GCJ02 / BD09.
import {esc} from './art.js';

export function validCoordinates(value){
 if(!value||!['WGS84','GCJ02','BD09'].includes(value.coordinate_type))return false;
 return [['latitude',90],['longitude',180]].every(([key,limit])=>{
  const raw=value[key];
  return (typeof raw==='number'||typeof raw==='string'&&raw.trim()!==''&&raw.length<=40)&&Number.isFinite(Number(raw))&&Math.abs(Number(raw))<=limit;
 });
}
export function stationNavigationLinks(device){
 const c=device?.coordinates;if(!validCoordinates(c))return [];
 const lat=String(Number(c.latitude)),lng=String(Number(c.longitude));
 const name=String(device.name||'POPOMO').slice(0,120),address=String(device.location||name).slice(0,403);
 const url=(base,params)=>base+'?'+new URLSearchParams(params);
 const links=[];
 if(c.coordinate_type==='WGS84'){
  links.push({id:'google',label:'Google Maps',url:url('https://www.google.com/maps/dir/',{api:'1',destination:`${lat},${lng}`})});
  links.push({id:'apple',label:'Apple Maps',url:url('https://maps.apple.com/directions',{destination:`${lat},${lng}`})});
 }
 // Amap's marker URI explicitly supports WGS84. Its navigation URI does not
 // document that flag: open the exact pin, then let the user choose a route.
 if(c.coordinate_type!=='BD09')links.push({id:'amap',label:'Amap',url:url('https://uri.amap.com/marker',{
  position:`${lng},${lat}`,name,coordinate:c.coordinate_type==='WGS84'?'wgs84':'gaode',src:'POPOMO',callnative:'1'})});
 links.push({id:'baidu',label:'Baidu Maps',url:url('https://api.map.baidu.com/marker',{
  location:`${lat},${lng}`,title:name,content:address,output:'html',coord_type:{WGS84:'wgs84',GCJ02:'gcj02',BD09:'bd09ll'}[c.coordinate_type],src:'webapp.popomo.storefront'})});
 return links;
}
export function stationNavigation(device,{lang='en-US',compact=false}={}){
 const links=stationNavigationLinks(device);if(!links.length)return '';
 const zh=lang==='zh-CN',names={google:'Google 地图',apple:'Apple 地图',amap:'高德地图',baidu:'百度地图'};
 return `<details class="station-navigation"><summary>${compact?(zh?'导航':'Directions'):(zh?'选择地图导航':'Choose a map')}</summary><div class="station-map-links">${links.map(link=>`<a href="${esc(link.url)}" target="_blank" rel="noopener noreferrer">${esc(zh?names[link.id]:link.label)} ↗</a>`).join('')}</div><p class="field-note">${zh?'在地图中确认目的地并选择路线。':'Confirm the destination and choose a route in the map.'}</p></details>`;
}
