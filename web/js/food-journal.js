const defaultData=()=>({calorie_goal:2000, entries:[]});
/* The journal lives in the server's data.json (see journal-client.js), shared
   with the Compose page. `data` below is this page's copy of it. */
let data=defaultData();
/* Server-reported AI timeouts; the 300 s safety net applies until they load. */
let timeoutConfig=null;
let timeoutReady=Promise.resolve();
function waitMillis(kind){
  return Config.channelFor(timeoutConfig,kind).waitMs;
}
const configNotice=document.getElementById('configNotice');
function applyData(doc){
  data={
    calorie_goal:(Number(doc&&doc.calorie_goal)||2000),
    entries:(doc&&Array.isArray(doc.entries))?doc.entries:[],
  };
  return data;
}

function localDateString(date=new Date()){
  const year=date.getFullYear();
  const month=String(date.getMonth()+1).padStart(2,'0');
  const day=String(date.getDate()).padStart(2,'0');
  return `${year}-${month}-${day}`;
}
function today(){ return localDateString(); }
function parseISO(iso){ return new Date(iso+'T12:00:00'); }
function fmt(n){ return new Intl.NumberFormat('en-US').format(Math.round(Number(n)||0)); }
function fmt1(n){ return String(Math.round((Number(n)||0)*10)/10); }
function cap(s){ return s ? s.charAt(0).toUpperCase()+s.slice(1) : ''; }
function longDate(iso){ return new Intl.DateTimeFormat(undefined,{weekday:'long',month:'long',day:'numeric'}).format(parseISO(iso)); }
function dayNum(iso){ return String(parseISO(iso).getDate()).padStart(2,'0'); }
function monthShort(iso){ return new Intl.DateTimeFormat(undefined,{month:'short'}).format(parseISO(iso)); }
function weekdayLong(iso){ return new Intl.DateTimeFormat(undefined,{weekday:'long'}).format(parseISO(iso)); }
function addDays(n){ const d=new Date(); d.setDate(d.getDate()+n); return localDateString(d); }
function dayLabel(iso){
  if(iso===today()) return 'Today';
  if(iso===addDays(-1)) return 'Yesterday';
  return weekdayLong(iso);
}

document.getElementById('date').value=today();
document.getElementById('goalInput').value=data.calorie_goal;
document.getElementById('headerDate').textContent=longDate(today());

function activateTab(name){
  const active=document.querySelector('.tab[data-tab="'+name+'"]');
  if(!active) return;
  document.querySelectorAll('.tab').forEach(x=>{x.classList.remove('active'); x.setAttribute('aria-selected','false');});
  document.querySelectorAll('.section').forEach(x=>x.classList.remove('active'));
  active.classList.add('active'); active.setAttribute('aria-selected','true');
  document.getElementById('panel-'+name).classList.add('active');
  document.title='The Food Journal — '+active.textContent.trim().replace(/^\d{2}/,'');
  render();
}

document.querySelectorAll('[data-tab]').forEach(el=>el.addEventListener('click',()=>activateTab(el.dataset.tab)));

async function parseMealText(text){
  await timeoutReady;
  const ctrl=new AbortController();
  /* Wait the server's effective parse timeout plus 10 s so its error wins. */
  const tid=setTimeout(()=>ctrl.abort(),waitMillis('parse'));
  try{
    const resp=await fetch('/api/parse', {
      method:'POST',
      headers:{'Content-Type':'application/json'},
      body:JSON.stringify({text}),
      signal:ctrl.signal
    });
    let payload=null;
    try{ payload=await resp.json(); }catch(_){ payload=null; }
    if(!resp.ok) throw new Error((payload&&payload.error)||('HTTP '+resp.status));
    return payload;
  }finally{ clearTimeout(tid); }
}

async function conjureRecipes(ingredients, useSoon){
  await timeoutReady;
  const ctrl=new AbortController();
  const tid=setTimeout(()=>ctrl.abort(),waitMillis('cook'));
  try{
    const resp=await fetch('/api/leftover-alchemist',{
      method:'POST', headers:{'Content-Type':'application/json'},
      body:JSON.stringify({ingredients, use_soon:useSoon}), signal:ctrl.signal
    });
    if(!resp.ok){ const err=await resp.json().catch(()=>({error:'Request failed'})); throw new Error(err.error||('HTTP '+resp.status)); }
    return await resp.json();
  }finally{ clearTimeout(tid); }
}

async function conjureRecipeImage(recipe){
  await timeoutReady;
  const ctrl=new AbortController();
  const tid=setTimeout(()=>ctrl.abort(),waitMillis('image'));
  try{
    const resp=await fetch('/api/recipe-image',{
      method:'POST', headers:{'Content-Type':'application/json'},
      body:JSON.stringify({title:recipe.title, description:recipe.description}), signal:ctrl.signal
    });
    if(!resp.ok){ const err=await resp.json().catch(()=>({error:'Image generation failed'})); throw new Error(err.error||'Image generation failed'); }
    return await resp.json();
  }finally{ clearTimeout(tid); }
}

function addText(parent, tag, text, className=''){
  const el=document.createElement(tag); el.textContent=text;
  if(className) el.className=className;
  parent.appendChild(el); return el;
}

function recipePlate(index){
  const plate=document.createElement('div');
  plate.className='plate plate--'+['green','amber','rose'][index%3];
  plate.setAttribute('role','img');
  plate.setAttribute('aria-label','Illustrated plate study for recipe '+(index+1));
  addText(plate,'span','Plate study '+String(index+1).padStart(2,'0'),'plate__tag');
  return plate;
}

let recipeImageQueue=Promise.resolve();

function renderRecipes(recipes){
  const results=document.getElementById('recipeResults');
  results.replaceChildren();
  const imageJobs=[];
  recipes.forEach((recipe,index)=>{
    const card=document.createElement('article'); card.className='recipe-card';

    const media=document.createElement('div'); media.className='recipe-media';
    if(recipe.image){
      const image=document.createElement('img');
      image.className='recipe-image'; image.src=recipe.image; image.alt='AI generated image of '+recipe.title;
      image.loading='lazy'; media.appendChild(image);
    }else if(recipe.image_pending){
      const frame=document.createElement('div');
      frame.className='recipe-image-frame';
      frame.setAttribute('role','img');
      frame.setAttribute('aria-label','Recipe photo is developing');
      const haze=document.createElement('div');
      haze.className='recipe-image-haze'; haze.setAttribute('aria-hidden','true');
      frame.appendChild(haze);
      const loading=document.createElement('div');
      loading.className='recipe-image-loading'; loading.setAttribute('aria-hidden','true');
      addText(loading,'span','','recipe-loading-ring');
      addText(loading,'span','Developing image');
      frame.appendChild(loading);
      media.appendChild(frame);
      imageJobs.push({recipe,frame,index});
    }else{
      media.appendChild(recipePlate(index));
    }
    card.appendChild(media);

    const body=document.createElement('div'); body.className='recipe-body';
    const topline=document.createElement('div'); topline.className='recipe-topline';
    const kicker=addText(topline,'span','Recipe '+String(index+1).padStart(2,'0'),'recipe-kicker');
    kicker.setAttribute('aria-hidden','true');
    addText(topline,'span','Serves '+recipe.servings,'recipe-serving');
    body.appendChild(topline);
    addText(body,'h3',recipe.title,'recipe-title');
    addText(body,'p',recipe.description,'recipe-description');

    const uses=document.createElement('p'); uses.className='recipe-ingredient-line';
    addText(uses,'strong','Uses');
    uses.appendChild(document.createTextNode(' '+(recipe.ingredients_used||[]).join(', ')));
    body.appendChild(uses);

    if(recipe.pantry_extras?.length){
      const extras=document.createElement('p'); extras.className='recipe-ingredient-line';
      addText(extras,'strong','Extras');
      extras.appendChild(document.createTextNode(' '+recipe.pantry_extras.join(', ')));
      body.appendChild(extras);
    }

    const detail=document.createElement('div'); detail.className='recipe-detail';
    const instructions=document.createElement('div'); instructions.className='recipe-instructions';
    const aside=document.createElement('div'); aside.className='recipe-aside';
    const list=document.createElement('ol'); list.className='recipe-steps';
    recipe.steps.forEach(step=>addText(list,'li',step));
    instructions.appendChild(list);

    const n=recipe.nutrition;
    const nutrition=document.createElement('div'); nutrition.className='recipe-nutrition';
    addText(nutrition,'span','Per serving, approximate','recipe-nutrition-label');
    const facts=document.createElement('div'); facts.className='recipe-facts';
    const fact=(value,label)=>{
      const item=document.createElement('div');
      addText(item,'strong',value);
      addText(item,'span',label);
      facts.appendChild(item);
    };
    fact(Math.round(n.calories)+'', 'kcal');
    fact(Math.round(n.protein)+'g', 'protein');
    fact(Math.round(n.carbs)+'g', 'carbs');
    fact(Math.round(n.fat)+'g', 'fat');
    nutrition.appendChild(facts);
    const footer=document.createElement('div'); footer.className='recipe-footer';
    const btn=addText(footer,'button','Add to tracker →','recipe-add'); btn.type='button';
    btn.addEventListener('click',()=>{
      activateTab('add');
      renderParsed(
        [{name:recipe.title,portion:'1 serving',calories:n.calories,protein:n.protein,carbs:n.carbs,fat:n.fat}],
        `Seeded from “${recipe.title}” · 1 serving · review before saving`,
        'From a recipe'
      );
      mealText.value=recipe.title;
      updateMealCount();
      toast('Recipe sent to Log a meal for review.','success');
    });
    aside.appendChild(nutrition);
    aside.appendChild(footer);
    detail.appendChild(instructions);
    detail.appendChild(aside);
    body.appendChild(detail);
    card.appendChild(body);
    results.appendChild(card);
  });
  imageJobs.forEach(job=>{
    recipeImageQueue=recipeImageQueue.then(async()=>{
      const {recipe,frame,index}=job;
      if(!frame.isConnected) return;
      try{
        const result=await conjureRecipeImage(recipe);
        const image=document.createElement('img');
        image.className='recipe-image'; image.src=result.image; image.alt='AI generated image of '+recipe.title;
        image.loading='lazy';
        frame.appendChild(image);
        if(image.decode){ try{ await image.decode(); }catch(_){} }
        frame.removeAttribute('role');
        frame.removeAttribute('aria-label');
        requestAnimationFrame(()=>requestAnimationFrame(()=>frame.classList.add('is-ready')));
      }catch(_){
        frame.replaceWith(recipePlate(index));
      }
    });
  });
}

function glideTo(target){
  // Let the browser's native smooth scroller do the work. The old version
  // recalculated layout and called window.scrollTo() on every animation frame,
  // which fought the GPU/CPU for frames while the local model was running.
  const reduced=window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  target.scrollIntoView({behavior:reduced?'auto':'smooth',block:'start',inline:'nearest'});
}

document.getElementById('conjureBtn').addEventListener('click',async()=>{
  const ingredients=document.getElementById('alchemistIngredients').value.trim();
  const useSoon=document.getElementById('alchemistUseSoon').value.trim();
  const btn=document.getElementById('conjureBtn');
  const status=document.getElementById('alchemistStatus');
  const results=document.getElementById('recipeResults');
  if(!ingredients){ status.textContent='Add at least one ingredient to begin the experiment.'; document.getElementById('alchemistIngredients').focus(); return; }
  btn.disabled=true; btn.innerHTML='<span class="spinner"></span>Creating…';
  status.textContent='Reading the fridge…';
  results.replaceChildren();
  results.setAttribute('aria-busy','true');
  try{
    const result=await conjureRecipes(ingredients,useSoon);
    if(!Array.isArray(result.recipes)||result.recipes.length===0) throw new Error('No recipe ideas came back. Please try again.');
    renderRecipes(result.recipes);
    results.removeAttribute('aria-busy');
    glideTo(results);
    status.textContent=result.recipes.some(recipe=>recipe.image_pending)
      ? 'Three ideas, freshly invented. Images are painting in the background; nutrition is an estimate.'
      : 'Three ideas, freshly invented. Nutrition is an estimate.';
  }catch(e){
    results.replaceChildren();
    results.removeAttribute('aria-busy');
    status.textContent=e.name==='AbortError'?'The ideas timed out. Try again in a moment.':'That did not work: '+e.message;
  }finally{ btn.disabled=false; btn.textContent='Create a meal'; }
});

function toast(msg,kind='success'){
  const t=document.getElementById('toast');
  if(!t) return;
  t.textContent=msg;
  t.className='toast show '+(kind==='error'?'error':'success');
  clearTimeout(window.__toastTid);
  window.__toastTid=setTimeout(()=>{ t.classList.remove('show'); }, 2500);
}

/* ---------- compose: describe a meal, review the items, save ---------- */

const parsedState={items:[], busy:false, editId:null};

function num(n){ return Math.max(0, Number(n)||0); }

function setParseBusy(busy){
  parsedState.busy=busy;
  const parseBtn=document.getElementById('parseBtn');
  parseBtn.disabled=busy;
  parseBtn.setAttribute('aria-busy', busy?'true':'false');
  parseBtn.innerHTML=busy?'<span class="spinner"></span>Estimating…':'Estimate nutrition';
  const manualBtn=document.getElementById('manualRowBtn');
  if(manualBtn) manualBtn.disabled=busy;
  const saveBtn=document.getElementById('saveParsedBtn');
  if(saveBtn) saveBtn.disabled=busy||parsedState.items.length===0;
}

function updateMealCount(){
  const text=document.getElementById('mealText');
  document.getElementById('mealCount').textContent=String(text.value.length);
}

function showParseError(message){
  const node=document.getElementById('parseError');
  node.textContent=message;
  node.hidden=false;
}
function hideParseError(){ document.getElementById('parseError').hidden=true; }

function resetParsedTotals(){
  ['totalCalories','totalProtein','totalCarbs','totalFat'].forEach(id=>{
    document.getElementById(id).textContent='—';
  });
  document.getElementById('totalsNote').textContent='';
  document.querySelectorAll('#parsedMacrobar [data-macro]').forEach(seg=>{ seg.style.width='0%'; });
  document.getElementById('macroLegend').textContent='';
}

function revealResult(sub, kicker='The plate'){
  document.getElementById('resultKicker').textContent=kicker;
  document.getElementById('resultSub').textContent=sub;
  document.getElementById('parseResult').hidden=false;
}

function buildParsedRow(item, index){
  const row=document.createElement('div');
  row.className='a-grid a-item';
  row.setAttribute('role','row');

  const itemLabel=item.name||('item '+(index+1));
  const cell=(label,className,input)=>{
    const wrap=document.createElement('label');
    wrap.className='a-cell'+(className?' '+className:'');
    const caption=document.createElement('span');
    caption.className='a-cell__label';
    caption.textContent=label;
    wrap.append(caption,input);
    return wrap;
  };
  const textInput=(field,label)=>{
    const input=document.createElement('input');
    input.type='text';
    input.value=item[field]||'';
    input.maxLength=120;
    input.setAttribute('aria-label',label);
    input.addEventListener('input',()=>{ item[field]=input.value; });
    return input;
  };
  const numberInput=(field,label)=>{
    const input=document.createElement('input');
    input.type='number';
    input.min='0';
    input.step='0.1';
    input.value=String(num(item[field]));
    input.setAttribute('aria-label',label);
    input.addEventListener('input',()=>{ item[field]=num(input.value); recomputeParsed(); });
    return input;
  };

  row.appendChild(cell('Item','a-cell--name',textInput('name','Item name '+(index+1))));
  row.appendChild(cell('Portion','',textInput('portion','Portion for '+itemLabel)));
  row.appendChild(cell('kcal','a-cell--num',numberInput('calories','Calories for '+itemLabel)));
  row.appendChild(cell('P','a-cell--num',numberInput('protein','Protein grams for '+itemLabel)));
  row.appendChild(cell('C','a-cell--num',numberInput('carbs','Carbs grams for '+itemLabel)));
  row.appendChild(cell('F','a-cell--num',numberInput('fat','Fat grams for '+itemLabel)));

  const remove=document.createElement('button');
  remove.type='button';
  remove.className='a-item__remove';
  remove.innerHTML='&times;';
  remove.setAttribute('aria-label','Remove '+itemLabel);
  remove.addEventListener('click',()=>{
    parsedState.items.splice(index,1);
    if(parsedState.items.length===0){
      document.getElementById('parsedRows').replaceChildren();
      document.getElementById('parseResult').hidden=true;
      resetParsedTotals();
      /* With every row gone there is nothing left to edit or save. */
      parsedState.editId=null;
      const save=document.getElementById('saveParsedBtn');
      if(save){ save.disabled=true; save.textContent='Save to the record'; }
      return;
    }
    paintParsedRows();
  });
  row.appendChild(remove);

  return row;
}

function paintParsedRows(){
  const host=document.getElementById('parsedRows');
  host.replaceChildren();
  parsedState.items.forEach((item,index)=>host.appendChild(buildParsedRow(item,index)));
  const save=document.getElementById('saveParsedBtn');
  if(save) save.disabled=parsedState.busy||parsedState.items.length===0;
  recomputeParsed();
}

function recomputeParsed(){
  const totals=parsedState.items.reduce((acc,item)=>{
    acc.calories+=num(item.calories);
    acc.protein+=num(item.protein);
    acc.carbs+=num(item.carbs);
    acc.fat+=num(item.fat);
    return acc;
  },{calories:0,protein:0,carbs:0,fat:0});

  document.getElementById('totalCalories').textContent=fmt(totals.calories);
  document.getElementById('totalProtein').textContent=fmt1(totals.protein);
  document.getElementById('totalCarbs').textContent=fmt1(totals.carbs);
  document.getElementById('totalFat').textContent=fmt1(totals.fat);

  const count=parsedState.items.length;
  document.getElementById('totalsNote').textContent=count
    ? `${count} ${count===1?'item':'items'}`
    : '';

  const energy=totals.protein*4+totals.carbs*4+totals.fat*9;
  const share=(grams,perGram)=>energy>0?(grams*perGram)/energy:0;
  const p=share(totals.protein,4), c=share(totals.carbs,4), f=share(totals.fat,9);
  const bar=document.getElementById('parsedMacrobar');
  bar.querySelector('[data-macro="p"]').style.width=`${(p*100).toFixed(1)}%`;
  bar.querySelector('[data-macro="c"]').style.width=`${(c*100).toFixed(1)}%`;
  bar.querySelector('[data-macro="f"]').style.width=`${(f*100).toFixed(1)}%`;
  document.getElementById('macroLegend').textContent=energy>0
    ? `Protein ${Math.round(p*100)}% · Carbs ${Math.round(c*100)}% · Fat ${Math.round(f*100)}% of energy`
    : 'The macro split appears once there are numbers to divide.';
}

function renderParsed(items, sub, kicker='The plate', focus=false){
  /* A fresh set of rows starts in "add" mode; editEntry re-enters edit mode
     after this call, so a recipe seed or a parse can never overwrite an edit. */
  parsedState.editId=null;
  const save=document.getElementById('saveParsedBtn');
  if(save) save.textContent='Save to the record';
  parsedState.items=items.map(item=>({
    name:String(item.name||''),
    portion:String(item.portion||''),
    calories:num(item.calories),
    protein:num(item.protein),
    carbs:num(item.carbs),
    fat:num(item.fat),
  }));
  revealResult(sub,kicker);
  paintParsedRows();
  if(focus) document.getElementById('resultTitle').focus({preventScroll:true});
  glideTo(document.getElementById('parseResult'));
}

function clearParsed(){
  parsedState.items=[];
  parsedState.editId=null;
  document.getElementById('parsedRows').replaceChildren();
  document.getElementById('parseResult').hidden=true;
  document.getElementById('mealText').value='';
  document.getElementById('date').value=today();
  updateMealCount();
  hideParseError();
  clearInlineErrors();
  resetParsedTotals();
  const save=document.getElementById('saveParsedBtn');
  if(save){ save.textContent='Save to the record'; save.disabled=true; }
  setParseBusy(false);
}

async function parseMeal(){
  if(parsedState.busy) return;
  const textInput=document.getElementById('mealText');
  const text=textInput.value.trim();
  clearInlineErrors();
  hideParseError();
  if(!text){
    showInlineError(textInput,'Describe at least one food first.');
    showParseError('Describe at least one food first.');
    textInput.focus();
    return;
  }

  parsedState.items=[];
  parsedState.editId=null;
  document.getElementById('parsedRows').replaceChildren();
  document.getElementById('parseResult').hidden=true;
  setParseBusy(true);
  resetParsedTotals();
  const save=document.getElementById('saveParsedBtn');
  if(save){ save.disabled=true; save.textContent='Save to the record'; }

  await timeoutReady;
  const parseWaitMs=waitMillis('parse');
  try{
    const payload=await parseMealText(text);
    if(!payload||!Array.isArray(payload.items)||payload.items.length===0){
      throw new Error('The model found no food in that description. Try naming the foods and portions.');
    }
    const count=payload.items.length;
    renderParsed(payload.items,`${count} ${count===1?'item':'items'} · edit any number before saving`,'The plate',true);
    hideParseError();
  }catch(error){
    parsedState.items=[];
    resetParsedTotals();
    const message=error.name==='AbortError'
      ? `No response after ${Math.round(parseWaitMs/1000)} seconds. The model may be slow or unreachable.`
      : error.message;
    showParseError('Couldn’t itemise that: '+message);
    revealResult('Estimate unavailable · add a row by hand to continue.','Manual entry');
  }finally{
    setParseBusy(false);
    if(parsedState.items.length) recomputeParsed();
  }
}

function manualRow(){
  if(parsedState.busy) return;
  hideParseError();
  clearInlineErrors();
  parsedState.items.push({name:'',portion:'',calories:0,protein:0,carbs:0,fat:0});
  document.getElementById('parseResult').hidden=false;
  if(!parsedState.editId){
    revealResult('Manual entry · nothing sent to the model · review before saving','Manual entry');
  }
  paintParsedRows();
  glideTo(document.getElementById('parseResult'));
  const inputs=document.querySelectorAll('#parsedRows .a-cell--name input');
  const last=inputs[inputs.length-1];
  if(last) last.focus({preventScroll:true});
}

async function saveParsed(){
  if(parsedState.busy) return;
  if(parsedState.items.length===0){
    showParseError('Add at least one item first.');
    return;
  }
  const blank=parsedState.items.findIndex(item=>!String(item.name||'').trim());
  if(blank!==-1){
    toast(`Item ${blank+1} needs a name before it can be saved.`,'error');
    const inputs=document.querySelectorAll('#parsedRows .a-cell--name input');
    if(inputs[blank]) inputs[blank].focus();
    return;
  }

  const activeMeal=document.querySelector('.meal-chip.active');
  const meal=activeMeal?activeMeal.dataset.meal:'breakfast';
  let dateStr=document.getElementById('date').value;
  if(!dateStr) dateStr=today();

  const entries=parsedState.items.map(item=>({
    name:String(item.name).trim(),
    portion:String(item.portion||'').trim(),
    calories:num(item.calories),
    protein:num(item.protein),
    carbs:num(item.carbs),
    fat:num(item.fat),
    meal,
    date:dateStr,
  }));

  const editId=parsedState.editId;
  const editing=editId!==null && editId!==undefined;
  const saveBtn=document.getElementById('saveParsedBtn');
  saveBtn.disabled=true;
  saveBtn.innerHTML='<span class="spinner"></span>Saving…';
  try{
    applyData(editing
      ? await JournalStore.updateEntries(editId,entries)
      : await JournalStore.addEntries(entries));
  }catch(error){
    saveBtn.disabled=false;
    saveBtn.textContent=editing?'Save changes':'Save to the record';
    toast('Could not save: '+error.message,'error');
    return;
  }
  toast(editing
    ? `Updated ${entries.length} ${entries.length===1?'item':'items'} on ${dateStr}.`
    : `Saved ${entries.length} ${entries.length===1?'item':'items'} to ${meal} on ${dateStr}.`,'success');
  clearParsed();
  render();
}

const mealText=document.getElementById('mealText');
mealText.addEventListener('input',()=>{
  updateMealCount();
  if(!document.getElementById('parseError').hidden) hideParseError();
});
document.querySelectorAll('[data-example]').forEach(chip=>{
  chip.addEventListener('click',()=>{
    mealText.value=chip.dataset.example||chip.textContent.trim();
    updateMealCount();
    mealText.focus();
  });
});
document.querySelectorAll('[data-ingredients]').forEach(chip=>{
  chip.addEventListener('click',()=>{
    const ingredients=document.getElementById('alchemistIngredients');
    ingredients.value=chip.dataset.ingredients||'';
    updateCharacterCount(ingredients,'alchemistIngredientsCount');
    ingredients.focus();
  });
});
function updateCharacterCount(input,countId){
  document.getElementById(countId).textContent=String(input.value.length);
}
const alchemistIngredients=document.getElementById('alchemistIngredients');
alchemistIngredients.addEventListener('input',()=>updateCharacterCount(alchemistIngredients,'alchemistIngredientsCount'));
updateCharacterCount(alchemistIngredients,'alchemistIngredientsCount');
document.getElementById('parseBtn').addEventListener('click',parseMeal);
document.getElementById('manualRowBtn').addEventListener('click',manualRow);
document.getElementById('clearParsedBtn').addEventListener('click',clearParsed);
document.getElementById('saveParsedBtn').addEventListener('click',saveParsed);

function clearInlineErrors(){
  document.querySelectorAll('.field-error').forEach(el=>el.remove());
  document.querySelectorAll('.has-error').forEach(el=>el.classList.remove('has-error'));
}
function showInlineError(input,msg){
  input.classList.add('has-error');
  const err=document.createElement('span');
  err.className='field-error';
  err.textContent=msg;
  input.parentNode.insertBefore(err,input.nextSibling);
}

function totalsForDate(entries, d){
  const day=entries.filter(e=>e.date===d);
  return {calories:day.reduce((s,e)=>s+e.calories,0), protein:day.reduce((s,e)=>s+e.protein,0), carbs:day.reduce((s,e)=>s+e.carbs,0), fat:day.reduce((s,e)=>s+e.fat,0), count:day.length};
}

function groupedEntries(search){
  const q=(search||'').trim().toLowerCase();
  const map=new Map();
  data.entries
    .filter(e=>!q || e.name.toLowerCase().includes(q) || e.meal.toLowerCase().includes(q))
    .forEach(e=>{
      if(!map.has(e.date)) map.set(e.date, []);
      map.get(e.date).push(e);
    });
  return Array.from(map.entries())
    .sort((a,b)=>b[0].localeCompare(a[0]))
    .map(([date, entries])=>{
      const total=entries.reduce((t,e)=>({calories:t.calories+e.calories,count:t.count+1}),{calories:0,count:0});
      return {date, entries, total};
    });
}

function entryRow(e, withTools){
  const row=document.createElement('div');
  row.className='a-row'+(withTools?'':' a-row--plain');
  row.dataset.id=e.id;
  addText(row,'span',cap(e.meal),'a-row__meal');
  const main=document.createElement('div'); main.className='a-row__main';
  addText(main,'span',e.name,'a-row__name');
  if(e.portion) addText(main,'span',e.portion,'a-row__portion');
  addText(main,'span',`P ${fmt1(e.protein)} · C ${fmt1(e.carbs)} · F ${fmt1(e.fat)}`,'a-row__macros');
  row.appendChild(main);
  const cal=document.createElement('span'); cal.className='a-row__cal';
  cal.appendChild(document.createTextNode(Math.round(e.calories)+''));
  addText(cal,'small','kcal');
  row.appendChild(cal);
  if(withTools){
    const tools=document.createElement('span'); tools.className='a-row__tools';
    const edit=addText(tools,'button','Edit','text-btn'); edit.type='button';
    edit.addEventListener('click',()=>editEntry(e.id));
    const del=addText(tools,'button','Delete','text-btn text-btn--danger'); del.type='button';
    del.addEventListener('click',()=>deleteEntry(e.id));
    row.appendChild(tools);
  }
  return row;
}

function editEntry(id){
  const entry=data.entries.find(e=>String(e.id)===String(id));
  if(!entry) return;
  activateTab('add');
  document.querySelectorAll('.meal-chip').forEach(c=>{
    const on=c.dataset.meal===entry.meal;
    c.classList.toggle('active',on);
    c.setAttribute('aria-pressed',on);
  });
  document.getElementById('date').value=entry.date||today();
  document.getElementById('mealText').value=entry.name;
  updateMealCount();
  renderParsed(
    [{name:entry.name,portion:entry.portion||'',calories:entry.calories,protein:entry.protein,carbs:entry.carbs,fat:entry.fat}],
    `Editing “${entry.name}” · saving replaces this entry`,
    'From the archive'
  );
  /* renderParsed resets to add mode, so re-assert the edit we are starting. */
  parsedState.editId=entry.id;
  const save=document.getElementById('saveParsedBtn');
  if(save) save.textContent='Save changes';
}

async function deleteEntry(id){
  const entry=data.entries.find(e=>String(e.id)===String(id));
  if(!entry) return;
  if(!confirm(`Delete "${entry.name}" (${entry.date})? This cannot be undone.`)) return;
  try{
    applyData(await JournalStore.removeEntry(id));
  }catch(error){
    toast('Could not delete: '+error.message,'error');
    return;
  }
  /* Do not leave the editor pointed at a row that no longer exists. */
  if(parsedState.editId!==null && String(parsedState.editId)===String(id)) clearParsed();
  render();
}

function renderEntries(){
  const body=document.getElementById('entryBody');
  const empty=document.getElementById('emptyState');
  const noResults=document.getElementById('noResults');
  const search=document.getElementById('entriesSearch')?.value||'';
  body.replaceChildren();
  if(data.entries.length===0){
    empty.classList.add('is-visible');
    noResults.hidden=true;
    return;
  }
  empty.classList.remove('is-visible');
  const groups=groupedEntries(search);
  if(groups.length===0){ noResults.hidden=false; return; }
  noResults.hidden=true;
  groups.forEach(g=>{
    const section=document.createElement('section'); section.className='a-day';
    const head=document.createElement('header'); head.className='a-day__head';
    const date=document.createElement('div'); date.className='a-day__date';
    addText(date,'strong',dayNum(g.date));
    addText(date,'span',`${monthShort(g.date)} · ${dayLabel(g.date)}`);
    head.appendChild(date);
    addText(head,'span',`${g.entries.length} ${g.entries.length===1?'entry':'entries'} · ${fmt(g.total.calories)} kcal`,'a-day__total');
    section.appendChild(head);
    g.entries.forEach(e=>section.appendChild(entryRow(e,true)));
    body.appendChild(section);
  });
}

document.getElementById('entriesSearch')?.addEventListener('input', renderEntries);

function renderTodayMenu(t){
  const wrap=document.getElementById('todayMenu');
  wrap.replaceChildren();
  const entries=data.entries.filter(e=>e.date===today());
  if(entries.length===0){
    addText(wrap,'p','Nothing logged yet. Even a handful of almonds counts.','a-empty');
  }else{
    entries.forEach(e=>wrap.appendChild(entryRow(e,false)));
  }
  document.getElementById('todayMenuNote').textContent=`${t.count} ${t.count===1?'entry':'entries'} · ${fmt(t.calories)} kcal`;
}

function renderMacroPlate(t){
  const proteinCal=t.protein*4;
  const carbsCal=t.carbs*4;
  const fatCal=t.fat*9;
  const total=proteinCal+carbsCal+fatCal;
  const ring=document.getElementById('macroPlateRing');
  const plate=document.getElementById('macroPlate');
  if(total>0){
    const proteinPct=(proteinCal/total)*100;
    const carbsPct=(carbsCal/total)*100;
    const fatPct=Math.max(0,100-proteinPct-carbsPct);
    ring.style.background=`conic-gradient(var(--macro-protein) 0 ${proteinPct}%, var(--macro-carbs) ${proteinPct}% ${proteinPct+carbsPct}%, var(--macro-fat) ${proteinPct+carbsPct}% 100%)`;
    ring.classList.remove('is-empty');
    plate.setAttribute('aria-label',`Today's macro split: ${Math.round(proteinPct)}% protein, ${Math.round(carbsPct)}% carbs, ${Math.round(fatPct)}% fat. ${fmt(t.calories)} calories logged.`);
  }else{
    ring.style.background='';
    ring.classList.add('is-empty');
    plate.setAttribute('aria-label',`No macros logged today. ${fmt(t.calories)} calories logged.`);
  }
  document.getElementById('macroPlateCalories').textContent=fmt(t.calories);
}

function renderSummary(){
  const tt=totalsForDate(data.entries,today());
  const goal=data.calorie_goal;
  const pct=goal>0?Math.min(100,(tt.calories/goal)*100):0;
  const remaining=goal-tt.calories;
  const dateText=longDate(today());
  document.getElementById('headerDate').textContent=dateText;
  document.getElementById('summaryDate').textContent=dateText;
  document.getElementById('todayCalories').textContent=fmt(tt.calories);
  document.getElementById('todayGoal').textContent=fmt(goal);
  document.getElementById('todayDeck').textContent=tt.count===0
    ? 'Nothing logged yet. The page is open — add the first thing you actually ate.'
    : `${tt.count} ${tt.count===1?'item':'items'} logged, ${fmt(tt.calories)} calories. ` +
      (remaining>0
        ? `There is room left for something good — ${fmt(remaining)} calories of it.`
        : `You are ${fmt(Math.abs(remaining))} over today’s target. Tomorrow is a fresh page.`);
  document.getElementById('todayPct').textContent=`${Math.round(pct)}% of daily target`;
  document.getElementById('todayRemaining').textContent=remaining>=0?`${fmt(remaining)} left`:`${fmt(Math.abs(remaining))} over`;
  document.getElementById('todayProtein').textContent=fmt(tt.protein);
  document.getElementById('todayCarbs').textContent=fmt(tt.carbs);
  document.getElementById('todayFat').textContent=fmt(tt.fat);
  renderMacroPlate(tt);
  document.getElementById('todayTarget').textContent=fmt(goal);
  document.getElementById('todayTargetNote').textContent=`calories · ${Math.round(pct)}% used`;
  const bar=document.getElementById('todayProgressBar');
  bar.style.width=pct+'%';
  bar.parentElement.setAttribute('aria-valuenow',Math.round(pct));
  renderTodayMenu(tt);
}

function renderGoal(){
  const input=document.getElementById('goalInput');
  if(document.activeElement!==input) input.value=data.calorie_goal;
  document.getElementById('goalStatus').textContent='Current daily calorie goal: '+fmt(data.calorie_goal)+'.';
  const goal=data.calorie_goal;
  const tt=totalsForDate(data.entries,today());
  const pct=goal>0?Math.min(100,(tt.calories/goal)*100):0;
  const remaining=goal-tt.calories;
  document.getElementById('goalFigure').textContent=fmt(goal);
  document.getElementById('goalTodayCalories').textContent=`${fmt(tt.calories)} eaten today`;
  document.getElementById('goalRemaining').textContent=remaining>=0?`${fmt(remaining)} remaining`:`${fmt(Math.abs(remaining))} over`;
  const bar=document.getElementById('goalProgressBar');
  bar.style.width=pct+'%';
  bar.parentElement.setAttribute('aria-valuenow',Math.round(pct));
}

document.getElementById('saveGoal').addEventListener('click', async ()=>{
  const g=parseFloat(document.getElementById('goalInput').value);
  const goalInput=document.getElementById('goalInput');
  clearInlineErrors();
  if(isNaN(g)||g<1){ showInlineError(goalInput,'Value must be at least 1.'); goalInput.focus(); return; }
  try{
    applyData(await JournalStore.setGoal(Math.round(g)));
  }catch(error){
    toast('Could not save the goal: '+error.message,'error');
    return;
  }
  /* render() repaints the status line, so set the confirmation after it. */
  render();
  document.getElementById('goalStatus').textContent='Daily calorie goal set to '+fmt(data.calorie_goal)+'.';
  toast('Daily goal updated to '+fmt(data.calorie_goal)+' calories.','success');
});

document.querySelectorAll('[data-goal-preset]').forEach(btn=>btn.addEventListener('click',()=>{
  document.getElementById('goalInput').value=btn.dataset.goalPreset;
  document.getElementById('goalInput').focus();
}));

document.querySelectorAll('.meal-chip').forEach(c=>{
  c.classList.toggle('active', c.dataset.meal==='breakfast');
  c.setAttribute('aria-pressed', c.dataset.meal==='breakfast');
  c.addEventListener('click',()=>{
    document.querySelectorAll('.meal-chip').forEach(x=>{
      const active=(x===c);
      x.classList.toggle('active', active);
      x.setAttribute('aria-pressed', active);
    });
  });
});

function render(){ renderEntries(); renderSummary(); renderGoal(); }

async function loadTimeouts(){
  timeoutConfig=await Config.load();
  if(timeoutConfig.source==='fallback'){
    configNotice.textContent=Config.describeFallback(timeoutConfig);
    configNotice.hidden=false;
  }
}

async function boot(){
  const journalReady=(async()=>{
    try{
      applyData(await JournalStore.read());
      const claim=await JournalStore.claimBrowserEntries(data);
      if(claim.document) applyData(claim.document);
      if(claim.moved) toast(`Moved ${claim.moved} ${claim.moved===1?'entry':'entries'} from this browser to the server.`,'success');
      if(claim.skipped) toast(`${claim.skipped} saved ${claim.skipped===1?'entry':'entries'} could not be read, so they were left in this browser.`,'error');
    }catch(error){
      toast('Could not reach the journal: '+error.message,'error');
    }
  })();
  /* Neither request can block the other: the journal renders as soon as its
     document arrives, and the timeouts apply once the config call settles. */
  timeoutReady=loadTimeouts();
  await journalReady;
  render();
  await timeoutReady;
}
boot();
