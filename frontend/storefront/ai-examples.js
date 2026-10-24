import {aiExamples} from './runtime-catalog.js';
export {aiExamples};
const emptyExample={id:'',name:'Example',subject:'No examples available',original:'',origin:'',results:{}};
export const exampleFor=id=>aiExamples.find(e=>e.id===id)||aiExamples[0]||emptyExample;
export const exampleResult=(exampleId='portrait',styleId)=>aiExamples.find(e=>e.id===exampleId)?.results[styleId];
