// Device identity in the URL selects the real read-only screen, never a demo.
const query=new URLSearchParams(location.search),config=window.POPOMO_DEVICE_CONFIG||{};
if(query.get('mode')==='info'||query.has('device_id')||config.mode==='info'||config.deviceId!==undefined){
 await import('./device-info-app.js');
}else{
 await import('./device-app.js');
}
