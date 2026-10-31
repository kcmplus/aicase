import {createRouter,createWebHistory} from 'vue-router';
import {session,restoreSession,can} from './api.js';
import {resources,viewPermissionsFor} from './resources.js';
import Login from './Login.vue';
import Dashboard from './Dashboard.vue';
import ResourcePage from './ResourcePage.vue';
import PromptSettings from './PromptSettings.vue';
import StripeSettings from './StripeSettings.vue';
import Customers from './Customers.vue';
import MailSettings from './MailSettings.vue';
import AIServiceSettings from './AIServiceSettings.vue';
import AIUsage from './AIUsage.vue';
import AICenter from './AICenter.vue';
const aiResources=['ai','ai-prompts','ai-service','ai-usage','ai-examples','ai-styles'];
const aiRedirect=path=>to=>({path,query:to.query,hash:to.hash});
export const router=createRouter({history:createWebHistory(import.meta.env.BASE_URL),routes:[
  {path:'/login',component:Login},
  {path:'/',component:Dashboard},
  {path:'/ai',component:AICenter,meta:{resource:'ai',module:'ai'},children:[
    {path:'',redirect:'/ai/prompts'},
    {path:'prompts',component:PromptSettings,props:{embedded:true},meta:{resource:'ai-prompts'}},
    {path:'service',component:AIServiceSettings,props:{embedded:true},meta:{resource:'ai-service'}},
    {path:'usage',component:AIUsage,props:{embedded:true},meta:{resource:'ai-usage'}},
  ]},
  {path:'/ai-prompts',redirect:aiRedirect('/ai/prompts')},
  {path:'/ai-service',redirect:aiRedirect('/ai/service')},
  {path:'/ai-usage',redirect:aiRedirect('/ai/usage')},
  {path:'/ai-examples',redirect:to=>({path:'/ai/prompts',query:{...to.query,tab:'examples'}})},
  {path:'/ai-styles',redirect:to=>({path:'/ai/prompts',query:{...to.query,tab:'style'}})},
  ...Object.keys(resources).filter(key=>!aiResources.includes(key)).map(resource=>({path:'/'+resource,component:resource==='customers'?Customers:resource==='mail'?MailSettings:resource==='stripe'?StripeSettings:ResourcePage,props:{resource},meta:{resource}})),
  {path:'/:pathMatch(.*)*',redirect:'/'},
]});
router.beforeEach(async to=>{
  if(!session.ready || to.path!=='/login'){try{await restoreSession();}catch{return to.path==='/login'?true:'/login';}}
  if(!session.user&&to.path!=='/login')return '/login';
  if(session.user&&to.path==='/login')return '/';
  if(to.meta.resource&&resources[to.meta.resource].superuserOnly&&!session.user?.is_superuser)return '/';
  if(to.meta.resource&&!viewPermissionsFor(to.meta.resource).some(can))return '/';
});
