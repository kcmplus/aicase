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
export const updateCustomerName=displayName=>customerRequest('',{method:'PATCH',body:{displayName}});
export const signOutCustomer=()=>customerRequest('',{method:'DELETE'});

export function customerPage(account,ui){
 const signedIn=account.authenticated===true,gift=Math.max(0,Number(account.signupCredits)||0);
 const subscription=account.subscription, balance={trial:signedIn?Math.max(0,Number(account.trialRemaining)||0):0,monthly:signedIn&&subscription&&Date.now()<subscription.endsAt?Math.max(0,(Number(subscription.monthlyLimit)||0)-(Number(subscription.used)||0)):0};
 const customer=account.customer||{},joined=customer.joinedAt?new Date(customer.joinedAt).toLocaleDateString(locale()):'';
 return `<section class="flow wrap account-flow"><a class="back-link" href="#choose">← Back to your design</a><div class="account-card"><span class="account-symbol" aria-hidden="true">${icon(signedIn?'check':'spark',28)}</span><p class="eyebrow">YOUR POPOMO ACCOUNT</p><h1>${signedIn?'A little more you.':gift?'Your first look is on us.':'Sign in to use AI Studio'}</h1>
 ${signedIn?`<p class="account-email" translate="no">${esc(customer.email)}</p><span class="account-verified">${icon('check',14)} Email verified</span>
 <div class="account-balances"><div class="account-balance"><strong>${balance.trial}</strong><span>Gift generations remaining</span></div><div class="account-balance"><strong>${balance.monthly}</strong><span>Monthly generations remaining</span></div></div>
 <p class="account-credit-note">Signup gifts and extra credits share one balance. Failed renders return your generation.</p>
 <form id="customer-profile-form" class="account-profile"><label for="customer-name">Display name</label><input id="customer-name" name="displayName" maxlength="60" autocomplete="nickname" placeholder="What should we call you?" value="${esc(customer.displayName||'')}" ${ui.busy?'disabled':''}><button class="text-button" type="submit" ${ui.busy?'disabled':''}>${ui.busy?'Please wait…':'Save profile'}</button></form>
 ${joined?`<p class="account-joined"><span>Member since</span> ${esc(joined)}</p>`:''}
 <p>Your AI allowance follows your account across devices.</p><a class="button primary full" href="${ui.next==='ai'?'#ai':'#choose?source=photo&studio=1'}">Continue designing ${icon('arrow',18)}</a><div class="account-shortcuts"><a href="#orders">My orders</a><a href="#membership">View AI plan</a></div><button class="text-button" data-customer-action="logout" ${ui.busy?'disabled':''}>Sign out</button>`:
 `<p>Sign in with your email. New here? We’ll create your account after verification.</p>${gift?`<div class="account-gift"><span>One-time welcome gift</span><strong>${Number(account.signupCredits)||0} <span>${Number(account.signupCredits)===1?'AI generation':'AI generations'}</span></strong><small>One gift per verified account. No subscription required.</small></div>`:''}
 <form id="customer-email-form"><label for="customer-email">Email address</label><input id="customer-email" name="email" type="email" autocomplete="email" maxlength="254" required placeholder="you@example.com" value="${esc(ui.email)}" ${ui.busy||ui.codeSent?'disabled':''}>
 ${ui.codeSent?`<p class="account-sent" role="status">Check your inbox for your six-digit code.</p><label for="customer-code">Verification code</label><input id="customer-code" name="code" inputmode="numeric" autocomplete="one-time-code" pattern="[0-9]{6}" minlength="6" maxlength="6" required placeholder="000000" ${ui.busy?'disabled':''}><small>The code expires in 10 minutes. Check spam if it’s missing.</small>`:''}
 <button class="button primary full" type="submit" ${ui.busy?'disabled':''}>${ui.busy?'Please wait…':ui.codeSent?'Verify & continue':'Send sign-in code'}</button></form>
 ${ui.codeSent?`<div class="account-secondary"><button class="text-button" data-customer-action="resend" ${ui.busy||Date.now()<ui.resendAt?'disabled':''}>Resend code</button><button class="text-button" data-customer-action="change-email" ${ui.busy?'disabled':''}>Use another email</button></div>`:''}<p class="account-note">We only send account emails. Your photo stays in your design.</p>`}
 ${ui.success?`<p class="account-sent" role="status">${esc(ui.success)}</p>`:''}
 ${ui.error?`<p class="account-error" role="alert">${esc(ui.error)}</p>`:''}</div></section>`;
}
