import {createRouter,createWebHistory} from 'vue-router';
import {session,restoreSession,can} from './api.js';
import {resources,viewPermissionsFor} from './resources.js';
import Login from './Login.vue';
import Dashboard from './Dashboard.vue';
import ResourcePage from './ResourcePage.vue';
import PromptSettings from './PromptSettings.vue';
import AirwallexSettings from './AirwallexSettings.vue';
import StripeSettings from './StripeSettings.vue';
import Customers from './Customers.vue';
import MailSettings from './MailSettings.vue';
import AIServiceSettings from './AIServiceSettings.vue';
import AIUsage from './AIUsage.vue';
import AICenter from './AICenter.vue';
import InventoryCenter from './InventoryCenter.vue';
import PaymentSettings from './PaymentSettings.vue';
import PhoneColors from './PhoneColors.vue';
import SettingsCenter from './SettingsCenter.vue';
import {settingsResourceKeys,visibleSettings} from './settings-navigation.js';
const aiResources=['ai','ai-prompts','ai-service','ai-usage','ai-examples','ai-styles'];
const paymentResources=['payments','stripe','airwallex'];
const aiRedirect=path=>to=>({path,query:to.query,hash:to.hash});
export const router=createRouter({history:createWebHistory(import.meta.env.BASE_URL),routes:[
  {path:'/login',component:Login},
  {path:'/',component:Dashboard},
  {path:'/inventory',component:InventoryCenter,meta:{resource:'inventory'}},
  {path:'/phone-colors',component:PhoneColors,meta:{resource:'phone-colors'}},
  {path:'/settings',component:SettingsCenter,meta:{module:'settings'},children:[
    {path:'mail',component:MailSettings,meta:{resource:'mail'}},
    {path:'ai',component:AIServiceSettings,meta:{resource:'ai-service'}},
    {path:'connections',component:InventoryCenter,props:{connectionsOnly:true},meta:{resource:'device-connections'}},
    ...['plans','users','roles','audit-logs'].map(resource=>({path:resource,component:ResourcePage,props:{resource},meta:{resource}})),
    {path:'payments',component:PaymentSettings,meta:{resource:'payments',settingsSection:'payments'},children:[
      {path:'',redirect:'/settings/payments/airwallex'},
      {path:'airwallex',component:AirwallexSettings,props:{embedded:true},meta:{resource:'airwallex'}},
      {path:'stripe',component:StripeSettings,props:{embedded:true},meta:{resource:'stripe'}},
    ]},
  ]},
  ...['mail','plans','users','roles','audit-logs','payments'].map(key=>({path:'/'+key,redirect:aiRedirect('/settings/'+key)})),
  {path:'/payments/airwallex',redirect:aiRedirect('/settings/payments/airwallex')},
  {path:'/payments/stripe',redirect:aiRedirect('/settings/payments/stripe')},
  {path:'/airwallex',redirect:aiRedirect('/settings/payments/airwallex')},
  {path:'/stripe',redirect:aiRedirect('/settings/payments/stripe')},
  {path:'/ai',component:AICenter,meta:{resource:'ai',module:'ai'},children:[
    {path:'',redirect:'/ai/prompts'},
    {path:'prompts',component:PromptSettings,props:{embedded:true},meta:{resource:'ai-prompts'}},
    {path:'service',redirect:aiRedirect('/settings/ai')},
    {path:'usage',component:AIUsage,props:{embedded:true},meta:{resource:'ai-usage'}},
  ]},
  {path:'/ai-prompts',redirect:aiRedirect('/ai/prompts')},
  {path:'/ai-service',redirect:aiRedirect('/settings/ai')},
  {path:'/ai-usage',redirect:aiRedirect('/ai/usage')},
  {path:'/ai-examples',redirect:to=>({path:'/ai/prompts',query:{...to.query,tab:'examples'}})},
  {path:'/ai-styles',redirect:to=>({path:'/ai/prompts',query:{...to.query,tab:'style'}})},
  ...Object.keys(resources).filter(key=>!settingsResourceKeys.has(key)&&key!=='inventory'&&key!=='phone-colors'&&!aiResources.includes(key)&&!paymentResources.includes(key)).map(resource=>({path:'/'+resource,component:resource==='customers'?Customers:resource==='mail'?MailSettings:ResourcePage,props:{resource},meta:{resource}})),
  {path:'/:pathMatch(.*)*',redirect:'/'},
]});
router.beforeEach(async to=>{
  if(!session.ready || to.path!=='/login'){try{await restoreSession();}catch{return to.path==='/login'?true:'/login';}}
  if(!session.user&&to.path!=='/login')return '/login';
  if(session.user&&to.path==='/login')return '/';
  if(to.meta.module==='settings'&&!visibleSettings(session.user).length)return '/';
  if(to.meta.resource&&resources[to.meta.resource].superuserOnly&&!session.user?.is_superuser)return '/';
  if(to.meta.resource&&!viewPermissionsFor(to.meta.resource).some(can))return '/';
});
