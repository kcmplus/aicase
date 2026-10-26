import {createRouter,createWebHistory} from 'vue-router';
import {session,restoreSession,can} from './api.js';
import {resources,viewPermissionsFor} from './resources.js';
import Login from './Login.vue';
import Dashboard from './Dashboard.vue';
import ResourcePage from './ResourcePage.vue';
import PromptSettings from './PromptSettings.vue';
export const router=createRouter({history:createWebHistory(import.meta.env.BASE_URL),routes:[
  {path:'/login',component:Login},
  {path:'/',component:Dashboard},
  ...Object.keys(resources).map(resource=>({path:'/'+resource,component:resource==='ai-prompts'?PromptSettings:ResourcePage,props:{resource},meta:{resource}})),
  {path:'/:pathMatch(.*)*',redirect:'/'},
]});
router.beforeEach(async to=>{
  if(!session.ready || to.path!=='/login'){try{await restoreSession();}catch{return to.path==='/login'?true:'/login';}}
  if(!session.user&&to.path!=='/login')return '/login';
  if(session.user&&to.path==='/login')return '/';
  if(to.meta.resource&&!viewPermissionsFor(to.meta.resource).some(can))return '/';
});
