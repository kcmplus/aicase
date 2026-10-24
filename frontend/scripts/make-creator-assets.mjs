import {mkdir,writeFile} from 'node:fs/promises';
const root=new URL('../storefront/assets/creator/',import.meta.url);await mkdir(root,{recursive:true});
const pink='#e44592',teal='#30b7b9',cream='#fef4e8';
const shapes={
 daisy:Array.from({length:8},(_,i)=>`<ellipse cx="80" cy="40" rx="20" ry="34" fill="${pink}" transform="rotate(${i*45} 80 80)"/>`).join('')+`<circle cx="80" cy="80" r="23" fill="${cream}"/>`,
 sparkle:`<path d="M80 8 97 62 152 80 97 98 80 152 63 98 8 80 63 62Z" fill="${teal}"/>`,
 tulip:`<path d="M80 142V66M80 119Q25 116 31 85Q72 85 80 119" stroke="${teal}" stroke-width="9" fill="${teal}"/><path d="M39 23 63 44 80 18 98 44 122 23V69Q80 118 39 69Z" fill="${pink}"/>`,
 bow:`<path d="M76 70Q4-2 15 87Q22 120 76 83L47 146 80 128 111 147 85 83Q153 127 147 47Q139 16 85 71Z" fill="${pink}"/><circle cx="80" cy="78" r="14" fill="#f7a6cd"/>`,
 smile:`<circle cx="80" cy="80" r="65" fill="#f5ce69"/><g fill="#2e3540"><ellipse cx="58" cy="66" rx="6" ry="10"/><ellipse cx="102" cy="66" rx="6" ry="10"/></g><path d="M43 94Q80 132 117 94" stroke="#2e3540" stroke-width="6" fill="none" stroke-linecap="round"/>`,
 cloud:`<path d="M34 118C-3 118 5 70 35 68C32 11 109 12 117 58C163 48 172 118 133 118Z" fill="#fff" stroke="${teal}" stroke-width="5"/>`,
 wave:`<path d="M5 65Q30 25 55 65T105 65T155 65M5 100Q30 60 55 100T105 100T155 100" stroke="${teal}" stroke-width="14" fill="none" stroke-linecap="round"/>`,
 mushroom:`<path d="M65 85 57 144H103L95 85" fill="${cream}" stroke="#dcbf99" stroke-width="3"/><path d="M13 92Q20 7 80 10Q140 7 147 92Z" fill="${pink}"/><g fill="${cream}"><circle cx="58" cy="42" r="10"/><circle cx="106" cy="62" r="12"/><circle cx="37" cy="76" r="8"/></g>`,
 leaf:`<path d="M22 139Q2 33 134 16Q148 129 22 139" fill="${teal}"/><path d="M15 147 112 40" stroke="${cream}" stroke-width="5"/>`,
 orange:`<circle cx="80" cy="94" r="55" fill="#f69657"/><path d="M80 43Q73 3 123 12Q127 46 80 43" fill="${teal}"/><path d="M43 67Q31 82 33 99" fill="none" stroke="${cream}" stroke-width="6" stroke-linecap="round"/>`,
 checker:Array.from({length:16},(_,i)=>`<rect x="${i%4*40}" y="${Math.floor(i/4)*40}" width="40" height="40" fill="${(i%4+Math.floor(i/4))%2?pink:cream}"/>`).join(''),
 'heart-line':`<path d="M80 138Q-8 84 21 39Q47 9 80 48Q113 9 139 39Q168 84 80 138Z" fill="none" stroke="${pink}" stroke-width="10" stroke-linejoin="round"/>`
};
for(const[id,body]of Object.entries(shapes))await writeFile(new URL(id+'.svg',root),`<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 160 160">${body}</svg>`);
await writeFile(new URL('README.txt',root),'12 POPOMO geometric vector stickers created for this prototype, 2026-10-21. They extend the existing flat vector visual style. Separate from the OpenMoji licensed collection. Generated photos, when present, are AI-created demonstration assets, not customer uploads or physical product proofs.');
console.log('Created 12 transparent vector sticker assets');
