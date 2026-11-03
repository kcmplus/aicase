import http from 'node:http';
import {readFile} from 'node:fs/promises';
import {fileURLToPath} from 'node:url';
import path from 'node:path';
const root=fileURLToPath(new URL('./storefront/',import.meta.url));
const port=Number(process.env.PORT)||4173;
const backend=new URL(process.env.CATALOG_BACKEND_URL||'http://127.0.0.1:8000');
http.createServer(async(req,res)=>{
 const pathname=new URL(req.url,'http://localhost').pathname;
 if(pathname.startsWith('/api/')||pathname.startsWith('/media/')){
  const upstream=http.request(new URL(req.url,backend),{method:req.method,headers:{...req.headers,host:backend.host}},response=>{res.writeHead(response.statusCode,{...response.headers,'Cache-Control':'no-store'});response.pipe(res);});
  upstream.setTimeout(25000,()=>upstream.destroy(new Error('Backend timeout')));
  upstream.on('error',()=>{if(!res.headersSent)res.writeHead(502,{'Content-Type':'application/json'});res.end('{"detail":"The local backend is unavailable. Please retry."}');});
  req.pipe(upstream);return;
 }

 try{
  const file=path.resolve(root,'.'+(pathname==='/'?'/index.html':decodeURIComponent(pathname)));
  if(!file.startsWith(root))throw Error('outside root');
  let data=await readFile(file);
  // Local kiosk previews can point phone scans at an existing public storefront.
  // Production static hosting uses the current origin or the host's own config.
  if(pathname==='/device.html'&&process.env.DEVICE_STOREFRONT_URL){
   const url=new URL(process.env.DEVICE_STOREFRONT_URL);
   if(!['http:','https:'].includes(url.protocol)||url.username||url.password)throw Error('Invalid storefront URL');
   const value=JSON.stringify(url.href).replaceAll('<','\\u003c');
   data=data.toString().replace('<script type="module"',`<script>window.POPOMO_DEVICE_CONFIG={storefrontUrl:${value},...window.POPOMO_DEVICE_CONFIG};</script><script type="module"`);
  }
  res.writeHead(200,{'Content-Type':({'.html':'text/html; charset=utf-8','.json':'application/json; charset=utf-8','.js':'text/javascript; charset=utf-8','.css':'text/css; charset=utf-8','.svg':'image/svg+xml','.png':'image/png','.jpg':'image/jpeg','.webp':'image/webp'})[path.extname(file)]||'application/octet-stream','Cache-Control':'no-store'});res.end(data);
 }catch{res.writeHead(404);res.end('Not found');}
}).listen(port,'127.0.0.1',()=>console.log(`AI CASE STUDIO: http://127.0.0.1:${port}`));
