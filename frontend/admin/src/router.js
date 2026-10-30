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
export const router=createRouter({history:createWebHistory(import.meta.env.BASE_URL),routes:[
  {path:'/login',component:Login},
  {path:'/',component:Dashboard},
  {path:'/ai-examples',redirect:'/ai-prompts?tab=examples'},
  {path:'/ai-styles',redirect:'/ai-prompts?tab=style'},
  ...Object.keys(resources).filter(key=>!['ai-examples','ai-styles'].includes(key)).map(resource=>({path:'/'+resource,component:resource==='customers'?Customers:resource==='mail'?MailSettings:resource==='stripe'?StripeSettings:resource==='ai-prompts'?PromptSettings:resource==='ai-service'?AIServiceSettings:resource==='ai-usage'?AIUsage:ResourcePage,props:{resource},meta:{resource}})),
  {path:'/:pathMatch(.*)*',redirect:'/'},
]});
router.beforeEach(async to=>{
  if(!session.ready || to.path!=='/login'){try{await restoreSession();}catch{return to.path==='/login'?true:'/login';}}
  if(!session.user&&to.path!=='/login')return '/login';
  if(session.user&&to.path==='/login')return '/';
  if(to.meta.resource&&resources[to.meta.resource].superuserOnly&&!session.user?.is_superuser)return '/';
  if(to.meta.resource&&!viewPermissionsFor(to.meta.resource).some(can))return '/';
});
