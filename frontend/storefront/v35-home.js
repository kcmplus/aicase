import {esc} from './art.js';
const tr=(lang,en,zh)=>lang==='zh-CN'?zh:en;
const curated=[['bloom','play','Playful','活泼','花开在手心','每天绽放一点快乐。'],['type','simple','Minimal','简约','做你自己','用自己的方式表达。'],['abstract','play','Playful','活泼','不必被定义','让日常多一点不同。'],['sunset','warm','Warm','温暖','慢时光','把柔软的时光带在身边。']];
export const homeLooks={
 pet:{en:'Pet pop art',zh:'宠物波普',original:'./assets/v35/pet.webp',result:'./assets/v35/inspiration/2.webp'},
 portrait:{en:'Anime portrait',zh:'动漫人像',original:'./assets/optimized/original-f068cf3fddb430feafca-640.webp',result:'./assets/v35/inspiration/1.webp'},
 travel:{en:'Travel watercolor',zh:'旅行水彩',original:'./assets/optimized/travel-original-8ccb1db2d03b3d8bc620-640.webp',result:'./assets/v35/inspiration/3.webp'}
};
export function homeCollection({works=[],preview=()=>'',lang='en-US'}={}){
 const say=(en,zh)=>tr(lang,en,zh),items=curated.filter(([id])=>works.some(work=>work.id===id));
 return `<section class="v35-collection v35-wrap" id="home-collection" tabindex="-1"><div class="v35-collection-heading"><div><p class="v35-kicker">THE LITTLE THINGS YOU LOVE</p><h2>${say('A little inspiration? Right here.','一点灵感？就在这里。')}</h2></div><p>${say('Start with a design you love. Add a little you.','从喜欢的设计开始，添一点你的风格。')}</p></div><div class="v35-collection-toolbar"><div class="v35-collection-filters" role="group" aria-label="${say('Filter design styles','筛选设计风格')}">${[['all','All designs','全部设计'],['play','Playful colors','缤纷趣味'],['simple','Everyday minimal','日常简约'],['warm','Soft & warm','柔软温暖']].map(([id,en,zh])=>`<button type="button" data-home-filter="${id}" aria-pressed="${id==='all'}">${say(en,zh)}</button>`).join('')}</div><span data-home-count role="status" aria-live="polite">${items.length} ${say('curated designs','款精选设计')}</span></div><div class="v35-curated-grid">${items.map(([id,category,en,zh,nameZh,descriptionZh],i)=>{const work=works.find(w=>w.id===id);return `<article class="v35-curated-card" data-home-category="${category}"><a href="#work?id=${encodeURIComponent(id)}" class="v35-curated-art" aria-label="${esc(say('Preview '+work.name,'预览'+nameZh))}"><span class="v35-curated-number">${String(i+1).padStart(2,'0')}</span><div class="v35-curated-phone">${preview(id)}</div><span class="v35-curated-arrow" aria-hidden="true">↗</span></a><h3><a href="#work?id=${encodeURIComponent(id)}">${esc(say(work.name,nameZh))}</a><span>${say(en,zh)}</span></h3><p>${esc(say(work.category,descriptionZh))}</p></article>`}).join('')}</div></section>`;
}
export function homeAI(lang='en-US'){
 const say=(en,zh)=>tr(lang,en,zh);
 return `<section class="v35-ai"><div class="v35-wrap"><div class="v35-ai-copy"><p class="v35-kicker">POPOMO AI STUDIO</p><h2>${say('A familiar photo.<br>A little <em>extraordinary.</em>','让熟悉的照片，<br>有点<em>不可思议。</em>')}</h2><p>${say('One photo. A whole new imagination.<br>Turn your favorite AI style into your own background.','一张照片，一种全新的想象。<br>把喜欢的 AI 风格，变成你的专属背景。')}</p><div class="v35-ai-tabs" role="group" aria-label="${say('AI style examples','AI 风格示例')}">${Object.entries(homeLooks).map(([id,look])=>`<button type="button" data-home-look="${id}" aria-pressed="${id==='pet'}">${say(look.en,look.zh)}</button>`).join('')}</div><a class="v35-entry v35-primary" data-action="home-ai" href="#choose?source=photo&studio=1">${say('AI design studio','AI 创作设计')} <span aria-hidden="true">↗</span></a></div><div class="v35-ai-visual" aria-label="${say('Example photo and AI style preview','原图和 AI 风格效果示例')}"><figure class="v35-ai-source"><img data-home-original src="${homeLooks.pet.original}" alt="${say('Original example photo','原图示例')}" loading="lazy" width="240" height="300"><figcaption>${say('YOUR PHOTO','你的照片')}</figcaption></figure><svg class="v35-ai-rosette" viewBox="0 0 200 200" aria-hidden="true"><g fill="none" stroke="currentColor" stroke-width="2.5">${Array.from({length:8},(_,i)=>`<circle cx="100" cy="55" r="45" transform="rotate(${i*45} 100 100)"/>`).join('')}</g></svg><div class="v35-ai-result"><img data-home-result src="${homeLooks.pet.result}" alt="${say('Pet pop art example','宠物波普示例')}" width="260" height="470" loading="lazy"><span>${say('✦ A LITTLE AI MAGIC','✦ 一点 AI 魔法')}</span></div><span class="v35-ai-spark" aria-hidden="true">✳</span></div></div></section>`;
}
// These controls only browse public examples; they never generate or upload images.
export function handleHomeControl(root,element,lang='en-US'){
 if(element.hasAttribute('data-home-collection')){
  root.querySelector('#home-collection')?.scrollIntoView({behavior:matchMedia('(prefers-reduced-motion: reduce)').matches?'instant':'smooth',block:'start'});
  root.querySelector('#home-collection')?.focus({preventScroll:true});return;
 }
 if(element.dataset.homeFilter){
  const category=element.dataset.homeFilter;let count=0;
  root.querySelectorAll('[data-home-filter]').forEach(button=>button.setAttribute('aria-pressed',String(button===element)));
  root.querySelectorAll('[data-home-category]').forEach(card=>{card.hidden=category!=='all'&&card.dataset.homeCategory!==category;if(!card.hidden)count++;});
  root.querySelector('[data-home-count]').textContent=count+' '+tr(lang,'curated designs','款精选设计');return;
 }
 const look=homeLooks[element.dataset.homeLook];if(!look)return;
 root.querySelectorAll('[data-home-look]').forEach(button=>button.setAttribute('aria-pressed',String(button===element)));
 root.querySelector('[data-home-original]').src=look.original;
 const result=root.querySelector('[data-home-result]');result.src=look.result;result.alt=tr(lang,look.en+' example',look.zh+'示例');
}
