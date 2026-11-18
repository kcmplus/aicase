import {esc,icon} from './art.js';
import {locale} from './simple-i18n.js';

export async function customerRequest(path='',{method='GET',body,fetcher=fetch}={}){
 const headers={'Content-Type':'application/json'};
 if(!['GET','HEAD'].includes(method)){
  const csrf=await fetcher('/api/v1/auth/csrf/',{credentials:'same-origin',cache:'no-store',signal:AbortSignal.timeout(25000)});
  if(!csrf.ok)throw Error('Sign-in could not be reached. Please try again.');
  headers['X-CSRFToken']=(await csrf.json()).csrfToken;
 }
 const response=await fetcher('/api/v1/store/customer/'+path,{method,headers,credentials:'same-origin',cache:'no-store',signal:AbortSignal.timeout(25000),...(body===undefined?{}:{body:JSON.stringify(body)})});
 let data;try{data=await response.json();}catch{throw Error('Sign-in could not be reached. Please try again.');}
 if(!response.ok){const error=Error(typeof data.detail==='string'?data.detail:Object.values(data).flat().join(' '));error.status=response.status;throw error;}
 return data;
}
export const sendEmailCode=email=>customerRequest('send-code/',{method:'POST',body:{email,language:locale()}});
export const verifyEmailCode=(email,code)=>customerRequest('verify/',{method:'POST',body:{email,code,language:locale()}});
export const getCustomerCredits=before=>customerRequest('credits/'+(before?'?before='+encodeURIComponent(before):''));
export const updateCustomerName=displayName=>customerRequest('',{method:'PATCH',body:{displayName}});
export const signOutCustomer=()=>customerRequest('',{method:'DELETE'});
export async function startSocialLogin(provider,{next='choose',search='',fetcher=fetch}={}){
 if(!['google','facebook'].includes(provider))throw Error('This sign-in method is unavailable.');
 const params=new URLSearchParams(search),body={next:next==='ai'?'ai':'choose',language:locale()};
 for(const key of ['device_id','shop_id'])if(/^\d{1,40}$/.test(params.get(key)||''))body[key]=params.get(key);
 const data=await customerRequest('social/'+provider+'/start/',{method:'POST',body,fetcher});
 const url=new URL(data.authorizationUrl);
 if(url.protocol!=='https:'||url.port||url.username||url.password||url.hash||(provider==='google'?(url.hostname!=='accounts.google.com'||url.pathname!=='/o/oauth2/v2/auth'):(url.hostname!=='www.facebook.com'||!/^\/v\d+\.0\/dialog\/oauth$/.test(url.pathname))))throw Error('This sign-in method is unavailable.');
 return url.href;
}
export function socialReturnMessage(result){return {failed:'Sign-in could not be completed. Please try again or use email.',cancelled:'Sign-in was cancelled. You can try again or use email.',verify_email:'Verify your email once to finish linking your account.'}[result]||'';}
export function socialButtons(account,ui){
 const providers=['google','facebook'].filter(p=>account.socialProviders?.includes(p));
 if(!providers.length||account.authenticated||account.socialPending)return '';
 const google='<svg width="20" height="20" viewBox="0 0 48 48" aria-hidden="true"><path fill="#EA4335" d="M24 9.5c3.54 0 6.71 1.22 9.21 3.6l6.85-6.85C35.9 2.38 30.47 0 24 0 14.62 0 6.51 5.38 2.56 13.22l7.98 6.19C12.43 13.72 17.74 9.5 24 9.5Z"/><path fill="#4285F4" d="M46.98 24.55c0-1.57-.15-3.09-.38-4.55H24v9.02h12.94c-.58 2.96-2.26 5.48-4.78 7.18l7.73 6C44.4 38.05 46.98 31.9 46.98 24.55Z"/><path fill="#FBBC05" d="M10.53 28.59A14.41 14.41 0 0 1 9.75 24c0-1.59.27-3.13.78-4.59l-7.98-6.19A23.87 23.87 0 0 0 0 24c0 3.87.93 7.52 2.56 10.78l7.97-6.19Z"/><path fill="#34A853" d="M24 48c6.48 0 11.93-2.13 15.91-5.8l-7.73-6c-2.15 1.45-4.92 2.3-8.18 2.3-6.26 0-11.57-4.22-13.47-9.91l-7.98 6.19C6.51 42.62 14.62 48 24 48Z"/></svg>';
 const facebook='<svg width="22" height="22" viewBox="0 0 24 24" aria-hidden="true"><circle cx="12" cy="12" r="12" fill="#1877F2"/><path fill="white" d="M13.5 23.9v-8.4h2.8l.4-3.3h-3.2v-2.1c0-1 .3-1.6 1.6-1.6h1.7v-3a23 23 0 0 0-2.5-.1c-2.5 0-4.2 1.5-4.2 4.3v2.5H7.3v3.3h2.8v8.3z"/></svg>';
 return `<div class="social-login-buttons">${providers.map(p=>`<button type="button" class="social-login-button" data-customer-action="social-${p}" ${ui.busy?'disabled':''}>${p==='google'?google:facebook}<span>${p==='google'?'Sign in with Google':'Continue with Facebook'}</span></button>`).join('')}</div><div class="account-divider"><span>or continue with email</span></div>`;
}

const creditLabels={opening:'Opening balance',signup:'Signup gift',grant:'Extra credits',generation:'Generation charge',cancel_refund:'Cancellation refund',failure_refund:'Generation refund',refund_expired:'Original period expired · No balance change',subscription:'Plan credits',renewal:'Monthly credits renewed',expiry:'Monthly credits expired'};
function creditActivity(ui){
 const rows=ui.ledger||[];
 return `<section class="account-ledger"><button type="button" class="account-ledger-toggle" data-customer-action="credits-toggle" aria-expanded="${!!ui.ledgerOpen}"><span>Credit activity</span><span aria-hidden="true">${ui.ledgerOpen?'−':'+'}</span></button>${ui.ledgerOpen?`<p class="account-ledger-note">1 credit = 1 AI generation. Balances are shown separately for gifts and monthly credits.</p>${ui.ledgerError?`<p class="account-error" role="alert">${esc(ui.ledgerError)}</p><button class="text-button" data-customer-action="credits-refresh">Refresh activity</button>`:''}${rows.length?`<ul class="credit-entries">${rows.map(row=>`<li><div><strong>${creditLabels[row.kind]||'Credit adjustment'}</strong><small><span>${row.pool==='gift'?'Gift credits':'Monthly credits'}</span> · ${esc(new Date(row.createdAt).toLocaleString(locale()))}</small>${row.renderId?`<small class="credit-ref"><span>Render</span> ${esc(row.renderId)}</small>`:''}</div><div class="credit-entry-amount"><b class="${row.amount>0?'credit-plus':row.amount<0?'credit-minus':''}">${row.amount>0?'+':''}${Number(row.amount)}</b><small><span>Balance</span> ${Number(row.balanceAfter)}</small></div></li>`).join('')}</ul>`:ui.ledgerBusy?'':'<p class="account-ledger-note">No credit activity yet.</p>'}${ui.ledgerBusy?'<p role="status" class="account-ledger-note">Loading activity…</p>':''}${ui.ledgerNext?`<button class="text-button" data-customer-action="credits-more" ${ui.ledgerBusy?'disabled':''}>Load earlier activity</button>`:''}<p class="account-ledger-note">Older balances appear as an opening balance.</p>`:''}</section>`;
}

export function customerPage(account,ui){
 const signedIn=account.authenticated===true,gift=Math.max(0,Number(account.signupCredits)||0);
 const subscription=account.subscription, balance={trial:signedIn?Math.max(0,Number(account.trialRemaining)||0):0,monthly:signedIn&&subscription&&Date.now()<subscription.endsAt?Math.max(0,(Number(subscription.monthlyLimit)||0)-(Number(subscription.used)||0)):0};
 const customer=account.customer||{},joined=customer.joinedAt?new Date(customer.joinedAt).toLocaleDateString(locale()):'';
 return `<section class="flow wrap account-flow ${signedIn?'':'account-signin'}"><a class="back-link" href="#choose">← Back to your design</a><div class="account-card">${!signedIn&&gift?`<div class="account-welcome"><span>${icon('spark',25)} <span>A welcome gift for you</span></span><strong>${gift} <span>${gift===1?'AI generation':'AI generations'}</span></strong></div>`:''}<span class="account-symbol" aria-hidden="true">${icon(signedIn?'check':'spark',28)}</span><p class="eyebrow">YOUR POPOMO ACCOUNT</p><h1>${signedIn?'A little more you.':'Welcome to POPOMO'}</h1>
 ${signedIn?`<p class="account-email" translate="no">${esc(customer.email)}</p><span class="account-verified">${icon('check',14)} Email verified</span>
 <div class="account-balances"><div class="account-balance"><strong>${balance.trial}</strong><span>Gift generations remaining</span></div><div class="account-balance"><strong>${balance.monthly}</strong><span>Monthly generations remaining</span></div></div>
 <p class="account-credit-note">Signup gifts and extra credits share one balance. Failed renders return your generation.</p>
 ${creditActivity(ui)}
 <form id="customer-profile-form" class="account-profile"><label for="customer-name">Display name</label><input id="customer-name" name="displayName" maxlength="60" autocomplete="nickname" placeholder="What should we call you?" value="${esc(customer.displayName||'')}" ${ui.busy?'disabled':''}><button class="text-button" type="submit" ${ui.busy?'disabled':''}>${ui.busy?'Please wait…':'Save profile'}</button></form>
 ${joined?`<p class="account-joined"><span>Member since</span> ${esc(joined)}</p>`:''}
 <p>Your AI allowance follows your account across devices.</p><a class="button primary full" href="${ui.next==='ai'?'#ai':'#choose?source=photo&studio=1'}">Continue designing ${icon('arrow',18)}</a><div class="account-shortcuts"><a href="#orders">My orders</a><a href="#membership">View AI plan</a></div><button class="text-button" data-customer-action="logout" ${ui.busy?'disabled':''}>Sign out</button>`:
 `<p>Sign in and keep every little inspiration.</p>${socialButtons(account,ui)}${account.socialPending?'<p class="account-sent" role="status">Verify your email once to finish linking your account.</p>':''}${account.emailEnabled===false?'<p class="account-error" role="status">Email sign-in is temporarily unavailable. Please try again later.</p>':''}
 <form id="customer-email-form"><label for="customer-email">Email address</label><input id="customer-email" name="email" type="email" autocomplete="email" maxlength="254" required placeholder="you@example.com" value="${esc(ui.email)}" ${ui.busy||ui.codeSent?'disabled':''}>
 ${ui.codeSent?`<p class="account-sent" role="status">Check your inbox for your six-digit code.</p><label for="customer-code">Verification code</label><input id="customer-code" name="code" inputmode="numeric" autocomplete="one-time-code" pattern="[0-9]{6}" minlength="6" maxlength="6" required placeholder="000000" ${ui.busy?'disabled':''}><small>The code expires in 10 minutes. Check spam if it’s missing.</small>`:''}
 <button class="button primary full" type="submit" ${ui.busy||account.emailEnabled===false?'disabled':''}>${ui.busy?'Please wait…':ui.codeSent?'Verify & continue':'Get verification code'}</button></form>
 ${ui.codeSent?`<div class="account-secondary"><button class="text-button" data-customer-action="resend" ${ui.busy||account.emailEnabled===false||Date.now()<ui.resendAt?'disabled':''}>Resend code</button><button class="text-button" data-customer-action="change-email" ${ui.busy?'disabled':''}>Use another email</button></div>`:''}${account.socialPending?'<button class="text-button" data-customer-action="cancel-social">Use another sign-in method</button>':''}<p class="account-note">Your account is created on your first sign-in.</p>${gift?'<p class="account-note">One-time welcome gift. One gift per verified account.</p>':''}`}
 ${ui.success?`<p class="account-sent" role="status">${esc(ui.success)}</p>`:''}
 ${ui.error?`<p class="account-error" role="alert">${esc(ui.error)}</p>`:''}</div></section>`;
}
