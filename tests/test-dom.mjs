// Isolated static injection tests: no browser, network or user page access.
import fs from 'node:fs';
import vm from 'node:vm';
import assert from 'node:assert/strict';
const src=fs.readFileSync(new URL('../src/agent_websearch/extension/page-functions.js',import.meta.url),'utf8');
const visible=extra=>({getClientRects:()=>[{}],...extra});
const cells=texts=>texts.map(text=>visible({innerText:text,colSpan:1,rowSpan:1}));
const trs=[visible({cells:cells(['Product','Share (%)'])}),visible({cells:cells(['A','40'])}),visible({cells:cells(['B','60'])})];
const table=visible({caption:{innerText:'Actual visible table'},querySelectorAll:s=>s==='tr'?trs:trs.flatMap(r=>r.cells)});
const para='This exact source paragraph explains the table and is long enough to be an excerpt.';
const root={innerText:para+'\nProduct Share (%)\nA 40\nB 60',querySelectorAll:s=>s==='table'?[table]:s==='a[href]'?[visible({href:'https://example.com/report.pdf',innerText:'Report'})]:s.includes('reviewBody')?[visible({innerText:'Visible review sample, not a representative survey.'}),{getClientRects:()=>[],innerText:'Hidden private text'}]:[]};
const document={body:root,title:'Source',querySelector:s=>s.startsWith('article,')?root:null,querySelectorAll:()=>[]};
const location={href:'https://example.com/report',hostname:'example.com'};
const definitions=vm.createContext({});vm.runInContext(src,definitions);
// Chrome serializes each function; it cannot reference sibling functions.
const inspect=vm.runInNewContext('('+definitions.inspectEvidence.toString()+')(12000,"table")',{document,location,URL});
assert.equal(inspect.tables[0].rows[1][1],'40');assert.equal(inspect.tables[0].complex,false);
assert.deepEqual(Array.from(inspect.excerpts),[para]);assert.equal(inspect.reviews.length,1);
assert.equal(inspect.document_links[0].url,'https://example.com/report.pdf');
const page=vm.runInNewContext('('+definitions.inspectPage.toString()+')(12000,0)',{document,location,URL});
assert.equal(page.title,'Source');assert.ok(page.text.includes('A 40'));
trs[0].cells[0].colSpan=2;
const merged=vm.runInNewContext('('+definitions.inspectEvidence.toString()+')(12000,"")',{document,location,URL});
assert.equal(merged.tables[0].complex,true);
console.log('PASS: individually serialized Chrome injection functions, visible tables/excerpts/PDF links/review samples, merged-cell warning, no hidden review access');
const worker=fs.readFileSync(new URL('../src/agent_websearch/extension/background.js',import.meta.url),'utf8');
for (const forbidden of ['tabs.query','cookies.','history.','debugger.','eval(','new Function','onMessageExternal','captureVisibleTab']) assert.ok(!worker.includes(forbidden),forbidden);
assert.ok(worker.includes('await ownedTab(tabId)'));
assert.ok(worker.includes("chrome.storage.local.get('paused')"));
const manifest=JSON.parse(fs.readFileSync(new URL('../src/agent_websearch/extension/manifest.json',import.meta.url),'utf8'));
assert.deepEqual(manifest.permissions,['scripting','storage','alarms']);
assert.ok(!manifest.externally_connectable && !manifest.web_accessible_resources);
// Popup reads actual broker health and never echoes credentials or old cache.
const elements=Object.fromEntries(['paused','refresh','status','detail','dot'].map(id=>[id,{checked:false,disabled:false,textContent:'',classList:{toggle(){}},setAttribute(){},removeAttribute(){},addEventListener(){}}]));
let health={connected:true,paused:false,pending:0};
const popupContext=vm.createContext({document:{getElementById:id=>elements[id]},
  chrome:{storage:{local:{get:async()=>({paused:false})},onChanged:{addListener(){}}},runtime:{sendMessage:async()=>({ok:true})}},
  EDGE_BRIDGE:{url:'http://127.0.0.1:8769',token:'unit-only-worker-token'},
  fetch:async()=>({ok:true,json:async()=>health}),AbortSignal, setInterval(){}});
vm.runInContext(fs.readFileSync(new URL('../src/agent_websearch/extension/popup.js',import.meta.url),'utf8'),popupContext);
await new Promise(resolve=>setImmediate(resolve));
assert.equal(elements.status.textContent,'已連線');
health={connected:false,paused:false,pending:0};await popupContext.update();
assert.equal(elements.status.textContent,'瀏覽器工作程序尚未連線');
popupContext.fetch=async()=>{throw new Error('offline')};await popupContext.update();
assert.equal(elements.status.textContent,'本機橋接服務未連線');assert.equal(elements.refresh.disabled,false);
console.log('PASS: owned-tab scope, screenshot-disabled manifest, live popup connected/offline states');
