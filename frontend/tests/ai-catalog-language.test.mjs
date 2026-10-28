import test from 'node:test';
import assert from 'node:assert/strict';
import {readFile} from 'node:fs/promises';
import {applyCatalog} from '../storefront/runtime-catalog.js';
import {aiGroups} from '../storefront/ai-examples.js';
import {groupAIExamples} from '../storefront/ai-example-groups.js';
import {stylePanel} from '../storefront/ai-view.js';
import {activeLook} from '../storefront/ai-look-browser.js';
import {locale,setLocale,t,localized} from '../storefront/simple-i18n.js';
import {composePrompt,promptTemplates} from '../admin/src/prompt-templates.js';

test('English is the default; translation retains amounts and managed text falls back to English',()=>{
 assert.equal(locale(),'en-US');assert.equal(t('$5.99/month · 15 generations'),'$5.99/month · 15 generations');
 setLocale('zh-CN');assert.equal(t('$5.99/month · 15 generations'),'$5.99/月 · 15 次生成');
 assert.equal(t('I agree to $5.99/month for 15 generations, renewing monthly until cancelled. This is a simulated subscription with no real charge.'),'我同意以 $5.99/月订阅 15 次生成，取消前每月续订。这是模拟订阅，不会实际扣款。');
 assert.equal(t('No subscription needed for your free trial. $5.99/month · 15 generations.'),'免费体验无需订阅。 $5.99/月 · 15 次生成。');
 assert.equal(t('Modern font'),'现代字体');
 assert.equal(localized({name:'Custom look'}),'Custom look');assert.equal(localized({name:'Custom look',name_zh:'定制效果'}),'定制效果');
 setLocale('unsupported');assert.equal(locale(),'zh-CN');setLocale('en-US');
});
test('the gallery groups shared originals and keeps each effect tied to its saved case',()=>{
 applyCatalog({version:2,plans:[],ai_styles:[{code:'paint',name:'Paint',name_zh:'手绘',image_path:'/assets/ai-styles/anime.png',prompt:'PRIVATE'},{code:'ink',name:'Ink',name_zh:'墨绘',image_path:'/assets/ai-styles/3d.png'}],ai_examples:[
  {code:'pet-study',name:'Pet study',name_zh:'宠物习作',subject:'One look',original_path:'./assets/ai-styles/pets-original.png',results:[{style_code:'paint',image_path:'/assets/ai-styles/pets-anime.png',prompt:'PRIVATE'}]},
  {code:'pet',name:'Pet',name_zh:'宠物',subject:'A friend',subject_zh:'好朋友',original_path:'/assets/ai-styles/pets-original.png',results:[{style_code:'paint',image_path:'/assets/ai-styles/pets-anime.png',prompt:'PRIVATE'},{style_code:'ink',image_path:'/assets/ai-styles/pets-3d.png'}]},
  {code:'travel',name:'Travel',subject:'A place',original_path:'/assets/ai-styles/travel-original.png',results:[{style_code:'ink',image_path:'/assets/ai-styles/travel-3d.png'}]},
  {code:'empty',name:'Empty',subject:'Empty',original_path:'/assets/ai-styles/original.png',results:[]}
 ]});
 const groups=aiGroups();assert.equal(groups.length,2);assert.equal(groups[0].looks.length,3);assert.equal(groups[0].example.id,'pet');
 assert.deepEqual(groups[0].looks.map(look=>[look.example.id,look.style.id]),[['pet-study','paint'],['pet','paint'],['pet','ink']]);
 const en=stylePanel({aiExample:'pet-study',aiStyle:'paint'},null,true);
 assert.equal((en.match(/data-ai-group=/g)||[]).length,2);
 assert.equal((en.match(/data-ai-look-example=/g)||[]).length,3);assert.equal((en.match(/data-ai-look-example="[^"]+" data-ai-look-style="[^"]+" aria-pressed="true"/g)||[]).length,1);
 assert.match(en,/data-ai-look-example="pet-study" data-ai-look-style="paint" aria-pressed="true"/);
 assert.doesNotMatch(en,/ai-example-picker|data-ai-style=|PRIVATE|ai-before-after/);
 const alternate=stylePanel({aiExample:'pet',aiStyle:'ink'},null,true);assert.match(alternate,/data-ai-look-example="pet" data-ai-look-style="ink" aria-pressed="true"/);
 const selected=activeLook({aiExample:'pet-study',aiStyle:'paint'});assert.equal(selected.group.example.id,'pet');assert.equal(selected.look.example.id,'pet-study');assert.equal(selected.look.style.id,'paint');
 const missing=activeLook({aiExample:'travel',aiStyle:'missing'});assert.equal(missing.look.example.id,'travel');assert.equal(missing.look.style.id,'ink');
 assert.match(en,/role="dialog"|<dialog/);assert.match(en,/data-look-view="effect"/);
 setLocale('zh-CN');const zh=stylePanel({aiExample:'pet',aiStyle:'paint'},null,true);assert.match(zh,/手绘 · 宠物/);assert.match(zh,/原始照片|Original photo/);setLocale('en-US');
});
test('admin grouping preserves all editable records, including inactive and empty cases',()=>{
 const records=[{id:1,original_path:'./assets/pet.png',active:false,results:[{style:1,prompt:'Keep this prompt'}]},{id:2,original_path:'/assets/pet.png',results:[{style:2},{style:3}]},{id:3,original_path:'/assets/other.png',results:[]}];
 const before=structuredClone(records),groups=groupAIExamples(records);
 assert.equal(groups.length,2);assert.equal(groups[0].example.id,2);assert.deepEqual(groups[0].examples.map(e=>e.id),[1,2]);assert.equal(groups[0].examples[0].results[0].prompt,'Keep this prompt');assert.equal(groups[1].examples[0].id,3);assert.deepEqual(records,before);
});
test('the additional style pack has matching reusable English templates and complete case recipes',async()=>{
 const pack=JSON.parse(await readFile(new URL('../../backend/management_api/seed/ai-style-pack.json',import.meta.url),'utf8'));
 assert.equal(pack.styles.length,8);assert.equal(pack.cases.length,8);
 assert.equal(new Set(pack.styles.map(style=>style.code)).size,8);
 for(const style of pack.styles){
  const template=promptTemplates.find(item=>item.id===style.code);assert.equal(template?.text,style.prompt);
  assert.ok(style.name_zh&&style.description_zh);assert.ok(style.prompt.length<=4000);
  for(const text of [style.name,style.description,style.prompt])assert.doesNotMatch(text,/[\u3400-\u9fff]/);
  const recipe=pack.cases.find(item=>item.style===style.code);assert.ok(recipe?.name_zh&&recipe?.subject_zh);assert.equal(recipe.image_path,style.image_path);assert.ok(recipe.prompt.length<=8000);
  for(const text of [recipe.name,recipe.subject,recipe.prompt])assert.doesNotMatch(text,/[\u3400-\u9fff]/);
  assert.match(recipe.prompt,/camera/i);assert.match(recipe.prompt,/Image 1/);
 }
});
test('all built-in generation prompts and composition headings are English',async()=>{
 const recipes=JSON.parse(await readFile(new URL('../../backend/management_api/seed/ai-recipes.json',import.meta.url),'utf8'));
 const texts=[...promptTemplates.map(p=>p.text),...recipes.styles.flatMap(s=>[s.name,s.description,s.prompt]),...recipes.cases.flatMap(c=>[c.name,c.subject,c.prompt]),...recipes.legacy_prompts.map(p=>p.prompt),composePrompt({name:'Gouache',prompt:'Keep the dog.'},{name:'iPhone 15 Pro',adaptation_prompt:'Keep the camera area clear.'})];
 for(const text of texts)assert.doesNotMatch(text,/[\u3400-\u9fff]/);
});
