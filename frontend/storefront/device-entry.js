// Preserve the existing real read-only identity screen. Older demo URLs now
// open the public read-only guide; they cannot start or finish simulated jobs.
const query=new URLSearchParams(location.search),config=window.POPOMO_DEVICE_CONFIG||{};
if(query.get('mode')==='info'||query.has('device_id')||config.mode==='info'||config.deviceId!==undefined){
 await import('./device-info-app.js');
}else{
 const destination=new URL('./',location.href);
 destination.search=location.search;
 destination.hash='kiosk';
 location.replace(destination.href);
}
