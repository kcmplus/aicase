import {resources,viewPermissionsFor} from './resources.js';

export const settingsItems=[
 {key:'mail',path:'/settings/mail',title:'邮件与登录',description:'邮箱验证码、Google / Facebook 登录及注册赠送',icon:'Message',group:'客户与收款'},
 {key:'payments',path:'/settings/payments',title:'支付配置',description:'Airwallex、Stripe 支付渠道与环境',icon:'CreditCard',group:'客户与收款'},
 {key:'plans',path:'/settings/plans',title:'价格与套餐',description:'单次打印价格、AI 月度订阅与额度',icon:'Wallet',group:'客户与收款'},
 {key:'ai-service',path:'/settings/ai',title:'AI 服务',description:'生图服务连接、模型与调用配置',icon:'MagicStick',group:'服务连接'},
 {key:'device-connections',path:'/settings/connections',title:'设备连接',description:'供应商凭据、商家连接与设备同步',icon:'Connection',group:'服务连接'},
 {key:'users',path:'/settings/users',title:'管理员账号',description:'后台账号、角色分配和启用状态',icon:'User',group:'管理与安全'},
 {key:'roles',path:'/settings/roles',title:'角色与权限',description:'各角色可查看和操作的后台功能',icon:'Lock',group:'管理与安全'},
 {key:'audit-logs',path:'/settings/audit-logs',title:'操作日志',description:'管理员登录和数据变更记录',icon:'Clock',group:'管理与安全'},
];
export const settingsResourceKeys=new Set(settingsItems.map(item=>item.key));
export function visibleSettings(user){
 if(!user)return [];
 return settingsItems.filter(item=>{
  const resource=resources[item.key];
  if(resource.superuserOnly&&!user.is_superuser)return false;
  return user.is_superuser||viewPermissionsFor(item.key).some(p=>user.permissions?.includes(p));
 });
}
