// Template labels are for Chinese-speaking operators; generation instructions stay in English.
import stylePack from '../../../backend/management_api/seed/ai-style-pack.json' with {type:'json'};
export const promptTemplates = [
  {id:'hand-painted',kind:'style',name:'温暖手绘插画（英文）',text:`Transform the input photo into a warm hand-painted illustration for a phone-case print.
Subject: Use the input photo as the sole reference. Preserve the number, identity, appearance, expression, pose, clothing and important accessories of all subjects. Do not replace people or change animal breeds.
Style: Gouache and crayon texture, soft paper grain, irregular dark outlines, clear color blocks and a few hand-drawn details. Simplify the background while retaining the recognizable setting.
Composition: Follow the target model's actual print template and adaptation requirements. Resize or reposition the whole subject and naturally extend the background as needed. Keep faces, ears and accessories complete and outside camera cutouts and trim areas. Do not stretch or crop through the subject.
Output: One continuous full-bleed flat artwork only. No phone, case body, lenses, holes, frame, guides, text, logos or watermark.`},
  {id:'memo-collage',kind:'style',name:'便利贴照片拼贴（英文）',text:`Transform the input photo into a travel-scrapbook photo collage for a phone-case print.
Subject: Preserve the main scenery, subjects, landmarks and spatial relationships. Keep a photographic texture within each paper fragment.
Style: Warm ivory paper, approximately 4 columns by 5 rows of photo fragments from the same continuous scene. Align the main ridgelines and shorelines across the fragments. Add narrow white borders, slight offsets, curled paper edges and soft shadows, with a few blank cream notes and pieces of tape away from key subjects.
Composition: Arrange the collage using the target model's actual print template. Keep key subjects in the safe area, with expendable background or blank paper in the camera region. Extend the backdrop through the bleed area.
Output: Flat artwork only. No phone, case body, camera, holes, tabletop, text, gibberish, trademarks, watermark or measurement lines.`},
  {id:'camera-aware',kind:'model',name:'通用机型适配规则（英文）',text:`Use this phone model's actual case-print template to determine the canvas aspect ratio, printable outline, camera cutout, bleed and subject-safe area.
Keep faces, ears, important accessories and main scenery fully within the safe area. Place only expendable background in the camera cutout and its clearance region; no subjects or text.
Resize or move the whole subject and naturally extend the background when needed. Do not stretch the subject or substitute a simple center crop for recomposition.
Extend a continuous background to the bleed edges. Do not draw camera lenses, cutouts, phone borders or template guides in the output.
If the actual case template is unavailable, treat the result as a composition preview only, not a calibrated print file.`},
  {id:'iphone15pro-study',kind:'model',name:'iPhone 15 Pro 构图示例（英文 · 未校准）',text:`This is an iPhone 15 Pro composition study, not a measured manufacturing dieline.
Reference canvas width:height is 70.6:146.6. Coordinates are percentages from the top-left corner.
Keep x=0–68%, y=0–35% limited to sky, distant scenery or other expendable background for conservative camera clearance. Do not place faces, ears, text or main subjects there.
Place the whole main subject within x=12–90%, y=39–92%. Preserve faces, ears, accessories and limbs, keeping important details about 8% from the edges. Resize or reposition the subject and extend the background without distortion.
Output continuous flat artwork without camera lenses, holes, phone borders or guides. Replace these study parameters with the manufacturer's actual case outline, cutout and bleed measurements before production printing.`},
 ...stylePack.styles.map(style=>({id:style.code,kind:'style',name:style.name_zh+'（英文）',text:style.prompt})),
];

export function composePrompt(style,model){
  const parts=[];
  if(style?.name)parts.push(`Target style: ${style.name}`);
  if(model?.name)parts.push(`Target phone model: ${model.name}`);
  if(style?.prompt?.trim())parts.push(`Style requirements:\n${style.prompt.trim()}`);
  if(model?.adaptation_prompt?.trim())parts.push(`Phone-model composition requirements:\n${model.adaptation_prompt.trim()}`);
  return parts.join('\n\n');
}
