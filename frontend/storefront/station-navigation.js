// Navigation uses unchanged WGS84 coordinates. Never relabel other coordinate systems.
import {esc} from './art.js';

export function validCoordinates(value){
 if(!value||!['WGS84','GCJ02','BD09'].includes(value.coordinate_type))return false;
 return [['latitude',90],['longitude',180]].every(([key,limit])=>{
  const raw=value[key];
  return (typeof raw==='number'||typeof raw==='string'&&raw.trim()!==''&&raw.length<=40)&&Number.isFinite(Number(raw))&&Math.abs(Number(raw))<=limit;
 });
}
export function stationNavigationLinks(device){
 const c=device?.coordinates;if(!validCoordinates(c)||c.coordinate_type!=='WGS84')return [];
 const destination=`${Number(c.latitude)},${Number(c.longitude)}`;
 const url=(base,params)=>base+'?'+new URLSearchParams(params);
 return [
  {id:'google',label:'Google Maps',url:url('https://www.google.com/maps/dir/',{api:'1',destination})},
  {id:'apple',label:'Apple Maps',url:url('https://maps.apple.com/directions',{destination})},
 ];
}
export function stationNavigation(device,{lang='en-US',compact=false}={}){
 const links=stationNavigationLinks(device);if(!links.length)return '';
 const zh=lang==='zh-CN',names={google:'Google 地图',apple:'Apple 地图'};
 return `<details class="station-navigation"><summary>${compact?(zh?'导航':'Directions'):(zh?'选择地图导航':'Choose a map')}</summary><div class="station-map-links">${links.map(link=>`<a href="${esc(link.url)}" target="_blank" rel="noopener noreferrer">${esc(zh?names[link.id]:link.label)} ↗</a>`).join('')}</div><p class="field-note">${zh?'在地图中确认目的地并选择路线。':'Confirm the destination and choose a route in the map.'}</p></details>`;
}
