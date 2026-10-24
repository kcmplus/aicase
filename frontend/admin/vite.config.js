import {defineConfig} from 'vite';
import vue from '@vitejs/plugin-vue';
export default defineConfig({
  base:'/admin/', plugins:[vue()],
  server:{proxy:{'/api':{target:'http://127.0.0.1:8000'},'/media':{target:'http://127.0.0.1:8000'},'/assets':{target:'http://127.0.0.1:4173'}}},
  build:{rollupOptions:{output:{manualChunks:{'element-plus':['element-plus'],'vue':['vue','vue-router']}}}},
});
